"""Sprint 0: health, mã lỗi ổn định, che dữ liệu nhạy cảm trong log, cấu hình production."""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.logging import JsonFormatter, RedactFilter, redact
from app.main import create_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Trỏ tới cổng không có dịch vụ: /ready phải báo "degraded" mà không treo
    monkeypatch.setenv("AICO_DATABASE_URL", "postgresql+psycopg://x:y@127.0.0.1:1/none")
    monkeypatch.setenv("AICO_REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setenv("AICO_HEALTH_TIMEOUT_S", "1")
    get_settings.cache_clear()
    app = create_app()

    @app.get("/api/v1/_boom")
    async def boom() -> None:
        raise RuntimeError("chi tiết nội bộ: mật khẩu=abc123")

    @app.get("/api/v1/_apperr")
    async def apperr() -> None:
        raise AppError("BUDGET_EXCEEDED", "Đã hết ngân sách LLM hôm nay.", 409)

    return TestClient(app, raise_server_exceptions=False)


def test_live(client: TestClient) -> None:
    r = client.get("/api/v1/health/live")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert len(r.headers["x-request-id"]) == 32


def test_ready_degraded_without_dependencies(client: TestClient) -> None:
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"]["status"] == "error" and body["checks"]["queue"]["status"] == "error"
    assert "x:y" not in r.text and "127.0.0.1" not in r.text  # không lộ chuỗi kết nối


def test_stable_error_codes(client: TestClient) -> None:
    r = client.get("/api/v1/khong-co")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    r = client.get("/api/v1/_apperr", headers={"x-request-id": "abc-123"})
    assert r.status_code == 409
    assert r.json() == {"error": {"code": "BUDGET_EXCEEDED", "message": "Đã hết ngân sách LLM hôm nay.", "request_id": "abc-123"}}
    r = client.get("/api/v1/_boom")
    assert r.status_code == 500 and r.json()["error"]["code"] == "INTERNAL"
    assert "abc123" not in r.text  # không lộ chi tiết nội bộ


@pytest.mark.parametrize(
    ("raw", "hidden"),
    [
        ("Khách 0912 345 678 hỏi", "0912 345 678"),
        ("gọi +84912345678 nhé", "+84912345678"),
        ("email chi.lan@example.com", "chi.lan@example.com"),
        ("key sk-ant-api03-AbCdEfGhIjKlMnOp", "sk-ant-api03-AbCdEfGhIjKlMnOp"),
        ("bot 123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw1", "AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw1"),
        ("khóa xk_9f8e7d6c5b4a3f2e1d", "xk_9f8e7d6c5b4a3f2e1d"),
    ],
)
def test_redact(raw: str, hidden: str) -> None:
    assert hidden not in redact(raw)


def test_redact_keeps_normal_numbers() -> None:
    assert redact("Đơn XTM-1042 tổng 125000 đ, 3 sản phẩm") == "Đơn XTM-1042 tổng 125000 đ, 3 sản phẩm"


def test_json_log_is_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    rec = logging.LogRecord("aico", logging.INFO, __file__, 1, "Khách %s, sđt %s", ("lan@example.com", "0987654321"), None)
    RedactFilter().filter(rec)
    out = json.loads(JsonFormatter().format(rec))
    assert out["msg"] == "Khách [email], sđt [sđt]" and out["level"] == "INFO"


def test_prod_requires_master_key() -> None:
    with pytest.raises(ValidationError):
        Settings(env="prod", master_key=None)
    assert Settings(env="prod", master_key="k" * 32).env == "prod"
