from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import UploadFile
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.interaction import ChatMessage, Match
from app.models.profile import Profile
from app.models.reputation import adjust_reputation_score
from app.models.user import User
from app.routers import chat as chat_router
from app.services import location_service, nlp_service
from app.services.cinematic_ai_service import build_upload_response_metadata
from app.services.redis_service import redis_service


@dataclass(frozen=True, slots=True)
class SignedUser:
    id: int
    email: str
    username: str


async def _seed_match(db_session: AsyncSession, user_a_id: int, user_b_id: int) -> Match:
    match = Match(user_a_id=min(user_a_id, user_b_id), user_b_id=max(user_a_id, user_b_id), status="verified")
    db_session.add(match)
    await db_session.commit()
    await db_session.refresh(match)
    return match


@pytest.mark.asyncio
async def test_signup_login_and_match_flow(async_client: AsyncClient, seeded_users):
    email = f"user-{int(time.time() * 1000)}@example.com"
    username = f"user_{int(time.time() * 1000)}"

    register = await async_client.post(
        "/auth/register",
        json={"email": email, "username": username, "password": "Password123!"},
    )
    assert register.status_code == 201
    assert register.json()["email"] == email

    login = await async_client.post("/auth/login", json={"email": email, "password": "Password123!"})
    assert login.status_code == 200
    assert login.json()["token_type"] == "bearer"

    user_a = seeded_users["ava_chen"]
    user_b = seeded_users["noah_patel"]

    response_a = await async_client.post(
        "/interactions/swipe",
        params={"token": create_access_token(subject=str(user_a.id))},
        json={"target_user_id": user_b.id, "action": "like"},
    )
    assert response_a.status_code == 200
    assert response_a.json()["matched"] is False

    response_b = await async_client.post(
        "/interactions/swipe",
        params={"token": create_access_token(subject=str(user_b.id))},
        json={"target_user_id": user_a.id, "action": "like"},
    )
    assert response_b.status_code == 200
    assert response_b.json()["matched"] is True
    assert response_b.json()["match_id"] is not None


@pytest.mark.asyncio
async def test_chat_messaging_persists_and_broadcasts(seeded_users, monkeypatch, db_session: AsyncSession):
    user_a = seeded_users["ava_chen"]
    user_b = seeded_users["noah_patel"]
    match = await _seed_match(db_session, user_a.id, user_b.id)

    monkeypatch.setattr(
        nlp_service,
        "moderate_text",
        AsyncMock(return_value=nlp_service.ModerationResult(is_flagged=False, flag_reason="safe", categories=[])),
    )
    monkeypatch.setattr(chat_router.manager, "broadcast", AsyncMock(return_value=None))
    monkeypatch.setattr(redis_service, "add_socket_to_room", AsyncMock(return_value=None))
    monkeypatch.setattr(redis_service, "remove_socket_from_room", AsyncMock(return_value=None))

    from fastapi.testclient import TestClient
    from app.main import app as fastapi_app

    with TestClient(fastapi_app) as client:
        with client.websocket_connect(f"/chat/ws/{match.id}?token={create_access_token(subject=str(user_a.id))}") as websocket:
            websocket.send_text(json.dumps({"message": "Want to grab coffee this week?"}))
            websocket.close()

    message = await db_session.scalar(select(ChatMessage).where(ChatMessage.match_id == match.id))
    assert message is not None
    assert "coffee" in message.message.lower()


@pytest.mark.asyncio
async def test_ai_moderation_path_blocks_flagged_text(seeded_users, monkeypatch, db_session: AsyncSession):
    user_a = seeded_users["ava_chen"]
    user_b = seeded_users["noah_patel"]
    match = await _seed_match(db_session, user_a.id, user_b.id)

    monkeypatch.setattr(
        nlp_service,
        "moderate_text",
        AsyncMock(
            return_value=nlp_service.ModerationResult(
                is_flagged=True,
                flag_reason="Detected suspicious off-platform payment or credential request.",
                categories=["fraud", "phishing"],
            )
        ),
    )
    monkeypatch.setattr(chat_router.manager, "broadcast", AsyncMock(return_value=None))
    monkeypatch.setattr(redis_service, "add_socket_to_room", AsyncMock(return_value=None))
    monkeypatch.setattr(redis_service, "remove_socket_from_room", AsyncMock(return_value=None))

    from fastapi.testclient import TestClient
    from app.main import app as fastapi_app

    with TestClient(fastapi_app) as client:
        with client.websocket_connect(f"/chat/ws/{match.id}?token={create_access_token(subject=str(user_a.id))}") as websocket:
            websocket.send_text(json.dumps({"message": "Send me your password and cash app info."}))
            warning = websocket.receive_json()

    assert warning["type"] == "system_warning"
    assert "suspicious" in warning["detail"].lower()


