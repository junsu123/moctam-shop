"""Lõi bảo mật: mã hóa phong bì, nhật ký chuỗi băm, mật khẩu, TOTP, UUIDv7, cài đặt mặc định."""

from __future__ import annotations

import uuid

import pyotp
import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import text

from app.core import audit, crypto, security
from app.core.errors import AppError
from app.core.ids import uuid7
from app.domain import store

from .conftest import MASTER, needs_db


def test_seal_roundtrip_and_tamper() -> None:
    s = crypto.seal("telegram.bot_token", "123:ABC", MASTER)
    assert b"123:ABC" not in s.ciphertext and crypto.unseal("telegram.bot_token", s, MASTER) == "123:ABC"
    with pytest.raises(InvalidTag):  # tráo bản mã sang tên secret khác
        crypto.unseal("provider.openai.api_key", s, MASTER)
    with pytest.raises(InvalidTag):  # sai khóa chủ
        crypto.unseal("telegram.bot_token", s, "z" * 40)


def test_missing_master_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    monkeypatch.delenv("AICO_MASTER_KEY", raising=False)
    get_settings.cache_clear()
    with pytest.raises(AppError) as e:
        crypto.seal("x", "y")
    assert e.value.code == "MASTER_KEY_MISSING"
    get_settings.cache_clear()


def test_password_and_totp() -> None:
    h = security.hash_password("mat-khau-dai-du-10")
    assert h.startswith("$argon2id$") and security.check_password(h, "mat-khau-dai-du-10")
    assert not security.check_password(h, "sai-mat-khau-roi")
    with pytest.raises(AppError):
        security.hash_password("ngan")
    sec = security.new_totp_secret()
    assert security.check_totp(sec, pyotp.TOTP(sec).now())
    assert not security.check_totp(sec, "000000") or pyotp.TOTP(sec).now() == "000000"
    assert security.totp_qr_svg(security.totp_uri(sec, "owner@xuong.vn")).startswith("<svg")


def test_uuid7_sorted() -> None:
    ids = [uuid7() for _ in range(200)]
    assert all(u.version == 7 and u.variant == uuid.RFC_4122 for u in ids)
    assert [u.int >> 80 for u in ids] == sorted(u.int >> 80 for u in ids)


@needs_db
async def test_audit_chain_detects_tampering(conn) -> None:  # type: ignore[no-untyped-def]
    for i in range(5):
        await audit.record(conn, "user:owner@xuong.vn", "test.action", f"thing:{i}", {"sđt": "0912345678", "n": i}, reason="lý do")
    rep = await audit.verify_chain(conn)
    assert rep.ok and rep.checked == 5
    data = (await conn.execute(text("SELECT data FROM audit_logs WHERE id = 1"))).scalar()
    assert "0912345678" not in str(data)  # đã che
    with pytest.raises(Exception, match="chỉ được thêm"):
        async with conn.begin_nested():
            await conn.execute(text("UPDATE audit_logs SET actor = 'x' WHERE id = 2"))
    # Giả lập superuser tắt trigger để sửa: chuỗi băm vẫn phát hiện
    await conn.execute(text("ALTER TABLE audit_logs DISABLE TRIGGER audit_no_change"))
    await conn.execute(text("UPDATE audit_logs SET action = 'sửa lén' WHERE id = 3"))
    await conn.execute(text("ALTER TABLE audit_logs ENABLE TRIGGER audit_no_change"))
    rep = await audit.verify_chain(conn)
    assert not rep.ok and rep.first_bad_id == 3
    await conn.rollback()


@needs_db
async def test_settings_defaults_and_secret_store(conn) -> None:  # type: ignore[no-untyped-def]
    b = await store.get_setting(conn, "budget")
    assert isinstance(b, store.Budget) and b.month_usd == 50 and b.day_usd == 1.67
    await store.put_setting(conn, "budget", store.Budget(month_usd=60), "user:o")
    assert (await store.get_setting(conn, "budget")).month_usd == 60  # type: ignore[attr-defined]
    with pytest.raises(ValueError):
        store.Hours(work_start="25:00")
    last4 = await store.put_secret(conn, "provider.anthropic.api_key", "sk-ant-api03-abcdefgh1234", "user:o")
    assert last4 == "1234"
    raw = (await conn.execute(text("SELECT ciphertext FROM secrets"))).scalar()
    assert b"sk-ant" not in bytes(raw)
    assert await store.get_secret(conn, "provider.anthropic.api_key") == "sk-ant-api03-abcdefgh1234"
    assert (await store.secret_info(conn, "provider.anthropic.api_key"))["last4"] == "1234"  # type: ignore[index]


def test_cli_setup_token_and_verify_audit(env: None, capsys: pytest.CaptureFixture[str]) -> None:
    from app import cli

    assert cli.main(["setup-token"]) == 0
    assert "Mã thiết lập:" in capsys.readouterr().out
    assert cli.main(["verify-audit"]) == 0
    assert "nguyên vẹn" in capsys.readouterr().out
