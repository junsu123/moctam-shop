"""Lệnh quản trị chạy trong container: `python -m app.cli setup-token` | `verify-audit` | `sync-brains` | `embed-memories`."""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.core import audit, db


async def _setup_token() -> int:
    from app.api.v1.auth import SETUP_TTL, issue_setup_token

    async with db.engine().begin() as conn:
        code = await issue_setup_token(conn)
    await db.dispose()
    if code is None:
        print("Đã có tài khoản Owner. Không cần mã thiết lập.")
        return 1
    print(f"Mã thiết lập: {code}  (dùng một lần, hết hạn sau {int(SETUP_TTL.total_seconds() // 60)} phút)")
    print("Mở http://127.0.0.1:3000/thiet-lap và nhập mã này.")
    return 0


async def _verify_audit() -> int:
    async with db.engine().connect() as conn:
        rep = await audit.verify_chain(conn)
    await db.dispose()
    if rep.ok:
        print(f"Nhật ký kiểm toán nguyên vẹn ({rep.checked} dòng).")
        return 0
    print(f"CẢNH BÁO: nhật ký bị sửa từ dòng #{rep.first_bad_id}.")
    return 2


async def _sync_brains() -> int:
    from app.brain import registry
    from app.core.config import get_settings
    from app.tools.gateway import sync_registry

    root = get_settings().brains_dir
    async with db.engine().begin() as conn:
        n = await sync_registry(conn)
        items = await registry.sync_all(conn, root, "system:startup")
    await db.dispose()
    print(f"Công cụ: {n}. Bộ não ({root}):")
    for i in items:
        print(f"  {i.agent_key:<20} {i.status:<12} {i.detail}")
    return 1 if any(i.status == "error" for i in items) else 0


async def _embed_memories() -> int:
    from app.memory.embedding import embed_pending

    async with db.engine().begin() as conn:
        rep = await embed_pending(conn, limit=10_000)
    await db.dispose()
    print(f"Nhúng trí nhớ: {rep.status}, đã nhúng {rep.embedded}, còn {rep.remaining} ({rep.model or 'chưa có model'}). {rep.detail}")
    return 0 if rep.status in ("done", "not_configured") else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.cli")
    p.add_argument("command", choices=["setup-token", "verify-audit", "sync-brains", "embed-memories"])
    a = p.parse_args(argv)
    run = {"setup-token": _setup_token, "verify-audit": _verify_audit, "sync-brains": _sync_brains, "embed-memories": _embed_memories}[
        a.command
    ]
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
