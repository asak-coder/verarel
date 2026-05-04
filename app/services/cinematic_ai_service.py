from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import UploadFile

AI_CINEMATIC_PROVIDER = os.getenv("AI_CINEMATIC_PROVIDER", "mock").strip().lower()
AI_CINEMATIC_API_BASE_URL = os.getenv("AI_CINEMATIC_API_BASE_URL", "https://api.example-cinematic-ai.com/v1").strip()
AI_CINEMATIC_API_KEY = os.getenv("AI_CINEMATIC_API_KEY", "").strip()
AI_CINEMATIC_WEBHOOK_SECRET = os.getenv("AI_CINEMATIC_WEBHOOK_SECRET", "").strip()
AI_CINEMATIC_TIMEOUT_SECONDS = float(os.getenv("AI_CINEMATIC_TIMEOUT_SECONDS", "30"))

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
AWS_REGION = os.getenv("AWS_REGION", "us-east-1").strip()
AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET", "").strip()
AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL", "").strip()
AWS_S3_PRESIGN_EXPIRY_SECONDS = 300
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


@dataclass(slots=True)
class CinematicUploadResult:
    original_object_key: str
    original_presigned_url: str
    provider_job_id: str | None = None
    webhook_target_url: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class CinematicWebhookResult:
    job_id: str
    output_image_url: str
    metadata: dict[str, Any] | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _build_s3_host() -> str:
    if AWS_S3_ENDPOINT_URL:
        parsed = urllib.parse.urlparse(AWS_S3_ENDPOINT_URL)
        if not parsed.hostname:
            raise ValueError("AWS_S3_ENDPOINT_URL is invalid")
        return parsed.hostname
    if not AWS_S3_BUCKET:
        raise ValueError("AWS_S3_BUCKET is required")
    return f"{AWS_S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com"


