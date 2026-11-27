"""Lệnh quản trị chạy trong container: `python -m app.cli setup-token` | `verify-audit`."""

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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.cli")
    p.add_argument("command", choices=["setup-token", "verify-audit"])
    a = p.parse_args(argv)
    return asyncio.run(_setup_token() if a.command == "setup-token" else _verify_audit())


if __name__ == "__main__":
    sys.exit(main())
