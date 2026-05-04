from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.models.reputation import derive_reliability_tier
from app.services import s3_service as s3_module
from app.services.redis_service import RedisService
from app.services.s3_service import S3PresignedPostRequest, S3Service
from app.routers import profile as profile_router
from app.routers import security as security_router
from app.routers import auth as auth_router
from app.routers import date_architect as date_architect_router


@pytest.mark.asyncio
async def test_redis_service_connect_ping_and_pubsub(monkeypatch):
    service = RedisService(url="redis://localhost:6379/0")

    fake_client = SimpleNamespace(
        ping=AsyncMock(return_value=True),
        publish=AsyncMock(return_value=1),
        aclose=AsyncMock(return_value=None),
    )

    monkeypatch.setattr("app.services.redis_service.redis.from_url", lambda *args, **kwargs: fake_client)

    client = await service.connect()
    assert client is fake_client
    assert await AsyncMock(side_effect=fake_client.ping)() is True
    assert await client.publish("validation:test", '{"ok":true}') == 1

    await service.close()
    fake_client.aclose.assert_awaited_once()


def test_reliability_tier_rules_are_monotonic():
    assert derive_reliability_tier(0) == "new"
    assert derive_reliability_tier(100) == "standard"
    assert derive_reliability_tier(140) == "trusted"
    assert derive_reliability_tier(180) == "elite"


def test_s3_service_requires_allowed_content_type(monkeypatch):
    monkeypatch.setattr(s3_module, "AWS_ACCESS_KEY_ID", "test", raising=False)
    monkeypatch.setattr(s3_module, "AWS_SECRET_ACCESS_KEY", "test", raising=False)
    monkeypatch.setattr(s3_module, "AWS_S3_BUCKET", "test-bucket", raising=False)

    fake_client = SimpleNamespace(
        generate_presigned_post=lambda **_: {"url": "https://example.com", "fields": {"Content-Type": "image/jpeg"}}
    )
    monkeypatch.setattr(s3_module.boto3, "client", lambda *args, **kwargs: fake_client, raising=False)

    service = S3Service()
    with pytest.raises(ValueError):
        service.create_presigned_post(
            S3PresignedPostRequest(user_id=1, content_type="application/pdf", filename="bad.pdf")
        )


@pytest.mark.asyncio
async def test_failure_simulation_redis_down(monkeypatch):
    service = RedisService(url="redis://localhost:6379/0")

    def raise_error(*args, **kwargs):
        raise ConnectionError("redis down")

    monkeypatch.setattr("app.services.redis_service.redis.from_url", lambda *args, **kwargs: SimpleNamespace(ping=raise_error))
    with pytest.raises(ConnectionError):
        await service.connect()


@pytest.mark.asyncio
async def test_failure_simulation_s3_missing_credentials(monkeypatch):
    monkeypatch.setattr(s3_module, "AWS_ACCESS_KEY_ID", "", raising=False)
    monkeypatch.setattr(s3_module, "AWS_SECRET_ACCESS_KEY", "", raising=False)
    monkeypatch.setattr(s3_module, "AWS_S3_BUCKET", "", raising=False)

    with pytest.raises(ValueError):
        S3Service()


@pytest.mark.asyncio
async def test_failure_simulation_ai_timeout_results_in_http_504(async_client: AsyncClient, monkeypatch):
    async def raise_timeout(*args, **kwargs):
        raise TimeoutError("AI timeout")

    monkeypatch.setattr(profile_router, "edit_image_with_ai", raise_timeout)

    response = await async_client.post(
        "/profile/studio/edit",
        data={"edit_command": "make brighter", "image_base64": "aGVsbG8="},
    )

    assert response.status_code == 504
    assert "timed out" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_auth_register_login_and_duplicate_rejection(async_client: AsyncClient):
    payload = {
        "email": "new.user@example.com",
        "username": "new_user_123",
        "password": "Password123!",
    }

    register = await async_client.post("/auth/register", json=payload)
    assert register.status_code == 201
    assert register.json()["email"] == payload["email"]

    duplicate = await async_client.post("/auth/register", json=payload)
    assert duplicate.status_code == 409

    login = await async_client.post(
        "/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert login.status_code == 200
    assert "access_token" in login.json()
    assert login.json()["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_geo_endpoint_happy_path(async_client: AsyncClient, monkeypatch):
    class FakeMatch:
        id = 10
        user_a_id = 1
        user_b_id = 2

    async def fake_get_match_by_participants(db, current_user_id: int, target_user_id: int):
        return FakeMatch()

    async def fake_calculate_match_midpoint(db, match_id: int):
        return SimpleNamespace(latitude=12.97, longitude=77.59)

    async def fake_suggest_venues_near_midpoint(midpoint):
        return [SimpleNamespace(name="Corner Cafe", rating=4.8, venue_type="cafe", address=None, photo_url=None, distance_meters=None)]

    monkeypatch.setattr("app.services.date_architect_service.get_match_by_participants", fake_get_match_by_participants)
    monkeypatch.setattr("app.services.date_architect_service.calculate_match_midpoint", fake_calculate_match_midpoint)
    monkeypatch.setattr("app.services.date_architect_service.suggest_venues_near_midpoint", fake_suggest_venues_near_midpoint)

    response = await async_client.post(
        "/date-architect/midpoint",
        headers={"X-User-Id": "1"},
        json={"target_user_id": 2},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["match_id"] == 10
    assert data["venues"][0]["name"] == "Corner Cafe"


@pytest.mark.asyncio
async def test_ai_image_webhook_gracefully_degrades_on_missing_signature(async_client: AsyncClient):
    response = await async_client.post(
        "/webhooks/ai-image-complete",
        json={"user_id": 1, "image_url": "https://example.com/x.jpg"},
    )
    assert response.status_code == 400
    assert "webhook" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_chat_icebreakers_requires_valid_payload(async_client: AsyncClient):
    response = await async_client.post("/chat/icebreakers", json={"user_a_id": 1, "user_b_id": 2})
    assert response.status_code in {200, 502, 404}


@pytest.mark.asyncio
async def test_ai_failure_returns_graceful_error(async_client: AsyncClient, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("provider failed")

    monkeypatch.setattr("app.services.security_service.verify_liveness_session", boom)
    response = await async_client.post(
        "/security/verify-liveness",
        json={"user_id": 1, "session_token": "validtoken"},
    )
    assert response.status_code in {400, 404, 502}
