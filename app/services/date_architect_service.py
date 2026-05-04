from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.models.interaction import Match
from app.models.user import User

LOCATION_API_PROVIDER = os.getenv("LOCATION_API_PROVIDER", "mock").strip().lower()
LOCATION_API_KEY = os.getenv("LOCATION_API_KEY", "").strip()
LOCATION_API_BASE_URL = os.getenv("LOCATION_API_BASE_URL", "https://api.example-location.com/v1").strip()
LOCATION_API_TIMEOUT_SECONDS = float(os.getenv("LOCATION_API_TIMEOUT_SECONDS", "8"))
LOCATION_API_ALLOWED_HOSTS = {
    "api.example-location.com",
    "places.googleapis.com",
    "maps.googleapis.com",
    "api.foursquare.com",
    "foursquare.com",
}
LOCATION_API_ALLOWED_SCHEMES = {"https"}
MAX_VENUE_RESULTS = 3


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


def _truncate_4_decimals(value: float) -> float:
    return float(f"{value:.4f}")


def obfuscate_point(point: GeoPoint) -> GeoPoint:
    return GeoPoint(
        latitude=_truncate_4_decimals(point.latitude),
        longitude=_truncate_4_decimals(point.longitude),
    )


def _validate_outbound_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in LOCATION_API_ALLOWED_SCHEMES:
        raise ValueError("Only https outbound requests are allowed")
    if parsed.hostname not in LOCATION_API_ALLOWED_HOSTS:
        raise ValueError("Outbound host is not allowlisted")
    if parsed.username or parsed.password:
        raise ValueError("Credentials in outbound URLs are not allowed")
    if parsed.path and re.search(r"//", parsed.path):
        raise ValueError("Malformed outbound URL path")


async def _request_json(client: httpx.AsyncClient, url: str, *, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    _validate_outbound_url(url)

    async for attempt in AsyncRetrying(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.4, min=0.4, max=2.0),
        reraise=True,
    ):
        with attempt:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Invalid provider payload")
            return payload

    raise RuntimeError("Location provider request failed")


async def calculate_match_midpoint(db: AsyncSession, match_id: int) -> GeoPoint:
    query = text(
        """
        SELECT
            ST_Y(
                ST_AsText(
                    ST_Transform(
                        ST_LineInterpolatePoint(
                            ST_MakeLine(
                                ARRAY[
                                    ST_SetSRID(ST_MakePoint(ST_X(u1.location::geometry), ST_Y(u1.location::geometry)), 4326)::geography,
                                    ST_SetSRID(ST_MakePoint(ST_X(u2.location::geometry), ST_Y(u2.location::geometry)), 4326)::geography
                                ]::geography[]
                            ),
                            0.5
                        )::geometry,
                        4326
                    )
                )::geometry
            ) AS latitude,
            ST_X(
                ST_AsText(
                    ST_Transform(
                        ST_LineInterpolatePoint(
                            ST_MakeLine(
                                ARRAY[
                                    ST_SetSRID(ST_MakePoint(ST_X(u1.location::geometry), ST_Y(u1.location::geometry)), 4326)::geography,
                                    ST_SetSRID(ST_MakePoint(ST_X(u2.location::geometry), ST_Y(u2.location::geometry)), 4326)::geography
                                ]::geography[]
                            ),
                            0.5
                        )::geometry,
                        4326
                    )
                )::geometry
            ) AS longitude
        FROM matches m
        JOIN users u1 ON u1.id = m.user_a_id
        JOIN users u2 ON u2.id = m.user_b_id
        WHERE m.id = :match_id
          AND m.status = 'verified'
          AND u1.location IS NOT NULL
          AND u2.location IS NOT NULL
        """
    )

    result = await db.execute(query, {"match_id": match_id})
    row = result.mappings().first()
    if row is None or row["latitude"] is None or row["longitude"] is None:
        raise ValueError("Unable to calculate midpoint for this match")

    return obfuscate_point(
        GeoPoint(latitude=float(row["latitude"]), longitude=float(row["longitude"]))
    )


async def get_verified_match_participants(db: AsyncSession, match_id: int, current_user_id: int, target_user_id: int) -> Match:
    match = await db.scalar(
        select(Match).where(
            Match.id == match_id,
            Match.status == "verified",
            ((Match.user_a_id == current_user_id) & (Match.user_b_id == target_user_id))
            | ((Match.user_a_id == target_user_id) & (Match.user_b_id == current_user_id)),
        )
    )
    if match is None:
        raise ValueError("Verified match not found for the requested users")
    return match


async def get_match_by_participants(db: AsyncSession, current_user_id: int, target_user_id: int) -> Match:
    match = await db.scalar(
        select(Match).where(
            Match.status == "verified",
            ((Match.user_a_id == current_user_id) & (Match.user_b_id == target_user_id))
            | ((Match.user_a_id == target_user_id) & (Match.user_b_id == current_user_id)),
        )
    )
    if match is None:
        raise ValueError("Verified match not found")
    return match


async def suggest_venues_near_midpoint(midpoint: GeoPoint) -> list[VenueSuggestion]:
    if not LOCATION_API_KEY or LOCATION_API_PROVIDER == "mock":
        return [
            VenueSuggestion(
                name="Harbor Light Cafe",
                rating=4.9,
                venue_type="cafe",
                address="120 Market Street",
                photo_url="https://cdn.example.com/venues/harbor-light-cafe.jpg",
                distance_meters=180,
            ),
            VenueSuggestion(
                name="Central Garden Park",
                rating=4.8,
                venue_type="park",
                address="8 Garden Lane",
                photo_url="https://cdn.example.com/venues/central-garden-park.jpg",
                distance_meters=540,
            ),
            VenueSuggestion(
                name="Blue Hour Bistro",
                rating=4.7,
                venue_type="restaurant",
                address="44 Riverfront Drive",
                photo_url="https://cdn.example.com/venues/blue-hour-bistro.jpg",
                distance_meters=860,
            ),
        ]

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {LOCATION_API_KEY}",
    }
    params = {
        "lat": midpoint.latitude,
        "lng": midpoint.longitude,
        "radius": 2000,
        "limit": MAX_VENUE_RESULTS,
        "categories": "cafe,park,restaurant",
    }

    async with httpx.AsyncClient(timeout=LOCATION_API_TIMEOUT_SECONDS) as client:
        payload = await _request_json(
            client,
            f"{LOCATION_API_BASE_URL}/places/nearby",
            params=params,
            headers=headers,
        )

    items = payload.get("results", [])
    suggestions: list[VenueSuggestion] = []

    if not isinstance(items, list):
        raise RuntimeError("Location provider returned an invalid response")

    for item in items[:MAX_VENUE_RESULTS]:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        rating = item.get("rating")
        if not isinstance(name, str) or not isinstance(rating, (int, float)):
            continue

        distance = item.get("distance_meters")
        suggestions.append(
            VenueSuggestion(
                name=name,
                rating=float(rating),
                venue_type=str(item.get("type") or item.get("category") or "venue"),
                address=item.get("address") if isinstance(item.get("address"), str) else None,
                photo_url=item.get("photo_url") if isinstance(item.get("photo_url"), str) else None,
                distance_meters=int(distance) if isinstance(distance, int) else None,
            )
        )

    if not suggestions:
        raise RuntimeError("Location provider returned no venue suggestions")

    return suggestions
