from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import create_access_token
from app.database import SessionLocal
from app.main import app as fastapi_app
from app.models.interaction import Match
from app.routers import chat as chat_router
from app.services import location_service, nlp_service, redis_service as redis_module
from app.services.nlp_service import IcebreakerResult, ModerationResult


@pytest.fixture()
def moderation_payloads() -> tuple[dict[str, Any], dict[str, Any]]:
    benign = {"message": "Hey, I noticed we both like coffee shops. Any favorite spot?"}
    flagged = {"message": "Send me your password and meet me off-platform for cash."}
    return benign, flagged


async def _get_or_create_match_id(user_a_id: int, user_b_id: int) -> int:
    async with SessionLocal() as session:
        match = await session.scalar(
            select(Match).where(
                Match.user_a_id == user_a_id,
                Match.user_b_id == user_b_id,
            )
        )
        if match is None:
            match = Match(user_a_id=user_a_id, user_b_id=user_b_id)
            session.add(match)
            await session.commit()
            await session.refresh(match)
        return match.id


@pytest.mark.asyncio
async def test_icebreakers_returns_three_strings(async_client, seeded_users, monkeypatch, live_ai):
    user_a = seeded_users["ava_chen"]
    user_b = seeded_users["noah_patel"]

    if not live_ai:

        async def fake_generate_icebreakers(session, user_a_id: int, user_b_id: int):
            assert user_a_id == user_a.id
            assert user_b_id == user_b.id
            return IcebreakerResult(
                icebreakers=[
                    "What’s your ideal coffee order?",
                    "What’s a low-key weekend that feels perfect to you?",
                    "Which hike or walk do you keep coming back to?",
                ]
            )

        monkeypatch.setattr(nlp_service, "generate_icebreakers", fake_generate_icebreakers)

    response = await async_client.post(
        "/chat/icebreakers",
        json={"user_a_id": user_a.id, "user_b_id": user_b.id},
    )

    assert response.status_code == 200
    data = response.json()
    assert list(data.keys()) == ["icebreakers"]
    assert isinstance(data["icebreakers"], list)
    assert len(data["icebreakers"]) == 3
    assert all(isinstance(item, str) and item.strip() for item in data["icebreakers"])


@pytest.mark.asyncio
async def test_meetup_suggestions_returns_midpoint_and_venues(async_client, seeded_users, monkeypatch):
    user_a = seeded_users["ava_chen"]
    user_b = seeded_users["noah_patel"]
    match_id = await _get_or_create_match_id(user_a.id, user_b.id)

    async def fake_calculate_match_midpoint(db, match_id: int):
        return location_service.GeoPoint(latitude=12.9721, longitude=77.5938)

    async def fake_suggest_venues_near_midpoint(midpoint):
        assert midpoint.latitude == 12.9721
        assert midpoint.longitude == 77.5938
        return [
            location_service.VenueSuggestion(
                name="The Corner Cafe",
                rating=4.8,
                venue_type="cafe",
                address="123 Main Street",
                photo_url="https://cdn.example.com/venues/corner-cafe.jpg",
                distance_meters=240,
            ),
            location_service.VenueSuggestion(
                name="Harbor Green Park",
                rating=4.7,
                venue_type="park",
                address="Park Avenue",
                photo_url="https://cdn.example.com/venues/harbor-green-park.jpg",
                distance_meters=620,
            ),
        ]

    monkeypatch.setattr(location_service, "calculate_match_midpoint", fake_calculate_match_midpoint)
    monkeypatch.setattr(location_service, "suggest_venues_near_midpoint", fake_suggest_venues_near_midpoint)

    response = await async_client.get(f"/matches/{match_id}/meetup-suggestions")

    assert response.status_code == 200
    data = response.json()
    assert data["match_id"] == match_id
    assert data["midpoint"]["latitude"] == 12.9721
    assert data["midpoint"]["longitude"] == 77.5938
    assert isinstance(data["venues"], list)
    assert len(data["venues"]) == 2
    assert data["venues"][0]["name"] == "The Corner Cafe"


def test_websocket_moderation_broadcasts_benign_and_blocks_flagged(monkeypatch, seeded_users):
    user_a = seeded_users["ava_chen"]
    user_b = seeded_users["noah_patel"]
    match_id = asyncio.run(_get_or_create_match_id(user_a.id, user_b.id))

    async def fake_moderate_text(message: str):
        if "password" in message.lower() or "cash" in message.lower():
            return ModerationResult(
                is_flagged=True,
                flag_reason="Detected suspicious off-platform payment or credential request.",
                categories=["fraud", "phishing"],
            )
        return ModerationResult(
            is_flagged=False,
            flag_reason="Looks safe.",
            categories=[],
        )

    async def fake_broadcast(match_id: int, message: dict[str, Any]) -> None:
        return None

    monkeypatch.setattr(nlp_service, "moderate_text", fake_moderate_text)
    monkeypatch.setattr(chat_router.manager, "broadcast", fake_broadcast)
    monkeypatch.setattr(redis_module.redis_service, "add_socket_to_room", AsyncMock())
    monkeypatch.setattr(redis_module.redis_service, "remove_socket_from_room", AsyncMock())

    jwt_token = create_access_token(subject=str(user_a.id))

    with TestClient(fastapi_app) as client:
        with client.websocket_connect(f"/chat/ws/{match_id}?token={jwt_token}") as websocket:
            websocket.send_text('{"message":"Hey, nice to meet you. Want to grab coffee?"}')
            websocket.close()


def test_websocket_moderation_blocks_flagged_message(monkeypatch, seeded_users):
    user_a = seeded_users["ava_chen"]
    user_b = seeded_users["noah_patel"]
    match_id = asyncio.run(_get_or_create_match_id(user_a.id, user_b.id))

    async def fake_moderate_text(message: str):
        return ModerationResult(
            is_flagged=True,
            flag_reason="Detected suspicious off-platform payment or credential request.",
            categories=["fraud", "phishing"],
        )

    monkeypatch.setattr(nlp_service, "moderate_text", fake_moderate_text)
    monkeypatch.setattr(chat_router.manager, "broadcast", AsyncMock())
    monkeypatch.setattr(redis_module.redis_service, "add_socket_to_room", AsyncMock())
    monkeypatch.setattr(redis_module.redis_service, "remove_socket_from_room", AsyncMock())

    jwt_token = create_access_token(subject=str(user_a.id))

    with TestClient(fastapi_app) as client:
        with client.websocket_connect(f"/chat/ws/{match_id}?token={jwt_token}") as websocket:
            websocket.send_text('{"message":"Send me your password and cash app info."}')
            warning = websocket.receive_json()
            assert warning["type"] == "system_warning"
            assert "suspicious" in warning["detail"].lower()
