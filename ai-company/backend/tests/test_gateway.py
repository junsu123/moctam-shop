"""UT-MGW-01…08: Model Gateway với nhà cung cấp giả (httpx.MockTransport). Không gọi mạng thật."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from tests.conftest import needs_db

pytestmark = needs_db
Handler = Callable[[httpx.Request], httpx.Response]


def anthropic_ok(text: str = "Xin chào", tin: int = 1000, tout: int = 500) -> httpx.Response:
    return httpx.Response(200, json={"content": [{"type": "text", "text": text}], "usage": {"input_tokens": tin, "output_tokens": tout}})


def openai_ok(text: str = "Hello", tin: int = 1000, tout: int = 500) -> httpx.Response:
    return httpx.Response(
        200, json={"choices": [{"message": {"content": text}}], "usage": {"prompt_tokens": tin, "completion_tokens": tout}}
    )


class Fake:
    """Nhà cung cấp giả: ghi lại mọi request, trả lời theo hàng đợi phản hồi cho từng host."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.queue: dict[str, list[httpx.Response]] = {"api.anthropic.com": [], "api.openai.com": []}

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append((req.url.host, json.loads(req.content)))
        q = self.queue[req.url.host]
        return q.pop(0) if q else (anthropic_ok() if "anthropic" in req.url.host else openai_ok())


@pytest.fixture
async def gw(conn: AsyncConnection) -> AsyncIterator[tuple[AsyncConnection, Fake]]:
    from app.domain import store
    from app.gateway import models

    await store.put_secret(conn, "provider.anthropic.api_key", "sk-ant-test-" + "a" * 30, "test")
    await store.put_secret(conn, "provider.openai.api_key", "sk-test-" + "o" * 30, "test")
    fake = Fake()
    models.transport = httpx.MockTransport(fake)
    yield conn, fake
    models.transport = None


async def _usage(conn: AsyncConnection) -> list[dict[str, Any]]:
    from app.core import db

    async with db.engine().connect() as c:  # sổ chi phí ghi bằng kết nối riêng
        return [dict(r) for r in await db.all_(c, "SELECT * FROM model_usage ORDER BY id")]


async def test_mgw01_routes_by_profile_and_registry(gw: tuple[AsyncConnection, Fake]) -> None:
    from app.core import db
    from app.gateway import models

    conn, fake = gw
    r = await models.complete(conn, "cheap", "sys", "Phân loại câu hỏi", agent_key="customer_agent")
    assert r.model_id == "claude-haiku-5-5" and fake.calls[-1][0] == "api.anthropic.com"
    assert fake.calls[-1][1]["model"] == "claude-haiku-5-5"
    # Đổi registry (không đổi mã agent) → đi qua adapter OpenAI
    await db.execute(conn, "UPDATE model_profiles SET model_id = 'gpt-5.4-mini', fallback_model_id = NULL WHERE profile = 'cheap'")
    r = await models.complete(conn, "cheap", "sys", "Phân loại câu hỏi", agent_key="customer_agent")
    assert r.model_id == "gpt-5.4-mini" and fake.calls[-1][0] == "api.openai.com"
    assert fake.calls[-1][1]["messages"][0] == {"role": "system", "content": "sys"}


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_mgw02_fallback_on_429_5xx(gw: tuple[AsyncConnection, Fake], status: int) -> None:
    from app.gateway import models

    conn, fake = gw
    fake.queue["api.anthropic.com"].append(httpx.Response(status, json={"error": "x"}))
    r = await models.complete(conn, "cheap", "sys", "hỏi", agent_key="seo_agent")
    assert r.fallback_used and r.model_id == "gpt-5.4-mini"
    u = await _usage(conn)
    assert [x["ok"] for x in u] == [False, True]
    assert u[0]["error_code"] in ("RATE_LIMITED", "PROVIDER_DOWN") and u[1]["fallback_of"] == "claude-haiku-5-5"


async def test_mgw02b_both_fail_gives_clear_error(gw: tuple[AsyncConnection, Fake]) -> None:
    from app.core.errors import AppError
    from app.gateway import models

    conn, fake = gw
    fake.queue["api.anthropic.com"].append(httpx.Response(401))
    fake.queue["api.openai.com"].append(httpx.Response(503))
    with pytest.raises(AppError) as e:
        await models.complete(conn, "cheap", "sys", "hỏi")
    assert e.value.code == "LLM_FAILED" and "Khóa API bị từ chối" in e.value.message
    assert "sk-ant" not in e.value.message


async def test_mgw03_cost_formula(gw: tuple[AsyncConnection, Fake]) -> None:
    from app.gateway import models

    conn, fake = gw
    fake.queue["api.anthropic.com"].append(anthropic_ok(tin=12_000, tout=3_000))
    r = await models.complete(conn, "writer_vi", "sys", "Viết bài", agent_key="content_agent", purpose="blog_draft")
    # Sonnet 5.5: 2 USD/1M vào, 10 USD/1M ra
    assert r.model_id == "claude-sonnet-5-5" and r.cost_usd == pytest.approx(12_000 * 2 / 1e6 + 3_000 * 10 / 1e6)
    u = (await _usage(conn))[-1]
    assert float(u["cost_usd"]) == pytest.approx(0.054) and u["agent_key"] == "content_agent" and u["purpose"] == "blog_draft"


