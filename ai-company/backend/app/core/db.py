"""Kết nối CSDL (SQLAlchemy async + psycopg). Mỗi request dùng một giao dịch; lỗi thì rollback toàn bộ."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.core.config import get_settings

_engine: AsyncEngine | None = None


def engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        # Pool nhỏ: máy Owner 16 GB, Postgres max_connections=40 (docker-compose.yml)
        _engine = create_async_engine(get_settings().database_url, pool_size=5, max_overflow=5, pool_pre_ping=True)
    return _engine


async def dispose() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


async def get_db() -> AsyncIterator[AsyncConnection]:
    """Dependency FastAPI: một giao dịch cho mỗi request."""
    async with engine().begin() as conn:
        yield conn


def psycopg_url() -> str:
    """Chuỗi kết nối psycopg thuần (cho LISTEN/NOTIFY)."""
    return get_settings().database_url.replace("postgresql+psycopg://", "postgresql://", 1)


async def one(conn: AsyncConnection, sql: str, params: Mapping[str, Any] | None = None) -> RowMapping | None:
    return (await conn.execute(text(sql), dict(params or {}))).mappings().first()


async def all_(conn: AsyncConnection, sql: str, params: Mapping[str, Any] | None = None) -> list[RowMapping]:
    return list((await conn.execute(text(sql), dict(params or {}))).mappings().all())


async def scalar(conn: AsyncConnection, sql: str, params: Mapping[str, Any] | None = None) -> Any:
    return (await conn.execute(text(sql), dict(params or {}))).scalar()


async def execute(conn: AsyncConnection, sql: str, params: Mapping[str, Any] | None = None) -> int:
    return (await conn.execute(text(sql), dict(params or {}))).rowcount
