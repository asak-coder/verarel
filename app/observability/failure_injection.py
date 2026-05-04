"""Config-based failure injection helpers scoped to test users."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class FailureInjectionConfig:
    enabled: bool = False
    test_user_ids: tuple[str, ...] = ()
    fail_redis: bool = False
    fail_ai: bool = False
    fail_s3: bool = False
    fail_httpx: bool = False
    fail_db: bool = False

    @classmethod
    def from_env(cls) -> "FailureInjectionConfig":
        def _bool(name: str) -> bool:
            return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}

        ids = tuple(i.strip() for i in os.getenv("FAILURE_INJECTION_TEST_USERS", "").split(",") if i.strip())
        return cls(
            enabled=_bool("FAILURE_INJECTION_ENABLED"),
            test_user_ids=ids,
            fail_redis=_bool("FAILURE_INJECTION_REDIS"),
            fail_ai=_bool("FAILURE_INJECTION_AI"),
            fail_s3=_bool("FAILURE_INJECTION_S3"),
            fail_httpx=_bool("FAILURE_INJECTION_HTTPX"),
            fail_db=_bool("FAILURE_INJECTION_DB"),
        )


CONFIG = FailureInjectionConfig.from_env()


def is_test_user(user_id: str | None, config: FailureInjectionConfig | None = None) -> bool:
    config = config or CONFIG
    return bool(user_id and user_id in config.test_user_ids)


def should_inject(failure_key: str, user_id: str | None = None, config: FailureInjectionConfig | None = None) -> bool:
    config = config or CONFIG
    if not config.enabled or not is_test_user(user_id, config):
        return False
    return {
        "redis": config.fail_redis,
        "ai": config.fail_ai,
        "s3": config.fail_s3,
        "httpx": config.fail_httpx,
        "db": config.fail_db,
    }.get(failure_key, False)


def maybe_fail(failure_key: str, user_id: str | None = None, config: FailureInjectionConfig | None = None) -> None:
    if should_inject(failure_key, user_id=user_id, config=config):
        raise RuntimeError(f"Injected failure: {failure_key}")


def scoped_user_id(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
        candidate = getattr(value, "id", None) or getattr(value, "user_id", None)
        if candidate:
            return str(candidate)
    return None
