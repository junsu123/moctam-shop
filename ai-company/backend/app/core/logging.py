"""Log JSON có cấu trúc, tự che dữ liệu nhạy cảm (SECURITY_PLAN §5).

Mọi dòng log đi qua RedactFilter: SĐT Việt Nam, email, khóa API (sk-…, xk_…), token bot Telegram, JWT
đều bị thay bằng nhãn trước khi ghi ra. Không có ngoại lệ, kể cả ở chế độ debug.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

from opentelemetry import trace

PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b"), "[token-telegram]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), "[jwt]"),
    (re.compile(r"\b(sk|xk|pk|rk)[-_][A-Za-z0-9_-]{12,}\b"), "[khóa]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[email]"),
    (re.compile(r"(?<!\d)(?:\+?84|0)(?:[\s.-]?\d){9,10}(?!\d)"), "[sđt]"),
]


def redact(text: str) -> str:
    for pat, label in PATTERNS:
        text = pat.sub(label, text)
    return text


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("request_id", "agent_id", "task_id"):
            if hasattr(record, key):
                out[key] = getattr(record, key)
        span = trace.get_current_span().get_span_context()
        if span.is_valid:  # nối log với trace (OpenTelemetry)
            out["trace_id"] = format(span.trace_id, "032x")
            out["span_id"] = format(span.span_id, "016x")
        if record.exc_info:
            out["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(out, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
