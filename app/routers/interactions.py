from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ALGORITHM, SECRET_KEY
from app.database import get_db
from app.models.interaction import Match, SwipeInteraction
from app.models.user import User
from app.services.redis_service import FLUSH_INTERVAL_SECONDS, redis_service
from app.workers.tasks import generate_icebreakers_for_match

router = APIRouter(prefix="/interactions", tags=["interactions"])


class SwipeRequest(BaseModel):
    target_user_id: int = Field(gt=0)
    action: Literal["like", "pass"]

    model_config = ConfigDict(extra="forbid")


class SwipeResponse(BaseModel):
    swipe_saved: bool
    matched: bool
    match_id: int | None = None
    detail: str


async def get_current_user_id(token: str) -> int:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        subject = payload.get("sub")
        if not subject:
            raise ValueError("missing subject")
        return int(subject)
    except (JWTError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token") from exc


async def _create_match(db: AsyncSession, user_id: int, target_user_id: int) -> Match:
    match = Match(user_a_id=min(user_id, target_user_id), user_b_id=max(user_id, target_user_id))
    db.add(match)
    await db.commit()
    await db.refresh(match)
    return match


async def _persist_swipe(db: AsyncSession, user_id: int, target_user_id: int, action: str, source: str) -> None:
    swipe = SwipeInteraction(
        swiper_id=user_id,
        target_user_id=target_user_id,
        action=action,
        source=source,
        created_at=datetime.now(timezone.utc),
    )
    db.add(swipe)
    await db.commit()


@router.post("/swipe", response_model=SwipeResponse)
async def swipe(payload: SwipeRequest, token: str, db: AsyncSession = Depends(get_db)) -> SwipeResponse:
    user_id = await get_current_user_id(token)

    if user_id == payload.target_user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot swipe on yourself")

    target_user = await db.scalar(select(User).where(User.id == payload.target_user_id))
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target user not found")

    await redis_service.record_swipe(user_id, payload.target_user_id, payload.action)
    await _persist_swipe(db, user_id, payload.target_user_id, payload.action, source="redis")

    if payload.action == "pass":
        return SwipeResponse(swipe_saved=True, matched=False, detail="Pass recorded")

    mutual_like = await redis_service.has_liked(payload.target_user_id, user_id)
    if not mutual_like:
        return SwipeResponse(swipe_saved=True, matched=False, detail="Like recorded")

    match_key_created = await redis_service.mark_match_seen(user_id, payload.target_user_id)
    if not match_key_created:
        return SwipeResponse(swipe_saved=True, matched=False, detail="Match already processed")

    existing_match = await db.scalar(
        select(Match).where(
            ((Match.user_a_id == min(user_id, payload.target_user_id)) & (Match.user_b_id == max(user_id, payload.target_user_id)))
        )
    )
    if existing_match is None:
        match = await _create_match(db, user_id, payload.target_user_id)
        generate_icebreakers_for_match(match.user_a_id, match.user_b_id)
        return SwipeResponse(
            swipe_saved=True,
            matched=True,
            match_id=match.id,
            detail="It's a match",
        )

    return SwipeResponse(
        swipe_saved=True,
        matched=True,
        match_id=existing_match.id,
        detail="It's a match",
    )


async def flush_swipes_to_postgres() -> None:
    while True:
        try:
            events = await redis_service.fetch_pending_swipe_events()
            if not events:
                await asyncio.sleep(FLUSH_INTERVAL_SECONDS)
                continue
            async with get_db().__wrapped__() as db:  # type: ignore[attr-defined]
                for event in events:
                    db.add(
                        SwipeInteraction(
                            swiper_id=event.swiped_by,
                            target_user_id=event.swiped_on,
                            action=event.action,
                            source="stream",
                            created_at=datetime.fromisoformat(event.created_at),
                        )
                    )
                await db.commit()
            await redis_service.trim_swipe_stream()
        except Exception:
            await asyncio.sleep(FLUSH_INTERVAL_SECONDS)
