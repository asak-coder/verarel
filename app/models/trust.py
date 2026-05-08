from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TrustTier(str, Enum):
    low = "Low"
    medium = "Medium"
    high = "High"


class VerificationType(str, Enum):
    selfie = "selfie"
    phone = "phone"
    email = "email"
    government_id = "government_id"


class VerificationStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    verified = "verified"
    rejected = "rejected"
    failed = "failed"


class UserTrust(Base):
    __tablename__ = "user_trust"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
        nullable=False,
    )
    trust_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trust_tier: Mapped[str] = mapped_column(String(16), nullable=False, default=TrustTier.low.value)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verification_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reports_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocks_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    selfie_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    phone_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    account_age_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    profile_completeness: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    behavior_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    suspicious_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_recalculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VerificationRequest(Base):
    __tablename__ = "verification_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=VerificationStatus.pending.value)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class TrustScoreResponse(BaseModel):
    score: int = Field(ge=0, le=100)
    tier: TrustTier
    verified: bool

    model_config = ConfigDict(from_attributes=True)


class SelfieVerificationRequest(BaseModel):
    user_id: int = Field(gt=0)
    image_base64: str = Field(min_length=20, max_length=20_000_000)

    model_config = ConfigDict(extra="forbid")


class ReportRequest(BaseModel):
    user_id: int = Field(gt=0)
    reporter_id: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)

    model_config = ConfigDict(extra="forbid")


class TrustScoreDetailResponse(TrustScoreResponse):
    reports_count: int
    blocks_count: int
    verification_type: str | None = None
    last_updated: datetime | None = None
    cached: bool = False

    model_config = ConfigDict(from_attributes=True)
