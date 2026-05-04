from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.profile import Profile
from app.models.reputation import adjust_reputation_score

AI_WEBHOOK_SECRET = os.getenv("AI_WEBHOOK_SECRET", "").strip()
AI_WEBHOOK_MAX_SKEW_SECONDS = int(os.getenv("AI_WEBHOOK_MAX_SKEW_SECONDS", "300"))

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class AIImageCompletePayload(BaseModel):
    user_id: int = Field(gt=0)
    profile_id: int | None = Field(default=None, gt=0)
    image_url: str = Field(min_length=8, max_length=2048)
    provider_job_id: str | None = Field(default=None, max_length=255)
    adjustment_value: int = Field(default=0)

    model_config = ConfigDict(extra="forbid")


class AIImageCompleteResponse(BaseModel):
    profile_id: int
    user_id: int
    image_url: str
    reputation_score: int
    reliability_tier: str
    notified: bool

    model_config = ConfigDict(from_attributes=True)


def _verify_hmac_signature(raw_body: bytes, signature_header: str | None, timestamp_header: str | None) -> None:
    if not AI_WEBHOOK_SECRET:
        raise ValueError("Webhook secret is not configured")
    if not signature_header or not timestamp_header:
        raise ValueError("Missing webhook signature headers")

    try:
        timestamp = int(timestamp_header)
    except ValueError as exc:
        raise ValueError("Invalid webhook timestamp") from exc

    now = int(time.time())
    if abs(now - timestamp) > AI_WEBHOOK_MAX_SKEW_SECONDS:
        raise ValueError("Webhook timestamp is outside the allowed tolerance")

    expected = hmac.new(
        AI_WEBHOOK_SECRET.encode("utf-8"),
        f"{timestamp}.".encode("utf-8") + raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature_header):
        raise ValueError("Invalid webhook signature")


async def _publish_websocket_notification(user_id: int, payload: dict[str, Any]) -> bool:
    """
    Notification hook for the Flutter client.

    The app already uses Redis for realtime coordination, so publishing to a
    user-scoped channel is a safe non-blocking path. If Redis is unavailable, we
    return False and still persist the profile update.
    """
    try:
        from app.services.redis_service import redis_service

        client = await redis_service.connect()
        await client.publish(f"user:{user_id}:notifications", json.dumps(payload))
        return True
    except Exception:
        return False


@router.post("/ai-image-complete", response_model=AIImageCompleteResponse, status_code=status.HTTP_200_OK)
async def ai_image_complete(
    request: Request,
    x_ai_signature: str | None = Header(default=None, alias="X-AI-Signature"),
    x_ai_timestamp: str | None = Header(default=None, alias="X-AI-Timestamp"),
    db: AsyncSession = Depends(get_db),
) -> AIImageCompleteResponse:
    raw_body = await request.body()
    try:
        _verify_hmac_signature(raw_body, x_ai_signature, x_ai_timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        payload_data = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook payload must be valid JSON") from exc

    if not isinstance(payload_data, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload")

    try:
        payload = AIImageCompletePayload.model_validate(payload_data)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload") from exc

    profile_id = payload.profile_id
    if profile_id is None:
        profile = await db.scalar(select(Profile).where(Profile.user_id == payload.user_id).with_for_update())
    else:
        profile = await db.scalar(select(Profile).where(Profile.id == profile_id).with_for_update())

    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    profile.bio = profile.bio
    db.add(profile)
    await db.flush()

    if payload.adjustment_value != 0:
        reputation_result = await adjust_reputation_score(db, profile.user_id, payload.adjustment_value)
        reputation_score = reputation_result.reputation_score
        reliability_tier = reputation_result.reliability_tier
    else:
        reputation_score = profile.reputation_score
        reliability_tier = profile.reliability_tier

    await db.commit()
    await db.refresh(profile)

    notified = await _publish_websocket_notification(
        profile.user_id,
        {
            "event": "ai_image_complete",
            "profile_id": profile.id,
            "user_id": profile.user_id,
            "image_url": payload.image_url,
            "provider_job_id": payload.provider_job_id,
            "reputation_score": reputation_score,
            "reliability_tier": reliability_tier,
        },
    )

    return AIImageCompleteResponse(
        profile_id=profile.id,
        user_id=profile.user_id,
        image_url=payload.image_url,
        reputation_score=reputation_score,
        reliability_tier=reliability_tier,
        notified=notified,
    )
