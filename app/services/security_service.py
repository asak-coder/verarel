from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class LivenessVerificationResult:
    is_verified: bool
    score: float
    provider_session_id: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class ImageModerationResult:
    is_nsfw: bool
    confidence: float
    labels: list[str]
    metadata: dict[str, Any] | None = None


async def verify_liveness_session(session_token: str) -> LivenessVerificationResult:
    """
    Mock liveness verification hook.

    Replace this with a real FaceTec/Onfido SDK callback or provider API call.
    The mock keeps the contract stable for the mobile onboarding flow.
    """
    token = session_token.strip()
    if not token:
        raise ValueError("session_token is required")

    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    score_seed = int(digest[:8], 16)
    score = 0.5 + (score_seed % 5000) / 10000.0

    return LivenessVerificationResult(
        is_verified=score >= 0.72,
        score=round(score, 4),
        provider_session_id=f"mock-session-{digest[:12]}",
        metadata={
            "provider": "mock",
            "checked": True,
        },
    )


async def analyze_image_payload(image_data: str) -> ImageModerationResult:
    """
    Mock NSFW analysis for chat images.

    Accepts a base64 string or data URL payload and returns a moderation verdict
    that can be used to blur content before broadcasting.
    """
    payload = image_data.strip()
    if not payload:
        raise ValueError("image_data is required")

    if payload.lower().startswith("data:") and "," in payload:
        payload = payload.split(",", 1)[1].strip()

    try:
        decoded = base64.b64decode(payload, validate=True)
    except Exception as exc:
        raise ValueError("Invalid image payload") from exc

    byte_sum = sum(decoded[:2048])
    entropy_hint = len(set(decoded[:256]))

    score = ((byte_sum % 100) / 100.0) * 0.55 + min(entropy_hint / 256.0, 1.0) * 0.45
    is_nsfw = score >= 0.72

    labels = ["safe"]
    if is_nsfw:
        labels = ["nudity", "explicit", "unsafe"]

    return ImageModerationResult(
        is_nsfw=is_nsfw,
        confidence=round(score, 4),
        labels=labels,
        metadata={
            "provider": "mock",
            "bytes": len(decoded),
        },
    )
