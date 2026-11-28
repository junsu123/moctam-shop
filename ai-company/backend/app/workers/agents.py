"""Worker agent: `python -m app.workers.agents`. Chạy task của các agent, phát Message Bus, lịch tự động, đối soát.

- Nhận việc bằng lease (`engine.claim`), chạy đồ thị LangGraph (`graph.execute`), tối đa `AICO_WORKER_CONCURRENCY` việc song song.
- Đánh thức bằng Redis (`aico:tasks:wake`); mất Redis vẫn chạy nhờ quét bảng mỗi 3 giây.
- Một việc lỗi không làm chết worker; chết giữa chừng thì worker khác (hoặc chính nó sau khi bật lại) chạy tiếp từ checkpoint.
RAM: xem docs/progress/sprint-4.md (đo bằng `ps` khi chạy E2E).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import socket
import time

from app.core import db
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.tasks import bus, engine, graph, hooks, reconcile, scheduler  # noqa: F401 — hooks: đăng ký xử lý phê duyệt

log = logging.getLogger("aico.worker")
POLL_S = 3.0


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


async def housekeeping() -> None:
    await bus.dispatch()
    async with db.engine().begin() as c:
        await scheduler.tick(c)
        await engine.promote(c)


async def claim(wid: str, n: int) -> list[dict[str, object]]:
    if n <= 0:
        return []
    async with db.engine().begin() as c:
        return await engine.claim(c, wid, n)


async def drain(wid: str | None = None, max_rounds: int = 50) -> int:
    """Chạy tuần tự tới khi không còn việc nào làm được ngay (dùng cho kiểm thử và lệnh `app.cli run-once`)."""
    wid = wid or worker_id()
    done = 0
    for _ in range(max_rounds):
        await housekeeping()
        ts = await claim(wid, 1)
        if not ts:
            await bus.dispatch()
            async with db.engine().begin() as c:
                await engine.promote(c)
            ts = await claim(wid, 1)
            if not ts:
                break
        for t in ts:
            await graph.execute(t, wid)
            done += 1
    return done


async def main() -> None:
    s = get_settings()
    setup_logging(s.log_level)
    wid = worker_id()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    await graph.setup()
    from redis.asyncio import Redis

    r = Redis.from_url(s.redis_url)
    running: set[asyncio.Task[str]] = set()
    last_reconcile = 0.0
    log.info("Worker %s bắt đầu, chạy song song tối đa %d việc", wid, s.worker_concurrency)
    while not stop.is_set():
        try:
            await housekeeping()
            if time.monotonic() - last_reconcile > reconcile.EVERY_S:
                rep = await reconcile.run()
                last_reconcile = time.monotonic()
                if rep.requeued or rep.timed_out:
                    log.info("Đối soát: nhận lại %d, quá giờ %d", len(rep.requeued), len(rep.timed_out))
            for t in await claim(wid, s.worker_concurrency - len(running)):
                job = asyncio.create_task(graph.execute(t, wid))
                running.add(job)
                job.add_done_callback(running.discard)
        except Exception as e:  # noqa: BLE001 — vòng lặp chính không được chết
            log.warning("Worker lỗi %s", type(e).__name__)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(r.blpop(["aico:tasks:wake"], timeout=POLL_S), timeout=POLL_S + 1)
    log.info("Worker dừng, chờ %d việc đang chạy lưu checkpoint", len(running))
    if running:
        await asyncio.wait(running, timeout=30)
    await graph.close()
    await r.aclose()
    await db.dispose()


if __name__ == "__main__":
    asyncio.run(main())
