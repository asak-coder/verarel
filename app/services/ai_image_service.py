from __future__ import annotations

import base64
import os
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import UploadFile

AI_IMAGE_PROVIDER = os.getenv("AI_IMAGE_PROVIDER", "replicate")
AI_IMAGE_API_KEY = os.getenv("AI_IMAGE_API_KEY", "")
AI_IMAGE_API_BASE_URL = os.getenv("AI_IMAGE_API_BASE_URL", "https://api.example-ai-image.com/v1")
AI_IMAGE_TIMEOUT_SECONDS = float(os.getenv("AI_IMAGE_TIMEOUT_SECONDS", "45"))


@dataclass(slots=True)
class AIImageEditResult:
    image_url: str
    provider_job_id: str | None = None
    metadata: dict[str, Any] | None = None


async def _normalize_image_payload(image_b64: str | None = None, image_file: UploadFile | None = None) -> str:
    if image_b64:
        candidate = image_b64.strip()
        if "," in candidate and candidate.lower().startswith("data:"):
            candidate = candidate.split(",", 1)[1].strip()

        try:
            base64.b64decode(candidate, validate=True)
        except Exception as exc:
            raise ValueError("Invalid base64 image payload") from exc

        return candidate

    if image_file is None:
        raise ValueError("An image payload is required")

    file_bytes = await image_file.read()
    if not file_bytes:
        raise ValueError("Uploaded image is empty")

    return base64.b64encode(file_bytes).decode("utf-8")


async def edit_image_with_ai(
    image_b64: str | None,
    edit_command: str,
    image_file: UploadFile | None = None,
) -> AIImageEditResult:
    """
    Wrapper for a third-party AI image editing API.

    Drop your real API key/provider values into the environment variables:
    - AI_IMAGE_PROVIDER
    - AI_IMAGE_API_KEY
    - AI_IMAGE_API_BASE_URL

    The HTTP request below is intentionally written as a commented/stubbed example
    so you can replace the endpoint and payload with the provider of your choice
    (Replicate, Photoroom, Cloudinary, etc.) without changing the router contract.
    """
    normalized_image = await _normalize_image_payload(image_b64=image_b64, image_file=image_file)
    command = edit_command.strip()
    if not command:
        raise ValueError("An edit command is required")

    # Example provider flow:
    # 1. POST base64 image + command to the external API
    # 2. Poll job status if the provider is asynchronous
    # 3. Return the final hosted image URL
    #
    # The block below is a safe stub that can be enabled later by swapping the
    # commented request for a real provider request.

    if not AI_IMAGE_API_KEY:
        mock_job_id = f"mock-{uuid.uuid4().hex[:12]}"
        return AIImageEditResult(
            image_url=f"https://cdn.example.com/ai-edits/{mock_job_id}.jpg",
            provider_job_id=mock_job_id,
            metadata={
                "provider": AI_IMAGE_PROVIDER,
                "mode": "stub",
                "command": command,
            },
        )

    headers = {
        "Authorization": f"Bearer {AI_IMAGE_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "image_base64": normalized_image,
        "edit_command": command,
        "output_format": "jpeg",
    }

    async with httpx.AsyncClient(timeout=AI_IMAGE_TIMEOUT_SECONDS) as client:
        # Real implementation example:
        # response = await client.post(
        #     f"{AI_IMAGE_API_BASE_URL}/edit",
        #     headers=headers,
        #     json=payload,
        # )
        # response.raise_for_status()
        # data = response.json()
        # return AIImageEditResult(
        #     image_url=data["image_url"],
        #     provider_job_id=data.get("job_id"),
        #     metadata=data,
        # )

        # Temporary stubbed call path for easy provider replacement:
        response = await client.post(
            f"{AI_IMAGE_API_BASE_URL}/edit",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    image_url = data.get("image_url") or data.get("url")
    if not isinstance(image_url, str) or not image_url:
        raise RuntimeError("AI image provider returned an invalid response")

    return AIImageEditResult(
        image_url=image_url,
        provider_job_id=data.get("job_id") if isinstance(data.get("job_id"), str) else None,
        metadata=data if isinstance(data, dict) else None,
    )
