"""Kho cài đặt (settings) và kho secret (mã hóa). Cài đặt có giá trị mặc định trong mã, ghi đè được qua trang quản trị."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import crypto, db


class Budget(BaseModel):
    """Trần chi phí LLM (DECISIONS Q-B1a: 50 USD/tháng, phương án B)."""

    month_usd: float = Field(default=50.0, ge=0, le=100_000)
    day_usd: float = Field(default=1.67, ge=0, le=10_000)
    day_burst_usd: float = Field(default=3.0, ge=0, le=10_000)  # một ngày được tiêu tới mức này nếu tháng còn dư
    alert_pct: int = Field(default=80, ge=10, le=100)


def _hhmm(v: str) -> str:
    h, m = v.split(":")
    if not (0 <= int(h) <= 23 and 0 <= int(m) <= 59):
        raise ValueError("giờ không hợp lệ")
    return f"{int(h):02d}:{int(m):02d}"


class Hours(BaseModel):
    """Giờ làm việc của máy và giờ yên lặng của Telegram (DECISIONS Q-W1, ADR-15)."""

    work_start: str = "07:00"
    work_end: str = "22:00"
    quiet_start: str = "22:00"
    quiet_end: str = "07:00"

    @field_validator("work_start", "work_end", "quiet_start", "quiet_end")
    @classmethod
    def check_hhmm(cls, v: str) -> str:
        return _hhmm(v)


class Website(BaseModel):
    """Kết nối website moctam qua API đồng bộ (khóa lưu ở kho secret: website.read_key, website.drafts_key, website.publish_key)."""

    base_url: str = Field(default="", max_length=200, pattern=r"^(https?://[A-Za-z0-9.\-]+(:\d+)?(/[A-Za-z0-9._~\-/]*)?)?$")


DEFAULTS: dict[str, type[BaseModel]] = {"budget": Budget, "hours": Hours, "website": Website}


def register(key: str, model: type[BaseModel]) -> None:
    """Module khác khai báo thêm loại cài đặt (vd lịch đăng bài, Content Gate) mà không vòng import."""
    DEFAULTS[key] = model


async def get_setting(conn: AsyncConnection, key: str) -> BaseModel:
    model = DEFAULTS[key]
    raw = await db.scalar(conn, "SELECT value FROM settings WHERE key = :k", {"k": key})
    return model.model_validate(raw or {})


async def put_setting(conn: AsyncConnection, key: str, value: BaseModel, actor: str) -> None:
    await db.execute(
        conn,
        "INSERT INTO settings(key, value, updated_by) VALUES (:k, CAST(:v AS jsonb), :a) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by, updated_at = now(), version = settings.version + 1",
        {"k": key, "v": value.model_dump_json(), "a": actor},
    )


async def get_raw(conn: AsyncConnection, key: str) -> Any:
    return await db.scalar(conn, "SELECT value FROM settings WHERE key = :k", {"k": key})


async def put_raw(conn: AsyncConnection, key: str, value: Any, actor: str = "system") -> None:
    await db.execute(
        conn,
        "INSERT INTO settings(key, value, updated_by) VALUES (:k, CAST(:v AS jsonb), :a) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by, updated_at = now(), version = settings.version + 1",
        {"k": key, "v": json.dumps(value, ensure_ascii=False), "a": actor},
    )


# ------------------------------------------------------------------ secret
async def put_secret(conn: AsyncConnection, name: str, value: str, actor: str) -> str:
    s = crypto.seal(name, value)
    last4 = value[-4:] if len(value) >= 8 else ""
    await db.execute(
        conn,
        "INSERT INTO secrets(name, ciphertext, wrapped_key, key_version, last4, updated_by) VALUES (:n, :c, :w, :v, :l4, :a) "
        "ON CONFLICT (name) DO UPDATE SET ciphertext = EXCLUDED.ciphertext, wrapped_key = EXCLUDED.wrapped_key, "
        "key_version = EXCLUDED.key_version, last4 = EXCLUDED.last4, updated_by = EXCLUDED.updated_by, updated_at = now()",
        {"n": name, "c": s.ciphertext, "w": s.wrapped_key, "v": s.key_version, "l4": last4, "a": actor},
    )
    return last4


async def get_secret(conn: AsyncConnection, name: str) -> str | None:
    r = await db.one(conn, "SELECT ciphertext, wrapped_key, key_version FROM secrets WHERE name = :n", {"n": name})
    if r is None:
        return None
    return crypto.unseal(name, crypto.Sealed(bytes(r["ciphertext"]), bytes(r["wrapped_key"]), int(r["key_version"])))


async def secret_info(conn: AsyncConnection, name: str) -> dict[str, Any] | None:
    r = await db.one(conn, "SELECT last4, updated_at FROM secrets WHERE name = :n", {"n": name})
    return {"last4": r["last4"], "updated_at": r["updated_at"]} if r else None


async def delete_secret(conn: AsyncConnection, name: str) -> None:
    await db.execute(conn, "DELETE FROM secrets WHERE name = :n", {"n": name})
