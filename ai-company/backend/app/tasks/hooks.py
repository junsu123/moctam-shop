"""Nối hàng chờ phê duyệt với Task Engine: Owner duyệt/từ chối (hoặc yêu cầu hết hạn) thì task đang chờ được đánh thức.

Đồ thị tự đọc kết quả duyệt từ CSDL khi chạy tiếp (`runtime.resume_value`), nên ở đây chỉ cần đánh thức đúng task.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import db
from app.domain import approvals
from app.tasks import engine


async def _task_of(conn: AsyncConnection, appr: dict[str, Any]) -> str | None:
    if appr["subject_type"] == "task_output":
        return str(appr["subject_id"])
    tid = await db.scalar(conn, "SELECT task_id FROM tool_invocations WHERE idempotency_key = :k", {"k": appr["subject_id"]})
    return str(tid) if tid else None


async def _wake(conn: AsyncConnection, appr: dict[str, Any], actor: str) -> None:
    tid = await _task_of(conn, appr)
    if tid:
        label = {"approved": "đã duyệt", "rejected": "từ chối", "expired": "hết hạn không ai duyệt"}.get(appr["status"], appr["status"])
        await engine.wake(conn, tid, actor=actor, reason=f"yêu cầu duyệt {label}")


for _st in ("tool_call", "task_output"):
    approvals.ON_APPROVE.setdefault(_st, _wake)
    approvals.ON_REJECT.setdefault(_st, _wake)
    approvals.ON_EXPIRE.setdefault(_st, _wake)
