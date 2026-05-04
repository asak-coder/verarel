"""OpenTelemetry tracing and request correlation helpers."""
from __future__ import annotations

import contextvars
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Mapping, MutableMapping, Optional

from fastapi import Request, Response

try:  # pragma: no cover - optional dependency wiring
    from opentelemetry import trace
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.trace import Tracer
except Exception:  # pragma: no cover - graceful degradation
    trace = None  # type: ignore[assignment]
    FastAPIInstrumentor = None  # type: ignore[assignment]
    HTTPXClientInstrumentor = None  # type: ignore[assignment]
    RedisInstrumentor = None  # type: ignore[assignment]
    SQLAlchemyInstrumentor = None  # type: ignore[assignment]
    Tracer = Any  # type: ignore[assignment]

REQUEST_ID_HEADER = "X-Request-ID"
TRACE_ID_HEADER = "X-Trace-ID"

_request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)


@dataclass(frozen=True)
class TracingConfig:
    service_name: str = "dating-app"
    enable_otel: bool = True


def _new_id() -> str:
    return uuid.uuid4().hex


def get_request_id() -> str | None:
    return _request_id_var.get()


def get_trace_id() -> str | None:
    return _trace_id_var.get()


def set_request_context(request_id: str | None = None, trace_id: str | None = None) -> tuple[contextvars.Token[str | None] | None, contextvars.Token[str | None] | None]:
    request_token = _request_id_var.set(request_id) if request_id is not None else None
    trace_token = _trace_id_var.set(trace_id) if trace_id is not None else None
    return request_token, trace_token


def reset_request_context(tokens: tuple[contextvars.Token[str | None] | None, contextvars.Token[str | None] | None]) -> None:
    request_token, trace_token = tokens
    if request_token is not None:
        _request_id_var.reset(request_token)
    if trace_token is not None:
        _trace_id_var.reset(trace_token)


def ensure_request_context(request: Request | None = None) -> tuple[str, str]:
    request_id = request.headers.get(REQUEST_ID_HEADER) if request is not None else None
    request_id = (request_id or get_request_id() or _new_id()).strip()
    trace_id = get_trace_id() or _new_id()
    set_request_context(request_id=request_id, trace_id=trace_id)
    return request_id, trace_id


def add_correlation_headers(response: Response, request_id: str | None = None, trace_id: str | None = None) -> None:
    rid = request_id or get_request_id()
    tid = trace_id or get_trace_id()
    if rid:
        response.headers[REQUEST_ID_HEADER] = rid
    if tid:
        response.headers[TRACE_ID_HEADER] = tid


def instrument_app(app: Any, config: TracingConfig | None = None) -> None:
    config = config or TracingConfig()
    if not config.enable_otel or FastAPIInstrumentor is None:
        return
    try:
        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        logging.getLogger(__name__).exception("otel_fastapi_instrumentation_failed")


def instrument_httpx() -> None:
    if HTTPXClientInstrumentor is None:
        return
    try:
        HTTPXClientInstrumentor().instrument()
    except Exception:
        logging.getLogger(__name__).exception("otel_httpx_instrumentation_failed")


def instrument_redis() -> None:
    if RedisInstrumentor is None:
        return
    try:
        RedisInstrumentor().instrument()
    except Exception:
        logging.getLogger(__name__).exception("otel_redis_instrumentation_failed")


def instrument_sqlalchemy(engine: Any) -> None:
    if SQLAlchemyInstrumentor is None:
        return
    try:
        target_engine = getattr(engine, "sync_engine", engine)
        SQLAlchemyInstrumentor().instrument(engine=target_engine)
    except Exception:
        logging.getLogger(__name__).exception("otel_sqlalchemy_instrumentation_failed")


def get_tracer(name: str) -> Any:
    if trace is None:
        return None
    return trace.get_tracer(name)


def low_cardinality_label(value: str | None, default: str = "unknown") -> str:
    if not value:
        return default
    value = value.strip().lower()
    return value if len(value) <= 64 else value[:64]


def traceable(operation: str, **attributes: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = get_tracer(__name__)
            if tracer is None:
                return await func(*args, **kwargs)
            with tracer.start_as_current_span(operation) as span:
                for key, value in attributes.items():
                    span.set_attribute(key, low_cardinality_label(value))
                return await func(*args, **kwargs)
        return async_wrapper
    return decorator


def extract_trace_id_from_headers(headers: Mapping[str, str] | MutableMapping[str, str]) -> str | None:
    return headers.get(TRACE_ID_HEADER) if headers else None
