"""Telegram Bot API tối giản qua httpx (getMe, sendMessage, getUpdates, answerCallbackQuery, editMessageReplyMarkup).

Không dùng thư viện bot lớn: chỉ cần vài phương thức, ít RAM, dễ giả lập khi kiểm thử (DECISIONS: ghi chú Sprint 1).
Token không bao giờ xuất hiện trong log: lỗi chỉ ghi mã HTTP và mô tả của Telegram đã qua `redact`.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import redact

transport: httpx.AsyncBaseTransport | None = None  # kiểm thử thay bằng MockTransport


class TelegramError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code, self.detail = code, detail


async def call(token: str, method: str, payload: dict[str, Any] | None = None, timeout_s: float = 15) -> Any:
    url = f"{get_settings().telegram_api_base.rstrip('/')}/bot{token}/{method}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s + 10, connect=10), transport=transport) as c:
            r = await c.post(url, json=payload or {})
    except httpx.TimeoutException as e:
        raise TelegramError("TIMEOUT", "Telegram không phản hồi") from e
    except httpx.HTTPError as e:
        raise TelegramError("NETWORK", f"Lỗi mạng khi gọi Telegram: {type(e).__name__}") from e
    try:
        d = r.json()
    except ValueError:
        d = {}
    if r.status_code == 401 or (r.status_code == 404 and method == "getMe"):
        raise TelegramError("TOKEN_INVALID", "Token bot không đúng (Telegram từ chối).")
    if r.status_code == 403:
        raise TelegramError("BLOCKED", "Bot bị chặn hoặc bị xóa khỏi nhóm.")
    if r.status_code == 429:
        raise TelegramError("RATE_LIMITED", "Telegram giới hạn tần suất gửi.")
    if not d.get("ok"):
        raise TelegramError("API_ERROR", f"Telegram lỗi HTTP {r.status_code}: {redact(str(d.get('description', '')))[:200]}")
    return d.get("result")


async def get_me(token: str) -> dict[str, Any]:
    res = await call(token, "getMe")
    return dict(res)


async def send(token: str, chat_id: int, text: str, reply_markup: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": False}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    await call(token, "sendMessage", payload)


async def answer_callback(token: str, callback_id: str, text: str) -> None:
    await call(token, "answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:190]})


async def clear_buttons(token: str, chat_id: int, message_id: int) -> None:
    await call(token, "editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id, "reply_markup": {"inline_keyboard": []}})


async def updates(token: str, offset: int, timeout_s: int = 25) -> list[dict[str, Any]]:
    res = await call(
        token, "getUpdates", {"offset": offset, "timeout": timeout_s, "allowed_updates": ["message", "callback_query"]}, timeout_s=timeout_s
    )
    return list(res or [])
