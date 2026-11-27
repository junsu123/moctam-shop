"""Worker trí nhớ: `python -m app.workers.memory`. Mỗi phút nhúng vector cho các mục trí nhớ mới (tối đa 256 mục mỗi lượt).

Chưa có khóa OpenAI thì chỉ chờ (trí nhớ vẫn tìm được theo từ khóa). Lỗi không làm worker chết. RAM đo được khoảng 90 MB (giới hạn 128 MB trong compose).
"""

from __future__ import annotations

import asyncio
import logging
import signal

from app.core import db
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.memory.embedding import embed_pending

log = logging.getLogger("aico.memory.worker")
EVERY_S = 60


async def tick() -> str:
    async with db.engine().begin() as conn:
        rep = await embed_pending(conn, limit=256)
    if rep.embedded:
        log.info("Đã nhúng %d mục trí nhớ (%s), còn %d", rep.embedded, rep.model, rep.remaining)
    return rep.status


async def main() -> None:
    setup_logging(get_settings().log_level)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    log.info("Memory worker bắt đầu")
    while not stop.is_set():
        try:
            await tick()
        except Exception as e:  # noqa: BLE001 — một lỗi không được làm chết worker
            log.warning("Memory worker lỗi %s", type(e).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=EVERY_S)
        except TimeoutError:
            pass
    await db.dispose()


if __name__ == "__main__":
    asyncio.run(main())
