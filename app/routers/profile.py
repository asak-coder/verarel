from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from app.services.ai_image_service import AIImageEditResult, edit_image_with_ai
from app.services.cinematic_ai_service import (
    build_upload_response_metadata,
    prepare_cinematic_upload,
    verify_cinematic_webhook,
)

router = APIRouter(prefix="/profile", tags=["profile"])


class ProfileStudioEditRequest(BaseModel):
    image_base64: str = Field(min_length=10)
    edit_command: str = Field(min_length=3, max_length=120)

    model_config = ConfigDict(extra="forbid")


class ProfileStudioEditResponse(BaseModel):
    image_url: str
    provider_job_id: str | None = None
    metadata: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)


class CinematicStudioPrepareResponse(BaseModel):
    original_object_key: str
    original_presigned_url: str
    provider_job_id: str | None = None
    webhook_target_url: str | None = None
    metadata: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)


class CinematicWebhookResponse(BaseModel):
    job_id: str
    output_image_url: str
    metadata: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)


@router.post("/studio/edit", response_model=ProfileStudioEditResponse, status_code=status.HTTP_200_OK)
async def edit_profile_photo(
    image_base64: str | None = Form(default=None),
    edit_command: str = Form(..., min_length=3, max_length=120),
    image_file: UploadFile | None = File(default=None),
) -> ProfileStudioEditResponse:
    if not image_base64 and image_file is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either image_base64 or image_file",
        )

    try:
        result: AIImageEditResult = await edit_image_with_ai(
            image_b64=image_base64,
            edit_command=edit_command,
            image_file=image_file,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="AI image editing timed out",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to process the image right now",
        ) from exc

    return ProfileStudioEditResponse(
        image_url=result.image_url,
        provider_job_id=result.provider_job_id,
        metadata=result.metadata,
    )


@router.post("/cinematic/prepare", response_model=CinematicStudioPrepareResponse, status_code=status.HTTP_200_OK)
async def prepare_cinematic_profile_photo(
    request: Request,
    image_file: UploadFile = File(...),
    edit_mode: str = Form(..., min_length=3, max_length=64),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> CinematicStudioPrepareResponse:
    if not x_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing user identity header")

    try:
        user_id = int(x_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity header") from exc

    if user_id <= 0:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity header")

    try:
        result = await prepare_cinematic_upload(image_file=image_file, user_id=user_id, edit_mode=edit_mode)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to prepare cinematic upload") from exc

    return CinematicStudioPrepareResponse(**build_upload_response_metadata(result))


@router.post("/cinematic/webhook", response_model=CinematicWebhookResponse, status_code=status.HTTP_200_OK)
async def cinematic_webhook(
    request: Request,
    x_ai_signature: str | None = Header(default=None, alias="X-AI-Signature"),
    x_ai_timestamp: str | None = Header(default=None, alias="X-AI-Timestamp"),
) -> CinematicWebhookResponse:
    raw_body = await request.body()
    try:
        result = verify_cinematic_webhook(raw_body, x_ai_signature, x_ai_timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return CinematicWebhookResponse(
        job_id=result.job_id,
        output_image_url=result.output_image_url,
        metadata=result.metadata,
    )
