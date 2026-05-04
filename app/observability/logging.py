"""Structured JSON logging helpers with request/trace correlation."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Mapping

from app.observability.tracing import get_request_id, get_trace_id


@dataclass(frozen=True)
class LogContext:
    request_id: str | None = None
    trace_id: str | None = None
    service: str | None = None


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None) or get_request_id()
        trace_id = getattr(record, "trace_id", None) or get_trace_id()
        if request_id:
            payload["request_id"] = request_id
        if trace_id:
            payload["trace_id"] = trace_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_json_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str, **context: Any) -> logging.LoggerAdapter:
    return logging.LoggerAdapter(logging.getLogger(name), context)


def bind_log_context(**kwargs: Any) -> dict[str, Any]:
    payload = {k: v for k, v in kwargs.items() if v is not None}
    if get_request_id() and "request_id" not in payload:
        payload["request_id"] = get_request_id()
    if get_trace_id() and "trace_id" not in payload:
        payload["trace_id"] = get_trace_id()
    return payload


def log_event(logger: logging.Logger, message: str, **fields: Any) -> None:
    logger.info(message, extra=bind_log_context(**fields))