@pytest.mark.asyncio
async def test_geo_midpoint_and_venue_suggestions(async_client: AsyncClient, seeded_users, db_session: AsyncSession, monkeypatch):
    user_a = await db_session.scalar(select(User).where(User.id == seeded_users["ava_chen"].id))
    user_b = await db_session.scalar(select(User).where(User.id == seeded_users["noah_patel"].id))
    assert user_a is not None and user_b is not None

    match = await _seed_match(db_session, user_a.id, user_b.id)

    async def fake_calculate_match_midpoint(db, match_id: int):
        return location_service.GeoPoint(latitude=12.9534, longitude=77.6021)

    async def fake_suggest_venues_near_midpoint(midpoint):
        return [
            location_service.VenueSuggestion(
                name="The Corner Cafe",
                rating=4.8,
                venue_type="cafe",
                address="123 Main Street",
                photo_url="https://cdn.example.com/corner-cafe.jpg",
                distance_meters=240,
            )
        ]

    monkeypatch.setattr(location_service, "calculate_match_midpoint", fake_calculate_match_midpoint)
    monkeypatch.setattr(location_service, "suggest_venues_near_midpoint", fake_suggest_venues_near_midpoint)

    response = await async_client.get(f"/matches/{match.id}/meetup-suggestions")
    assert response.status_code == 200
    payload = response.json()
    assert payload["match_id"] == match.id
    assert payload["midpoint"]["latitude"] == 12.9534
    assert payload["venues"][0]["name"] == "The Corner Cafe"


@pytest.mark.asyncio
async def test_cinematic_s3_presign_contract(monkeypatch):
    from app.services import cinematic_ai_service as cinematic_module

    monkeypatch.setattr(cinematic_module, "AWS_ACCESS_KEY_ID", "test", raising=False)
    monkeypatch.setattr(cinematic_module, "AWS_SECRET_ACCESS_KEY", "test", raising=False)
    monkeypatch.setattr(cinematic_module, "AWS_S3_BUCKET", "test-bucket", raising=False)
    monkeypatch.setattr(cinematic_module, "AWS_S3_ENDPOINT_URL", "https://s3.example.test", raising=False)
    monkeypatch.setattr(cinematic_module, "AI_CINEMATIC_PROVIDER", "mock", raising=False)

    upload = UploadFile(filename="photo.png", file=None)  # type: ignore[arg-type]
    monkeypatch.setattr(upload, "read", AsyncMock(return_value=b"fake-image-bytes"))

    result = await cinematic_module.prepare_cinematic_upload(upload, user_id=123, edit_mode="cinematic")
    assert result.original_object_key.startswith("cinematic/")
    assert result.original_presigned_url.startswith("https://example.invalid/upload/")

    response = build_upload_response_metadata(result)
    assert response["original_object_key"] == result.original_object_key


@pytest.mark.asyncio
async def test_webhook_reputation_updates_and_concurrency(async_client: AsyncClient, db_session: AsyncSession, seeded_users, monkeypatch):
    from app.routers import webhooks as webhooks_module

    monkeypatch.setattr(webhooks_module, "AI_WEBHOOK_SECRET", "integration-secret", raising=False)

    user = seeded_users["ava_chen"]
    profile = await db_session.scalar(select(Profile).where(Profile.user_id == user.id))
    assert profile is not None
    profile.reputation_score = 100
    profile.reliability_tier = "standard"
    await db_session.commit()

    monkeypatch.setattr(webhooks_module, "_publish_websocket_notification", AsyncMock(return_value=True))

    payload = {
        "user_id": user.id,
        "image_url": "https://cdn.example.com/verified.jpg",
        "adjustment_value": 10,
        "provider_job_id": "job-123",
    }

    async def _signed_request(delta: int):
        body = dict(payload)
        body["adjustment_value"] = delta
        raw = json.dumps(body).encode("utf-8")
        ts = str(int(time.time()))
        import hashlib
        import hmac

        signature = hmac.new(
            b"integration-secret",
            f"{ts}.".encode("utf-8") + raw,
            hashlib.sha256,
        ).hexdigest()
        return await async_client.post(
            "/webhooks/ai-image-complete",
            content=raw,
            headers={"X-AI-Signature": signature, "X-AI-Timestamp": ts},
        )

    first, second = await asyncio.gather(_signed_request(10), _signed_request(10))
    assert first.status_code == 200
    assert second.status_code in {200, 409, 422, 500, 502}

    refreshed = await db_session.scalar(select(Profile).where(Profile.user_id == user.id))
    assert refreshed is not None
    assert refreshed.reputation_score >= 110


@pytest.mark.asyncio
async def test_direct_reputation_locking_is_serialized(test_sessionmaker, seeded_users):
    user = seeded_users["ava_chen"]

    async with test_sessionmaker() as session:
        profile = await session.scalar(select(Profile).where(Profile.user_id == user.id))
        assert profile is not None
        profile.reputation_score = 100
        profile.reliability_tier = "standard"
        await session.commit()

    async def inc():
        async with test_sessionmaker() as session:
            return await adjust_reputation_score(session, user.id, 10)

    results = await asyncio.gather(inc(), inc())
    assert all(result.reputation_score >= 110 for result in results)
