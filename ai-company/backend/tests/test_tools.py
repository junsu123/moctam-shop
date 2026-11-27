"""UT-TOOL-01…06: Tool Gateway (schema vào/ra, timeout, retry, ghi nhật ký, chống trùng, phê duyệt).

Công cụ `testkit` chỉ tồn tại trong test (fixture), không có trong mã production."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import db
from app.domain import notify
from app.tools import spec as tools
from app.tools.gateway import ToolError, invoke
from tests.conftest import needs_db

pytestmark = [needs_db, pytest.mark.usefixtures("synced")]
AGENT = "automation_agent"
CALLS: dict[str, int] = {}


class EchoIn(BaseModel):
    text: str = Field(max_length=10)


class EchoOut(BaseModel):
    echo: str


async def _echo(ctx: tools.ToolCtx, inp: EchoIn) -> EchoOut:
    CALLS["echo"] = CALLS.get("echo", 0) + 1
    return EchoOut(echo=inp.text)


async def _flaky(ctx: tools.ToolCtx, inp: EchoIn) -> EchoOut:
    CALLS["flaky"] = CALLS.get("flaky", 0) + 1
    if ctx.attempt < 2:
        raise ToolError("TRANSIENT", "mạng chập chờn")
    return EchoOut(echo=inp.text)


async def _broken(ctx: tools.ToolCtx, inp: EchoIn) -> EchoOut:
    CALLS["broken"] = CALLS.get("broken", 0) + 1
    raise ToolError("BAD_INPUT_UPSTREAM", "nền tảng từ chối")


async def _slow(ctx: tools.ToolCtx, inp: EchoIn) -> EchoOut:
    await asyncio.sleep(1)
    return EchoOut(echo=inp.text)


async def _badout(ctx: tools.ToolCtx, inp: EchoIn) -> Any:
    return {"wrong": 1}


async def _effect(ctx: tools.ToolCtx, inp: EchoIn) -> EchoOut:
    await notify.enqueue(ctx.conn, "report", f"tác động {inp.text}")  # tác động nội bộ, cùng giao dịch với bản ghi lời gọi
    return EchoOut(echo=inp.text)


def _a(name: str, handler: Any, level: int = 1, side: Any = "internal", tags: tuple[str, ...] = ()) -> tools.ActionSpec:
    return tools.ActionSpec(
        name=name,
        description=name,
        min_level=level,
        side_effects=side,
        tags=tags,
        input_model=EchoIn,
        output_model=EchoOut,
        handler=handler,
    )


@pytest.fixture(autouse=True)
def testkit() -> Iterator[None]:
    CALLS.clear()
    tools.register(
        tools.ToolSpec(
            id="testkit",
            description="chỉ dùng trong test",
            risk="low",
            timeout_s=0.2,
            retry=tools.RetryPolicy(max_attempts=3, backoff_s=0.01, retry_on=("TIMEOUT", "TRANSIENT")),
            actions={
                a.name: a
                for a in (
                    _a("echo", _echo),
                    _a("flaky", _flaky),
                    _a("broken", _broken),
                    _a("slow", _slow),
                    _a("badout", _badout),
                    _a("effect", _effect, 2),
                    _a("bulk", _effect, 3, "external", ("bulk_send",)),
                )
            },
        )
    )
    yield
    tools.REGISTRY.pop("testkit", None)


@pytest.fixture
async def granted(conn: AsyncConnection) -> AsyncConnection:
    for action in ("echo", "flaky", "broken", "slow", "badout", "effect", "bulk"):
        await db.execute(
            conn,
            "INSERT INTO agent_permissions(agent_key, tool_id, action, autonomy_level, granted_by) VALUES (:a, 'testkit', :ac, 3, 'test')",
            {"a": AGENT, "ac": action},
        )
    return conn


async def _inv(key: str) -> dict[str, Any]:
    async with db.engine().connect() as c:
        r = await db.one(c, "SELECT * FROM tool_invocations WHERE idempotency_key = :k", {"k": key})
    assert r is not None
    return dict(r)


async def test_tool01_input_and_output_schema(granted: AsyncConnection) -> None:
    from app.core.errors import AppError

    with pytest.raises(AppError) as e:
        await invoke(
            granted, agent_key=AGENT, tool_id="testkit", action="echo", input={"text": "quá dài hơn mười ký tự"}, idempotency_key="k1"
        )
    assert e.value.code == "TOOL_INPUT_INVALID"
    r = await invoke(granted, agent_key=AGENT, tool_id="testkit", action="badout", input={"text": "a"}, idempotency_key="k2")
    assert r.status == "failed" and r.error_code == "TOOL_OUTPUT_INVALID" and r.attempts == 1
    ok = await invoke(granted, agent_key=AGENT, tool_id="testkit", action="echo", input={"text": "chào"}, idempotency_key="k3")
    assert ok.status == "succeeded" and ok.output == {"echo": "chào"}


async def test_tool02_timeout(granted: AsyncConnection) -> None:
    r = await invoke(granted, agent_key=AGENT, tool_id="testkit", action="slow", input={"text": "a"}, idempotency_key="slow-1")
    assert r.status == "failed" and r.error_code == "TIMEOUT" and r.attempts == 3  # TIMEOUT nằm trong retry_on
    row = await _inv("slow-1")
    assert row["status"] == "failed" and row["error_code"] == "TIMEOUT"


async def test_tool03_retry_policy(granted: AsyncConnection) -> None:
    r = await invoke(granted, agent_key=AGENT, tool_id="testkit", action="flaky", input={"text": "a"}, idempotency_key="f-1")
    assert r.status == "succeeded" and r.attempts == 2 and CALLS["flaky"] == 2
    r = await invoke(granted, agent_key=AGENT, tool_id="testkit", action="broken", input={"text": "a"}, idempotency_key="b-1")
    assert r.status == "failed" and r.attempts == 1 and CALLS["broken"] == 1  # lỗi không tạm thời: không thử lại


async def test_tool04_invocation_audit_and_policy_records(granted: AsyncConnection) -> None:
    await invoke(granted, agent_key=AGENT, tool_id="testkit", action="echo", input={"text": "a"}, idempotency_key="a-1", task_id="task-9")
    row = await _inv("a-1")
    assert row["status"] == "succeeded" and row["task_id"] == "task-9" and row["duration_ms"] is not None and row["output"] == {"echo": "a"}
    async with db.engine().connect() as c:
        acts = [r["action"] for r in await db.all_(c, "SELECT action FROM audit_logs ORDER BY id")]
        pol = await db.all_(c, "SELECT decision, rule FROM policy_decisions WHERE tool_id = 'testkit'")
    assert "tool.invoked" in acts and [(p["decision"], p["rule"]) for p in pol] == [("allow", "permitted")]
    denied = await invoke(granted, agent_key="social_agent", tool_id="testkit", action="echo", input={"text": "a"}, idempotency_key="a-2")
    assert denied.status == "denied" and denied.error_code == "POLICY_DENIED" and "mặc định từ chối" in str(denied.error)
    assert (await _inv("a-2"))["status"] == "denied"


async def test_tool05_idempotency_no_second_effect(granted: AsyncConnection) -> None:
    from app.core.errors import AppError

    first = await invoke(granted, agent_key=AGENT, tool_id="testkit", action="effect", input={"text": "x"}, idempotency_key="task1:step3")
    again = await invoke(granted, agent_key=AGENT, tool_id="testkit", action="effect", input={"text": "x"}, idempotency_key="task1:step3")
    assert first.status == again.status == "succeeded" and again.replayed and again.output == first.output
    async with db.engine().connect() as c:
        assert await db.scalar(c, "SELECT count(*) FROM notifications WHERE text = 'tác động x'") == 1
    with pytest.raises(AppError) as e:
        await invoke(granted, agent_key=AGENT, tool_id="testkit", action="effect", input={"text": "y"}, idempotency_key="task1:step3")
    assert e.value.code == "IDEMPOTENCY_CONFLICT"


async def test_tool06_approval_flow_and_digest(granted: AsyncConnection) -> None:
    from app.domain import approvals

    r = await invoke(granted, agent_key=AGENT, tool_id="testkit", action="bulk", input={"text": "khuyến mãi"}, idempotency_key="bulk-1")
    assert r.status == "waiting_approval" and r.approval_id and r.decision and r.decision.risk == "high"
    assert CALLS.get("effect", 0) == 0 and (await _inv("bulk-1"))["status"] == "waiting_approval"
    # Gọi lại khi chưa duyệt: không tạo yêu cầu thứ hai
    r2 = await invoke(
        granted,
        agent_key=AGENT,
        tool_id="testkit",
        action="bulk",
        input={"text": "khuyến mãi"},
        idempotency_key="bulk-1",
        approval_id=r.approval_id,
    )
    assert r2.status == "waiting_approval" and r2.approval_id == r.approval_id
    async with db.engine().begin() as c:
        await approvals.decide(c, r.approval_id, True, "user:o")
    done = await invoke(
        granted,
        agent_key=AGENT,
        tool_id="testkit",
        action="bulk",
        input={"text": "khuyến mãi"},
        idempotency_key="bulk-1",
        approval_id=r.approval_id,
    )
    assert done.status == "succeeded"
    # Phê duyệt của nội dung này không dùng cho nội dung khác
    other = await invoke(
        granted,
        agent_key=AGENT,
        tool_id="testkit",
        action="bulk",
        input={"text": "giảm giá"},
        idempotency_key="bulk-2",
        approval_id=r.approval_id,
    )
    assert other.status == "waiting_approval" and other.approval_id != r.approval_id


async def test_unconfigured_tool_and_real_tools(conn: AsyncConnection) -> None:
    r = await invoke(conn, agent_key="content_agent", tool_id="site", action="draft", input={"title": "x"}, idempotency_key="n-1")
    assert r.status == "failed" and r.error_code == "NOT_CONFIGURED" and "chưa được kết nối" in str(r.error)
    s = await invoke(conn, agent_key="data_analyst", tool_id="signals", action="read", input={}, idempotency_key="s-1")
    assert s.status == "succeeded" and s.output and s.output["agents"] == {"active": 15} and s.output["approvals_pending"] == 0
    n1 = await invoke(
        conn, agent_key="data_analyst", tool_id="notify", action="owner", input={"text": "Báo cáo tuần"}, idempotency_key="rep-1"
    )
    n2 = await invoke(
        conn, agent_key="data_analyst", tool_id="notify", action="owner", input={"text": "Báo cáo tuần"}, idempotency_key="rep-1"
    )
    assert n1.status == "succeeded" and n2.replayed
    async with db.engine().connect() as c:
        rows = await db.all_(c, "SELECT kind, text FROM notifications")
    assert [(x["kind"], x["text"]) for x in rows] == [("report", "[data_analyst] Báo cáo tuần")]
    social = await invoke(conn, agent_key="social_agent", tool_id="notify", action="owner", input={"text": "x"}, idempotency_key="rep-2")
    assert social.status == "denied"  # Mạng xã hội không có quyền báo cáo thẳng cho Owner
