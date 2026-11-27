"""Điểm vào của máy chủ AI Marketing Company (FastAPI)."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from app import __version__
from app.api.v1 import health
from app.core import errors
from app.core.config import get_settings
from app.core.logging import setup_logging


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)
    app = FastAPI(
        title="AI Marketing Company",
        version=__version__,
        docs_url="/api/docs" if settings.env != "prod" else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.env != "prod" else None,
    )
    errors.install(app)
    v1 = APIRouter(prefix="/api/v1")
    v1.include_router(health.router)
    app.include_router(v1)
    return app


app = create_app()
