from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.compatibility import CompatibilityScore
from app.models.interaction import ChatMessage, Match
from app.models.profile import Profile
from app.observability.metrics import observe_redis_command, set_redis_hit_ratio
from app.services.redis_service import redis_service

MAX_BIO_LENGTH = 5000
MAX_INTERESTS = 40
MAX_INTEREST_LENGTH = 64
CACHE_TTL_SECONDS = 900
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 10
CACHE_PREFIX = "compatibility"
RATE_LIMIT_PREFIX = "compatibility:ratelimit"
SANITIZE_RE = re.compile(r"[\x00-\x1f\x7f<>`$\\\\]")
HARMFUL_RE = re.compile(
    r"(password|credit card|crypto|wallet|seed phrase|off-platform|cash app|venmo|telegram|whatsapp|bitcoin)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class CompatibilityResult:
    score: int
    reasons: list[str]
    updated_at: datetime
    cache_hit: bool = False
    computed_at: datetime | None = None


def _normalize_pair(user_id_1: int, user_id_2: int) -> tuple[int, int]:
    if user_id_1 == user_id_2:
        raise ValueError("Users must be different")
    low = min(user_id_1, user_id_2)
    high = max(user_id_1, user_id_2)
    return (low, high)


def cache_key(user_id_1: int, user_id_2: int) -> str:
    low, high = _normalize_pair(user_id_1, user_id_2)
    return f"{CACHE_PREFIX}:{low}:{high}"


def _sanitize_text(value: str, max_length: int) -> str:
    cleaned = SANITIZE_RE.sub(" ", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:max_length]


def _safe_interest_list(items: list[Any]) -> list[str]:
    safe: list[str] = []
    for item in items[:MAX_INTERESTS]:
        text_value = _sanitize_text(str(item), MAX_INTEREST_LENGTH)
        if text_value:
            safe.append(text_value.lower())
    return safe


def _semantic_overlap_score(text_a: str, text_b: str) -> tuple[int, list[str]]:
    tokens_a = {token for token in re.findall(r"[a-z0-9]+", text_a.lower()) if len(token) > 2}
    tokens_b = {token for token in re.findall(r"[a-z0-9]+", text_b.lower()) if len(token) > 2}
    if not tokens_a or not tokens_b:
        return 0, []
    intersection = tokens_a & tokens_b
    jaccard = len(intersection) / len(tokens_a | tokens_b)
    reasons: list[str] = []
    if intersection:
        reasons.append("Similar profile language and interests")
    return int(round(jaccard * 35)), reasons


def _interest_score(interests_a: list[str], interests_b: list[str]) -> tuple[int, list[str]]:
    set_a = set(interests_a)
    set_b = set(interests_b)
    if not set_a or not set_b:
        return 0, []
    overlap = sorted(set_a & set_b)
    score = min(30, len(overlap) * 10)
    reasons = [f"Both enjoy {', '.join(overlap[:3])}"] if overlap else []
    return score, reasons


def _behavior_score(message_count: int, positive_ratio: float) -> tuple[int, list[str]]:
    score = min(25, int(message_count * 3) + int(positive_ratio * 15))
    reasons: list[str] = []
    if message_count >= 3:
        reasons.append("High response engagement")
    if positive_ratio >= 0.6:
        reasons.append("Similar communication style")
    return score, reasons


def _location_score(distance_km: float | None) -> tuple[int, list[str]]:
    if distance_km is None:
        return 0, []
    if distance_km <= 5:
        return 10, ["Close in location"]
    if distance_km <= 25:
        return 6, ["Reasonable distance for meeting up"]
    return 2, []


def _safety_penalty(bio_a: str, bio_b: str) -> int:
    return 20 if HARMFUL_RE.search(bio_a) or HARMFUL_RE.search(bio_b) else 0


def _finalize_score(raw_score: int) -> int:
    return max(0, min(100, raw_score))


async def _fetch_pair_by_match(db: AsyncSession, match_id: int) -> tuple[int, int]:
    match = await db.scalar(select(Match).where(Match.id == match_id))
    if match is None:
        raise LookupError("Match not found")
    return match.user_a_id, match.user_b_id


async def _fetch_profiles(db: AsyncSession, user_id_1: int, user_id_2: int) -> tuple[Profile, Profile]:
    profile_1 = await db.scalar(select(Profile).where(Profile.user_id == user_id_1))
    profile_2 = await db.scalar(select(Profile).where(Profile.user_id == user_id_2))
    if profile_1 is None or profile_2 is None:
        raise LookupError("Profile not found")
    return profile_1, profile_2


def _message_signature(message: str) -> float:
    lowered = message.lower()
    positive_markers = ("thanks", "love", "great", "cool", "awesome", "haha", "lol", "nice", "sure", "sounds good")
    negative_markers = ("hate", "stop", "no", "angry", "upset", "boring", "annoying")
    pos = sum(1 for marker in positive_markers if marker in lowered)
    neg = sum(1 for marker in negative_markers if marker in lowered)
    return max(0.0, min(1.0, (pos + 1) / (pos + neg + 2)))


async def _behavior_from_chat(db: AsyncSession, user_id_1: int, user_id_2: int) -> tuple[int, list[str]]:
    result = await db.execute(
        select(ChatMessage.message)
        .join(Match, Match.id == ChatMessage.match_id)
        .where(
            ((Match.user_a_id == user_id_1) & (Match.user_b_id == user_id_2))
            | ((Match.user_a_id == user_id_2) & (Match.user_b_id == user_id_1))
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(20)
    )
    messages = [row[0] for row in result.all()]
    if not messages:
        return 0, []
    positive_ratio = sum(_message_signature(message) for message in messages) / len(messages)
    return _behavior_score(len(messages), positive_ratio)


def _location_distance_km(profile_1: Profile, profile_2: Profile) -> float | None:
    if getattr(profile_1.user, "location", None) is None or getattr(profile_2.user, "location", None) is None:
        return None
    return 0.0


def _build_reasons(*reason_groups: list[str]) -> list[str]:
    seen: set[str] = set()
    reasons: list[str] = []
    for group in reason_groups:
        for reason in group:
            if reason and reason not in seen:
                seen.add(reason)
                reasons.append(reason)
    return reasons[:5]


async def get_cached_compatibility(user_id_1: int, user_id_2: int) -> CompatibilityResult | None:
    key = cache_key(user_id_1, user_id_2)
    started = time.perf_counter()
    try:
        client = await redis_service.connect()
        cached = await client.get(key)
        observe_redis_command("get", time.perf_counter() - started, "ok")
        if not cached:
            set_redis_hit_ratio("compatibility", 0.0)
            return None
        payload = json.loads(cached)
        set_redis_hit_ratio("compatibility", 1.0)
        return CompatibilityResult(
            score=int(payload["score"]),
            reasons=list(payload.get("reasons", [])),
            updated_at=datetime.fromisoformat(payload["updated_at"]),
            cache_hit=True,
            computed_at=datetime.fromisoformat(payload["computed_at"]) if payload.get("computed_at") else None,
        )
    except Exception:
        observe_redis_command("get", time.perf_counter() - started, "error")
        return None


async def set_cached_compatibility(user_id_1: int, user_id_2: int, result: CompatibilityResult) -> None:
    key = cache_key(user_id_1, user_id_2)
    started = time.perf_counter()
    payload = json.dumps(
        {
            "score": result.score,
            "reasons": result.reasons,
            "updated_at": result.updated_at.isoformat(),
            "computed_at": (result.computed_at or result.updated_at).isoformat(),
        },
        separators=(",", ":"),
    )
    try:
        client = await redis_service.connect()
        await client.setex(key, CACHE_TTL_SECONDS, payload)
        observe_redis_command("setex", time.perf_counter() - started, "ok")
    except Exception:
        observe_redis_command("setex", time.perf_counter() - started, "error")


async def store_compatibility(
    db: AsyncSession,
    user_id_1: int,
    user_id_2: int,
    score: int,
    reasons: list[str],
    updated_at: datetime | None = None,
) -> None:
    low_id, high_id = _normalize_pair(user_id_1, user_id_2)
    updated_at = updated_at or datetime.now(timezone.utc)
    row = await db.scalar(
        select(CompatibilityScore).where(
            CompatibilityScore.user_id_1 == low_id,
            CompatibilityScore.user_id_2 == high_id,
        )
    )
    if row is None:
        row = CompatibilityScore(
            user_id_1=low_id,
            user_id_2=high_id,
            score=score,
            reasons=reasons,
            cache_key=cache_key(low_id, high_id),
            updated_at=updated_at,
        )
        db.add(row)
    else:
        row.score = score
        row.reasons = reasons
        row.cache_key = cache_key(low_id, high_id)
        row.updated_at = updated_at
    await db.commit()
    await db.refresh(row)


async def rate_limit_compatibility(user_id: int) -> None:
    client = await redis_service.connect()
    window = int(datetime.now(timezone.utc).timestamp() // RATE_LIMIT_WINDOW_SECONDS)
    key = f"{RATE_LIMIT_PREFIX}:{user_id}:{window}"
    current = await client.incr(key)
    if current == 1:
        await client.expire(key, RATE_LIMIT_WINDOW_SECONDS + 1)
    if current > RATE_LIMIT_MAX_REQUESTS:
        raise PermissionError("Rate limit exceeded")


async def calculate_compatibility(db: AsyncSession, user_id_1: int, user_id_2: int) -> CompatibilityResult:
    low_id, high_id = _normalize_pair(user_id_1, user_id_2)

    cached = await get_cached_compatibility(low_id, high_id)
    if cached is not None:
        return cached

    profile_1, profile_2 = await _fetch_profiles(db, low_id, high_id)
    bio_1 = _sanitize_text(profile_1.bio, MAX_BIO_LENGTH)
    bio_2 = _sanitize_text(profile_2.bio, MAX_BIO_LENGTH)
    interests_1 = _safe_interest_list(profile_1.interests or [])
    interests_2 = _safe_interest_list(profile_2.interests or [])

    semantic_score, semantic_reasons = _semantic_overlap_score(bio_1, bio_2)
    interest_score, interest_reasons = _interest_score(interests_1, interests_2)
    behavior_score, behavior_reasons = await _behavior_from_chat(db, low_id, high_id)
    location_score, location_reasons = _location_score(_location_distance_km(profile_1, profile_2))

    total = semantic_score + interest_score + behavior_score + location_score - _safety_penalty(bio_1, bio_2)
    score = _finalize_score(total)
    reasons = _build_reasons(interest_reasons, semantic_reasons, behavior_reasons, location_reasons)

    updated_at = datetime.now(timezone.utc)
    await store_compatibility(db, low_id, high_id, score, reasons, updated_at)
    result = CompatibilityResult(score=score, reasons=reasons, updated_at=updated_at, computed_at=updated_at)
    await set_cached_compatibility(low_id, high_id, result)
    return result


async def recompute_and_cache(db: AsyncSession, user_id_1: int, user_id_2: int) -> CompatibilityResult:
    result = await calculate_compatibility(db, user_id_1, user_id_2)
    await set_cached_compatibility(user_id_1, user_id_2, result)
    return result


async def get_compatibility_row(db: AsyncSession, user_id_1: int, user_id_2: int) -> CompatibilityScore | None:
    low_id, high_id = _normalize_pair(user_id_1, user_id_2)
    return await db.scalar(
        select(CompatibilityScore).where(
            CompatibilityScore.user_id_1 == low_id,
            CompatibilityScore.user_id_2 == high_id,
        )
    )


async def get_compatibility_by_match(db: AsyncSession, match_id: int) -> tuple[CompatibilityResult, tuple[int, int]]:
    user_id_1, user_id_2 = await _fetch_pair_by_match(db, match_id)
    result = await calculate_compatibility(db, user_id_1, user_id_2)
    return result, (user_id_1, user_id_2)
