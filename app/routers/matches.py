from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.interaction import Match
from app.services.location_service import GeoPoint, VenueSuggestion, calculate_match_midpoint, suggest_venues_near_midpoint

router = APIRouter(prefix="/matches", tags=["matches"])


class MeetupSuggestionResponse(BaseModel):
    match_id: int
    midpoint: GeoPointSchema
    venues: list[VenueSuggestionSchema]

    model_config = ConfigDict(from_attributes=True)


class GeoPointSchema(BaseModel):
    latitude: float
    longitude: float

    model_config = ConfigDict(from_attributes=True)


class VenueSuggestionSchema(BaseModel):
    name: str
    rating: float
    venue_type: str
    address: str | None = None
    photo_url: str | None = None
    distance_meters: int | None = None

    model_config = ConfigDict(from_attributes=True)


@router.get("/{match_id}/meetup-suggestions", response_model=MeetupSuggestionResponse, status_code=status.HTTP_200_OK)
async def get_meetup_suggestions(
    match_id: int,
    db: AsyncSession = Depends(get_db),
) -> MeetupSuggestionResponse:
    match = await db.scalar(select(Match).where(Match.id == match_id))
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")

    try:
        midpoint = await calculate_match_midpoint(db, match_id)
        venues = await suggest_venues_near_midpoint(midpoint)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return MeetupSuggestionResponse(
        match_id=match_id,
        midpoint=GeoPointSchema(latitude=midpoint.latitude, longitude=midpoint.longitude),
        venues=[
            VenueSuggestionSchema(
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