def _canonical_query(params: dict[str, str]) -> str:
    items = sorted((k, v) for k, v in params.items() if v != "")
    return urllib.parse.urlencode(items, quote_via=urllib.parse.quote, safe="~")


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _aws_sigv4_signing_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
    k_date = _sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = hmac.new(k_date, region.encode("utf-8"), hashlib.sha256).digest()
    k_service = hmac.new(k_region, service.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()


def _presign_s3_put_url(object_key: str, content_type: str) -> str:
    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY or not AWS_S3_BUCKET:
        raise ValueError("AWS credentials and bucket are required for presigned uploads")

    host = _build_s3_host()
    now = _utc_now()
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    scope = f"{date_stamp}/{AWS_REGION}/s3/aws4_request"

    canonical_uri = f"/{urllib.parse.quote(object_key, safe='/')}"
    query_params = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": urllib.parse.quote(f"{AWS_ACCESS_KEY_ID}/{scope}", safe=""),
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(AWS_S3_PRESIGN_EXPIRY_SECONDS),
        "X-Amz-SignedHeaders": "host;content-type",
    }
    canonical_query_string = _canonical_query(query_params)
    canonical_headers = f"content-type:{content_type}\nhost:{host}\n"
    signed_headers = "content-type;host"
    payload_hash = "UNSIGNED-PAYLOAD"

    canonical_request = "\n".join(
        [
            "PUT",
            canonical_uri,
            canonical_query_string,
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signing_key = _aws_sigv4_signing_key(AWS_SECRET_ACCESS_KEY, date_stamp, AWS_REGION, "s3")
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    base_url = AWS_S3_ENDPOINT_URL.rstrip("/") if AWS_S3_ENDPOINT_URL else f"https://{host}"
    final_query = f"{canonical_query_string}&X-Amz-Signature={signature}"
    return f"{base_url}/{urllib.parse.quote(object_key, safe='/')}?{final_query}"


def _verify_webhook_signature(raw_body: bytes, signature_header: str | None, timestamp_header: str | None) -> None:
    if not AI_CINEMATIC_WEBHOOK_SECRET:
        raise ValueError("Webhook secret is not configured")
    if not signature_header or not timestamp_header:
        raise ValueError("Missing webhook signature headers")

    try:
        timestamp = int(timestamp_header)
    except ValueError as exc:
        raise ValueError("Invalid webhook timestamp") from exc

    now = int(_utc_now().timestamp())
    if abs(now - timestamp) > 300:
        raise ValueError("Webhook timestamp is outside the allowed tolerance")

    expected = hmac.new(
        AI_CINEMATIC_WEBHOOK_SECRET.encode("utf-8"),
        f"{timestamp}.".encode("utf-8") + raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature_header):
        raise ValueError("Invalid webhook signature")


async def _read_and_validate_upload(image_file: UploadFile) -> tuple[bytes, str]:
    content_type = (image_file.content_type or "").strip().lower()
    if content_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise ValueError("Unsupported image type")

    data = await image_file.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise ValueError("Uploaded image is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Uploaded image is too large")
    return data, content_type


def _normalize_bytes_to_webp_bytes(raw_bytes: bytes) -> bytes:
    # Client already sanitizes and compresses; server keeps the contract explicit.
    # This is a deterministic placeholder conversion boundary for future image tooling.
    return raw_bytes


def _build_object_key(filename: str | None) -> str:
    suffix = ".jpg"
    if filename:
        lower = filename.lower()
        if lower.endswith(".png"):
            suffix = ".png"
        elif lower.endswith(".webp"):
            suffix = ".webp"
    token = secrets.token_urlsafe(24).replace("-", "").replace("_", "")
    date_prefix = _utc_now().strftime("%Y/%m/%d")
    return f"cinematic/{date_prefix}/{token}{suffix}"


async def prepare_cinematic_upload(image_file: UploadFile, user_id: int, edit_mode: str) -> CinematicUploadResult:
    raw_bytes, content_type = await _read_and_validate_upload(image_file)
    sanitized_bytes = _normalize_bytes_to_webp_bytes(raw_bytes)
    object_key = _build_object_key(image_file.filename)

    if AI_CINEMATIC_PROVIDER == "mock" or not AI_CINEMATIC_API_KEY:
        return CinematicUploadResult(
            original_object_key=object_key,
            original_presigned_url=f"https://example.invalid/upload/{object_key}",
            provider_job_id=f"mock-{secrets.token_hex(8)}",
            webhook_target_url=None,
            metadata={
                "provider": "mock",
                "user_id": user_id,
                "edit_mode": edit_mode,
                "content_type": content_type,
                "size": len(sanitized_bytes),
            },
        )

    presigned_url = _presign_s3_put_url(object_key, content_type)

    webhook_path = "/profile/cinematic/webhook"
    webhook_target_url = f"{AI_CINEMATIC_API_BASE_URL.rstrip('/')}{webhook_path}"

    payload = {
        "source_image_url": presigned_url,
        "webhook_url": webhook_target_url,
        "mode": edit_mode,
        "object_key": object_key,
        "expires_in_seconds": AWS_S3_PRESIGN_EXPIRY_SECONDS,
    }

    headers = {
        "Authorization": f"Bearer {AI_CINEMATIC_API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=AI_CINEMATIC_TIMEOUT_SECONDS) as client:
        response = await client.post(f"{AI_CINEMATIC_API_BASE_URL.rstrip('/')}/jobs", json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    if not isinstance(data, dict):
        raise RuntimeError("AI provider returned an invalid response")

    provider_job_id = data.get("job_id")
    if not isinstance(provider_job_id, str) or not provider_job_id:
        raise RuntimeError("AI provider response missing job_id")

    return CinematicUploadResult(
        original_object_key=object_key,
        original_presigned_url=presigned_url,
        provider_job_id=provider_job_id,
        webhook_target_url=webhook_target_url,
        metadata=data,
    )


def verify_cinematic_webhook(raw_body: bytes, signature_header: str | None, timestamp_header: str | None) -> CinematicWebhookResult:
    _verify_webhook_signature(raw_body, signature_header, timestamp_header)

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        raise ValueError("Webhook payload must be valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("Invalid webhook payload")

    job_id = payload.get("job_id")
    output_image_url = payload.get("output_image_url") or payload.get("image_url")
    if not isinstance(job_id, str) or not job_id:
        raise ValueError("Webhook payload missing job_id")
    if not isinstance(output_image_url, str) or not output_image_url:
        raise ValueError("Webhook payload missing output image URL")

    return CinematicWebhookResult(
        job_id=job_id,
        output_image_url=output_image_url,
        metadata=payload,
    )


def build_upload_response_metadata(upload: CinematicUploadResult) -> dict[str, Any]:
    return {
        "original_object_key": upload.original_object_key,
        "provider_job_id": upload.provider_job_id,
        "webhook_target_url": upload.webhook_target_url,
        "metadata": upload.metadata,
    }
