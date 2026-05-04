from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Callable, Literal

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

try:
    from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest
except ImportError as exc:  # pragma: no cover - dependency guard
    raise RuntimeError(
        "prometheus_client is required. Add it to requirements.txt before importing app.observability.metrics."
    ) from exc


SERVICE_NAME = os.getenv("SERVICE_NAME", "aken-api")
SERVICE_ENV = os.getenv("SERVICE_ENV", "production")

registry = CollectorRegistry(auto_describe=True)


def _counter(name: str, documentation: str, labelnames: tuple[str, ...] = ()) -> Counter:
    return Counter(name, documentation, labelnames=labelnames, registry=registry)


def _gauge(name: str, documentation: str, labelnames: tuple[str, ...] = ()) -> Gauge:
    return Gauge(name, documentation, labelnames=labelnames, registry=registry)


def _histogram(name: str, documentation: str, labelnames: tuple[str, ...] = (), buckets: tuple[float, ...] | None = None) -> Histogram:
    kwargs = {"labelnames": labelnames, "registry": registry}
    if buckets is not None:
        kwargs["buckets"] = buckets
    return Histogram(name, documentation, **kwargs)


API_REQUESTS_TOTAL = _counter(
    "aken_api_requests_total",
    "Total HTTP requests handled by the API",
    ("method", "endpoint", "status", "service", "env"),
)
API_REQUEST_LATENCY_SECONDS = _histogram(
    "aken_api_request_latency_seconds",
    "HTTP request latency in seconds",
    ("method", "endpoint", "status", "service", "env"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10),
)
API_REQUEST_EXCEPTIONS_TOTAL = _counter(
    "aken_api_request_exceptions_total",
    "Unhandled HTTP request exceptions",
    ("method", "endpoint", "exception", "service", "env"),
)

WEBSOCKET_CONNECTIONS_TOTAL = _counter(
    "aken_websocket_connections_total",
    "Total WebSocket connections accepted",
    ("endpoint", "event", "service", "env"),
)
WEBSOCKET_MESSAGES_TOTAL = _counter(
    "aken_websocket_messages_total",
    "WebSocket messages processed",
    ("endpoint", "direction", "message_type", "service", "env"),
)
WEBSOCKET_FAILURES_TOTAL = _counter(
    "aken_websocket_failures_total",
    "WebSocket failures by type",
    ("endpoint", "reason", "service", "env"),
)
WEBSOCKET_ACTIVE_CONNECTIONS = _gauge(
    "aken_websocket_active_connections",
    "Current active WebSocket connections",
    ("endpoint", "service", "env"),
)

AI_REQUESTS_TOTAL = _counter(
    "aken_ai_requests_total",
    "Total AI requests",
    ("model", "operation", "status", "provider", "service", "env"),
)
AI_LATENCY_SECONDS = _histogram(
    "aken_ai_latency_seconds",
    "AI request latency in seconds",
    ("model", "operation", "status", "provider", "service", "env"),
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30, 60),
)
AI_TOKEN_USAGE_TOTAL = _counter(
    "aken_ai_tokens_total",
    "AI token usage",
    ("model", "operation", "direction", "provider", "service", "env"),
)
AI_TIMEOUTS_TOTAL = _counter(
    "aken_ai_timeouts_total",
    "AI timeouts",
    ("model", "operation", "provider", "service", "env"),
)
AI_FALLBACKS_TOTAL = _counter(
    "aken_ai_fallbacks_total",
    "AI graceful degradation fallbacks used",
    ("operation", "fallback_type", "service", "env"),
)

DB_QUERY_LATENCY_SECONDS = _histogram(
    "aken_db_query_latency_seconds",
    "Database query latency in seconds",
    ("operation", "table", "status", "service", "env"),
    buckets=(0.005, 0.01, 0.02, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)
DB_LOCK_WAIT_SECONDS = _histogram(
    "aken_db_lock_wait_seconds",
    "Time spent waiting on DB locks",
    ("table", "operation", "service", "env"),
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)
DB_DEADLOCKS_TOTAL = _counter(
    "aken_db_deadlocks_total",
    "Deadlock occurrences",
    ("operation", "service", "env"),
)
DB_ERRORS_TOTAL = _counter(
    "aken_db_errors_total",
    "Database errors",
    ("operation", "error", "service", "env"),
)

REDIS_COMMAND_LATENCY_SECONDS = _histogram(
    "aken_redis_command_latency_seconds",
    "Redis command latency in seconds",
    ("command", "status", "service", "env"),
    buckets=(0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.25, 0.5, 1, 2),
)
REDIS_COMMANDS_TOTAL = _counter(
    "aken_redis_commands_total",
    "Redis command counts",
    ("command", "status", "service", "env"),
)
REDIS_HIT_RATIO = _gauge(
    "aken_redis_hit_ratio",
    "Redis cache hit ratio",
    ("cache_name", "service", "env"),
)
REDIS_MEMORY_BYTES = _gauge(
    "aken_redis_memory_bytes",
    "Redis memory used in bytes",
    ("instance", "service", "env"),
)
REDIS_ERRORS_TOTAL = _counter(
    "aken_redis_errors_total",
    "Redis errors",
    ("operation", "error", "service", "env"),
)

UPLOADS_TOTAL = _counter(
    "aken_uploads_total",
    "Upload attempts",
    ("media_type", "status", "source", "service", "env"),
)
UPLOAD_LATENCY_SECONDS = _histogram(
    "aken_upload_latency_seconds",
    "Upload latency in seconds",
    ("media_type", "status", "source", "service", "env"),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20),
)
UPLOAD_BYTES_TOTAL = _counter(
    "aken_upload_bytes_total",
    "Total upload bytes accepted",
    ("media_type", "source", "service", "env"),
)
UPLOAD_REJECTS_TOTAL = _counter(
    "aken_upload_rejects_total",
    "Rejected uploads",
    ("reason", "source", "service", "env"),
)

