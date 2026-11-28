"""Message Bus (SRS §6.1, AGENT_DESIGN §5): bảng `agent_messages` là outbox.

- `send` ghi message trong CÙNG giao dịch với thay đổi gây ra nó (task, kết quả…): giao dịch rollback thì message cũng mất.
- `dispatch` phát message đang chờ, giao **ít nhất một lần** (thất bại thì thử lại có giãn cách). Phía nhận bỏ qua bản trùng
  nhờ khóa chống trùng của chính tác động (vd task con có id định trước, ứng viên kiến thức gắn `source_message_id`).
- `knowledge_sharing` chỉ vào hộp ứng viên `knowledge_candidates`, KHÔNG ghi thẳng vào trí nhớ của ai (BRAIN_SPEC §7.2).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import db
from app.core.errors import AppError
from app.core.ids import uuid7
from app.domain import notify
from app.domain.approvals import _json

log = logging.getLogger("aico.bus")
TYPES = (
    "task_request",
    "task_response",
    "knowledge_sharing",
    "research_result",
    "review_request",
    "approval_request",
    "error_report",
    "performance_report",
)
MAX_ATTEMPTS = 8


async def send(
    conn: AsyncConnection,
    message_type: str,
    *,
    sender: str,
    receiver: str,
    payload: dict[str, Any],
    key: str,
    task_id: str | None = None,
    correlation_id: str | None = None,
    conversation_id: str | None = None,
    priority: int = 2,
    trust: str = "internal",
    expires_in: timedelta | None = None,
) -> str:
    """Ghi message vào outbox. Cùng `key` thì không tạo message thứ hai (trả id cũ)."""
    if message_type not in TYPES:
        raise AppError("MESSAGE_TYPE_INVALID", f"Loại message không hợp lệ: {message_type}.", 422)
    mid = uuid7()
    row = await db.one(
        conn,
        "INSERT INTO agent_messages(id, message_type, sender, receiver, task_id, conversation_id, correlation_id, priority, payload, trust, "
        "idempotency_key, expires_at) VALUES (:id, :t, :s, :r, CAST(:task AS uuid), CAST(:conv AS uuid), CAST(:corr AS uuid), :p, "
        "CAST(:pl AS jsonb), :tr, :k, :e) ON CONFLICT (idempotency_key) DO NOTHING RETURNING id",
        {
            "id": mid,
            "t": message_type,
            "s": sender,
            "r": receiver,
            "task": task_id,
            "conv": conversation_id,
            "corr": correlation_id,
            "p": priority,
            "pl": _json(payload),
            "tr": trust,
            "k": key,
            "e": datetime.now(UTC) + expires_in if expires_in else None,
        },
    )
    if row is None:
        return str(await db.scalar(conn, "SELECT id FROM agent_messages WHERE idempotency_key = :k", {"k": key}))
    return str(row["id"])


# ------------------------------------------------------------------ phía nhận
async def _on_task_request(conn: AsyncConnection, m: dict[str, Any]) -> None:
    from app.tasks import engine

    p = m["payload"]
    deadline = datetime.fromisoformat(p["deadline"]) if p.get("deadline") else None
    await engine.create(
        conn,
        task_id=p["task_id"],  # id định trước: giao lại message không tạo task thứ hai
        idempotency_key=f"msg:{m['id']}",
        title=p["title"],
        description=p.get("description", ""),
        task_type=p.get("task_type", "generic"),
        created_by=m["sender"],
        assigned_agent=m["receiver"].removeprefix("agent:"),
        priority=int(p.get("priority", 2)),
        deadline=deadline,
        input_data=p.get("input", {}),
        success_criteria=p.get("success_criteria", []),
        requires_review=bool(p.get("requires_review", False)),
        reviewer=p.get("reviewer"),
        requires_approval=bool(p.get("requires_approval", False)),
        autonomy_max=int(p.get("autonomy_max", 2)),
        budget_usd=float(p.get("budget_usd", 0)),
        parent_id=str(m["task_id"]) if m["task_id"] else None,
    )


async def _on_review_request(conn: AsyncConnection, m: dict[str, Any]) -> None:
    """Review của agent cấp trên: tạo task loại `review` cho người review; kết quả quay về task gốc (`runtime.finish_review`)."""
    from app.tasks import engine

    p = m["payload"]
    if not m["receiver"].startswith("agent:"):
        return  # Owner review trên dashboard: task đã ở WAITING_REVIEW, không cần tạo gì thêm
    await engine.create(
        conn,
        idempotency_key=f"msg:{m['id']}",
        title=f"Review: {p['title']}"[:300],
        description="Review đầu ra của cấp dưới theo tiêu chí thành công và rubric.",
        task_type="review",
        created_by="system:bus",
        assigned_agent=m["receiver"].removeprefix("agent:"),
        priority=1,
        input_data={"subject_task_id": p["task_id"], "round": p["round"], "output": p["output"], "criteria": p.get("criteria", [])},
        success_criteria=[{"type": "field_in", "field": "verdict", "values": ["approve", "request_changes", "reject"]}],
        autonomy_max=2,
        budget_usd=float(p.get("budget_usd", 0.1)),
        timeout_s=900,
    )


async def _on_knowledge(conn: AsyncConnection, m: dict[str, Any]) -> None:
    p = m["payload"]
    await db.execute(
        conn,
        "INSERT INTO knowledge_candidates(id, proposed_by, target_scope, title, claim, evidence, trust, source_message_id) "
        "VALUES (:id, :by, :sc, :ti, :cl, CAST(:ev AS jsonb), :tr, :m) ON CONFLICT (source_message_id) DO NOTHING",
        {
            "id": uuid7(),
            "by": m["sender"],
            "sc": p.get("target_scope", "company"),
            "ti": str(p.get("title", ""))[:200],
            "cl": str(p.get("claim", ""))[:4000],
            "ev": _json(p.get("evidence", [])),
            "tr": "untrusted" if m["trust"] == "untrusted" else "internal",
            "m": m["id"],
        },
    )


async def _on_error(conn: AsyncConnection, m: dict[str, Any]) -> None:
    p = m["payload"]
    if m["receiver"] == "owner":
        await notify.enqueue(
            conn, "alert", f"⚠️ Việc lỗi, đã hết lượt thử: {p.get('title', '')} ({p.get('code', '')})", dedupe_key=f"msg:{m['id']}"
        )


async def _noop(conn: AsyncConnection, m: dict[str, Any]) -> None:
    """task_response, research_result, performance_report: lưu trong hộp thư của người nhận (chính bảng này) để truy hồi."""


HANDLERS = {
    "task_request": _on_task_request,
    "review_request": _on_review_request,
    "knowledge_sharing": _on_knowledge,
    "error_report": _on_error,
    "task_response": _noop,
    "research_result": _noop,
    "performance_report": _noop,
    "approval_request": _noop,  # yêu cầu duyệt đã tạo thẳng trong hàng chờ phê duyệt (approvals) khi gửi
}


async def dispatch(limit: int = 50) -> int:
    """Phát các message đang chờ. Mỗi message một giao dịch riêng: lỗi một message không chặn các message khác."""
    done = 0
    for _ in range(limit):
        async with db.engine().begin() as conn:
            row = await db.one(
                conn,
                "SELECT * FROM agent_messages WHERE status = 'queued' AND (not_before IS NULL OR not_before <= now()) "
                "ORDER BY priority, created_at LIMIT 1 FOR UPDATE SKIP LOCKED",
            )
            if row is None:
                break
            m = dict(row)
            if m["expires_at"] and m["expires_at"] < datetime.now(UTC):
                await db.execute(conn, "UPDATE agent_messages SET status = 'expired' WHERE id = :i", {"i": m["id"]})
                continue
            try:
                async with conn.begin_nested():
                    await HANDLERS[m["message_type"]](conn, m)
                await db.execute(
                    conn,
                    "UPDATE agent_messages SET status = 'delivered', delivered_at = now(), attempts = attempts + 1 WHERE id = :i",
                    {"i": m["id"]},
                )
                done += 1
            except Exception as e:  # noqa: BLE001 — một message lỗi không được làm dừng bus
                err = e.message if isinstance(e, AppError) else type(e).__name__
                n = int(m["attempts"]) + 1
                log.warning("Message %s (%s) lỗi: %s", m["id"], m["message_type"], err)
                final = n >= MAX_ATTEMPTS or (isinstance(e, AppError) and e.status < 500 and e.code != "TASK_VERSION_CONFLICT")
                await db.execute(
                    conn,
                    "UPDATE agent_messages SET attempts = :n, last_error = :e, status = :s, not_before = now() + make_interval(secs => :d) "
                    "WHERE id = :i",
                    {"n": n, "e": err[:500], "s": "failed" if final else "queued", "d": min(600, 5 * 2**n), "i": m["id"]},
                )
                if final and m["task_id"]:
                    from app.tasks import engine

                    await engine.log_event(conn, str(m["task_id"]), "message_failed", f"Không giao được {m['message_type']}: {err}")
                    if m["message_type"] == "task_request":  # task con không tạo được: task cha không chờ mãi
                        await db.execute(
                            conn,
                            "DELETE FROM task_dependencies WHERE task_id = :p AND depends_on = CAST(:c AS uuid)",
                            {"p": m["task_id"], "c": m["payload"].get("task_id")},
                        )
                        await engine.promote(conn, str(m["task_id"]))
    return done
