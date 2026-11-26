"""Lỗi có mã ổn định (SRS §16, §21): mọi lỗi trả về {"error": {"code", "message", "request_id"}}.

`code` là chuỗi cố định cho máy đọc (frontend, test); `message` là tiếng Việt cho người đọc.
Lỗi không lường trước không bao giờ lộ chi tiết nội bộ ra ngoài; chi tiết nằm trong log (đã che dữ liệu nhạy cảm).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

log = logging.getLogger("aico.errors")


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _body(code: str, message: str, request: Request) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message, "request_id": getattr(request.state, "request_id", "")}}


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        rid = request.headers.get("x-request-id", "")
        if not (0 < len(rid) <= 64 and rid.replace("-", "").isalnum()):
            rid = uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response


STATUS_CODES = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 401: "UNAUTHENTICATED", 403: "FORBIDDEN", 429: "RATE_LIMITED"}
STATUS_TEXT = {
    404: "Không tìm thấy.",
    405: "Phương thức không được hỗ trợ.",
    401: "Cần đăng nhập.",
    403: "Không có quyền.",
    429: "Quá nhiều yêu cầu.",
}


def install(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)

    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(_body(exc.code, exc.message, request), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = ", ".join(".".join(str(p) for p in e["loc"] if p != "body") for e in exc.errors()[:5])
        return JSONResponse(_body("VALIDATION_FAILED", f"Dữ liệu không hợp lệ: {fields}", request), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(_body(code, STATUS_TEXT.get(exc.status_code, str(exc.detail)), request), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("Lỗi không lường trước", extra={"request_id": getattr(request.state, "request_id", "")})
        return JSONResponse(_body("INTERNAL", "Đã có lỗi hệ thống; chi tiết nằm trong log.", request), status_code=500)
