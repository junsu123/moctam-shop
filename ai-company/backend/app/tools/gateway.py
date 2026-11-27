"""Tool Gateway: mọi tác động của agent đi qua đây (CLAUDE.md quy tắc 4).

Một lời gọi: kiểm schema đầu vào → khóa chống trùng → Policy Engine → (chờ duyệt) → chạy có timeout và thử lại theo
chính sách → kiểm schema đầu ra → ghi `tool_invocations` + audit.

Chạy đúng một lần: tác động nội bộ của công cụ và việc đánh dấu `succeeded` nằm **chung một giao dịch**. Gọi lại cùng
`idempotency_key` sau khi đã thành công chỉ trả lại kết quả cũ, không tạo tác động thứ hai.

Gateway ghi bằng kết nối riêng (commit ngay). Không gọi gateway trong một giao dịch đã ghi audit (khóa advisory của audit).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import audit, db
from app.core.errors import AppError
from app.core.ids import uuid7
from app.core.telemetry import tracer
from app.domain import approvals
from app.policy.engine import Decision, PolicyCtx, authorize
from app.tools import spec as tools

log = logging.getLogger("aico.tools")


class ToolError(Exception):
    """Lỗi do công cụ báo. `TRANSIENT` được thử lại theo retry_policy; mã khác thì không."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class InvokeResult:
    status: str  # succeeded | waiting_approval | denied | failed
    invocation_id: str
    output: dict[str, Any] | None = None
    approval_id: str | None = None
    decision: Decision | None = None
    error_code: str | None = None
    error: str | None = None
    replayed: bool = False
    attempts: int = 0


async def _save(key: str, **f: Any) -> dict[str, Any]:
    """Tạo hoặc cập nhật bản ghi lời gọi theo khóa chống trùng (commit ngay)."""
    from app.domain.approvals import _json

    if "output" in f:
        f["output"] = None if f["output"] is None else _json(f["output"])
    cols = list(f)
    sets = ", ".join(f"{c} = CAST(:{c} AS jsonb)" if c == "output" else f"{c} = :{c}" for c in cols)
    async with db.engine().begin() as c:
        row = await db.one(c, f"UPDATE tool_invocations SET {sets} WHERE idempotency_key = :key RETURNING *", {**f, "key": key})  # noqa: S608
    assert row is not None
    return dict(row)


async def _existing(key: str) -> dict[str, Any] | None:
    async with db.engine().connect() as c:
        r = await db.one(c, "SELECT * FROM tool_invocations WHERE idempotency_key = :k", {"k": key})
    return dict(r) if r else None


async def _audit(actor: str, action: str, resource: str, data: dict[str, Any]) -> None:
    async with db.engine().begin() as c:
        await audit.record(c, actor, action, resource, data)


