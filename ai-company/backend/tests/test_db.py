"""Migration lên/xuống trên Postgres thật (IT-DB-01) và /ready khi CSDL sẵn sàng.

Cần AICO_TEST_DATABASE_URL trỏ tới một CSDL **riêng cho kiểm thử** (tên phải chứa "test").
Không có biến này thì bỏ qua (CI luôn đặt biến này).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

URL = os.environ.get("AICO_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="chưa đặt AICO_TEST_DATABASE_URL")
BACKEND = Path(__file__).resolve().parents[1]


def _alembic(*args: str) -> None:
    assert "test" in URL.rsplit("/", 1)[-1], "Chỉ chạy migration thử trên CSDL có tên chứa 'test'"
    env = {**os.environ, "AICO_DATABASE_URL": URL}
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, check=True, capture_output=True)


def _q(sql: str) -> object:
    eng = create_engine(URL)
    try:
        with eng.connect() as c:
            return c.execute(text(sql)).scalar()
    finally:
        eng.dispose()


def test_migration_up_down_up() -> None:
    _alembic("downgrade", "base")
    _alembic("upgrade", "head")
    assert _q("SELECT count(*) FROM pg_extension WHERE extname IN ('vector','pg_trgm','unaccent')") == 3
    assert _q("SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'langgraph'") == 1
    assert _q("SELECT value FROM system_meta WHERE key = 'installed_at'")
    _alembic("downgrade", "base")
    assert _q("SELECT to_regclass('public.system_meta')") is None
    _alembic("upgrade", "head")
    assert _q("SELECT version_num FROM alembic_version") == "0001_baseline"


def test_vector_works() -> None:
    _alembic("upgrade", "head")
    assert _q("SELECT '[1,0,0]'::vector <=> '[0,1,0]'::vector") == pytest.approx(1.0)


@pytest.mark.skipif(not os.environ.get("AICO_TEST_REDIS_URL"), reason="chưa đặt AICO_TEST_REDIS_URL")
def test_ready_ok_with_real_services(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.main import create_app

    _alembic("upgrade", "head")
    monkeypatch.setenv("AICO_DATABASE_URL", URL)
    monkeypatch.setenv("AICO_REDIS_URL", os.environ["AICO_TEST_REDIS_URL"])
    get_settings.cache_clear()
    r = TestClient(create_app()).get("/api/v1/health/ready")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok" and r.json()["checks"]["database"]["latency_ms"] is not None
