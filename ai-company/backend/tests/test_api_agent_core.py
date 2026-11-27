"""API Agent Core (trang từng agent, bộ não, phê duyệt, công cụ) + OpenTelemetry + chống dùng lại mã TOTP."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

import pytest
import yaml

from tests.conftest import BRAINS, OwnerSession, needs_db, sync_brains

pytestmark = [needs_db, pytest.mark.usefixtures("synced")]


async def test_agent_detail(owner: OwnerSession) -> None:
    api = owner.api
    assert (await api.get("/api/v1/agents/khong_co")).status_code == 404
    d = (await api.get("/api/v1/agents/seo_agent")).json()
    assert d["display_name"] == "SEO" and d["manager"]["agent_key"] == "marketing_director"
    assert d["brain"]["brain_version"] == "1.0.0" and d["brain"]["state"] == "active"
    assert d["integrity"]["ok"] is True
    assert d["bundle"]["identity"]["personality"]["evidence_strictness"] == 0.9
    publish = next(p for p in d["permissions"] if p["tool_id"] == "site" and p["action"] == "publish")
    assert publish["autonomy_level"] == 3 and publish["limits"] == {"per_day": 2} and publish["action_info"]["min_level"] == 3
    assert publish["available"] is False  # website chưa có API publish (Sprint 4)
    md = (await api.get("/api/v1/agents/marketing_director")).json()
    assert {r["agent_key"] for r in md["direct_reports"]} == {"seo_agent", "content_agent", "social_agent", "ads_agent", "creative_agent"}


async def test_tools_catalog(owner: OwnerSession) -> None:
    tools = {t["id"]: t for t in (await owner.api.get("/api/v1/tools")).json()}
    assert tools["signals"]["available"] and tools["notify"]["available"] and not tools["site"]["available"]
    assert tools["ads"]["actions"]["change_budget"]["tags"] == ["spend_over_threshold"]
    assert {g["agent_key"] for g in tools["notify"]["grants"]} == {"ai_ceo", "web_cro_agent", "data_analyst", "automation_agent"}


async def test_promote_brain_via_approval_queue(owner: OwnerSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    api = owner.api
    root = tmp_path / "brains"
    shutil.copytree(BRAINS, root)
    p = root / "content_agent/brain.yaml"
    m = yaml.safe_load(p.read_text(encoding="utf-8"))
    m["versions"]["brain_version"] = "1.1.0"
    m["budget"] = {"usd_per_day": 0.2}
    p.write_text(yaml.safe_dump(m, allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv("AICO_BRAINS_DIR", str(root))
    get_settings.cache_clear()

    items = {i["agent_key"]: i for i in (await api.post("/api/v1/brains/sync", headers=owner.h)).json()}
    assert items["content_agent"]["status"] == "proposed" and items["seo_agent"]["status"] == "unchanged"
    assert (await api.get("/api/v1/approvals/count")).json() == {"pending": 1}
    appr = (await api.get("/api/v1/approvals")).json()[0]
    assert appr["risk"] == "high" and appr["title"] == "Thăng hạng bộ não Nội dung: 1.0.0 → 1.1.0"
    assert {"path": "budget.usd_per_day", "from": 0.1, "to": 0.2} in appr["payload"]["diff"]
    versions = (await api.get("/api/v1/agents/content_agent/brains")).json()
    assert [v["state"] for v in versions] == ["draft", "active"]
    d = (await api.get(f"/api/v1/agents/content_agent/brains/diff?a={versions[1]['id']}&b={versions[0]['id']}")).json()
    assert (
        d["from"] == "1.0.0"
        and d["to"] == "1.1.0"
        and d["changes"]
        == [
            {"path": "budget.usd_per_day", "from": 0.1, "to": 0.2},
            {"path": "versions.brain_version", "from": "1.0.0", "to": "1.1.0"},
        ]
    )
    r = await api.post(f"/api/v1/approvals/{appr['id']}/decide", json={"approve": True}, headers=owner.h)
    assert r.status_code == 403 and r.json()["error"]["code"] == "REAUTH_REQUIRED"
    await owner.reauth()
    r = await api.post(f"/api/v1/approvals/{appr['id']}/decide", json={"approve": True, "note": "ok"}, headers=owner.h)
    assert r.json()["status"] == "approved"
    assert (await api.get("/api/v1/agents/content_agent")).json()["brain"]["brain_version"] == "1.1.0"
    again = await api.post(f"/api/v1/approvals/{appr['id']}/decide", json={"approve": False}, headers=owner.h)
    assert again.status_code == 409
    # Quay lại bản cũ (cần xác thực lại: vẫn còn trong 5 phút)
    r = await api.post(f"/api/v1/agents/content_agent/brains/{versions[1]['id']}/rollback", headers=owner.h)
    assert r.json() == {"ok": True}
    assert (await api.get("/api/v1/agents/content_agent")).json()["brain"]["brain_version"] == "1.0.0"
    h = (await api.get("/api/v1/agents/content_agent/history")).json()
    assert [v["event"] for v in h["versions"]] == ["rolled_back", "activated", "proposed", "bootstrap"]
    done = (await api.get("/api/v1/approvals?status=done")).json()
    assert done[0]["status"] == "approved" and done[0]["decided_by"] == f"user:{owner.EMAIL}"
    ev = [e["action"] for e in (await api.get("/api/v1/events")).json() if e["source"] == "audit"]
    assert {"approval.requested", "approval.approved", "brain.activated", "brain.rolled_back"} <= set(ev)


async def test_tool_approval_rejected_with_note(owner: OwnerSession) -> None:
    from app.core import db
    from app.tools.gateway import invoke

    async with db.engine().connect() as c:
        r = await invoke(
            c,
            agent_key="growth_director",
            tool_id="experiment",
            action="launch_live",
            input={"page": "/san-pham/tra-sen"},
            idempotency_key="exp-1",
        )
    assert r.status == "waiting_approval"
    appr = (await owner.api.get("/api/v1/approvals")).json()[0]
    assert appr["risk"] == "medium" and appr["subject_type"] == "tool_call" and appr["payload"]["input"] == {"page": "/san-pham/tra-sen"}
    r2 = await owner.api.post(
        f"/api/v1/approvals/{appr['id']}/decide", json={"approve": False, "note": "Chưa đủ lượt truy cập"}, headers=owner.h
    )
    assert r2.json()["status"] == "rejected" and r2.json()["decision_note"] == "Chưa đủ lượt truy cập"
    h = (await owner.api.get("/api/v1/agents/growth_director/history")).json()
    assert h["invocations"][0]["status"] == "waiting_approval" and h["decisions"][0]["rule"] == "permission_requires_approval"


async def test_lifecycle_via_api(owner: OwnerSession) -> None:
    api = owner.api
    assert (await api.post("/api/v1/agents/seo_agent/pause", json={"reason": "x"}, headers=owner.h)).json()["state"] == "paused"
    assert (await api.post("/api/v1/agents/seo_agent/pause", json={}, headers=owner.h)).json()["state"] == "paused"  # lặp lại không lỗi
    assert (await api.post("/api/v1/agents/seo_agent/resume", headers=owner.h)).json()["state"] == "active"
    ov = (await api.get("/api/v1/overview")).json()
    assert ov["approvals_pending"] == 0


async def test_totp_code_cannot_be_reused(owner: OwnerSession) -> None:
    api = owner.api
    await api.post("/api/v1/auth/logout", headers=owner.h)
    code = owner.code()
    body = {"email": owner.EMAIL, "password": owner.PASSWORD, "code": code}
    assert (await api.post("/api/v1/auth/login", json=body)).status_code == 200
    st = (await api.get("/api/v1/auth/state")).json()
    await api.post("/api/v1/auth/logout", headers={"X-CSRF-Token": st["csrf"]})
    r = await api.post("/api/v1/auth/login", json=body)  # kẻ nhìn trộm dùng lại đúng mã đó
    assert r.status_code == 401 and r.json()["error"]["code"] == "LOGIN_FAILED"


def test_totp_step_window() -> None:
    import pyotp

    from app.core.security import totp_step

    sec = pyotp.random_base32()
    t = pyotp.TOTP(sec)
    now = 1_800_000_000.0
    cur = int(now // 30)
    assert totp_step(sec, t.at(now), None, now) == cur
    assert totp_step(sec, t.at(now - 30), None, now) == cur - 1  # lệch đồng hồ 1 bước vẫn nhận
    assert totp_step(sec, t.at(now - 60), None, now) is None
    assert totp_step(sec, t.at(now), cur, now) is None  # đã dùng bước này
    assert totp_step(sec, t.at(now + 30), cur, now) == cur + 1


async def test_opentelemetry_spans_and_log_correlation(owner: OwnerSession) -> None:
    from opentelemetry import trace
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from app.core import db, telemetry
    from app.core.logging import JsonFormatter
    from app.tools.gateway import invoke

    mem = InMemorySpanExporter()
    telemetry.provider().add_span_processor(SimpleSpanProcessor(mem))
    await owner.api.get("/api/v1/agents/seo_agent")
    async with db.engine().connect() as c:
        await invoke(c, agent_key="data_analyst", tool_id="signals", action="read", input={}, idempotency_key="otel-1", task_id="t-7")
    spans = {s.name: s for s in mem.get_finished_spans()}
    assert "GET /api/v1/agents/{key}" in spans
    tool_span, pol = spans["tool.invoke"], spans["policy.authorize"]
    assert (
        tool_span.attributes and tool_span.attributes["aico.tool.status"] == "succeeded" and tool_span.attributes["aico.task_id"] == "t-7"
    )
    assert pol.parent is not None and pol.parent.span_id == tool_span.context.span_id  # chính sách nằm trong lời gọi công cụ
    with trace.get_tracer("t").start_as_current_span("x") as sp:
        line = json.loads(JsonFormatter().format(logging.LogRecord("aico", logging.INFO, "f", 1, "xin chào", None, None)))
    assert line["trace_id"] == format(sp.get_span_context().trace_id, "032x")


async def test_sync_reports_bundle_errors(owner: OwnerSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    root = tmp_path / "brains"
    shutil.copytree(BRAINS, root)
    (root / "ads_agent/identity/role.yaml").write_text("mission: ngắn\n", encoding="utf-8")
    monkeypatch.setenv("AICO_BRAINS_DIR", str(root))
    get_settings.cache_clear()
    items = {i["agent_key"]: i for i in (await owner.api.post("/api/v1/brains/sync", headers=owner.h)).json()}
    assert items["ads_agent"]["status"] == "error"
    assert (
        "identity.role.mission" in items["ads_agent"]["detail"]
        and "identity.role.responsibilities: thiếu trường bắt buộc" in items["ads_agent"]["detail"]
    )
    # Bản đang chạy không bị ảnh hưởng
    assert (await owner.api.get("/api/v1/agents/ads_agent")).json()["integrity"]["ok"] is True
    assert {i.status for i in await sync_brains()} == {"unchanged"}
