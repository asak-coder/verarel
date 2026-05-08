from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.trust import ReportRequest, SelfieVerificationRequest, TrustScoreDetailResponse, TrustScoreResponse
from app.services.trust_service import get_trust_score, record_report, submit_selfie_verification

router = APIRouter(prefix="/trust", tags=["trust"])


@router.get("/{user_id}", response_model=TrustScoreDetailResponse, status_code=status.HTTP_200_OK)
@router.get("/api/trust/{user_id}", response_model=TrustScoreDetailResponse, include_in_schema=False)
async def fetch_trust_score(user_id: int, db: AsyncSession = Depends(get_db)) -> TrustScoreDetailResponse:
    try:
        return await get_trust_score(db, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/verify/selfie", response_model=TrustScoreDetailResponse, status_code=status.HTTP_200_OK)
@router.post("/api/verify/selfie", response_model=TrustScoreDetailResponse, include_in_schema=False)
async def verify_selfie(
    payload: SelfieVerificationRequest,
    db: AsyncSession = Depends(get_db),
) -> TrustScoreDetailResponse:
    try:
        return await submit_selfie_verification(db, payload.user_id, payload.image_base64)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/report", response_model=TrustScoreDetailResponse, status_code=status.HTTP_200_OK)
@router.post("/api/trust/report", response_model=TrustScoreDetailResponse, include_in_schema=False)
async def report_user(
    payload: ReportRequest,
    db: AsyncSession = Depends(get_db),
) -> TrustScoreDetailResponse:
    if payload.user_id == payload.reporter_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot report yourself")

    try:
        return await record_report(db, payload.user_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/summary/{user_id}", response_model=TrustScoreResponse, status_code=status.HTTP_200_OK)
@router.get("/api/trust/summary/{user_id}", response_model=TrustScoreResponse, include_in_schema=False)
async def trust_summary(user_id: int, db: AsyncSession = Depends(get_db)) -> TrustScoreResponse:
    try:
        detail = await get_trust_score(db, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return TrustScoreResponse(score=detail.score, tier=detail.tier, verified=detail.verified)
