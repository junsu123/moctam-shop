"""Công cụ nội bộ của Task Engine, chạy qua Tool Gateway (Policy Engine + khóa chống trùng + audit) như mọi công cụ khác.

- `task.delegate`: giao việc cho agent khác theo hợp đồng (tiêu chí đo được, ngân sách, hạn chót). Kiểm hợp đồng NGAY khi gọi để
  agent lập lại kế hoạch được; task con được tạo bởi Message Bus từ message `task_request` (id task con định trước).
- `knowledge.share`: gửi ứng viên kiến thức qua Message Bus vào hộp thẩm định; không ghi thẳng vào trí nhớ của ai.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core import db
from app.core.errors import AppError
from app.tools.spec import ToolCtx

NS = uuid.UUID("6f1c2b5e-3a9d-4c7e-9b1a-5d2e8f0a7c41")


class Criterion(BaseModel):
    type: Literal["required_fields", "max_len", "min_len", "contains", "not_contains", "field_in", "min_items", "manual"]
    field: str | None = None
    fields: list[str] | None = None
    n: int | None = None
    text: str | list[str] | None = None
    values: list[str] | None = None
    description: str | None = None


class DelegateIn(BaseModel):
    agent: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(default="", max_length=4000)
    task_type: str = Field(default="generic", pattern=r"^[a-z][a-z0-9_]{1,40}$")
    success_criteria: list[Criterion] = Field(min_length=1, max_length=10)
    budget_usd: float = Field(gt=0, le=5)
    deadline_hours: float = Field(gt=0, le=720)
    input: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=2, ge=0, le=3)


class DelegateOut(BaseModel):
    task_id: str
    agent: str
    message_id: str


async def allowed_receivers(conn: Any, sender: str) -> list[str]:
    """Giao xuống cấp dưới trực tiếp, hoặc ngang cấp cùng phòng; AI CEO giao được cho mọi agent (AGENT_DESIGN §5)."""
    me = await db.one(conn, "SELECT agent_key, kind, department FROM agents WHERE agent_key = :a", {"a": sender})
    if me is None:
        return []
    rows = await db.all_(
        conn,
        "SELECT a.agent_key FROM agents a JOIN agent_status s ON s.agent_id = a.id WHERE a.agent_key <> :a AND s.state <> 'disabled' "
        "AND (:exec OR a.reports_to = :a OR (a.department = :d AND a.kind = :k)) ORDER BY a.sort_order",
        {"a": sender, "exec": me["kind"] == "executive", "d": me["department"], "k": me["kind"]},
    )
    return [r["agent_key"] for r in rows]


async def delegate(ctx: ToolCtx, inp: DelegateIn) -> DelegateOut:
    try:
        return await _delegate(ctx, inp)
    except AppError as e:  # lỗi hợp đồng: trả mã và lời giải thích để agent lập lại kế hoạch
        from app.tools.gateway import ToolError

        raise ToolError(e.code, e.message) from e


async def _delegate(ctx: ToolCtx, inp: DelegateIn) -> DelegateOut:
    from app.tasks import bus, engine

    if not ctx.task_id:
        raise AppError("TASK_CONTEXT_MISSING", "Chỉ giao việc được từ trong một task.", 422)
    if inp.agent not in await allowed_receivers(ctx.conn, ctx.agent_key):
        raise AppError("DELEGATE_NOT_ALLOWED", f"{ctx.agent_key} không được giao việc cho {inp.agent}.", 403)
    parent = await engine.get(ctx.conn, ctx.task_id, lock=True)
    deadline = datetime.now(UTC) + timedelta(hours=inp.deadline_hours)
    await engine.check_child(ctx.conn, parent, inp.budget_usd, exclude=str(uuid.uuid5(NS, ctx.idempotency_key)))
    child = str(uuid.uuid5(NS, ctx.idempotency_key))
    await engine.add_dependency(ctx.conn, ctx.task_id, child)
    mid = await bus.send(
        ctx.conn,
        "task_request",
        sender=f"agent:{ctx.agent_key}",
        receiver=f"agent:{inp.agent}",
        task_id=ctx.task_id,
        correlation_id=str(parent["root_id"]),
        key=f"delegate:{ctx.idempotency_key}",
        priority=inp.priority,
        payload={
            "task_id": child,
            "title": inp.title,
            "description": inp.description,
            "task_type": inp.task_type,
            "success_criteria": [c.model_dump(exclude_none=True) for c in inp.success_criteria],
            "budget_usd": inp.budget_usd,
            "deadline": (min(deadline, parent["deadline"]) if parent["deadline"] else deadline).isoformat(),
            "input": inp.input,
            "priority": inp.priority,
            "requires_review": True,
            "reviewer": f"agent:{ctx.agent_key}",
            "autonomy_max": int(parent["autonomy_max"]),
        },
    )
    await engine.log_event(
        ctx.conn, ctx.task_id, "delegated", f"Giao cho {inp.agent}: {inp.title}", agent=ctx.agent_key, data={"child": child}
    )
    return DelegateOut(task_id=child, agent=inp.agent, message_id=mid)


class ShareIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    claim: str = Field(min_length=10, max_length=4000)
    evidence: list[str] = Field(min_length=1, max_length=10)
    target_scope: str = Field(default="company", pattern=r"^(company|dept:[a-z_]+)$")


class ShareOut(BaseModel):
    message_id: str


async def share(ctx: ToolCtx, inp: ShareIn) -> ShareOut:
    from app.tasks import bus

    untrusted = bool(
        ctx.task_id
        and await db.scalar(
            ctx.conn,
            "SELECT EXISTS (SELECT 1 FROM tool_invocations ti WHERE ti.task_id = :t AND ti.status = 'succeeded' "
            "AND (ti.tool_id || '.' || ti.action) = ANY(:u))",
            {"t": ctx.task_id, "u": untrusted_actions()},
        )
    )
    mid = await bus.send(
        ctx.conn,
        "knowledge_sharing",
        sender=f"agent:{ctx.agent_key}",
        receiver="learning_engine",
        task_id=ctx.task_id,
        key=f"share:{ctx.idempotency_key}",
        trust="untrusted" if untrusted else "internal",
        payload=inp.model_dump(),
    )
    return ShareOut(message_id=mid)


def untrusted_actions() -> list[str]:
    from app.tools.spec import REGISTRY

    return [f"{t.id}.{a.name}" for t in REGISTRY.values() for a in t.actions.values() if a.untrusted_output]
