"""Đăng nhập Owner: thiết lập lần đầu (mã thiết lập + TOTP bắt buộc), đăng nhập, khóa tạm, xác thực lại, đăng xuất."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import audit, db, security
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.ids import uuid7
from app.domain import store

router = APIRouter(prefix="/auth", tags=["auth"])
SETUP_TTL = timedelta(minutes=30)


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _set_cookie(resp: Response, token: str) -> None:
    resp.set_cookie(
        security.SESSION_COOKIE,
        token,
        max_age=int(security.SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="strict",
        secure=get_settings().cookie_secure,
        path="/",
    )


async def _has_users(conn: AsyncConnection) -> bool:
    return bool(await db.scalar(conn, "SELECT EXISTS (SELECT 1 FROM users)"))


async def issue_setup_token(conn: AsyncConnection) -> str | None:
    """Tạo mã thiết lập dùng một lần (30 phút). Chỉ có khi chưa có tài khoản nào. Gọi từ CLI: python -m app.cli setup-token."""
    if await _has_users(conn):
        return None
    raw = secrets.token_hex(4).upper()
    code = f"{raw[:4]}-{raw[4:]}"
    exp = (datetime.now(UTC) + SETUP_TTL).isoformat()
    await db.execute(
        conn,
        "INSERT INTO system_meta(key, value) VALUES ('setup_token', :v) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
        {"v": f"{security.sha(code)}|{exp}"},
    )
    return code


async def _check_setup_token(conn: AsyncConnection, code: str) -> None:
    v = await db.scalar(conn, "SELECT value FROM system_meta WHERE key = 'setup_token'")
    if not v:
        raise AppError(
            "SETUP_TOKEN_INVALID", "Mã thiết lập không đúng hoặc đã hết hạn. Tạo mã mới bằng scripts\\windows\\khoi-dong.ps1.", 403
        )
    h, exp = str(v).split("|", 1)
    if datetime.fromisoformat(exp) < datetime.now(UTC) or not security.same(h, security.sha(code.strip().upper())):
        raise AppError(
            "SETUP_TOKEN_INVALID", "Mã thiết lập không đúng hoặc đã hết hạn. Tạo mã mới bằng scripts\\windows\\khoi-dong.ps1.", 403
        )


class StateOut(BaseModel):
    needs_setup: bool
    authenticated: bool
    user: dict[str, str] | None = None
    csrf: str | None = None
    reauth_until: datetime | None = None


@router.get("/state", response_model=StateOut)
async def state(request: Request, conn: AsyncConnection = Depends(db.get_db)) -> StateOut:
    if not await _has_users(conn):
        return StateOut(needs_setup=True, authenticated=False)
    cur = await security._load(conn, request)
    if cur is None:
        return StateOut(needs_setup=False, authenticated=False)
    return StateOut(
        needs_setup=False,
        authenticated=True,
        user={"email": cur.email, "display_name": cur.display_name, "role": cur.role},
        csrf=cur.csrf,
        reauth_until=cur.reauth_until,
    )


class SetupIn(BaseModel):
    setup_token: str = Field(min_length=4, max_length=20)
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=security.MIN_PASSWORD, max_length=200)


class SetupOut(BaseModel):
    totp_secret: str
    totp_uri: str
    qr_svg: str


@router.post("/setup", response_model=SetupOut)
async def setup(body: SetupIn, request: Request, conn: AsyncConnection = Depends(db.get_db)) -> SetupOut:
    """Bước 1: tạo tài khoản Owner (chưa dùng được) và mã TOTP. Bước 2 (/setup/confirm) nhập mã 6 số để kích hoạt."""
    if await _has_users(conn):
        raise AppError("ALREADY_SET_UP", "Đã có tài khoản Owner.", 409)
    await _check_setup_token(conn, body.setup_token)
    sec = security.new_totp_secret()
    uid = uuid7()
    await db.execute(
        conn,
        "INSERT INTO users(id, email, display_name, role, password_hash) VALUES (:id, :e, :n, 'owner', :p)",
        {"id": uid, "e": body.email.lower(), "n": body.display_name, "p": security.hash_password(body.password)},
    )
    await store.put_secret(conn, f"totp:{uid}", sec, "system")
    await audit.record(conn, "system", "auth.setup_started", f"user:{body.email.lower()}", request_id=_rid(request))
    uri = security.totp_uri(sec, body.email.lower())
    return SetupOut(totp_secret=sec, totp_uri=uri, qr_svg=security.totp_qr_svg(uri))


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)
    code: str = Field(min_length=6, max_length=10)


async def _verify(conn: AsyncConnection, body: LoginIn, request: Request, require_confirmed: bool = True) -> dict[str, object]:
    """Kiểm mật khẩu + TOTP; đếm lần sai; khóa 15 phút sau 5 lần. Thông báo lỗi như nhau dù sai email hay mật khẩu."""
    bad = AppError("LOGIN_FAILED", "Email, mật khẩu hoặc mã xác thực không đúng.", 401)
    u = await db.one(conn, "SELECT * FROM users WHERE email = :e AND status = 'active'", {"e": body.email.lower()})
    if u is None:
        security.dummy_check(body.password)  # tốn thời gian như khi email tồn tại: không dò được email
        raise bad
    now = datetime.now(UTC)
    if u["locked_until"] and u["locked_until"] > now:
        raise AppError("LOCKED", "Tài khoản tạm khóa do nhập sai nhiều lần. Thử lại sau 15 phút.", 423)
    if require_confirmed and u["totp_confirmed_at"] is None:
        raise AppError("SETUP_INCOMPLETE", "Chưa hoàn tất thiết lập xác thực hai lớp.", 409)
    sec = await store.get_secret(conn, f"totp:{u['id']}") or ""
    if not (security.check_password(u["password_hash"], body.password) and security.check_totp(sec, body.code)):
        # Ghi lần sai bằng giao dịch riêng: lỗi trả về sẽ rollback giao dịch của request, nhưng bộ đếm khóa phải được giữ.
        async with db.engine().begin() as c2:
            fails = int(
                await db.scalar(
                    c2, "UPDATE users SET failed_logins = failed_logins + 1 WHERE id = :id RETURNING failed_logins", {"id": u["id"]}
                )
            )
            locked = fails >= security.MAX_FAILS
            if locked:
                await db.execute(
                    c2,
                    "UPDATE users SET failed_logins = 0, locked_until = :l WHERE id = :id",
                    {"l": now + security.LOCK_FOR, "id": u["id"]},
                )
            await audit.record(c2, f"user:{u['email']}", "auth.login_failed", data={"lock": locked}, request_id=_rid(request))
        raise bad
    await db.execute(conn, "UPDATE users SET failed_logins = 0, locked_until = NULL WHERE id = :id", {"id": u["id"]})
    return dict(u)


@router.post("/setup/confirm")
async def setup_confirm(body: LoginIn, request: Request, response: Response, conn: AsyncConnection = Depends(db.get_db)) -> dict[str, bool]:
    u = await _verify(conn, body, request, require_confirmed=False)
    if u["totp_confirmed_at"] is not None:
        raise AppError("ALREADY_SET_UP", "Đã có tài khoản Owner.", 409)
    await db.execute(conn, "UPDATE users SET totp_confirmed_at = now() WHERE id = :id", {"id": u["id"]})
    await db.execute(conn, "DELETE FROM system_meta WHERE key = 'setup_token'")
    token, _ = await security.create_session(conn, str(u["id"]), request.headers.get("user-agent"))
    await audit.record(conn, f"user:{u['email']}", "auth.setup_completed", request_id=_rid(request))
    _set_cookie(response, token)
    return {"ok": True}


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response, conn: AsyncConnection = Depends(db.get_db)) -> dict[str, bool]:
    u = await _verify(conn, body, request)
    token, _ = await security.create_session(conn, str(u["id"]), request.headers.get("user-agent"))
    await audit.record(conn, f"user:{u['email']}", "auth.login", request_id=_rid(request))
    _set_cookie(response, token)
    return {"ok": True}


class ReauthIn(BaseModel):
    password: str = Field(max_length=200)
    code: str = Field(min_length=6, max_length=10)


@router.post("/reauth")
async def reauth(
    body: ReauthIn, request: Request, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Depends(security.current_user)
) -> dict[str, datetime]:
    await _verify(conn, LoginIn(email=cur.email, password=body.password, code=body.code), request)
    until = datetime.now(UTC) + security.REAUTH_TTL
    await db.execute(conn, "UPDATE user_sessions SET reauth_until = :u WHERE id = :id", {"u": until, "id": cur.session_id})
    await audit.record(conn, cur.actor, "auth.reauth", request_id=_rid(request))
    return {"reauth_until": until}


@router.post("/logout")
async def logout(
    request: Request, response: Response, conn: AsyncConnection = Depends(db.get_db), cur: security.Current = Depends(security.current_user)
) -> dict[str, bool]:
    await db.execute(conn, "UPDATE user_sessions SET revoked_at = now() WHERE id = :id", {"id": cur.session_id})
    await audit.record(conn, cur.actor, "auth.logout", request_id=_rid(request))
    response.delete_cookie(security.SESSION_COOKIE, path="/")
    return {"ok": True}
