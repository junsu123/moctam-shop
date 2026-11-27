"""Điểm vào của máy chủ AI Marketing Company (FastAPI)."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from app import __version__
from app.api.v1 import agents, auth, control, health, telegram
from app.core import errors, telemetry
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
    v1.include_router(auth.router)
    v1.include_router(control.router)
    v1.include_router(telegram.router)
    v1.include_router(agents.router)
    app.include_router(v1)
    telemetry.instrument(app)
    return app


app = create_app()
