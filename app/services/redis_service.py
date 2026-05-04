from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator

import redis.asyncio as redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SWIPE_TTL_SECONDS = int(os.getenv("SWIPE_TTL_SECONDS", "2592000"))  # 30 days
MATCH_TTL_SECONDS = int(os.getenv("MATCH_TTL_SECONDS", "2592000"))
FLUSH_INTERVAL_SECONDS = int(os.getenv("SWIPE_FLUSH_INTERVAL_SECONDS", "300"))  # 5 minutes


@dataclass(slots=True)
class SwipeEvent:
    swiped_by: int
    swiped_on: int
    action: str
    created_at: str


class RedisService:
    """
    Redis-backed fast path for swipe coordination and WebSocket presence.

    Key structure:
    - likes:{user_id} -> SET of user_ids this user has liked
    - passes:{user_id} -> SET of user_ids this user has passed
    - swipe_events -> STREAM of swipe events for async flushing into PostgreSQL
    - match:{user_a}:{user_b} -> STRING marker to dedupe mutual match handling
    - room:{match_id} -> SET of connected websocket client identifiers
    """

    def __init__(self, url: str = REDIS_URL) -> None:
        self._url = url
        self._client: redis.Redis | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> redis.Redis:
        async with self._lock:
            if self._client is None:
                self._client = redis.from_url(self._url, decode_responses=True)
                await self._client.ping()
        return self._client

    async def close(self) -> None:
        async with self._lock:
            if self._client is not None:
                await self._client.aclose()
                self._client = None

    async def _redis(self) -> redis.Redis:
        return await self.connect()

    @staticmethod
    def likes_key(user_id: int) -> str:
        return f"likes:{user_id}"

    @staticmethod
    def passes_key(user_id: int) -> str:
        return f"passes:{user_id}"

    @staticmethod
    def match_key(user_a_id: int, user_b_id: int) -> str:
        low, high = sorted((user_a_id, user_b_id))
        return f"match:{low}:{high}"

    @staticmethod
    def room_key(match_id: int) -> str:
        return f"room:{match_id}"

    @staticmethod
    def _event_payload(swiped_by: int, swiped_on: int, action: str) -> dict[str, str]:
        return {
            "swiped_by": str(swiped_by),
            "swiped_on": str(swiped_on),
            "action": action,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    async def record_swipe(self, swiped_by: int, swiped_on: int, action: str) -> None:
        client = await self._redis()
        pipe = client.pipeline(transaction=False)

        if action == "like":
            pipe.sadd(self.likes_key(swiped_by), swiped_on)
            pipe.expire(self.likes_key(swiped_by), SWIPE_TTL_SECONDS)
        elif action == "pass":
            pipe.sadd(self.passes_key(swiped_by), swiped_on)
            pipe.expire(self.passes_key(swiped_by), SWIPE_TTL_SECONDS)
        else:
            raise ValueError("action must be either 'like' or 'pass'")

        pipe.xadd("swipe_events", self._event_payload(swiped_by, swiped_on, action), maxlen=100000, approximate=True)
        await pipe.execute()

    async def has_liked(self, user_id: int, target_user_id: int) -> bool:
        client = await self._redis()
        return bool(await client.sismember(self.likes_key(user_id), target_user_id))

    async def has_passed(self, user_id: int, target_user_id: int) -> bool:
        client = await self._redis()
        return bool(await client.sismember(self.passes_key(user_id), target_user_id))

    async def mark_match_seen(self, user_a_id: int, user_b_id: int) -> bool:
        client = await self._redis()
        key = self.match_key(user_a_id, user_b_id)
        created = await client.set(key, "1", nx=True, ex=MATCH_TTL_SECONDS)
        return bool(created)

    async def add_socket_to_room(self, match_id: int, connection_id: str) -> None:
        client = await self._redis()
        key = self.room_key(match_id)
        await client.sadd(key, connection_id)
        await client.expire(key, MATCH_TTL_SECONDS)

    async def remove_socket_from_room(self, match_id: int, connection_id: str) -> None:
        client = await self._redis()
        key = self.room_key(match_id)
        await client.srem(key, connection_id)

    async def fetch_pending_swipe_events(self, count: int = 1000) -> list[SwipeEvent]:
        client = await self._redis()
        entries = await client.xread({"swipe_events": "0-0"}, count=count, block=1)
        events: list[SwipeEvent] = []
        for _, items in entries:
            for _, fields in items:
                events.append(
                    SwipeEvent(
                        swiped_by=int(fields["swiped_by"]),
                        swiped_on=int(fields["swiped_on"]),
                        action=str(fields["action"]),
                        created_at=str(fields["created_at"]),
                    )
                )
        return events

    async def trim_swipe_stream(self, max_length: int = 5000) -> None:
        client = await self._redis()
        await client.xtrim("swipe_events", maxlen=max_length, approximate=True)

    async def session(self) -> AsyncIterator[redis.Redis]:
        client = await self._redis()
        yield client


redis_service = RedisService()
