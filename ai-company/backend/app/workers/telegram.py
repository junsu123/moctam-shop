"""Worker Telegram: `python -m app.workers.telegram`.

Vòng lặp: long-poll getUpdates (25 giây) → xử lý lệnh/mã kết nối → gửi thông báo đang chờ.
Chưa có token thì ngủ 30 giây rồi kiểm lại (Owner nhập token trong trang quản trị, không cần khởi động lại).
Lỗi mạng không làm worker chết: chờ lùi dần tối đa 5 phút. RAM khoảng 60 MB.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from app.core import db
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.domain import store
from app.telegram import bot, service

log = logging.getLogger("aico.telegram.worker")
OFFSET_KEY = "telegram_offset"


async def _token() -> str | None:
    async with db.engine().begin() as c:
        return await store.get_secret(c, service.TOKEN_SECRET)


async def tick(token: str, seen_unknown: set[int], poll_s: int = 25) -> None:
    async with db.engine().begin() as c:
        offset = int(await db.scalar(c, "SELECT value FROM system_meta WHERE key = :k", {"k": OFFSET_KEY}) or 0)
    ups = await bot.updates(token, offset, poll_s)
    for u in ups:
        async with db.engine().begin() as c:
            await service.handle_update(c, token, u, seen_unknown)
            await db.execute(
                c,
                "INSERT INTO system_meta(key, value) VALUES (:k, :v) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
                {"k": OFFSET_KEY, "v": str(int(u["update_id"]) + 1)},
            )
    async with db.engine().begin() as c:
        await service.dispatch(c, token)


async def main() -> None:
    setup_logging(get_settings().log_level)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    backoff = 1.0
    seen: set[int] = set()
    log.info("Telegram worker bắt đầu")
    while not stop.is_set():
        try:
            token = await _token()
            if not token:
                await asyncio.wait_for(stop.wait(), timeout=30)
                continue
            await tick(token, seen)
            backoff = 1.0
        except TimeoutError:
            continue
        except Exception as e:  # noqa: BLE001 — một lỗi không được làm chết worker
            log.warning("Telegram worker lỗi %s; thử lại sau %.0f giây", type(e).__name__, backoff)
            try:
                await asyncio.wait_for(stop.wait(), timeout=backoff)
            except TimeoutError:
                pass
            backoff = min(backoff * 2, 300)
    await db.dispose()
    log.info("Telegram worker dừng")


if __name__ == "__main__":
    asyncio.run(main())
