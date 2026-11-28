"""Hàng đợi thông báo cho Owner (outbox). Telegram worker đọc và gửi; máy mất mạng thì gửi lại sau.

Nội dung luôn qua `redact`: không có SĐT, email, khóa API hay token trong tin Telegram (SECURITY_PLAN §3.4).
"""

from __future__ import annotations

import json
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import db
from app.core.logging import redact

Kind = Literal["publish", "report", "alert", "approval", "test"]


async def enqueue(
    conn: AsyncConnection,
    kind: Kind,
    text: str,
    urgent: bool = False,
    dedupe_key: str | None = None,
    buttons: list[dict[str, Any]] | None = None,
) -> int | None:
    """Thêm một thông báo. Trùng `dedupe_key` thì bỏ qua (vd cảnh báo 80% ngân sách chỉ gửi một lần mỗi tháng).

    `buttons`: nút Telegram [{action, text, subject_type, subject_id, digest}], chỉ gửi cho chat có quyền duyệt; mỗi nút
    được ký và dùng một lần (app.telegram.buttons)."""
    nid = await db.scalar(
        conn,
        "INSERT INTO notifications(kind, text, urgent, dedupe_key, buttons) VALUES (:k, :t, :u, :d, CAST(:b AS jsonb)) "
        "ON CONFLICT (dedupe_key) DO NOTHING RETURNING id",
        {
            "k": kind,
            "t": redact(text)[:3500],
            "u": urgent,
            "d": dedupe_key,
            "b": json.dumps(buttons, ensure_ascii=False) if buttons else None,
        },
    )
    return int(nid) if nid is not None else None
