from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast, Protocol

try:
    import boto3
    from botocore.client import Config
except ImportError:  # pragma: no cover - runtime fallback when dependency is missing locally
    boto3 = None
    Config = None

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from botocore.client import BaseClient


AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
AWS_SESSION_TOKEN = os.getenv("AWS_SESSION_TOKEN", "").strip()
AWS_REGION = os.getenv("AWS_REGION", "us-east-1").strip()
AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET", "").strip()
AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL", "").strip()
AWS_S3_PRESIGN_EXPIRY_SECONDS = 300
AWS_S3_UPLOAD_MAX_BYTES = 12 * 1024 * 1024
ALLOWED_IMAGE_MIME_TYPES = ("image/jpeg", "image/png", "image/webp")


class S3PresignedPostRequest(BaseModel):
    user_id: int = Field(gt=0)
    content_type: str = Field(min_length=3, max_length=64)
    filename: str | None = Field(default=None, max_length=255)

    model_config = ConfigDict(extra="forbid")


class S3PresignedPostResponse(BaseModel):
    upload_url: str
    upload_fields: dict[str, str]
    object_key: str
    expires_in_seconds: int
    max_bytes: int

    model_config = ConfigDict(from_attributes=True)


@dataclass(slots=True)
class PresignedPostResult:
    upload_url: str
    upload_fields: dict[str, str]
    object_key: str
    expires_in_seconds: int
    max_bytes: int


class _S3ClientLike(Protocol):
    def generate_presigned_post(
        self,
        *,
        Bucket: str,
        Key: str,
        ExpiresIn: int,
        Fields: dict[str, str],
        Conditions: list[Any],
    ) -> dict[str, Any]: ...


class S3Service:
    """
    Generates short-lived direct-to-S3 upload forms.

    The bucket is never exposed with permanent credentials. If AWS is down or the
    SDK cannot sign a request, the call raises a RuntimeError so the router can
    return a controlled 502 instead of hanging or leaking internals.
    """

    def __init__(self) -> None:
        self._client: _S3ClientLike = self._build_client()

    def _build_client(self) -> _S3ClientLike:
        if boto3 is None or Config is None:
            raise RuntimeError("boto3 and botocore must be installed to generate S3 upload forms")
        if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY or not AWS_S3_BUCKET:
            raise ValueError("AWS credentials and bucket are required for S3 uploads")

        session_kwargs: dict[str, Any] = {
            "aws_access_key_id": AWS_ACCESS_KEY_ID,
            "aws_secret_access_key": AWS_SECRET_ACCESS_KEY,
            "region_name": AWS_REGION,
        }
        if AWS_SESSION_TOKEN:
            session_kwargs["aws_session_token"] = AWS_SESSION_TOKEN

        client = boto3.client(
            "s3",
            endpoint_url=AWS_S3_ENDPOINT_URL or None,
            config=Config(signature_version="s3v4"),
            **session_kwargs,
        )
        return cast(_S3ClientLike, client)

    @staticmethod
    def _build_object_key(user_id: int, filename: str | None) -> str:
        extension = ".jpg"
        if filename:
            lower = filename.lower()
            if lower.endswith(".png"):
                extension = ".png"
            elif lower.endswith(".webp"):
                extension = ".webp"
        token = secrets.token_urlsafe(24).replace("-", "").replace("_", "")
        date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
        return f"profiles/{user_id}/{date_prefix}/{token}{extension}"

    @staticmethod
    def _validate_content_type(content_type: str) -> str:
        normalized = content_type.strip().lower()
        if normalized not in ALLOWED_IMAGE_MIME_TYPES:
            raise ValueError("Unsupported image type")
        return normalized

    def create_presigned_post(self, request: S3PresignedPostRequest) -> PresignedPostResult:
        content_type = self._validate_content_type(request.content_type)
        object_key = self._build_object_key(request.user_id, request.filename)

        try:
            response = self._client.generate_presigned_post(
                Bucket=AWS_S3_BUCKET,
                Key=object_key,
                ExpiresIn=AWS_S3_PRESIGN_EXPIRY_SECONDS,
                Fields={
                    "Content-Type": content_type,
                    "success_action_status": "201",
                },
                Conditions=[
                    {"Content-Type": content_type},
                    ["content-length-range", 1, AWS_S3_UPLOAD_MAX_BYTES],
                ],
            )
        except Exception as exc:
            raise RuntimeError("Unable to generate S3 upload form") from exc

        upload_url = response.get("url")
        fields = response.get("fields")
        if not isinstance(upload_url, str) or not upload_url:
            raise RuntimeError("S3 returned an invalid upload URL")
        if not isinstance(fields, dict):
            raise RuntimeError("S3 returned invalid form fields")

        normalized_fields: dict[str, str] = {
            str(key): str(value) for key, value in fields.items() if value is not None
        }

        return PresignedPostResult(
            upload_url=upload_url,
            upload_fields=normalized_fields,
            object_key=object_key,
            expires_in_seconds=AWS_S3_PRESIGN_EXPIRY_SECONDS,
            max_bytes=AWS_S3_UPLOAD_MAX_BYTES,
        )


try:
    s3_service = S3Service()
except ValueError:
    s3_service = None
