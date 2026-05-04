from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.profile import Profile


class ReputationAdjustmentRequest(BaseModel):
    user_id: int = Field(gt=0)
    adjustment_value: int = Field(description="Signed delta to apply to the user's reputation score.")

    model_config = ConfigDict(extra="forbid")


class ReputationAdjustmentResponse(BaseModel):
    user_id: int
    reputation_score: int
    reliability_tier: str

    model_config = ConfigDict(from_attributes=True)


@dataclass(frozen=True, slots=True)
class ReputationTierRule:
    minimum_score: int
    name: str


REPUTATION_TIERS: tuple[ReputationTierRule, ...] = (
    ReputationTierRule(minimum_score=180, name="elite"),
    ReputationTierRule(minimum_score=140, name="trusted"),
    ReputationTierRule(minimum_score=100, name="standard"),
    ReputationTierRule(minimum_score=0, name="new"),
)


class ReputationProfileMixin:
    """
    Shared reputation columns for Profile rows.

    The actual Profile model lives in app.models.profile; this mixin exists so the
    reputation-specific logic, schema helpers, and row-locking update flow can stay
    centralized in one module without creating circular imports elsewhere.
    """

    reputation_score: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    reliability_tier: Mapped[str] = mapped_column(String(32), nullable=False, default="standard")


def derive_reliability_tier(score: int) -> str:
    for tier in REPUTATION_TIERS:
        if score >= tier.minimum_score:
            return tier.name
    return "new"


async def adjust_reputation_score(db: AsyncSession, user_id: int, adjustment_value: int) -> ReputationAdjustmentResponse:
    """
    Concurrency-safe score adjustment.

    This uses SELECT ... FOR UPDATE so concurrent requests serialize on the same
    profile row. That prevents lost updates when multiple webhook events, moderation
    jobs, or client actions adjust the score at the same time.
    """
    if user_id <= 0:
        raise ValueError("user_id must be positive")
    if adjustment_value == 0:
        raise ValueError("adjustment_value must not be zero")

    result = await db.execute(
        select(Profile).where(Profile.user_id == user_id).with_for_update()
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise LookupError("Profile not found")

    new_score = max(0, int(profile.reputation_score) + int(adjustment_value))
    profile.reputation_score = new_score
    profile.reliability_tier = derive_reliability_tier(new_score)

    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    return ReputationAdjustmentResponse(
        user_id=profile.user_id,
        reputation_score=profile.reputation_score,
        reliability_tier=profile.reliability_tier,
    )