async def _invoke(
    conn: AsyncConnection,
    *,
    agent_key: str,
    tool_id: str,
    action: str,
    input: dict[str, Any],  # noqa: A002
    idempotency_key: str,
    task_id: str | None = None,
    ctx: PolicyCtx | None = None,
    approval_id: str | None = None,
) -> InvokeResult:
    spec = tools.get(tool_id)
    act = spec.actions.get(action) if spec else None
    if spec is None or act is None:
        raise AppError("TOOL_NOT_FOUND", f"Không có công cụ {tool_id}.{action}.", 404)
    try:
        inp = act.input_model.model_validate(input)
    except ValidationError as e:
        raise AppError("TOOL_INPUT_INVALID", f"Đầu vào của {tool_id}.{action} không hợp lệ: {e.errors()[0]['msg']}", 422) from e
    payload = {"agent": agent_key, "tool": tool_id, "action": action, "input": inp.model_dump(mode="json")}
    in_digest = approvals.digest(payload)
    resource = f"tool:{tool_id}.{action}"
    actor = f"agent:{agent_key}"

    old = await _existing(idempotency_key)
    if old:
        if old["input_digest"] != in_digest:
            raise AppError("IDEMPOTENCY_CONFLICT", "Khóa chống trùng đã dùng cho một lời gọi khác.", 409)
        if old["status"] == "succeeded":
            return InvokeResult("succeeded", str(old["id"]), old["output"], replayed=True, attempts=old["attempts"])
        stale = old["at"] + timedelta(seconds=spec.timeout_s * spec.retry.max_attempts + 30) < datetime.now(UTC)
        if old["status"] == "running" and not stale:
            raise AppError("TOOL_IN_PROGRESS", "Lời gọi với khóa này đang chạy.", 409)
        inv_id = str(old["id"])
    else:
        inv_id = str(uuid7())
        async with db.engine().begin() as c:
            await db.execute(
                c,
                "INSERT INTO tool_invocations(id, tool_id, action, agent_key, task_id, idempotency_key, input_digest, status) "
                "VALUES (:id, :t, :a, :ag, :task, :k, :d, 'running') ON CONFLICT (idempotency_key) DO NOTHING",
                {"id": inv_id, "t": tool_id, "a": action, "ag": agent_key, "task": task_id, "k": idempotency_key, "d": in_digest},
            )

    decision = await authorize(conn, agent_key, tool_id, action, ctx)
    if decision.kind == "deny":
        await _save(idempotency_key, status="denied", error_code="POLICY_DENIED", error=decision.reason, finished_at=datetime.now(UTC))
        await _audit(actor, "tool.denied", resource, {"rule": decision.rule, "reason": decision.reason})
        return InvokeResult("denied", inv_id, decision=decision, error_code="POLICY_DENIED", error=decision.reason)
    if decision.kind == "require_approval":
        ok = False
        if approval_id:
            async with db.engine().connect() as c:
                ok, why = await approvals.usable(c, approval_id, "tool_call", idempotency_key, payload)
            if not ok:
                log.info("Phê duyệt không dùng được: %s", why)
        if not ok:
            async with db.engine().begin() as c:
                name = await db.scalar(c, "SELECT display_name FROM agents WHERE agent_key = :a", {"a": agent_key}) or agent_key
                appr = await approvals.create(
                    c,
                    subject_type="tool_call",
                    subject_id=idempotency_key,
                    action=f"{tool_id}.{action}",
                    risk=decision.risk,
                    requested_by=actor,
                    title=f"{name} muốn: {act.description[:1].lower()}{act.description[1:]}",
                    summary=decision.reason,
                    payload=payload,
                )
            await _save(idempotency_key, status="waiting_approval", approval_id=appr["id"])
            return InvokeResult("waiting_approval", inv_id, approval_id=str(appr["id"]), decision=decision)
    if act.handler is None:
        msg = f"Công cụ {tool_id} chưa được kết nối"
        await _save(idempotency_key, status="failed", error_code="NOT_CONFIGURED", error=msg, finished_at=datetime.now(UTC))
        return InvokeResult("failed", inv_id, decision=decision, error_code="NOT_CONFIGURED", error=msg)

    attempts = 0
    code, err = "ERROR", ""
    t0 = time.perf_counter()
    while attempts < spec.retry.max_attempts:
        attempts += 1
        await _save(idempotency_key, status="running", attempts=attempts, approval_id=approval_id)
        try:
            async with db.engine().begin() as tx:
                out = await asyncio.wait_for(
                    act.handler(tools.ToolCtx(tx, agent_key, task_id, idempotency_key, attempts), inp), timeout=spec.timeout_s
                )
                try:
                    out_data = act.output_model.model_validate(out.model_dump() if isinstance(out, BaseModel) else out).model_dump(
                        mode="json"
                    )
                except ValidationError as e:
                    raise ToolError("TOOL_OUTPUT_INVALID", f"Đầu ra sai schema: {e.errors()[0]['msg']}") from e
                from app.domain.approvals import _json

                await db.execute(
                    tx,
                    "UPDATE tool_invocations SET status = 'succeeded', output = CAST(:o AS jsonb), error_code = NULL, error = NULL, "
                    "duration_ms = :ms, finished_at = now() WHERE idempotency_key = :k",
                    {"o": _json(out_data), "ms": round((time.perf_counter() - t0) * 1000), "k": idempotency_key},
                )
            await _audit(actor, "tool.invoked", resource, {"attempts": attempts})
            return InvokeResult("succeeded", inv_id, out_data, decision=decision, attempts=attempts)
        except TimeoutError:
            code, err = "TIMEOUT", f"Quá {spec.timeout_s:g} giây"
        except ToolError as e:
            code, err = e.code, e.message
        except Exception as e:  # noqa: BLE001 — lỗi của công cụ không được làm sập agent
            code, err = "ERROR", type(e).__name__
            log.warning("Công cụ %s.%s lỗi %s", tool_id, action, type(e).__name__)
        if code not in spec.retry.retry_on:
            break
        if attempts < spec.retry.max_attempts:
            await asyncio.sleep(spec.retry.backoff_s * 2 ** (attempts - 1))
    await _save(
        idempotency_key,
        status="failed",
        error_code=code,
        error=err[:500],
        attempts=attempts,
        duration_ms=round((time.perf_counter() - t0) * 1000),
        finished_at=datetime.now(UTC),
    )
    await _audit(actor, "tool.failed", resource, {"code": code, "attempts": attempts})
    return InvokeResult("failed", inv_id, decision=decision, error_code=code, error=err, attempts=attempts)


