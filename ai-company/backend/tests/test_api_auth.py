"""IT-AUTH: thiết lập lần đầu, đăng nhập 2 lớp, khóa tạm, CSRF, xác thực lại, đăng xuất (TEST_PLAN §3, SECURITY_PLAN §2.1)."""

from __future__ import annotations

import pyotp
import pytest
from httpx import AsyncClient

from tests.conftest import OwnerSession, make_owner, needs_db

pytestmark = needs_db


async def test_state_before_setup(api: AsyncClient) -> None:
    r = await api.get("/api/v1/auth/state")
    assert r.json() == {"needs_setup": True, "authenticated": False, "user": None, "csrf": None, "reauth_until": None}


async def test_setup_requires_valid_token(api: AsyncClient) -> None:
    r = await api.post(
        "/api/v1/auth/setup", json={"setup_token": "ABCD-1234", "email": "a@b.vn", "display_name": "A", "password": "x" * 12}
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "SETUP_TOKEN_INVALID"


async def test_full_setup_then_cannot_setup_again(api: AsyncClient) -> None:
    o = await make_owner(api)
    st = (await api.get("/api/v1/auth/state")).json()
    assert st["user"]["role"] == "owner" and st["user"]["email"] == OwnerSession.EMAIL
    assert "aico_session" in api.cookies
    from app.api.v1.auth import issue_setup_token
    from app.core import db

    async with db.engine().begin() as c:
        assert await issue_setup_token(c) is None  # đã có Owner thì CLI không cấp mã nữa
    r = await api.post("/api/v1/auth/setup", json={"setup_token": "X" * 9, "email": "b@b.vn", "display_name": "B", "password": "y" * 12})
    assert r.status_code == 409
    # nhật ký có đủ các bước
    ev = (await api.get("/api/v1/events")).json()
    actions = [e["action"] for e in ev if e["source"] == "audit"]
    assert "auth.setup_started" in actions and "auth.setup_completed" in actions
    assert o.csrf


async def test_setup_can_restart_before_confirm(api: AsyncClient) -> None:
    """Tải lại trang giữa bước 1 và 2: vẫn đang 'cần thiết lập', làm lại được với cùng mã thiết lập; mã TOTP cũ hết hiệu lực."""
    from app.api.v1.auth import issue_setup_token
    from app.core import db

    async with db.engine().begin() as c:
        tok = await issue_setup_token(c)
    body = {"setup_token": tok, "email": "o@xuong.vn", "display_name": "O", "password": "p" * 12}
    first = (await api.post("/api/v1/auth/setup", json=body)).json()["totp_secret"]
    assert (await api.get("/api/v1/auth/state")).json()["needs_setup"] is True
    second = (await api.post("/api/v1/auth/setup", json={**body, "email": "chu@xuong.vn"})).json()["totp_secret"]
    assert first != second
    r = await api.post("/api/v1/auth/setup/confirm", json={"email": "chu@xuong.vn", "password": "p" * 12, "code": pyotp.TOTP(second).now()})
    assert r.status_code == 200
    r = await api.post("/api/v1/auth/login", json={"email": "o@xuong.vn", "password": "p" * 12, "code": pyotp.TOTP(first).now()})
    assert r.status_code == 401


async def test_setup_unconfirmed_account_cannot_login(api: AsyncClient) -> None:
    from app.api.v1.auth import issue_setup_token
    from app.core import db

    async with db.engine().begin() as c:
        tok = await issue_setup_token(c)
    r = await api.post("/api/v1/auth/setup", json={"setup_token": tok, "email": "o@x.vn", "display_name": "O", "password": "p" * 12})
    sec = r.json()["totp_secret"]
    assert r.json()["qr_svg"].startswith("<svg")
    r = await api.post("/api/v1/auth/login", json={"email": "o@x.vn", "password": "p" * 12, "code": pyotp.TOTP(sec).now()})
    assert r.status_code == 409 and r.json()["error"]["code"] == "SETUP_INCOMPLETE"


async def test_login_logout_and_wrong_code(owner: OwnerSession) -> None:
    api = owner.api
    r = await api.post("/api/v1/auth/logout", headers=owner.h)
    assert r.status_code == 200
    assert (await api.get("/api/v1/agents")).status_code == 401
    bad = await api.post("/api/v1/auth/login", json={"email": owner.EMAIL, "password": owner.PASSWORD, "code": "000000"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "LOGIN_FAILED"
    unknown = await api.post("/api/v1/auth/login", json={"email": "ai@do.vn", "password": owner.PASSWORD, "code": "000000"})
    assert unknown.json()["error"] == {**unknown.json()["error"], "code": "LOGIN_FAILED", "message": bad.json()["error"]["message"]}
    ok = await api.post("/api/v1/auth/login", json={"email": owner.EMAIL, "password": owner.PASSWORD, "code": owner.code()})
    assert ok.status_code == 200
    assert (await api.get("/api/v1/agents")).status_code == 200


async def test_lockout_after_five_failures(owner: OwnerSession) -> None:
    api = owner.api
    for _ in range(5):
        r = await api.post("/api/v1/auth/login", json={"email": owner.EMAIL, "password": "sai-mat-khau-123", "code": owner.code()})
        assert r.status_code == 401
    r = await api.post("/api/v1/auth/login", json={"email": owner.EMAIL, "password": owner.PASSWORD, "code": owner.code()})
    assert r.status_code == 423 and r.json()["error"]["code"] == "LOCKED"


async def test_csrf_required_on_writes(owner: OwnerSession) -> None:
    r = await owner.api.post("/api/v1/agents/seo_agent/pause", json={})
    assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF_FAILED"
    r = await owner.api.post("/api/v1/agents/seo_agent/pause", json={}, headers={"X-CSRF-Token": "gia-mao"})
    assert r.status_code == 403
    r = await owner.api.post("/api/v1/agents/seo_agent/pause", json={}, headers=owner.h)
    assert r.status_code == 200


async def test_reauth_gate_for_sensitive_ops(owner: OwnerSession) -> None:
    r = await owner.api.put("/api/v1/providers/anthropic/key", json={"api_key": "sk-ant-" + "a" * 40}, headers=owner.h)
    assert r.status_code == 403 and r.json()["error"]["code"] == "REAUTH_REQUIRED"
    await owner.reauth()
    r = await owner.api.put("/api/v1/providers/anthropic/key", json={"api_key": "sk-ant-" + "a" * 36 + "WXYZ"}, headers=owner.h)
    assert r.status_code == 200 and r.json()["key_last4"] == "WXYZ"


@pytest.mark.parametrize(
    "path", ["/api/v1/agents", "/api/v1/settings", "/api/v1/providers", "/api/v1/overview", "/api/v1/events", "/api/v1/telegram"]
)
async def test_endpoints_require_login(api: AsyncClient, path: str) -> None:
    r = await api.get(path)
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHENTICATED"
