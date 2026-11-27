"""Hàng chờ phê duyệt chung (SECURITY_PLAN §3.2): công cụ, bộ não, quyền…

- Mỗi phê duyệt gắn với **digest của nội dung** cụ thể; nội dung đổi thì phê duyệt cũ không dùng được.
- Có hạn (mặc định 72 giờ, lấy từ hiến pháp). Hết hạn là tự hủy: im lặng không phải đồng ý.
- Rủi ro cao (đổi quyền, thăng hạng bộ não, tiêu tiền…) chỉ duyệt trên dashboard sau khi xác thực lại.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import audit, db
from app.core.errors import AppError
from app.core.ids import uuid7
from app.domain import notify

DEFAULT_TTL_H = 72
Handler = Callable[[AsyncConnection, dict[str, Any], str], Awaitable[None]]
ON_APPROVE: dict[str, Handler] = {}
ON_REJECT: dict[str, Handler] = {}


def digest(payload: Any) -> str:
    from app.brain.loader import digest as _d

    return _d(payload)


async def create(
    conn: AsyncConnection,
    *,
    subject_type: str,
    subject_id: str,
    action: str,
    title: str,
    summary: str = "",
    payload: dict[str, Any],
    risk: str,
    requested_by: str,
    ttl_hours: int = DEFAULT_TTL_H,
) -> dict[str, Any]:
    """Tạo yêu cầu duyệt; nếu đã có yêu cầu đang chờ cho đúng nội dung này thì trả lại yêu cầu đó."""
    await expire_due(conn)
    dg = digest(payload)
    old = await db.one(
        conn,
        "SELECT * FROM approvals WHERE subject_type = :t AND subject_id = :s AND payload_digest = :d AND status = 'pending'",
        {"t": subject_type, "s": subject_id, "d": dg},
    )
    if old:
        return dict(old)
    aid = uuid7()
    row = await db.one(
        conn,
        "INSERT INTO approvals(id, subject_type, subject_id, action, title, summary, payload, payload_digest, risk, requested_by, expires_at) "
        "VALUES (:id, :t, :s, :a, :ti, :su, CAST(:p AS jsonb), :d, :r, :by, :e) RETURNING *",
        {
            "id": aid,
            "t": subject_type,
            "s": subject_id,
            "a": action,
            "ti": title[:200],
            "su": summary[:1000],
            "p": _json(payload),
            "d": dg,
            "r": risk,
            "by": requested_by,
            "e": datetime.now(UTC) + timedelta(hours=ttl_hours),
        },
    )
    assert row is not None
    await audit.record(conn, requested_by, "approval.requested", f"approval:{aid}", {"title": title[:200], "risk": risk, "action": action})
    where = "trên trang quản trị (cần xác thực lại)" if risk == "high" else "trên trang quản trị"
    await notify.enqueue(conn, "approval", f"🔔 Cần anh/chị duyệt: {title}. Mở Phê duyệt {where}.", dedupe_key=f"approval:{aid}")
    return dict(row)


def _json(v: Any) -> str:
    from app.brain.loader import canonical

    return canonical(v)


async def expire_due(conn: AsyncConnection) -> int:
    rows = await db.all_(
        conn,
        "UPDATE approvals SET status = 'expired', decided_at = now() WHERE status = 'pending' AND expires_at <= now() RETURNING id, title",
    )
    for r in rows:
        await audit.record(conn, "system", "approval.expired", f"approval:{r['id']}", {"title": r["title"]})
    return len(rows)


async def decide(conn: AsyncConnection, approval_id: str, approve: bool, actor: str, note: str | None = None) -> dict[str, Any]:
    await expire_due(conn)
    row = await db.one(conn, "SELECT * FROM approvals WHERE id = CAST(:i AS uuid) FOR UPDATE", {"i": approval_id})
    if row is None:
        raise AppError("APPROVAL_NOT_FOUND", "Không có yêu cầu duyệt này.", 404)
    if row["status"] != "pending":
        raise AppError("APPROVAL_NOT_PENDING", f"Yêu cầu này đã ở trạng thái {STATUS_TEXT.get(row['status'], row['status'])}.", 409)
    status = "approved" if approve else "rejected"
    upd = await db.one(
        conn,
        "UPDATE approvals SET status = :s, decided_by = :by, decided_at = now(), decision_note = :n WHERE id = :i RETURNING *",
        {"s": status, "by": actor, "n": note or None, "i": row["id"]},
    )
    assert upd is not None
    handler = (ON_APPROVE if approve else ON_REJECT).get(row["subject_type"])
    if handler:
        await handler(conn, dict(upd), actor)
    await audit.record(conn, actor, f"approval.{status}", f"approval:{row['id']}", {"title": row["title"]}, reason=note)
    return dict(upd)


async def usable(conn: AsyncConnection, approval_id: str, subject_type: str, subject_id: str, payload: Any) -> tuple[bool, str]:
    """Phê duyệt còn dùng được cho đúng nội dung này không (UT-POL: hết hạn hoặc digest lệch → không)."""
    row = await db.one(conn, "SELECT * FROM approvals WHERE id = CAST(:i AS uuid)", {"i": approval_id})
    if row is None:
        return False, "không có phê duyệt này"
    if row["subject_type"] != subject_type or row["subject_id"] != subject_id:
        return False, "phê duyệt dành cho việc khác"
    if row["status"] != "approved":
        return False, f"phê duyệt đang ở trạng thái {STATUS_TEXT.get(row['status'], row['status'])}"
    if row["expires_at"] <= datetime.now(UTC):
        return False, "phê duyệt đã hết hạn"
    if row["payload_digest"] != digest(payload):
        return False, "nội dung đã đổi sau khi được duyệt"
    return True, "ok"


STATUS_TEXT = {"pending": "chờ duyệt", "approved": "đã duyệt", "rejected": "đã từ chối", "expired": "hết hạn", "cancelled": "đã hủy"}