GEO_QUERY_LATENCY_SECONDS = _histogram(
    "aken_geo_query_latency_seconds",
    "Geospatial query latency in seconds",
    ("query", "status", "service", "env"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)
GEO_QUERY_CACHE_HIT_RATIO = _gauge(
    "aken_geo_query_cache_hit_ratio",
    "Geospatial cache hit ratio",
    ("query", "service", "env"),
)
GEO_QUERY_RESULTS_TOTAL = _counter(
    "aken_geo_query_results_total",
    "Geospatial query results returned",
    ("query", "status", "service", "env"),
)

COST_ESTIMATED_USD_TOTAL = _counter(
    "aken_cost_estimated_usd_total",
    "Estimated cost by vendor",
    ("vendor", "service", "env"),
)
COST_EVENTS_TOTAL = _counter(
    "aken_cost_events_total",
    "Cost tracking events",
    ("vendor", "category", "service", "env"),
)

SYSTEM_HEALTH = _gauge(
    "aken_system_health",
    "Overall system health score from 0 to 1",
    ("service", "env"),
)

SERVICE_TAGS = {"service": SERVICE_NAME, "env": SERVICE_ENV}


@dataclass(slots=True)
class MetricsContext:
    endpoint: str
    method: str
    status: str
    service: str = SERVICE_NAME
    env: str = SERVICE_ENV


def observe_http_request(endpoint: str, method: str, status: int | str, duration_seconds: float) -> None:
    status_str = str(status)
    labels = {"method": method.upper(), "endpoint": endpoint, "status": status_str, **SERVICE_TAGS}
    API_REQUESTS_TOTAL.labels(**labels).inc()
    API_REQUEST_LATENCY_SECONDS.labels(**labels).observe(duration_seconds)


def observe_http_exception(endpoint: str, method: str, exception: str) -> None:
    API_REQUEST_EXCEPTIONS_TOTAL.labels(
        method=method.upper(),
        endpoint=endpoint,
        exception=exception,
        **SERVICE_TAGS,
    ).inc()


def observe_websocket_event(endpoint: str, event: Literal["connect", "disconnect", "failure"], reason: str = "normal") -> None:
    if event == "connect":
        WEBSOCKET_CONNECTIONS_TOTAL.labels(endpoint=endpoint, event=event, **SERVICE_TAGS).inc()
        WEBSOCKET_ACTIVE_CONNECTIONS.labels(endpoint=endpoint, **SERVICE_TAGS).inc()
        return
    if event == "disconnect":
        WEBSOCKET_CONNECTIONS_TOTAL.labels(endpoint=endpoint, event=event, **SERVICE_TAGS).inc()
        WEBSOCKET_ACTIVE_CONNECTIONS.labels(endpoint=endpoint, **SERVICE_TAGS).dec()
        return
    WEBSOCKET_FAILURES_TOTAL.labels(endpoint=endpoint, reason=reason, **SERVICE_TAGS).inc()


def observe_websocket_message(endpoint: str, direction: Literal["in", "out"], message_type: str) -> None:
    WEBSOCKET_MESSAGES_TOTAL.labels(
        endpoint=endpoint,
        direction=direction,
        message_type=message_type,
        **SERVICE_TAGS,
    ).inc()


def observe_ai_request(model: str, operation: str, status: str, provider: str, duration_seconds: float, input_tokens: int | None = None, output_tokens: int | None = None) -> None:
    labels = {
        "model": model,
        "operation": operation,
        "status": status,
        "provider": provider,
        **SERVICE_TAGS,
    }
    AI_REQUESTS_TOTAL.labels(**labels).inc()
    AI_LATENCY_SECONDS.labels(**labels).observe(duration_seconds)
    if input_tokens is not None:
        AI_TOKEN_USAGE_TOTAL.labels(model=model, operation=operation, direction="input", provider=provider, **SERVICE_TAGS).inc(input_tokens)
    if output_tokens is not None:
        AI_TOKEN_USAGE_TOTAL.labels(model=model, operation=operation, direction="output", provider=provider, **SERVICE_TAGS).inc(output_tokens)


def observe_ai_timeout(model: str, operation: str, provider: str) -> None:
    AI_TIMEOUTS_TOTAL.labels(model=model, operation=operation, provider=provider, **SERVICE_TAGS).inc()


def observe_ai_fallback(operation: str, fallback_type: str) -> None:
    AI_FALLBACKS_TOTAL.labels(operation=operation, fallback_type=fallback_type, **SERVICE_TAGS).inc()


def observe_db_query(operation: str, table: str, duration_seconds: float, status: str = "ok") -> None:
    DB_QUERY_LATENCY_SECONDS.labels(operation=operation, table=table, status=status, **SERVICE_TAGS).observe(duration_seconds)


def observe_db_lock_wait(operation: str, table: str, duration_seconds: float) -> None:
    DB_LOCK_WAIT_SECONDS.labels(operation=operation, table=table, **SERVICE_TAGS).observe(duration_seconds)


def observe_db_deadlock(operation: str) -> None:
    DB_DEADLOCKS_TOTAL.labels(operation=operation, **SERVICE_TAGS).inc()


def observe_db_error(operation: str, error: str) -> None:
    DB_ERRORS_TOTAL.labels(operation=operation, error=error, **SERVICE_TAGS).inc()


def observe_redis_command(command: str, duration_seconds: float, status: str = "ok") -> None:
    REDIS_COMMAND_LATENCY_SECONDS.labels(command=command, status=status, **SERVICE_TAGS).observe(duration_seconds)
    REDIS_COMMANDS_TOTAL.labels(command=command, status=status, **SERVICE_TAGS).inc()


def set_redis_hit_ratio(cache_name: str, ratio: float) -> None:
    REDIS_HIT_RATIO.labels(cache_name=cache_name, **SERVICE_TAGS).set(ratio)


def set_redis_memory_bytes(instance: str, bytes_used: int) -> None:
    REDIS_MEMORY_BYTES.labels(instance=instance, **SERVICE_TAGS).set(bytes_used)


def observe_redis_error(operation: str, error: str) -> None:
    REDIS_ERRORS_TOTAL.labels(operation=operation, error=error, **SERVICE_TAGS).inc()


def observe_upload(media_type: str, status: str, source: str, duration_seconds: float, size_bytes: int | None = None) -> None:
    labels = {"media_type": media_type, "status": status, "source": source, **SERVICE_TAGS}
    UPLOADS_TOTAL.labels(**labels).inc()
    UPLOAD_LATENCY_SECONDS.labels(**labels).observe(duration_seconds)
    if size_bytes is not None and status == "success":
        UPLOAD_BYTES_TOTAL.labels(media_type=media_type, source=source, **SERVICE_TAGS).inc(size_bytes)


def reject_upload(reason: str, source: str) -> None:
    UPLOAD_REJECTS_TOTAL.labels(reason=reason, source=source, **SERVICE_TAGS).inc()


def observe_geo_query(query: str, duration_seconds: float, cache_hit_ratio: float | None = None, results: int | None = None, status: str = "ok") -> None:
    GEO_QUERY_LATENCY_SECONDS.labels(query=query, status=status, **SERVICE_TAGS).observe(duration_seconds)
    if cache_hit_ratio is not None:
        GEO_QUERY_CACHE_HIT_RATIO.labels(query=query, **SERVICE_TAGS).set(cache_hit_ratio)
    if results is not None:
        GEO_QUERY_RESULTS_TOTAL.labels(query=query, status=status, **SERVICE_TAGS).inc(results)


def observe_cost(vendor: str, category: str, estimated_usd: float) -> None:
    COST_EVENTS_TOTAL.labels(vendor=vendor, category=category, **SERVICE_TAGS).inc()
    COST_ESTIMATED_USD_TOTAL.labels(vendor=vendor, **SERVICE_TAGS).inc(estimated_usd)


def set_system_health(score: float) -> None:
    SYSTEM_HEALTH.labels(**SERVICE_TAGS).set(score)


@asynccontextmanager
async def metrics_timer(observer: Callable[[float], None]) -> AsyncIterator[None]:
    started = time.perf_counter()
    try:
        yield
    finally:
        observer(time.perf_counter() - started)


def build_metrics_router() -> APIRouter:
    router = APIRouter(tags=["metrics"])

    @router.get("/metrics", include_in_schema=False)
    async def metrics() -> PlainTextResponse:
        return PlainTextResponse(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    return router


class MonitoringMiddleware:
    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: dict) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            observe_http_exception(scope.get("path", "unknown"), request.method, exc.__class__.__name__)
            raise
        finally:
            duration = time.perf_counter() - start
            route = scope.get("route")
            endpoint = route.path if route is not None else scope.get("path", "unknown")
            observe_http_request(endpoint, request.method, status_code, duration)
