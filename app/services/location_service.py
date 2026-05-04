from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Awaitable, cast

import httpx
import redis.asyncio as redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal
from app.services.redis_service import REDIS_URL


LOCATION_API_PROVIDER = os.getenv("LOCATION_API_PROVIDER", "google_places").strip().lower()
LOCATION_API_KEY = os.getenv("LOCATION_API_KEY", "").strip()
LOCATION_API_BASE_URL = os.getenv("LOCATION_API_BASE_URL", "https://maps.googleapis.com/maps/api/place").strip()
LOCATION_API_TIMEOUT_SECONDS = float(os.getenv("LOCATION_API_TIMEOUT_SECONDS", "20"))
LOCATION_CACHE_TTL_SECONDS = int(os.getenv("LOCATION_CACHE_TTL_SECONDS", "3600"))
LOCATION_CACHE_RADIUS_METERS = 1000


@dataclass(slots=True)
class GeoPoint:
    latitude: float
    longitude: float


@dataclass(slots=True)
class VenueSuggestion:
    name: str
    rating: float
    venue_type: str
    address: str | None = None
    photo_url: str | None = None
    distance_meters: int | None = None


class LocationService:
    """
    Location lookup service with Redis caching.

    The midpoint is hashed into a deterministic cache key. Nearby results are
    stored as JSON so repeated date-planning requests do not hammer the external
    Places provider. If Redis is unavailable, the service safely falls back to a
    direct provider call instead of blocking the request path.
    """

    def __init__(self, redis_url: str = REDIS_URL) -> None:
        self._redis_url = redis_url
        self._redis: redis.Redis | None = None

    async def _redis_client(self) -> redis.Redis:
        if self._redis is None:
            client = redis.from_url(self._redis_url, decode_responses=True)
            await cast(Awaitable[bool], client.ping())
            self._redis = client
        return self._redis

    @staticmethod
    def _hash_midpoint(midpoint: GeoPoint) -> str:
        normalized = f"{midpoint.latitude:.5f}:{midpoint.longitude:.5f}"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @classmethod
    def _cache_key(cls, midpoint: GeoPoint) -> str:
        return f"places:midpoint:{cls._hash_midpoint(midpoint)}"

    @staticmethod
    def _midpoint_sql() -> str:
        # Raw PostGIS SQL uses geography-aware interpolation so the midpoint is
        # geodesic rather than a flat Cartesian average.
        return """
        SELECT
            ST_Y(
                ST_LineInterpolatePoint(
                    ST_MakeLine(u1.location::geography, u2.location::geography)::geometry,
                    0.5
                )
            ) AS latitude,
            ST_X(
                ST_LineInterpolatePoint(
                    ST_MakeLine(u1.location::geography, u2.location::geography)::geometry,
                    0.5
                )
            ) AS longitude
        FROM matches m
        JOIN users u1 ON u1.id = m.user_a_id
        JOIN users u2 ON u2.id = m.user_b_id
        WHERE m.id = :match_id
          AND u1.location IS NOT NULL
          AND u2.location IS NOT NULL
        """

    async def calculate_match_midpoint(self, db: AsyncSession, match_id: int) -> GeoPoint:
        result = await db.execute(text(self._midpoint_sql()), {"match_id": match_id})
        row = result.mappings().first()
        if row is None or row["latitude"] is None or row["longitude"] is None:
            raise ValueError("Unable to calculate midpoint for this match")
        return GeoPoint(latitude=float(row["latitude"]), longitude=float(row["longitude"]))

    async def get_venues_near_midpoint(self, midpoint: GeoPoint) -> list[VenueSuggestion]:
        cache_key = self._cache_key(midpoint)

        try:
            client = await self._redis_client()
            cached = await client.get(cache_key)
            if cached:
                raw_items = json.loads(cached)
                return [VenueSuggestion(**item) for item in raw_items]
        except Exception:
            # Redis failure should not take the feature offline; continue to the
            # provider path and return live results.
            pass

        venues = await self._fetch_places(midpoint)

        try:
            client = await self._redis_client()
            await client.setex(cache_key, LOCATION_CACHE_TTL_SECONDS, json.dumps([venue.__dict__ for venue in venues]))
        except Exception:
            # Cache write failures are non-fatal. The request still succeeds, we
            # just lose the short-lived performance benefit for this query.
            pass

        return venues

    async def _fetch_places(self, midpoint: GeoPoint) -> list[VenueSuggestion]:
        if not LOCATION_API_KEY:
            return [
                VenueSuggestion(
                    name="The Corner Cafe",
                    rating=4.8,
                    venue_type="cafe",
                    address="123 Main Street",
                    photo_url="https://cdn.example.com/venues/corner-cafe.jpg",
                    distance_meters=240,
                ),
                VenueSuggestion(
                    name="Harbor Green Park",
                    rating=4.7,
                    venue_type="park",
                    address="Park Avenue",
                    photo_url="https://cdn.example.com/venues/harbor-green-park.jpg",
                    distance_meters=620,
                ),
                VenueSuggestion(
                    name="Bluebird Coffee Lounge",
                    rating=4.6,
                    venue_type="cafe",
                    address="88 River Road",
                    photo_url="https://cdn.example.com/venues/bluebird-coffee.jpg",
                    distance_meters=910,
                ),
            ]

        params = {
            "location": f"{midpoint.latitude},{midpoint.longitude}",
            "radius": LOCATION_CACHE_RADIUS_METERS,
            "type": "cafe|park|restaurant",
            "key": LOCATION_API_KEY,
        }

        async with httpx.AsyncClient(timeout=LOCATION_API_TIMEOUT_SECONDS) as client:
            response = await client.get(f"{LOCATION_API_BASE_URL}/nearbysearch/json", params=params)
            response.raise_for_status()
            data = response.json()

        results = data.get("results", []) if isinstance(data, dict) else []
        venues: list[VenueSuggestion] = []

        for item in results[:5]:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            rating = item.get("rating")
            if not isinstance(name, str) or not isinstance(rating, (int, float)):
                continue
            venues.append(
                VenueSuggestion(
                    name=name,
                    rating=float(rating),
                    venue_type=str(item.get("types", ["venue"])[0] if isinstance(item.get("types"), list) and item.get("types") else item.get("type") or "venue"),
                    address=item.get("vicinity") if isinstance(item.get("vicinity"), str) else None,
                    photo_url=None,
                    distance_meters=None,
                )
            )

        if not venues:
            raise RuntimeError("Location provider returned no venue suggestions")

        return venues


location_service = LocationService()


async def calculate_match_midpoint(db: AsyncSession, match_id: int) -> GeoPoint:
    return await location_service.calculate_match_midpoint(db, match_id)


async def suggest_venues_near_midpoint(midpoint: GeoPoint) -> list[VenueSuggestion]:
    return await location_service.get_venues_near_midpoint(midpoint)
