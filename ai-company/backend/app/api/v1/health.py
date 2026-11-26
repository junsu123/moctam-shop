"""Kiểm tra sức khỏe: /live (tiến trình còn sống) và /ready (CSDL + Valkey sẵn sàng).

Docker dùng /live làm healthcheck; dashboard dùng /ready để hiển thị tình trạng hệ thống.
Không trả chuỗi kết nối hay thông điệp lỗi gốc (có thể chứa mật khẩu); chỉ trả trạng thái + mã lỗi ngắn.
"""

from __future__ import annotations

import asyncio
import time
from typing import Literal

import redis.asyncio as aioredis
from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app import __version__
from app.core.config import get_settings

router = APIRouter(prefix="/health", tags=["health"])


class Check(BaseModel):
    status: Literal["ok", "error"]
    latency_ms: int | None = None
    detail: str | None = None


class Ready(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    checks: dict[str, Check]


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


async def _check_db(url: str, limit_s: float) -> Check:
    t0 = time.perf_counter()
    engine = create_async_engine(url, pool_pre_ping=False, connect_args={"connect_timeout": max(1, int(limit_s))})
    try:
        async with asyncio.timeout(limit_s):
            async with engine.connect() as conn:
                ext = (await conn.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector'"))).scalar()
        if ext is None:
            return Check(status="error", detail="Chưa bật extension pgvector (chạy migration)")
        return Check(status="ok", latency_ms=round((time.perf_counter() - t0) * 1000))
    except Exception as exc:  # noqa: BLE001 — chỉ báo loại lỗi, không lộ chi tiết
        return Check(status="error", detail=type(exc).__name__)
    finally:
        await engine.dispose()


async def _check_redis(url: str, limit_s: float) -> Check:
    t0 = time.perf_counter()
    client = aioredis.from_url(url, socket_connect_timeout=limit_s, socket_timeout=limit_s)
    try:
        async with asyncio.timeout(limit_s):
            await client.ping()
        return Check(status="ok", latency_ms=round((time.perf_counter() - t0) * 1000))
    except Exception as exc:  # noqa: BLE001
        return Check(status="error", detail=type(exc).__name__)
    finally:
        await client.aclose()


@router.get("/ready", response_model=Ready)
async def ready(response: Response) -> Ready:
    s = get_settings()
    db, rd = await asyncio.gather(_check_db(s.database_url, s.health_timeout_s), _check_redis(s.redis_url, s.health_timeout_s))
    checks = {"database": db, "queue": rd}
    ok = all(c.status == "ok" for c in checks.values())
    if not ok:
        response.status_code = 503
    return Ready(status="ok" if ok else "degraded", version=__version__, checks=checks)
