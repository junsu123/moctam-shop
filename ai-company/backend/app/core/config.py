"""Cấu hình đọc từ biến môi trường (tiền tố AICO_). Không có secret nào trong mã nguồn (SRS §10, §21)."""

from __future__ import annotations

from functools import lru_cache
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

    @model_validator(mode="after")
    def _prod_needs_master_key(self) -> Settings:
        if self.env == "prod" and (self.master_key is None or len(self.master_key.get_secret_value()) < 32):
            raise ValueError("AICO_MASTER_KEY phải có ít nhất 32 ký tự khi chạy production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
