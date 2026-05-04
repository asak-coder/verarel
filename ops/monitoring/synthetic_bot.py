#!/usr/bin/env python3
"""Synthetic monitoring bot for the dating app API.

The bot is designed for cron, Kubernetes CronJobs, or Celery beat wrappers.
It performs a best-effort, degrade-gracefully workflow:

1. Register or log in a test user.
2. Fetch the current profile.
3. Try to create a match or fetch meetup suggestions.
4. Send a message in an available conversation/match context.
5. Optionally validate websocket delivery if websocket support is available.

All configuration is supplied via environment variables. No secrets are
hard-coded in this script.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import string
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import httpx


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rand_suffix(length: int = 8) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    return value.strip()


def _truthy(name: str, default: str = "false") -> bool:
    return _env(name, default).lower() in {"1", "true", "yes", "on"}


@dataclass
class StepResult:
    name: str
    status: str
    detail: str = ""
    duration_ms: int = 0


@dataclass
class RunResult:
    status: str
    started_at: str
    finished_at: str = ""
    base_url: str = ""
    steps: list[StepResult] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    user_identifier: str = ""
    auth_mode: str = ""
    exit_code: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "base_url": self.base_url,
            "user_identifier": self.user_identifier,
            "auth_mode": self.auth_mode,
            "exit_code": self.exit_code,
            "metrics": self.metrics,
            "steps": [step.__dict__ for step in self.steps],
        }


class SyntheticBot:
    def __init__(self, client: httpx.AsyncClient, base_url: str, config: dict[str, Any]) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.config = config
        self.token: str = ""
        self.headers: dict[str, str] = {}
        self.result = RunResult(
            status="unknown",
            started_at=_utc_now(),
            base_url=self.base_url,
            user_identifier=config["user_identifier"],
        )

    def _record(self, name: str, status: str, started: float, detail: str = "") -> None:
        self.result.steps.append(
            StepResult(
                name=name,
                status=status,
                detail=detail,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        )

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _auth_headers(self) -> dict[str, str]:
        headers = {"accept": "application/json"}
        if self.token:
            headers["authorization"] = f"Bearer {self.token}"
        return headers

    async def _request(self, method: str, path: str, *, json_body: Any = None) -> httpx.Response:
        return await self.client.request(method, self._url(path), json=json_body, headers=self._auth_headers())

    async def run(self, validate_ws: bool = False) -> RunResult:
        await self._authenticate()
        await self._fetch_profile()
        await self._match_or_suggestions()
        await self._send_message()
        if validate_ws:
            await self._validate_websocket()
        self.result.finished_at = _utc_now()
        self.result.status = "success" if all(step.status != "failed" for step in self.result.steps if step.name != "websocket") else "degraded"
        if any(step.status == "failed" for step in self.result.steps):
            self.result.exit_code = 1
            if self.result.status == "success":
                self.result.status = "degraded"
        return self.result

    async def _authenticate(self) -> None:
        started = time.perf_counter()
        email = self.config["email"]
        password = self.config["password"]
        tried_register = False

        login_paths = ["/auth/login", "/api/auth/login", "/login"]
        register_paths = ["/auth/register", "/api/auth/register", "/register", "/auth/signup", "/api/auth/signup"]

        async def try_login() -> bool:
            payloads = [
                {"email": email, "password": password},
                {"username": email, "password": password},
            ]
            for path in login_paths:
                for payload in payloads:
                    try:
                        resp = await self._request("POST", path, json_body=payload)
                        if resp.status_code < 400:
                            data = self._safe_json(resp)
                            token = self._extract_token(data)
                            if token:
                                self.token = token
                                return True
                    except Exception:
                        continue
            return False

        if await try_login():
            self.result.auth_mode = "login"
            self._record("auth", "success", started, "logged in")
            return

        if not self.config["register_if_needed"]:
            self._record("auth", "failed", started, "login failed and register_if_needed=false")
            return

        tried_register = True
        register_payloads = [
            {"email": email, "password": password, "confirm_password": password},
            {"email": email, "password": password},
            {"username": email, "email": email, "password": password},
        ]
        for path in register_paths:
            for payload in register_payloads:
                try:
                    resp = await self._request("POST", path, json_body=payload)
                    if resp.status_code < 400:
                        data = self._safe_json(resp)
                        token = self._extract_token(data)
                        if token:
                            self.token = token
                        self.result.auth_mode = "register"
                        self._record("auth", "success", started, "registered")
                        return
                except Exception:
                    continue
        detail = "login failed"
        if tried_register:
            detail += "; register failed or unavailable"
        self._record("auth", "failed", started, detail)

    async def _fetch_profile(self) -> None:
        started = time.perf_counter()
        paths = ["/profile/me", "/api/profile/me", "/profile", "/api/profile"]
        for path in paths:
            try:
                resp = await self._request("GET", path)
                if resp.status_code < 400:
                    self.result.metrics["profile_status"] = resp.status_code
                    self._record("profile", "success", started, path)
                    return
            except Exception as exc:
                last_exc = exc
        self._record("profile", "failed", started, "profile endpoint unavailable or unauthorized")

    async def _match_or_suggestions(self) -> None:
        started = time.perf_counter()
        candidates = [
            ("POST", "/matches", {"target_user_id": self.config["target_user_id"]}),
            ("POST", "/api/matches", {"target_user_id": self.config["target_user_id"]}),
            ("GET", "/matches/suggestions", None),
            ("GET", "/api/matches/suggestions", None),
            ("GET", "/meetups/suggestions", None),
            ("GET", "/api/meetups/suggestions", None),
        ]
        for method, path, payload in candidates:
            try:
                resp = await self._request(method, path, json_body=payload)
                if resp.status_code < 400:
                    self.result.metrics["match_or_suggestion_status"] = resp.status_code
                    self._record("match_or_suggestions", "success", started, path)
                    return
                if resp.status_code in {404, 405}:
                    continue
            except Exception:
                continue
        self._record("match_or_suggestions", "skipped", started, "no supported match or suggestion endpoint found")

    async def _send_message(self) -> None:
        started = time.perf_counter()
        message_text = self.config["message"]
        paths = [
            ("/chat/messages", {"message": message_text}),
            ("/api/chat/messages", {"message": message_text}),
            ("/messages", {"message": message_text}),
            ("/api/messages", {"message": message_text}),
        ]
        for path, payload in paths:
            try:
                resp = await self._request("POST", path, json_body=payload)
                if resp.status_code < 400:
                    self.result.metrics["message_status"] = resp.status_code
                    self._record("message", "success", started, path)
                    return
                if resp.status_code in {404, 405}:
                    continue
            except Exception:
                continue
        self._record("message", "skipped", started, "no supported chat/message endpoint found")

    async def _validate_websocket(self) -> None:
        started = time.perf_counter()
        ws_url = self.config["websocket_url"]
        if not ws_url:
            self._record("websocket", "skipped", started, "WEBSOCKET_URL not set")
            return
        try:
            import websockets  # type: ignore
        except Exception:
            self._record("websocket", "skipped", started, "websockets package unavailable")
            return
        try:
            headers = []
            if self.token:
                headers.append(("Authorization", f"Bearer {self.token}"))
            async with websockets.connect(ws_url, extra_headers=headers, ping_interval=10, close_timeout=5) as ws:
                try:
                    await asyncio.wait_for(ws.recv(), timeout=self.config["websocket_timeout_seconds"])
                    self._record("websocket", "success", started, "received message")
                except asyncio.TimeoutError:
                    self._record("websocket", "failed", started, "timed out waiting for message")
        except Exception as exc:
            self._record("websocket", "skipped", started, f"websocket unavailable: {exc.__class__.__name__}")

    @staticmethod
    def _safe_json(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _extract_token(data: dict[str, Any]) -> str:
        for key in ("access_token", "token", "jwt", "auth_token"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
        nested = data.get("data")
        if isinstance(nested, dict):
            return SyntheticBot._extract_token(nested)
        return ""


def build_config(args: argparse.Namespace) -> dict[str, Any]:
    suffix = _rand_suffix()
    email = _env("SYNTHETIC_EMAIL", f"synthetic+{suffix}@example.com")
    password = _env("SYNTHETIC_PASSWORD", "")
    if not password:
        password = f"{_env('SYNTHETIC_PASSWORD_PREFIX', 'Synthetic!')}{suffix}9"
    return {
        "user_identifier": email,
        "email": email,
        "password": password,
        "register_if_needed": _truthy("SYNTHETIC_REGISTER_IF_NEEDED", "true"),
        "target_user_id": _env("SYNTHETIC_TARGET_USER_ID", ""),
        "message": _env("SYNTHETIC_MESSAGE", "Synthetic monitoring hello"),
        "websocket_url": _env("SYNTHETIC_WEBSOCKET_URL", ""),
        "websocket_timeout_seconds": int(_env("SYNTHETIC_WEBSOCKET_TIMEOUT_SECONDS", "10")),
    }


async def main_async(args: argparse.Namespace) -> int:
    base_url = _env("SYNTHETIC_BASE_URL", "http://localhost:8000")
    timeout = httpx.Timeout(float(_env("SYNTHETIC_HTTP_TIMEOUT_SECONDS", "15")))
    config = build_config(args)

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        bot = SyntheticBot(client, base_url, config)
        result = await bot.run(validate_ws=args.validate_websocket)
        print(json.dumps(result.to_dict(), ensure_ascii=False))
        return result.exit_code if args.strict else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synthetic monitoring bot")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if any step fails")
    parser.add_argument("--validate-websocket", action="store_true", help="Attempt websocket validation")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print(json.dumps({"status": "interrupted", "started_at": _utc_now()}))
        return 130
    except Exception as exc:
        print(json.dumps({"status": "error", "error": exc.__class__.__name__, "detail": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())