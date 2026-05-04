from __future__ import annotations

from typing import Any

from celery import shared_task

from app.services.ai_service import generate_compatibility, generate_icebreakers, moderate_content
from app.services.vector_service import upsert_user_vector


def _load_user_profile(user_id: int) -> dict[str, Any]:
    """
    Placeholder profile loader.

    Replace with async database access or a repository layer once the Phase 2
    user/profile tables and service abstractions are fully connected.
    """
    return {
        "id": user_id,
        "username": f"user_{user_id}",
        "bio": "Bio not yet wired to a profile table.",
        "preferences": {},
        "interests": [],
        "location": None,
    }


def _dummy_image_to_text(photo_ref: str | None) -> str:
    if not photo_ref:
        return "No image provided."
    return f"Image reference {photo_ref} appears to be a normal user-submitted photo."


@shared_task(name="app.workers.tasks.index_user_profile_text")
def index_user_profile_text(user_id: int, bio: str | None = None, preferences_text: str | None = None) -> dict[str, str]:
    text_parts = [part for part in [bio, preferences_text] if part]
    combined_text = " ".join(text_parts).strip()
    if not combined_text:
        return {"status": "skipped", "reason": "No text provided"}

    upsert_user_vector(
        user_id=user_id,
        text=combined_text,
        kind="profile_text",
        extra_metadata={"source": "celery", "user_id": user_id},
    )
    return {"status": "ok", "vector_kind": "profile_text"}


@shared_task(name="app.workers.tasks.generate_match_score")
def generate_match_score(user_a_id: int, user_b_id: int) -> dict[str, Any]:
    user_a = _load_user_profile(user_a_id)
    user_b = _load_user_profile(user_b_id)

    vector_context = {
        "user_a_vector_id": f"user:{user_a_id}:profile_text",
        "user_b_vector_id": f"user:{user_b_id}:profile_text",
        "semantic_signals": "Pending Pinecone fetch integration.",
    }

    result = generate_compatibility(user_a=user_a, user_b=user_b, vector_context=vector_context)
    return result.model_dump()


@shared_task(name="app.workers.tasks.generate_icebreakers_for_match")
def generate_icebreakers_for_match(user_a_id: int, user_b_id: int) -> dict[str, Any]:
    user_a = _load_user_profile(user_a_id)
    user_b = _load_user_profile(user_b_id)
    result = generate_icebreakers(user_a=user_a, user_b=user_b)
    return result.model_dump()


@shared_task(name="app.workers.tasks.moderate_user_submission")
def moderate_user_submission(bio: str, photo_ref: str | None = None) -> dict[str, Any]:
    image_description = _dummy_image_to_text(photo_ref)
    result = moderate_content(bio=bio, image_description=image_description)
    return result.model_dump()
