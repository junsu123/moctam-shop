"""Nghiệp vụ Telegram: kết nối chat bằng mã 6 số, nhận lệnh, gửi thông báo theo giờ yên lặng.

Luồng kết nối (DECISIONS Q-O2): Owner bấm "Tạo mã kết nối" trên trang quản trị → nhắn `/ketnoi 123456`
cho bot (trong chat riêng hoặc nhóm) → worker kiểm mã (băm, 10 phút, dùng một lần) → chat vào danh sách trắng.
Tin từ chat ngoài danh sách bị bỏ qua và ghi nhật ký, không trả lời (tránh lộ bot cho người lạ).
"""

from __future__ import annotations

import logging
import re
import secrets
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import audit, db, security
from app.domain import store
from app.telegram import bot

log = logging.getLogger("aico.telegram")
VN = ZoneInfo("Asia/Ho_Chi_Minh")
TOKEN_SECRET = "telegram.bot_token"  # noqa: S105 — tên khóa trong kho secret, không phải giá trị
LINK_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
LINK_RE = re.compile(r"^/(?:ketnoi|start)(?:@\w+)?\s+(\d{6})\s*$")


async def new_link_code(conn: AsyncConnection, actor: str, can_approve: bool) -> tuple[str, datetime]:
    code = f"{secrets.randbelow(1_000_000):06d}"
    exp = datetime.now(UTC) + LINK_TTL
    await db.execute(
        conn,
        "INSERT INTO telegram_link_codes(code_hash, requested_by, can_approve, expires_at) VALUES (:h, :a, :c, :e)",
        {"h": security.sha("tg:" + code), "a": actor, "c": can_approve, "e": exp},
    )
    return code, exp


def in_quiet(now: datetime, hours: store.Hours) -> bool:
    t = now.astimezone(VN).time()
    qs, qe = time.fromisoformat(hours.quiet_start), time.fromisoformat(hours.quiet_end)
    if qs == qe:
        return False
    return qs <= t < qe if qs < qe else (t >= qs or t < qe)


async def _reply(token: str, chat_id: int, text: str) -> None:
    try:
        await bot.send(token, chat_id, text)
    except bot.TelegramError as e:
        log.warning("Không trả lời được chat Telegram: %s", e.code)


async def handle_update(conn: AsyncConnection, token: str, upd: dict[str, Any], seen_unknown: set[int] | None = None) -> str:
    """Xử lý một update. Trả về nhãn kết quả (để kiểm thử): linked / bad_code / ignored / known / skip."""
    msg = upd.get("message") or {}
    chat = msg.get("chat") or {}
    if "id" not in chat:
        return "skip"
    chat_id = int(chat["id"])
    title = str(
        chat.get("title") or " ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x) or chat.get("username") or chat_id
    )
    text = str(msg.get("text") or "").strip()
    m = LINK_RE.match(text)
    if m:
        code_hash = security.sha("tg:" + m.group(1))
        row = await db.one(
            conn,
            "UPDATE telegram_link_codes SET used_at = now(), used_chat_id = :c "
            "WHERE code_hash = :h AND used_at IS NULL AND expires_at > now() RETURNING requested_by, can_approve",
            {"c": chat_id, "h": code_hash},
        )
        if row is None:
            await audit.record(conn, "telegram", "telegram.link_failed", f"telegram_chat:{chat_id}")
            await _reply(token, chat_id, "Mã kết nối không đúng hoặc đã hết hạn. Tạo mã mới trong trang quản trị (Cài đặt → Telegram).")
            return "bad_code"
        await db.execute(
            conn,
            "INSERT INTO telegram_chats(chat_id, title, can_approve, added_by) VALUES (:c, :t, :a, :b) "
            "ON CONFLICT (chat_id) DO UPDATE SET title = EXCLUDED.title, can_approve = EXCLUDED.can_approve, enabled = true",
            {"c": chat_id, "t": title[:120], "a": row["can_approve"], "b": row["requested_by"]},
        )
        await audit.record(
            conn,
            row["requested_by"],
            "telegram.chat_linked",
            f"telegram_chat:{chat_id}",
            {"title": title[:120], "can_approve": row["can_approve"]},
        )
        await _reply(
            token,
            chat_id,
            f"Đã kết nối với AI Marketing Company. Chat này sẽ nhận báo cáo{' và được duyệt việc' if row['can_approve'] else ''}.",
        )
        return "linked"
    known = await db.scalar(conn, "SELECT enabled FROM telegram_chats WHERE chat_id = :c", {"c": chat_id})
    if not known:
        # Không trả lời người lạ. Ghi nhật ký một lần mỗi chat mỗi lần chạy worker để không ngập nhật ký.
        if seen_unknown is None or chat_id not in seen_unknown:
            await audit.record(conn, "telegram", "telegram.ignored", f"telegram_chat:{chat_id}", {"title": title[:120]})
            if seen_unknown is not None:
                seen_unknown.add(chat_id)
        return "ignored"
    if text in ("/trangthai", "/status"):
        n = await db.scalar(conn, "SELECT count(*) FROM agent_status WHERE state = 'active'")
        await _reply(token, chat_id, f"Hệ thống đang chạy. {n} agent hoạt động.")
    return "known"


