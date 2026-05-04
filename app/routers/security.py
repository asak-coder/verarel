from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.security_service import verify_liveness_session

router = APIRouter(prefix="/security", tags=["security"])


class LivenessVerifyRequest(BaseModel):
    user_id: int = Field(gt=0)
    session_token: str = Field(min_length=8, max_length=512)

    model_config = ConfigDict(extra="forbid")


class LivenessVerifyResponse(BaseModel):
    user_id: int
    is_verified: bool
    score: float
    provider_session_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


@router.post("/verify-liveness", response_model=LivenessVerifyResponse, status_code=status.HTTP_200_OK)
async def verify_liveness(
    payload: LivenessVerifyRequest,
    db: AsyncSession = Depends(get_db),
) -> LivenessVerifyResponse:
    try:
        result = await verify_liveness_session(payload.session_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    user = await db.scalar(select(User).where(User.id == payload.user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.is_verified = result.is_verified
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return LivenessVerifyResponse(
        user_id=user.id,
        is_verified=user.is_verified,
        score=result.score,
        provider_session_id=result.provider_session_id,
    )
