"""IT-CC: agent, cài đặt, nhà cung cấp, tổng quan, diễn biến + SSE (Control Center v1)."""

from __future__ import annotations

import asyncio
import json

import httpx

from tests.conftest import OwnerSession, needs_db

pytestmark = needs_db


async def test_agents_list_pause_resume(owner: OwnerSession) -> None:
    api = owner.api
    agents = (await api.get("/api/v1/agents")).json()
    assert len(agents) == 15 and agents[0]["agent_key"] == "ai_ceo"
    assert all(a["state"] == "active" for a in agents)
    r = await api.post("/api/v1/agents/seo_agent/pause", json={"reason": "Kiểm tra lại từ khóa"}, headers=owner.h)
    assert r.json() == {"agent_key": "seo_agent", "state": "paused"}
    a = next(a for a in (await api.get("/api/v1/agents")).json() if a["agent_key"] == "seo_agent")
    assert a["state"] == "paused" and a["reason"] == "Kiểm tra lại từ khóa" and a["changed_by"] == f"user:{owner.EMAIL}"
    await api.post("/api/v1/agents/seo_agent/resume", headers=owner.h)
    assert (await api.post("/api/v1/agents/khong_co/pause", json={}, headers=owner.h)).status_code == 404
    r = await api.post("/api/v1/agents/pause-all", json={"reason": "Bảo trì"}, headers=owner.h)
    assert r.json() == {"paused": 15}
    ev = [e for e in (await api.get("/api/v1/events")).json() if e["source"] == "audit"]
    assert [e["action"] for e in ev[:3]] == ["agent.pause_all", "agent.resume", "agent.pause"]
    assert ev[0]["text"] == "tạm dừng toàn bộ agent"


async def test_budget_and_hours(owner: OwnerSession) -> None:
    api = owner.api
    s = (await api.get("/api/v1/settings")).json()
    assert s["budget"] == {"month_usd": 50.0, "day_usd": 1.67, "day_burst_usd": 3.0, "alert_pct": 80}
    assert s["hours"]["quiet_start"] == "22:00"
    r = await api.put("/api/v1/settings/budget", json={"month_usd": 40, "day_usd": 5, "day_burst_usd": 3, "alert_pct": 80}, headers=owner.h)
    assert r.status_code == 422
    r = await api.put(
        "/api/v1/settings/budget", json={"month_usd": 40, "day_usd": 1.3, "day_burst_usd": 2.5, "alert_pct": 75}, headers=owner.h
    )
    assert r.status_code == 200
    r = await api.put(
        "/api/v1/settings/hours",
        json={"work_start": "7:00", "work_end": "21:30", "quiet_start": "21:30", "quiet_end": "7:00"},
        headers=owner.h,
    )
    assert r.json()["work_start"] == "07:00"
    assert (await api.put("/api/v1/settings/hours", json={"work_start": "25:00"}, headers=owner.h)).status_code == 422
    s = (await api.get("/api/v1/settings")).json()
    assert s["budget"]["month_usd"] == 40 and s["hours"]["work_end"] == "21:30"


async def test_providers_listing_never_leaks_key(owner: OwnerSession) -> None:
    api = owner.api
    p = (await api.get("/api/v1/providers")).json()
    assert {x["id"] for x in p} == {"anthropic", "openai"} and not any(x["configured"] for x in p)
    anth = next(x for x in p if x["id"] == "anthropic")
    opus = next(m for m in anth["models"] if "opus" in m["id"])
    assert opus["enabled"] is False and opus["price_out_per_mtok"] == 20.0
    await owner.reauth()
    key = "sk-ant-api03-" + "Q" * 40 + "9z9z"
    await api.put("/api/v1/providers/anthropic/key", json={"api_key": key}, headers=owner.h)
    body = (await api.get("/api/v1/providers")).text
    assert key not in body and "9z9z" in body
    ev = (await api.get("/api/v1/events")).text
    assert key not in ev


async def test_provider_test_button(owner: OwnerSession, monkeypatch: object) -> None:
    from app.gateway import models as gw

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.headers["x-api-key"].startswith("sk-ant-")
        return httpx.Response(200, json={"content": [{"type": "text", "text": "OK"}], "usage": {"input_tokens": 20, "output_tokens": 1}})

    gw.transport = httpx.MockTransport(handler)
    try:
        api = owner.api
        r = await api.post("/api/v1/providers/anthropic/test", headers=owner.h)
        assert r.json()["ok"] is False and "Chưa nhập" in r.json()["detail"]
        await owner.reauth()
        await api.put("/api/v1/providers/anthropic/key", json={"api_key": "sk-ant-" + "k" * 40}, headers=owner.h)
        r = await api.post("/api/v1/providers/anthropic/test", headers=owner.h)
        assert r.json()["ok"] is True, r.json()
        p = next(x for x in (await api.get("/api/v1/providers")).json() if x["id"] == "anthropic")
        assert p["last_test_ok"] is True
        from app.core import db

        async with db.engine().connect() as c:
            row = await db.one(c, "SELECT model_id, purpose, tokens_in, cost_usd, ok FROM model_usage")
        assert row is not None and row["model_id"] == "claude-haiku-5-5" and row["purpose"] == "provider_test"
        assert abs(float(row["cost_usd"]) - (20 * 0.10 + 1 * 0.50) / 1e6) < 1e-9
    finally:
        gw.transport = None


async def test_overview_shape(owner: OwnerSession) -> None:
    ov = (await owner.api.get("/api/v1/overview")).json()
    assert ov["health"]["checks"]["database"]["status"] == "ok"
    assert ov["telegram"] == {"configured": False, "chats": 0}
    assert ov["budget"]["month_cap_usd"] == 50.0 and ov["agents"]["by_state"] == {"active": 15}


async def test_sse_stream_pushes_new_audit_event(owner: OwnerSession) -> None:
    """SSE: một thao tác ghi nhật ký phải tới trình duyệt qua LISTEN/NOTIFY (không phải hỏi vòng)."""
    from app.main import create_app

    app = create_app()
    got: list[dict[str, object]] = []

    async def listen() -> None:
        # ASGITransport của httpx không truyền luồng từng phần, nên gọi thẳng ứng dụng ASGI để đọc từng sự kiện.
        cookie = "; ".join(f"{k}={v}" for k, v in owner.api.cookies.items())
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/v1/events/stream",
            "raw_path": b"/api/v1/events/stream",
            "query_string": b"",
            "root_path": "",
            "headers": [(b"host", b"127.0.0.1"), (b"cookie", cookie.encode())],
            "client": ("127.0.0.1", 1),
            "server": ("127.0.0.1", 80),
        }
        done = asyncio.Event()

        async def receive() -> dict[str, object]:
            await done.wait()
            return {"type": "http.disconnect"}

        async def send(msg: dict[str, object]) -> None:
            if msg["type"] == "http.response.body":
                for line in bytes(msg.get("body", b"")).decode().splitlines():  # type: ignore[arg-type]
                    if line.startswith("data: "):
                        got.append(json.loads(line[6:]))
                        done.set()

        await app(scope, receive, send)

    task = asyncio.create_task(listen())
    await asyncio.sleep(0.5)
    await owner.api.post("/api/v1/agents/content_agent/pause", json={"reason": "SSE"}, headers=owner.h)
    await asyncio.wait_for(task, timeout=10)
    assert got and got[0]["action"] == "agent.pause" and got[0]["resource"] == "agent:content_agent"
    assert "T" in str(got[0]["at"])  # cùng định dạng ISO với /events để giao diện sắp xếp đúng
