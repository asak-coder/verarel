from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.date_architect_service import (
    GeoPoint,
    VenueSuggestion,
    calculate_match_midpoint,
    get_match_by_participants,
    obfuscate_point,
    suggest_venues_near_midpoint,
)

router = APIRouter(prefix="/date-architect", tags=["date-architect"])


class DateArchitectRequest(BaseModel):
    target_user_id: int = Field(gt=0)

    model_config = ConfigDict(extra="forbid")


class DateArchitectResponsePoint(BaseModel):
    latitude: float
    longitude: float

    model_config = ConfigDict(from_attributes=True)


class DateArchitectVenueResponse(BaseModel):
    name: str
    rating: float
    venue_type: str
    address: str | None = None
    photo_url: str | None = None
    distance_meters: int | None = None

    model_config = ConfigDict(from_attributes=True)


class DateArchitectResponse(BaseModel):
    match_id: int
    midpoint: DateArchitectResponsePoint
    venues: list[DateArchitectVenueResponse]

    model_config = ConfigDict(from_attributes=True)


def _read_current_user_id(x_user_id: str | None) -> int:
    if not x_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing user identity header")
    try:
        user_id = int(x_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity header") from exc
    if user_id <= 0:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity header")
    return user_id


@router.post("/midpoint", response_model=DateArchitectResponse, status_code=status.HTTP_200_OK)
@router.get("/api/date-plan/{match_id}", response_model=DateArchitectResponse, include_in_schema=False)
async def create_date_architect_plan(
    payload: DateArchitectRequest,
    db: AsyncSession = Depends(get_db),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> DateArchitectResponse:
    current_user_id = _read_current_user_id(x_user_id)

    try:
        match = await get_match_by_participants(db, current_user_id, payload.target_user_id)
        midpoint = await calculate_match_midpoint(db, match.id)
        venues = await suggest_venues_near_midpoint(midpoint)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    obfuscated_midpoint = obfuscate_point(midpoint)

    return DateArchitectResponse(
        match_id=match.id,
        midpoint=DateArchitectResponsePoint(
            latitude=obfuscated_midpoint.latitude,
            longitude=obfuscated_midpoint.longitude,
        ),
        venues=[
            DateArchitectVenueResponse(
                name=venue.name,
                rating=venue.rating,
                venue_type=venue.venue_type,
                address=venue.address,
                photo_url=venue.photo_url,
                distance_meters=venue.distance_meters,
            )
            for venue in venues
        ],
    )
