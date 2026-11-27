"""Hạ tầng kiểm thử dùng CSDL thật (AICO_TEST_DATABASE_URL, tên chứa 'test') và Redis (AICO_TEST_REDIS_URL)."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text

TEST_DB = os.environ.get("AICO_TEST_DATABASE_URL", "")
TEST_REDIS = os.environ.get("AICO_TEST_REDIS_URL", "redis://127.0.0.1:1/0")
MASTER = "test-master-key-" + "x" * 32
BACKEND = Path(__file__).resolve().parents[1]
needs_db = pytest.mark.skipif(not TEST_DB, reason="chưa đặt AICO_TEST_DATABASE_URL")


def _seed_profiles() -> list[tuple[str, str, str | None, str]]:
    """Hồ sơ model gốc lấy từ chính migration 0002, để test nào đổi registry thì test sau vẫn bắt đầu từ trạng thái chuẩn."""
    spec = importlib.util.spec_from_file_location("m0002", BACKEND / "migrations" / "versions" / "0002_control_center.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return list(mod.PROFILES)


PROFILES = _seed_profiles()

# Bảng có dữ liệu do người dùng/hệ thống sinh ra (xóa giữa các test); bảng cấu hình (agents, registry) giữ nguyên
RESET_TABLES = [
    "notification_deliveries",
    "notifications",
    "telegram_link_codes",
    "telegram_chats",
    "model_usage",
    "settings",
    "secrets",
    "user_sessions",
    "users",
    "audit_logs",
]


def alembic(*args: str) -> None:
    assert "test" in TEST_DB.rsplit("/", 1)[-1], "Chỉ chạy trên CSDL có tên chứa 'test'"
    env = {**os.environ, "AICO_DATABASE_URL": TEST_DB}
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, check=True, capture_output=True)


@pytest.fixture(scope="session")
def migrated() -> None:
    if not TEST_DB:
        pytest.skip("chưa đặt AICO_TEST_DATABASE_URL")
    alembic("upgrade", "head")


def reset_db() -> None:
    eng = create_engine(TEST_DB)
    with eng.begin() as c:
        c.execute(text("SET LOCAL aico.allow_truncate = 'on'"))
        c.execute(text("TRUNCATE " + ", ".join(RESET_TABLES) + " RESTART IDENTITY CASCADE"))
        c.execute(text("UPDATE agent_status SET state = 'active', reason = NULL, changed_by = NULL, circuit_failures = 0"))
        c.execute(text("UPDATE provider_registry SET last_test_at = NULL, last_test_ok = NULL, last_test_detail = NULL"))
        c.execute(text("UPDATE model_registry SET enabled = (id <> 'claude-opus-5-5')"))
        for prof, mid, fb, _ in PROFILES:
            c.execute(
                text("UPDATE model_profiles SET model_id = :m, fallback_model_id = :f WHERE profile = :p"), {"m": mid, "f": fb, "p": prof}
            )
        c.execute(text("DELETE FROM system_meta WHERE key IN ('setup_token', 'telegram_offset')"))
    eng.dispose()


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, migrated: None) -> None:
    from app.core import db
    from app.core.config import get_settings

    monkeypatch.setenv("AICO_DATABASE_URL", TEST_DB)
    monkeypatch.setenv("AICO_REDIS_URL", TEST_REDIS)
    monkeypatch.setenv("AICO_MASTER_KEY", MASTER)
    monkeypatch.setenv("AICO_ENV", "test")
    get_settings.cache_clear()
    db._engine = None
    reset_db()


@pytest.fixture
async def conn(env: None) -> AsyncIterator[object]:
    from app.core import db

    # Giao dịch của test luôn rollback; phần gateway/worker ghi bằng kết nối riêng thì reset_db() dọn ở test sau.
    async with db.engine().connect() as c:
        tx = await c.begin()
        yield c
        await tx.rollback()
    await db.dispose()


@pytest.fixture
async def api(env: None) -> AsyncIterator[AsyncClient]:
    from app.core import db
    from app.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as c:
        yield c
    await db.dispose()


class OwnerSession:
    """Owner đã thiết lập xong và đăng nhập; `h` là header CSRF cho thao tác ghi."""

    EMAIL = "owner@xuongtramoc.vn"
    PASSWORD = "mat-khau-rat-dai-123"  # noqa: S105 — chỉ dùng trong test

    def __init__(self, api: AsyncClient, totp_secret: str, csrf: str) -> None:
        self.api, self.secret, self.csrf = api, totp_secret, csrf

    @property
    def h(self) -> dict[str, str]:
        return {"X-CSRF-Token": self.csrf}

    def code(self) -> str:
        import pyotp

        return str(pyotp.TOTP(self.secret).now())

    async def reauth(self) -> None:
        r = await self.api.post("/api/v1/auth/reauth", json={"password": self.PASSWORD, "code": self.code()}, headers=self.h)
        assert r.status_code == 200, r.text


async def make_owner(api: AsyncClient) -> OwnerSession:
    import pyotp

    from app.api.v1.auth import issue_setup_token
    from app.core import db

    async with db.engine().begin() as c:
        token = await issue_setup_token(c)
    assert token
    r = await api.post(
        "/api/v1/auth/setup",
        json={"setup_token": token, "email": OwnerSession.EMAIL, "display_name": "Chủ xưởng", "password": OwnerSession.PASSWORD},
    )
    assert r.status_code == 200, r.text
    secret = r.json()["totp_secret"]
    r = await api.post(
        "/api/v1/auth/setup/confirm",
        json={"email": OwnerSession.EMAIL, "password": OwnerSession.PASSWORD, "code": pyotp.TOTP(secret).now()},
    )
    assert r.status_code == 200, r.text
    st = (await api.get("/api/v1/auth/state")).json()
    assert st["authenticated"]
    return OwnerSession(api, secret, st["csrf"])


@pytest.fixture
async def owner(api: AsyncClient) -> OwnerSession:
    return await make_owner(api)
