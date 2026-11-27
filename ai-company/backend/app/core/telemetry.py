"""OpenTelemetry (ARCHITECTURE: log + trace). Mỗi request, lời gọi LLM, lời gọi công cụ và quyết định chính sách là một span.

- Có `AICO_OTEL_ENDPOINT`: gửi trace qua OTLP/HTTP tới collector (Jaeger, Grafana Tempo…).
- Không đặt: trace vẫn được tạo để gắn `trace_id` vào log JSON, không gửi đi đâu. Tốn thêm khoảng 15 MB RAM.
"""

from __future__ import annotations

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app import __version__
from app.core.config import get_settings

_provider: TracerProvider | None = None
_httpx_done = False


def provider() -> TracerProvider:
    """Cài TracerProvider một lần cho cả tiến trình (OpenTelemetry không cho đặt lại)."""
    global _provider
    if _provider is None:
        s = get_settings()
        _provider = TracerProvider(resource=Resource.create({"service.name": s.otel_service_name, "service.version": __version__}))
        if s.otel_endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            _provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=s.otel_endpoint.rstrip("/") + "/v1/traces")))
        trace.set_tracer_provider(_provider)
    return _provider


def instrument(app: FastAPI) -> None:
    global _httpx_done
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    provider()
    # Bỏ qua kiểm tra sức khỏe và luồng SSE (mở lâu, không có ý nghĩa đo)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="api/v1/health/.*,api/v1/events/stream", tracer_provider=provider())
    if not _httpx_done:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument(tracer_provider=provider())
        _httpx_done = True


tracer = trace.get_tracer("aico")