async def test_mgw04_budget_caps_block_and_alert(gw: tuple[AsyncConnection, Fake]) -> None:
    from app.core import db
    from app.core.errors import AppError
    from app.domain import store
    from app.gateway import models

    conn, fake = gw
    await store.put_setting(conn, "budget", store.Budget(month_usd=0.10, day_usd=0.10, day_burst_usd=0.10, alert_pct=50), "test")
    fake.queue["api.anthropic.com"].append(anthropic_ok(tin=10_000, tout=4_000))  # 0.06 USD → 60% trần tháng
    await models.complete(conn, "writer_vi", "sys", "a", max_tokens=100)
    async with db.engine().connect() as c:
        alerts = await db.all_(c, "SELECT text, urgent, dedupe_key FROM notifications")
    assert len(alerts) == 1 and alerts[0]["urgent"] and alerts[0]["dedupe_key"].startswith("budget_alert:")
    n_calls = len(fake.calls)
    with pytest.raises(AppError) as e:
        await models.complete(conn, "writer_vi", "sys", "b", max_tokens=8_000)  # ước tính 0.08 USD → vượt trần
    assert e.value.code == "BUDGET_EXCEEDED" and e.value.status == 429
    assert len(fake.calls) == n_calls  # chặn TRƯỚC khi gọi, không tốn tiền
    u = (await _usage(conn))[-1]
    assert u["error_code"] == "BUDGET_EXCEEDED" and float(u["cost_usd"]) == 0
    async with db.engine().connect() as c:
        keys = [r["dedupe_key"] for r in await db.all_(c, "SELECT dedupe_key FROM notifications ORDER BY id")]
    assert keys[0].startswith("budget_alert:") and keys[1].startswith("budget_block:")


async def test_mgw04b_paused_agent_cannot_call(gw: tuple[AsyncConnection, Fake]) -> None:
    from app.core import db
    from app.core.errors import AppError
    from app.gateway import models

    conn, fake = gw
    await db.execute(conn, "UPDATE agent_status s SET state = 'paused' FROM agents a WHERE a.id = s.agent_id AND a.agent_key = 'ads_agent'")
    with pytest.raises(AppError) as e:
        await models.complete(conn, "cheap", "sys", "x", agent_key="ads_agent")
    assert e.value.code == "AGENT_PAUSED" and not fake.calls


class Plan(BaseModel):
    title: str
    steps: list[str]


async def test_mgw05_structured_output_with_one_repair(gw: tuple[AsyncConnection, Fake]) -> None:
    from app.gateway import models

    conn, fake = gw
    fake.queue["api.anthropic.com"] += [
        anthropic_ok("Đây là kế hoạch: tiêu đề A"),
        anthropic_ok('```json\n{"title": "A", "steps": ["b"]}\n```'),
    ]
    r = await models.complete(conn, "cheap", "sys", "lập kế hoạch", schema=Plan)
    assert isinstance(r.data, Plan) and r.data.steps == ["b"]
    assert len(fake.calls) == 2 and "không hợp lệ" in fake.calls[1][1]["messages"][0]["content"]
    assert '"title"' in fake.calls[0][1]["system"]  # schema được gửi kèm


async def test_mgw06_structured_output_gives_up_after_repair(gw: tuple[AsyncConnection, Fake]) -> None:
    from app.core.errors import AppError
    from app.gateway import models

    conn, fake = gw
    fake.queue["api.anthropic.com"] += [anthropic_ok("sai"), anthropic_ok("vẫn sai")]
    with pytest.raises(AppError) as e:
        await models.complete(conn, "cheap", "sys", "x", schema=Plan)
    assert e.value.code == "LLM_BAD_OUTPUT" and len(fake.calls) == 2


async def test_mgw07_08_pii_redacted_before_leaving(gw: tuple[AsyncConnection, Fake]) -> None:
    from app.gateway import models

    conn, fake = gw
    prompt = "Khách 0912 345 678 (lan.nguyen@gmail.com) hỏi về trà sen, khóa sk-ant-api03-abcdefghijklmnopqrstu"
    await models.complete(conn, "cheap", "Gọi lại 0987654321", prompt)
    body = json.dumps(fake.calls[-1][1], ensure_ascii=False)
    for leak in ("0912 345 678", "345 678", "lan.nguyen@gmail.com", "0987654321", "abcdefghijklmnopqrstu"):
        assert leak not in body
    assert "trà sen" in body


async def test_profile_and_key_errors(gw: tuple[AsyncConnection, Fake]) -> None:
    from app.core import db
    from app.core.errors import AppError
    from app.domain import store
    from app.gateway import models

    conn, _ = gw
    with pytest.raises(AppError) as e:
        await models.complete(conn, "khong_co", "s", "p")
    assert e.value.code == "PROFILE_UNKNOWN"
    await store.delete_secret(conn, "provider.anthropic.api_key")
    await store.delete_secret(conn, "provider.openai.api_key")
    with pytest.raises(AppError) as e:
        await models.complete(conn, "cheap", "s", "p")
    assert e.value.code == "LLM_FAILED" and "chưa có khóa API" in e.value.message
    await db.execute(conn, "UPDATE model_registry SET enabled = false")
    with pytest.raises(AppError) as e:
        await models.complete(conn, "cheap", "s", "p")
    assert e.value.code == "NO_MODEL"


async def test_spend_allows_daily_burst_only_from_unused_budget(conn: AsyncConnection) -> None:
    from app.gateway import models

    s = await models.spend(conn)
    assert s["today_usd"] == 0 and s["day_cap_usd"] == 1.67
    assert 1.67 <= s["allowed_today_usd"] <= 3.0
