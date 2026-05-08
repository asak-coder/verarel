from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import Profile
from app.models.trust import TrustScoreDetailResponse, TrustScoreResponse, TrustTier, UserTrust
from app.models.user import User
from app.services.redis_service import redis_service
from app.services.security_service import analyze_image_payload, verify_liveness_session

TRUST_SCORE_CACHE_PREFIX = "trust_score"
TRUST_SCORE_CACHE_TTL_SECONDS = 600
VERIFICATION_HOURLY_LIMIT = 5
VERIFICATION_WINDOW_SECONDS = 3600


@dataclass(slots=True)
class TrustScoreComponents:
    profile_completeness: int
    selfie_verified: bool
    phone_verified: bool
    email_verified: bool
    account_age_days: int
    behavior_score: int
    reports_count: int
    blocks_count: int
    suspicious_score: int

    def total(self) -> int:
        score = 20
        score += min(self.profile_completeness, 20)
        score += 15 if self.selfie_verified else 0
        score += 10 if self.phone_verified else 0
        score += 10 if self.email_verified else 0
        score += min(self.account_age_days, 30)
        score += min(self.behavior_score, 15)
        score -= min(self.reports_count * 6, 30)
        score -= min(self.blocks_count * 8, 30)
        score -= min(self.suspicious_score, 35)
        return max(0, min(100, score))


def derive_trust_tier(score: int) -> TrustTier:
    if score >= 70:
        return TrustTier.high
    if score >= 40:
        return TrustTier.medium
    return TrustTier.low


def _profile_completeness(profile: Profile | None) -> int:
    if profile is None:
        return 0
    filled = 0
    fields: list[Any] = [profile.display_name, profile.bio, profile.interests]
    for field in fields:
        if field:
            filled += 1
    return int((filled / len(fields)) * 20)


def _behavior_score(user: User, trust_row: UserTrust | None) -> int:
    score = 5
    if user.is_active:
        score += 3
    if trust_row and trust_row.verified:
        score += 4
    if trust_row and trust_row.last_recalculated_at:
        score += 3
    return min(score, 15)


def _account_age_days(created_at: datetime | None) -> int:
    if created_at is None:
        return 0
    delta = datetime.now(timezone.utc) - created_at
    return max(0, min(delta.days, 30))


async def _ensure_user_trust(db: AsyncSession, user_id: int) -> UserTrust:
    trust = await db.scalar(select(UserTrust).where(UserTrust.user_id == user_id))
    if trust is not None:
        return trust
    trust = UserTrust(user_id=user_id)
    db.add(trust)
    await db.flush()
    return trust


async def _load_trust_context(db: AsyncSession, user_id: int) -> tuple[User, Profile | None, UserTrust]:
    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise LookupError("User not found")

    profile = await db.scalar(select(Profile).where(Profile.user_id == user_id))
    trust = await _ensure_user_trust(db, user_id)
    return user, profile, trust


def _cache_key(user_id: int) -> str:
    return f"{TRUST_SCORE_CACHE_PREFIX}:{user_id}"


async def get_cached_trust_score(user_id: int) -> TrustScoreDetailResponse | None:
    client = await redis_service.connect()
    payload = await client.get(_cache_key(user_id))
    if not payload:
        return None
    try:
        data = json.loads(payload)
        return TrustScoreDetailResponse(**data, cached=True)
    except Exception:
        return None


async def set_cached_trust_score(user_id: int, response: TrustScoreDetailResponse) -> None:
    client = await redis_service.connect()
    await client.set(_cache_key(user_id), response.model_dump_json(), ex=TRUST_SCORE_CACHE_TTL_SECONDS)


async def recalculate_trust_score(db: AsyncSession, user_id: int) -> TrustScoreDetailResponse:
    user, profile, trust = await _load_trust_context(db, user_id)

    components = TrustScoreComponents(
        profile_completeness=_profile_completeness(profile),
        selfie_verified=bool(trust.selfie_verified),
        phone_verified=bool(trust.phone_verified),
        email_verified=bool(trust.email_verified),
        account_age_days=_account_age_days(user.created_at),
        behavior_score=_behavior_score(user, trust),
        reports_count=int(trust.reports_count),
        blocks_count=int(trust.blocks_count),
        suspicious_score=int(trust.suspicious_score),
    )
    score = components.total()
    tier = derive_trust_tier(score)
    trust.trust_score = score
    trust.trust_tier = tier.value
    trust.verified = bool(trust.selfie_verified or trust.phone_verified or trust.email_verified)
    trust.verification_type = (
        "selfie"
        if trust.selfie_verified
        else "phone"
        if trust.phone_verified
        else "email"
        if trust.email_verified
        else None
    )
    trust.profile_completeness = components.profile_completeness
    trust.account_age_days = components.account_age_days
    trust.behavior_score = components.behavior_score
    trust.last_recalculated_at = datetime.now(timezone.utc)

    db.add(trust)
    await db.commit()
    await db.refresh(trust)

    response = TrustScoreDetailResponse(
        score=trust.trust_score,
        tier=TrustTier(trust.trust_tier),
        verified=trust.verified,
        reports_count=trust.reports_count,
        blocks_count=trust.blocks_count,
        verification_type=trust.verification_type,
        last_updated=trust.last_updated,
        cached=False,
    )
    await set_cached_trust_score(user_id, response)
    return response


async def get_trust_score(db: AsyncSession, user_id: int) -> TrustScoreDetailResponse:
    cached = await get_cached_trust_score(user_id)
    if cached is not None:
        return cached

    return await recalculate_trust_score(db, user_id)


async def submit_selfie_verification(db: AsyncSession, user_id: int, image_base64: str) -> TrustScoreDetailResponse:
    user, _, trust = await _load_trust_context(db, user_id)
    client = await redis_service.connect()
    limit_key = f"trust_verify_rl:{user_id}"
    count = await client.incr(limit_key)
    if count == 1:
        await client.expire(limit_key, VERIFICATION_WINDOW_SECONDS)
    if count > VERIFICATION_HOURLY_LIMIT:
        raise ValueError("Too many verification attempts")

    verdict = await analyze_image_payload(image_base64)
    if verdict.is_nsfw:
        trust.suspicious_score = min(trust.suspicious_score + 15, 100)
        trust.selfie_verified = False
        trust.verified = False
        db.add(trust)
        await db.commit()
        await db.refresh(trust)
        raise ValueError("Selfie verification rejected")

    digest = hashlib.sha256(image_base64.strip().encode("utf-8")).hexdigest()
    liveness = await verify_liveness_session(digest[:32])

    trust.selfie_verified = liveness.is_verified and liveness.score >= 0.72
    trust.verified = trust.selfie_verified or trust.phone_verified or trust.email_verified
    trust.verification_type = "selfie" if trust.selfie_verified else trust.verification_type
    trust.last_recalculated_at = datetime.now(timezone.utc)
    db.add(trust)
    await db.commit()
    await db.refresh(trust)

    return await recalculate_trust_score(db, user.id)


async def record_report(db: AsyncSession, user_id: int) -> TrustScoreDetailResponse:
    _, _, trust = await _load_trust_context(db, user_id)
    trust.reports_count += 1
    trust.suspicious_score = min(trust.suspicious_score + 5, 100)
    db.add(trust)
    await db.commit()
    await db.refresh(trust)
    return await recalculate_trust_score(db, user_id)
