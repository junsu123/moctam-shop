"""Mật khẩu (Argon2id), TOTP 2FA, phiên đăng nhập, CSRF, khóa tạm khi sai nhiều lần (SECURITY_PLAN §2.1)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pyotp
import segno
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import db
from app.core.errors import AppError

SESSION_COOKIE = "aico_session"
SESSION_TTL = timedelta(hours=12)
IDLE_TTL = timedelta(hours=2)
REAUTH_TTL = timedelta(minutes=5)
MAX_FAILS = 5
LOCK_FOR = timedelta(minutes=15)
MIN_PASSWORD = 10

_ph = PasswordHasher()  # Argon2id, tham số mặc định của thư viện


def hash_password(pw: str) -> str:
    if len(pw) < MIN_PASSWORD:
        raise AppError("WEAK_PASSWORD", f"Mật khẩu cần ít nhất {MIN_PASSWORD} ký tự.", 422)
    return _ph.hash(pw)


def check_password(stored: str, pw: str) -> bool:
    try:
        return _ph.verify(stored, pw)
    except (VerificationError, InvalidHashError):
        return False


_DUMMY: str | None = None


def dummy_check(pw: str) -> None:
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = _ph.hash(secrets.token_hex(16))
    check_password(_DUMMY, pw)


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="AI Marketing Company")


def totp_qr_svg(uri: str) -> str:
    return str(segno.make(uri, error="m").svg_inline(scale=5, dark="#1E2B24", light="#FFFFFF"))


def check_totp(secret: str, code: str) -> bool:
    code = "".join(ch for ch in code if ch.isdigit())
    return len(code) == 6 and pyotp.TOTP(secret).verify(code, valid_window=1)


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


@dataclass
class Current:
    user_id: str
    email: str
    display_name: str
    role: str
    session_id: str
    csrf: str
    reauth_until: datetime | None

    @property
    def actor(self) -> str:
        return f"user:{self.email}"


async def create_session(conn: AsyncConnection, user_id: str, user_agent: str | None) -> tuple[str, str]:
    from app.core.ids import uuid7

    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    await db.execute(
        conn,
        "INSERT INTO user_sessions(id, user_id, token_hash, csrf_token, expires_at, user_agent) VALUES (:id, :uid, :th, :csrf, :exp, :ua)",
        {
            "id": uuid7(),
            "uid": user_id,
            "th": sha(token),
            "csrf": csrf,
            "exp": datetime.now(UTC) + SESSION_TTL,
            "ua": (user_agent or "")[:200],
        },
    )
    return token, csrf


async def _load(conn: AsyncConnection, request: Request) -> Current | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    r = await db.one(
        conn,
        "SELECT s.id, s.csrf_token, s.reauth_until, s.last_seen_at, s.expires_at, u.id AS uid, u.email, u.display_name, u.role, u.status "
        "FROM user_sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = :th AND s.revoked_at IS NULL",
        {"th": sha(token)},
    )
    now = datetime.now(UTC)
    if r is None or r["status"] != "active" or r["expires_at"] < now or r["last_seen_at"] + IDLE_TTL < now:
        return None
    await db.execute(conn, "UPDATE user_sessions SET last_seen_at = now() WHERE id = :id", {"id": r["id"]})
    return Current(str(r["uid"]), r["email"], r["display_name"], r["role"], str(r["id"]), r["csrf_token"], r["reauth_until"])


async def current_user(request: Request, conn: AsyncConnection = Depends(db.get_db)) -> Current:
    cur = await _load(conn, request)
    if cur is None:
        raise AppError("UNAUTHENTICATED", "Cần đăng nhập.", 401)
    # CSRF: mọi thao tác thay đổi dữ liệu phải kèm X-CSRF-Token khớp phiên (cookie SameSite=Strict là lớp thứ hai)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        sent = request.headers.get("x-csrf-token", "")
        if not sent or not same(sent, cur.csrf):
            raise AppError("CSRF_FAILED", "Phiên làm việc không hợp lệ, hãy tải lại trang.", 403)
    request.state.actor = cur.actor
    return cur


def require_role(*roles: str) -> Any:
    async def dep(cur: Current = Depends(current_user)) -> Current:
        if cur.role not in roles:
            raise AppError("FORBIDDEN", "Không có quyền.", 403)
        return cur

    return dep


async def recent_auth(cur: Current = Depends(current_user)) -> Current:
    """Thao tác nhạy cảm (đổi token Telegram, khóa API, thêm chat được duyệt) cần vừa nhập lại mật khẩu + mã 2FA."""
    if cur.reauth_until is None or cur.reauth_until < datetime.now(UTC):
        raise AppError("REAUTH_REQUIRED", "Thao tác này cần nhập lại mật khẩu và mã xác thực.", 403)
    return cur
