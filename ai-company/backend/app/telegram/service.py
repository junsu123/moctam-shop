"""Nghiệp vụ Telegram: kết nối chat bằng mã 6 số, nhận lệnh, gửi thông báo theo giờ yên lặng.

Luồng kết nối (DECISIONS Q-O2): Owner bấm "Tạo mã kết nối" trên trang quản trị → nhắn `/ketnoi 123456`
cho bot (trong chat riêng hoặc nhóm) → worker kiểm mã (băm, 10 phút, dùng một lần) → chat vào danh sách trắng.
Tin từ chat ngoài danh sách bị bỏ qua và ghi nhật ký, không trả lời (tránh lộ bot cho người lạ).

Sprint 4b: nút có chữ ký dưới tin (Duyệt / Từ chối / Gỡ bài / Góp ý, xem app.telegram.buttons), lệnh /tamdung xuatban,
/tieptuc xuatban; tin nhắn ngay sau khi bấm Góp ý (hoặc Từ chối) được ghi thành góp ý.
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
from app.core.errors import AppError
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


async def handle_callback(conn: AsyncConnection, token: str, cq: dict[str, Any]) -> str:
    """Owner bấm nút dưới tin (Duyệt / Từ chối / Gỡ bài / Góp ý). Trả nhãn kết quả (để kiểm thử)."""
    from app.content import publishing
    from app.domain import approvals
    from app.telegram import buttons

    msg = cq.get("message") or {}
    chat_id = int((msg.get("chat") or {}).get("id") or 0)
    cid = str(cq.get("id") or "")
    b, why = await buttons.claim(conn, str(cq.get("data") or ""), chat_id)
    if b is None:
        await _answer(token, cid, why)
        return "rejected"
    actor = f"telegram:{chat_id}"
    result = ""
    try:
        if b["action"] in ("approve", "reject"):
            a = await db.one(
                conn, "SELECT id, payload_digest, risk, status FROM approvals WHERE id = CAST(:i AS uuid)", {"i": b["subject_id"]}
            )
            if a is None or a["payload_digest"] != b["digest"]:
                result = "Nội dung đã thay đổi sau khi gửi nút: không duyệt được. Mở trang Phê duyệt để xem bản mới."
            elif a["risk"] == "high":
                result = "Việc rủi ro cao chỉ duyệt được trên trang quản trị."
            else:
                ok = b["action"] == "approve"
                await approvals.decide(conn, b["subject_id"], ok, actor, "Duyệt qua Telegram" if ok else "Từ chối qua Telegram")
                result = "Đã duyệt." if ok else "Đã từ chối. Bấm trả lời tin này nếu muốn ghi góp ý."
                if not ok:
                    await _prompt(conn, chat_id, "approval_note", b["subject_id"])
        elif b["action"] == "unpublish":
            await publishing.unpublish(conn, b["subject_id"], actor=actor, reason="Owner bấm Gỡ bài trên Telegram")
            result = "Đã gỡ bài khỏi website."
        elif b["action"] == "feedback":
            await _prompt(conn, chat_id, "publish_feedback", b["subject_id"])
            result = "Nhắn góp ý cho bài này (trong 30 phút). Agent sẽ ghi nhớ cho lần sau."
    except AppError as e:
        result = e.message
    await buttons.finish(conn, b, result)
    await _answer(token, cid, result)
    if b["action"] != "feedback":
        await _reply(token, chat_id, result)
        if msg.get("message_id"):
            try:
                await bot.clear_buttons(token, chat_id, int(msg["message_id"]))
            except bot.TelegramError as e:
                log.info("Không gỡ được nút cũ: %s", e.code)
    else:
        await _reply(token, chat_id, result)
    await audit.record(
        conn, actor, "telegram.button", f"{b['subject_type']}:{b['subject_id']}", {"action": b["action"], "result": result[:200]}
    )
    return b["action"] if result.startswith(("Đã", "Nhắn")) else "refused"


async def _answer(token: str, callback_id: str, text: str) -> None:
    if not callback_id:
        return
    try:
        await bot.answer_callback(token, callback_id, text)
    except bot.TelegramError as e:
        log.info("answerCallbackQuery lỗi %s", e.code)


async def _prompt(conn: AsyncConnection, chat_id: int, kind: str, subject_id: str) -> None:
    from app.telegram.buttons import PROMPT_TTL

    await db.execute(
        conn,
        "INSERT INTO telegram_prompts(chat_id, kind, subject_type, subject_id, expires_at) VALUES (:c, :k, :st, :s, :e) "
        "ON CONFLICT (chat_id) DO UPDATE SET kind = EXCLUDED.kind, subject_type = EXCLUDED.subject_type, subject_id = EXCLUDED.subject_id, "
        "expires_at = EXCLUDED.expires_at, created_at = now()",
        {
            "c": chat_id,
            "k": kind,
            "st": "publish" if kind == "publish_feedback" else "approval",
            "s": subject_id,
            "e": datetime.now(UTC) + PROMPT_TTL,
        },
    )


async def _command(conn: AsyncConnection, token: str, chat_id: int, text: str) -> bool:
    """Lệnh của chat đã kết nối. Trả True nếu đã xử lý."""
    from app.content import publishing

    can = bool(await db.scalar(conn, "SELECT can_approve FROM telegram_chats WHERE chat_id = :c", {"c": chat_id}))
    t = re.sub(r"@\w+", "", text).strip().lower()
    if t in ("/trangthai", "/status"):
        n = await db.scalar(conn, "SELECT count(*) FROM agent_status WHERE state = 'active'")
        s = await publishing.settings(conn)
        await _reply(
            token,
            chat_id,
            f"Hệ thống đang chạy. {n} agent hoạt động. Lịch đăng: giai đoạn {s.phase}" + (", ĐANG TẠM DỪNG." if s.paused else "."),
        )
        return True
    if t in ("/tamdung xuatban", "/tieptuc xuatban"):
        if not can:
            await _reply(token, chat_id, "Chat này không có quyền điều khiển xuất bản.")
            return True
        pause = t.startswith("/tamdung")
        await publishing.set_paused(conn, pause, actor=f"telegram:{chat_id}", reason="lệnh Telegram")
        await _reply(
            token,
            chat_id,
            "Đã tạm dừng tự xuất bản. Bài trong hàng chờ được giữ nguyên; nhắn /tieptuc xuatban để chạy lại."
            if pause
            else "Đã cho tự xuất bản chạy lại theo lịch.",
        )
        return True
    if t.startswith("/"):
        return False
    p = await db.one(conn, "SELECT * FROM telegram_prompts WHERE chat_id = :c AND expires_at > now()", {"c": chat_id})
    if p is None or not can:
        return False
    await db.execute(conn, "DELETE FROM telegram_prompts WHERE chat_id = :c", {"c": chat_id})
    if p["kind"] == "publish_feedback":
        await publishing.feedback(conn, p["subject_id"], actor=f"telegram:{chat_id}", text=text[:2000])
    else:
        await db.execute(
            conn,
            "UPDATE approvals SET decision_note = :n WHERE id = CAST(:i AS uuid) AND status = 'rejected'",
            {"n": text[:2000], "i": p["subject_id"]},
        )
        await audit.record(conn, f"telegram:{chat_id}", "approval.note", f"approval:{p['subject_id']}", {"note": text[:300]})
    await _reply(token, chat_id, "Đã ghi góp ý. Agent sẽ nhớ cho những lần sau.")
    return True


async def handle_update(conn: AsyncConnection, token: str, upd: dict[str, Any], seen_unknown: set[int] | None = None) -> str:
    """Xử lý một update. Trả về nhãn kết quả (để kiểm thử): linked / bad_code / ignored / known / skip / hành động nút."""
    if upd.get("callback_query"):
        cq = upd["callback_query"]
        chat_id = int(((cq.get("message") or {}).get("chat") or {}).get("id") or 0)
        if not await db.scalar(conn, "SELECT enabled FROM telegram_chats WHERE chat_id = :c", {"c": chat_id}):
            await audit.record(conn, "telegram", "telegram.ignored", f"telegram_chat:{chat_id}", {"callback": True})
            return "ignored"
        return await handle_callback(conn, token, cq)
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
    if text and await _command(conn, token, chat_id, text):
        return "command"
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
        "SELECT id, kind, text, urgent, attempts, buttons FROM notifications WHERE status = 'queued' "
        "ORDER BY urgent DESC, id LIMIT 20 FOR UPDATE SKIP LOCKED",
    )
    for n in rows:
        if quiet and not n["urgent"]:
            out["held"] += 1
            continue
        chats = await db.all_(
            conn,
            "SELECT c.chat_id, c.can_approve FROM telegram_chats c WHERE c.enabled AND :k = ANY(c.receives) "
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
                markup = None
                if n["buttons"] and c["can_approve"]:  # nút chỉ gửi cho chat có quyền duyệt; mỗi chat mã riêng
                    from app.telegram import buttons

                    markup = await buttons.keyboard(conn, int(c["chat_id"]), list(n["buttons"]))
                await bot.send(token, int(c["chat_id"]), str(n["text"]), markup)
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