async def dispatch(conn: AsyncConnection, token: str, now: datetime | None = None) -> dict[str, int]:
    """Gửi các thông báo đang chờ. Trong giờ yên lặng chỉ gửi tin khẩn; tin thường để sáng gửi."""
    now = now or datetime.now(UTC)
    hours = await store.get_setting(conn, "hours")
    assert isinstance(hours, store.Hours)
    quiet = in_quiet(now, hours)
    out = {"sent": 0, "held": 0, "failed": 0, "no_recipient": 0}
    rows = await db.all_(
        conn,
        "SELECT id, kind, text, urgent, attempts FROM notifications WHERE status = 'queued' ORDER BY urgent DESC, id LIMIT 20 FOR UPDATE SKIP LOCKED",
    )
    for n in rows:
        if quiet and not n["urgent"]:
            out["held"] += 1
            continue
        chats = await db.all_(
            conn,
            "SELECT c.chat_id FROM telegram_chats c WHERE c.enabled AND :k = ANY(c.receives) "
            "AND NOT EXISTS (SELECT 1 FROM notification_deliveries d WHERE d.notification_id = :id AND d.chat_id = c.chat_id)",
            {"k": n["kind"], "id": n["id"]},
        )
        already = await db.scalar(conn, "SELECT count(*) FROM notification_deliveries WHERE notification_id = :id", {"id": n["id"]})
        if not chats and not already:
            await db.execute(conn, "UPDATE notifications SET status = 'no_recipient' WHERE id = :id", {"id": n["id"]})
            out["no_recipient"] += 1
            continue
        err = None
        for c in chats:
            try:
                await bot.send(token, int(c["chat_id"]), str(n["text"]))
                await db.execute(
                    conn, "INSERT INTO notification_deliveries(notification_id, chat_id) VALUES (:n, :c)", {"n": n["id"], "c": c["chat_id"]}
                )
            except bot.TelegramError as e:
                err = e.code
                log.warning("Gửi Telegram lỗi %s", e.code)
        attempts = int(n["attempts"]) + 1
        if err is None:
            await db.execute(
                conn,
                "UPDATE notifications SET status = 'sent', sent_at = now(), attempts = :a WHERE id = :id",
                {"a": attempts, "id": n["id"]},
            )
            out["sent"] += 1
        else:
            st = "failed" if attempts >= MAX_ATTEMPTS else "queued"
            await db.execute(
                conn,
                "UPDATE notifications SET status = :s, attempts = :a, last_error = :e WHERE id = :id",
                {"s": st, "a": attempts, "e": err, "id": n["id"]},
            )
            out["failed"] += 1
    return out
