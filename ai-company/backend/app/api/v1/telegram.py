"""Cấu hình Telegram trong trang quản trị: token bot (mã hóa), mã kết nối chat, danh sách chat, gửi thử."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import audit, db, security
from app.core.errors import AppError
from app.domain import notify, store
from app.telegram import bot, service

router = APIRouter(prefix="/telegram", tags=["telegram"])
Owner = Depends(security.require_role("owner", "manager"))
KINDS = {"publish", "report", "alert", "approval", "test"}


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "")


@router.get("")
async def status(conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Depends(security.current_user)) -> dict[str, Any]:
    info = await store.secret_info(conn, service.TOKEN_SECRET)
    meta = await store.get_raw(conn, "telegram") or {}
    chats = await db.all_(
        conn, "SELECT chat_id, title, can_approve, receives, enabled, added_at, added_by FROM telegram_chats ORDER BY added_at"
    )
    return {
        "configured": info is not None,
        "bot_username": meta.get("bot_username") if info else None,
        "token_last4": info["last4"] if info else None,
        "token_updated_at": info["updated_at"] if info else None,
        "chats": [dict(c) for c in chats],
    }


class TokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=100, pattern=r"^\d+:[A-Za-z0-9_-]+$")


@router.put("/token")
async def put_token(
    body: TokenIn, request: Request, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Depends(security.recent_auth)
) -> dict[str, Any]:
    """Kiểm token bằng getMe trước khi lưu; token sai thì không lưu."""
    try:
        me = await bot.get_me(body.token)
    except bot.TelegramError as e:
        raise AppError("TELEGRAM_" + e.code, e.detail, 400) from e
    last4 = await store.put_secret(conn, service.TOKEN_SECRET, body.token, cur.actor)
    await store.put_raw(conn, "telegram", {"bot_username": me.get("username"), "bot_id": me.get("id")}, cur.actor)
    await audit.record(
        conn, cur.actor, "telegram.token_set", "telegram", {"bot": me.get("username"), "last4": last4}, request_id=_rid(request)
    )
    return {"configured": True, "bot_username": me.get("username"), "token_last4": last4}


class LinkIn(BaseModel):
    can_approve: bool = False


@router.post("/link-code")
async def link_code(
    body: LinkIn, request: Request, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner
) -> dict[str, Any]:
    if body.can_approve:
        await security.recent_auth(cur)  # chat được duyệt việc cần xác thực lại
    if await store.secret_info(conn, service.TOKEN_SECRET) is None:
        raise AppError("TELEGRAM_NOT_CONFIGURED", "Chưa nhập token bot Telegram.", 409)
    code, exp = await service.new_link_code(conn, cur.actor, body.can_approve)
    meta = await store.get_raw(conn, "telegram") or {}
    await audit.record(conn, cur.actor, "telegram.link_code", "telegram", {"can_approve": body.can_approve}, request_id=_rid(request))
    return {"code": code, "expires_at": exp, "bot_username": meta.get("bot_username"), "command": f"/ketnoi {code}"}


class ChatPatch(BaseModel):
    enabled: bool | None = None
    can_approve: bool | None = None
    receives: list[str] | None = None


@router.patch("/chats/{chat_id}")
async def patch_chat(
    chat_id: int, body: ChatPatch, request: Request, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner
) -> dict[str, Any]:
    if body.can_approve:
        await security.recent_auth(cur)
    if body.receives is not None and not set(body.receives) <= KINDS:
        raise AppError("VALIDATION_FAILED", "Loại thông báo không hợp lệ.", 422)
    old = await db.one(conn, "SELECT enabled, can_approve, receives FROM telegram_chats WHERE chat_id = :c", {"c": chat_id})
    if old is None:
        raise AppError("CHAT_NOT_FOUND", "Không có chat này.", 404)
    new = {
        "enabled": old["enabled"] if body.enabled is None else body.enabled,
        "can_approve": old["can_approve"] if body.can_approve is None else body.can_approve,
        "receives": list(old["receives"]) if body.receives is None else sorted(set(body.receives)),
    }
    await db.execute(
        conn,
        "UPDATE telegram_chats SET enabled = :enabled, can_approve = :can_approve, receives = :receives WHERE chat_id = :c",
        {**new, "c": chat_id},
    )
    await audit.record(
        conn,
        cur.actor,
        "telegram.chat_updated",
        f"telegram_chat:{chat_id}",
        {"from": {**dict(old), "receives": list(old["receives"])}, "to": new},
        request_id=_rid(request),
    )
    return {"chat_id": chat_id, **new}


@router.delete("/chats/{chat_id}")
async def delete_chat(
    chat_id: int, request: Request, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner
) -> dict[str, bool]:
    n = await db.execute(conn, "DELETE FROM telegram_chats WHERE chat_id = :c", {"c": chat_id})
    if not n:
        raise AppError("CHAT_NOT_FOUND", "Không có chat này.", 404)
    await audit.record(conn, cur.actor, "telegram.chat_removed", f"telegram_chat:{chat_id}", request_id=_rid(request))
    return {"ok": True}


@router.post("/test")
async def send_test(request: Request, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Owner) -> dict[str, Any]:
    """Xếp một tin thử (khẩn, để gửi được cả trong giờ yên lặng). Worker gửi trong vài giây."""
    if await store.secret_info(conn, service.TOKEN_SECRET) is None:
        raise AppError("TELEGRAM_NOT_CONFIGURED", "Chưa nhập token bot Telegram.", 409)
    now = datetime.now(service.VN).strftime("%H:%M %d/%m/%Y")
    nid = await notify.enqueue(conn, "test", f"✅ Tin thử từ AI Marketing Company lúc {now}.", urgent=True)
    return {"queued": True, "notification_id": nid}
