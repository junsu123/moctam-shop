"""Nút bấm Telegram có chữ ký (SECURITY_PLAN §3.4).

Mỗi nút = một mã ngẫu nhiên trong `telegram_buttons`, gắn: hành động + đối tượng + digest nội dung + chat được gửi + hạn dùng.
`callback_data` = "<mã>.<chữ ký>", chữ ký HMAC-SHA256 (khóa suy ra từ AICO_MASTER_KEY) trên toàn bộ các trường đó.
Nút chỉ chạy khi: chat đúng là chat đã nhận nút, chat còn quyền duyệt, chữ ký đúng, chưa hết hạn, chưa dùng (một lần),
và digest còn khớp nội dung hiện tại (nội dung đổi sau khi gửi thì nút vô hiệu).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import audit, db
from app.core.config import get_settings
from app.core.errors import AppError

TTL = timedelta(hours=72)  # bằng hạn của yêu cầu duyệt
PROMPT_TTL = timedelta(minutes=30)


def _key() -> bytes:
    mk = get_settings().master_key
    if mk is None:
        raise AppError("MASTER_KEY_MISSING", "Thiếu AICO_MASTER_KEY.", 500)
    return hashlib.sha256(b"telegram-buttons:" + mk.get_secret_value().encode()).digest()


def _sign(token: str, action: str, subject_type: str, subject_id: str, dg: str, chat_id: int, exp: datetime) -> str:
    msg = f"{token}|{action}|{subject_type}|{subject_id}|{dg}|{chat_id}|{int(exp.timestamp())}".encode()
    return base64.urlsafe_b64encode(hmac.new(_key(), msg, hashlib.sha256).digest())[:22].decode()


async def make(conn: AsyncConnection, chat_id: int, b: dict[str, Any]) -> dict[str, str]:
    """Tạo một nút cho một chat. Trả nút dạng Bot API (`text`, `callback_data` ≤ 64 byte)."""
    token = secrets.token_urlsafe(9)
    exp = (datetime.now(UTC) + TTL).replace(microsecond=0)
    await db.execute(
        conn,
        "INSERT INTO telegram_buttons(token, action, subject_type, subject_id, digest, chat_id, expires_at) VALUES (:t, :a, :st, :si, :d, :c, :e)",
        {"t": token, "a": b["action"], "st": b["subject_type"], "si": b["subject_id"], "d": b["digest"], "c": chat_id, "e": exp},
    )
    return {
        "text": b["text"],
        "callback_data": f"{token}.{_sign(token, b['action'], b['subject_type'], b['subject_id'], b['digest'], chat_id, exp)}",
    }


async def keyboard(conn: AsyncConnection, chat_id: int, buttons: list[dict[str, Any]]) -> dict[str, Any]:
    return {"inline_keyboard": [[await make(conn, chat_id, b) for b in buttons]]}


async def claim(conn: AsyncConnection, data: str, chat_id: int) -> tuple[dict[str, Any] | None, str]:
    """Kiểm và đánh dấu đã dùng. Trả (nút, "") nếu hợp lệ; (None, lý do) nếu không."""
    token, _, sig = data.partition(".")
    row = await db.one(conn, "SELECT * FROM telegram_buttons WHERE token = :t FOR UPDATE", {"t": token})
    if row is None or not sig:
        return None, "Nút không hợp lệ."
    good = _sign(token, row["action"], row["subject_type"], row["subject_id"], row["digest"], int(row["chat_id"]), row["expires_at"])
    if not hmac.compare_digest(good, sig) or int(row["chat_id"]) != chat_id:
        await audit.record(conn, f"telegram:{chat_id}", "telegram.button_forged", f"telegram_button:{token}")
        return None, "Nút không hợp lệ."
    can = await db.scalar(conn, "SELECT enabled AND can_approve FROM telegram_chats WHERE chat_id = :c", {"c": chat_id})
    if not can:
        return None, "Chat này không có quyền duyệt."
    if row["used_at"] is not None:
        return None, "Nút này đã được dùng."
    if row["expires_at"] <= datetime.now(UTC):
        return None, "Nút đã hết hạn."
    await db.execute(conn, "UPDATE telegram_buttons SET used_at = now() WHERE token = :t", {"t": token})
    return dict(row), ""


async def finish(conn: AsyncConnection, b: dict[str, Any], result: str) -> None:
    """Ghi kết quả; các nút cùng đối tượng (gửi cho chat khác, hoặc nút Duyệt/Từ chối còn lại) hết tác dụng."""
    await db.execute(conn, "UPDATE telegram_buttons SET used_result = :r WHERE token = :t", {"r": result[:200], "t": b["token"]})
    acts = ["approve", "reject"] if b["action"] in ("approve", "reject") else [b["action"]]
    await db.execute(
        conn,
        "UPDATE telegram_buttons SET used_at = now(), used_result = 'đã xử lý ở nút khác' WHERE used_at IS NULL "
        "AND subject_type = :st AND subject_id = :si AND action = ANY(:acts)",
        {"st": b["subject_type"], "si": b["subject_id"], "acts": acts},
    )
