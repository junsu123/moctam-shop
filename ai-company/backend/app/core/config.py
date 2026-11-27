"""Cấu hình đọc từ biến môi trường (tiền tố AICO_). Không có secret nào trong mã nguồn (SRS §10, §21)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AICO_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://aico:aico@127.0.0.1:5432/aico"
    redis_url: str = "redis://127.0.0.1:6379/0"
    # Khóa chủ để mã hóa secret (token Telegram, khóa API) theo kiểu phong bì: Sprint 1 dùng.
    master_key: SecretStr | None = None
    health_timeout_s: float = Field(default=2.0, gt=0, le=10)
    # Trang quản trị chạy http://127.0.0.1 nên cookie mặc định không đặt cờ Secure; bật khi đứng sau HTTPS.
    cookie_secure: bool = False
    # Telegram Bot API (đổi được để kiểm thử)
    telegram_api_base: str = "https://api.telegram.org"
    # Thư mục bộ não (brains/). Trong container được gắn chỉ đọc vào /brains.
    brains_dir: Path = Path(__file__).resolve().parents[3] / "brains"
    # OpenTelemetry: gửi trace về collector OTLP/HTTP nếu đặt (vd http://otel:4318). Để trống: chỉ gắn trace_id vào log.
    otel_endpoint: str | None = None
    otel_service_name: str = "aico-backend"

    @model_validator(mode="after")
    def _prod_needs_master_key(self) -> Settings:
        if self.env == "prod" and (self.master_key is None or len(self.master_key.get_secret_value()) < 32):
            raise ValueError("AICO_MASTER_KEY phải có ít nhất 32 ký tự khi chạy production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
