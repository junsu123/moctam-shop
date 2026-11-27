"""Vòng đời agent (AGENT_DESIGN §1): chuyển trạng thái hợp lệ, mọi thay đổi đều ghi nhật ký."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import audit, db
from app.core.errors import AppError

STATES = ("active", "paused", "learning", "waiting_approval", "degraded", "disabled")
TRANSITIONS: dict[str, frozenset[str]] = {
    "active": frozenset({"paused", "learning", "waiting_approval", "degraded", "disabled"}),
    "learning": frozenset({"active", "paused", "degraded", "disabled"}),
    "waiting_approval": frozenset({"active", "paused", "degraded", "disabled"}),
    "degraded": frozenset({"active", "paused", "disabled"}),  # cầu dao mở: Owner cho chạy lại sau khi xem lỗi
    "paused": frozenset({"active", "disabled"}),
    "disabled": frozenset({"paused"}),  # bật lại thì về tạm dừng trước, Owner xem rồi mới cho chạy
}
STATE_TEXT = {
    "active": "đang chạy",
    "paused": "tạm dừng",
    "learning": "đang học",
    "waiting_approval": "chờ duyệt",
    "degraded": "gặp lỗi",
    "disabled": "tắt",
}
# Trạng thái không được nhận việc mới / không được gọi công cụ hay AI
BLOCKED = frozenset({"paused", "degraded", "disabled"})


def can(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, frozenset())


async def transition(
    conn: AsyncConnection, agent: str, target: str, actor: str, reason: str = "", request_id: str | None = None
) -> dict[str, str]:
    row = await db.one(
        conn, "SELECT s.state FROM agent_status s JOIN agents a ON a.id = s.agent_id WHERE a.agent_key = :k FOR UPDATE OF s", {"k": agent}
    )
    if row is None:
        raise AppError("AGENT_NOT_FOUND", "Không có agent này.", 404)
    cur = row["state"]
    if cur == target:
        return {"agent_key": agent, "state": cur}
    if not can(cur, target):
        raise AppError("AGENT_STATE", f"Không chuyển được từ “{STATE_TEXT[cur]}” sang “{STATE_TEXT[target]}”.", 409)
    await db.execute(
        conn,
        "UPDATE agent_status s SET state = :st, reason = :r, changed_by = :by, updated_at = now(), "
        "circuit_failures = CASE WHEN CAST(:st AS text) = 'active' THEN 0 ELSE circuit_failures END FROM agents a WHERE a.id = s.agent_id AND a.agent_key = :k",
        {"st": target, "r": reason or None, "by": actor, "k": agent},
    )
    action = {"paused": "agent.pause", "active": "agent.resume", "disabled": "agent.disable"}.get(target, f"agent.state.{target}")
    await audit.record(conn, actor, action, f"agent:{agent}", {"from": cur, "to": target}, reason=reason or None, request_id=request_id)
    return {"agent_key": agent, "state": target}
