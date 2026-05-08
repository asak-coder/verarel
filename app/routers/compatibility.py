from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ALGORITHM, SECRET_KEY
from app.database import get_db
from app.models.compatibility import CompatibilityScore
from app.services.compatibility_service import (
    CompatibilityResult,
    calculate_compatibility,
    get_compatibility_by_match,
    get_compatibility_row,
    rate_limit_compatibility,
    recompute_and_cache,
)
from app.services.redis_service import redis_service
from jose import JWTError, jwt

router = APIRouter(prefix="/compatibility", tags=["compatibility"])


class CompatibilityResponse(BaseModel):
    score: int = Field(ge=0, le=100)
    reasons: list[str]
    last_updated: str
    cache_hit: bool = False

    model_config = ConfigDict(from_attributes=True)


class CompatibilityRecomputeRequest(BaseModel):
    match_id: int = Field(gt=0)

    model_config = ConfigDict(extra="forbid")


class CompatibilityRecomputeResponse(BaseModel):
    match_id: int
    score: int
    reasons: list[str]
    last_updated: str

    model_config = ConfigDict(from_attributes=True)


def _read_user_id_from_token(token: str | None) -> int:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        subject = payload.get("sub")
        if not subject:
            raise ValueError("missing subject")
        return int(subject)
    except (JWTError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token") from exc


@router.get("/{match_id}", response_model=CompatibilityResponse, status_code=status.HTTP_200_OK)
@router.get("/api/compatibility/{match_id}", response_model=CompatibilityResponse, include_in_schema=False)
async def get_compatibility(
    match_id: int,
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> CompatibilityResponse:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    current_user_id = _read_user_id_from_token(token)
    await rate_limit_compatibility(current_user_id)

    result, (user_a_id, user_b_id) = await get_compatibility_by_match(db, match_id)

    if current_user_id not in {user_a_id, user_b_id}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only access your own matches")

    return CompatibilityResponse(
        score=result.score,
        reasons=result.reasons,
        last_updated=result.updated_at.isoformat(),
        cache_hit=result.cache_hit,
    )


@router.post("/recompute", response_model=CompatibilityRecomputeResponse, status_code=status.HTTP_200_OK)
@router.post("/api/compatibility/recompute", response_model=CompatibilityRecomputeResponse, include_in_schema=False)
async def recompute_compatibility(
    payload: CompatibilityRecomputeRequest,
    db: AsyncSession = Depends(get_db),
    x_internal_key: str | None = Header(default=None, alias="X-Internal-Key"),
) -> CompatibilityRecomputeResponse:
    if not x_internal_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing internal authorization")
    result, (user_a_id, user_b_id) = await get_compatibility_by_match(db, payload.match_id)
    recomputed = await recompute_and_cache(db, user_a_id, user_b_id)
    return CompatibilityRecomputeResponse(
        match_id=payload.match_id,
        score=recomputed.score,
        reasons=recomputed.reasons,
        last_updated=recomputed.updated_at.isoformat(),
    )