async def invoke(conn: AsyncConnection, **kw: Any) -> InvokeResult:
    """Gọi công cụ qua gateway (xem `_invoke`), trong một span OpenTelemetry."""
    with tracer.start_as_current_span(
        "tool.invoke",
        attributes={"aico.agent": kw["agent_key"], "aico.tool": f"{kw['tool_id']}.{kw['action']}", "aico.task_id": kw.get("task_id") or ""},
    ) as span:
        r = await _invoke(conn, **kw)
        span.set_attribute("aico.tool.status", r.status)
        span.set_attribute("aico.tool.attempts", r.attempts)
        if r.error_code:
            span.set_attribute("aico.tool.error_code", r.error_code)
        return r


async def sync_registry(conn: AsyncConnection) -> int:
    """Chiếu danh mục công cụ (mã nguồn) vào bảng `tool_registry` để Control Center hiển thị."""
    from app.domain.approvals import _json

    n = 0
    for t in tools.REGISTRY.values():
        actions = {
            k: {
                "description": a.description,
                "min_level": a.min_level,
                "side_effects": a.side_effects,
                "tags": list(a.tags),
                "untrusted_output": a.untrusted_output,
                "available": a.handler is not None,
            }
            for k, a in t.actions.items()
        }
        await db.execute(
            conn,
            "INSERT INTO tool_registry(id, description, actions, input_schema, output_schema, side_effects, risk, default_timeout_s, retry_policy, available) "
            "VALUES (:id, :d, CAST(:a AS jsonb), CAST(:i AS jsonb), CAST(:o AS jsonb), :s, :r, :to, CAST(:rp AS jsonb), :av) "
            "ON CONFLICT (id) DO UPDATE SET description = EXCLUDED.description, actions = EXCLUDED.actions, input_schema = EXCLUDED.input_schema, "
            "output_schema = EXCLUDED.output_schema, side_effects = EXCLUDED.side_effects, risk = EXCLUDED.risk, "
            "default_timeout_s = EXCLUDED.default_timeout_s, retry_policy = EXCLUDED.retry_policy, available = EXCLUDED.available, updated_at = now()",
            {
                "id": t.id,
                "d": t.description,
                "a": _json(actions),
                "i": _json({k: a.input_model.model_json_schema() for k, a in t.actions.items()}),
                "o": _json({k: a.output_model.model_json_schema() for k, a in t.actions.items()}),
                "s": t.side_effects,
                "r": t.risk,
                "to": t.timeout_s,
                "rp": _json({"max_attempts": t.retry.max_attempts, "backoff_s": t.retry.backoff_s, "retry_on": list(t.retry.retry_on)}),
                "av": t.available,
            },
        )
        n += 1
    return n
