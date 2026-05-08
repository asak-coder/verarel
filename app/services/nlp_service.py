from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.models.user import User
from app.services.vector_service import PINECONE_NAMESPACE, get_pinecone_index

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20240620")
MAX_CHAT_SUGGESTION_MESSAGES = int(os.getenv("MAX_CHAT_SUGGESTION_MESSAGES", "10"))
MAX_CHAT_MESSAGE_LENGTH = int(os.getenv("MAX_CHAT_MESSAGE_LENGTH", "500"))
SANITIZE_RE = re.compile(r"[\x00-\x1f\x7f<>`$\\\\]")


class ModerationResult(BaseModel):
    is_flagged: bool
    flag_reason: str = Field(min_length=5, max_length=300)
    categories: list[str] = Field(default_factory=list)


class IcebreakerResult(BaseModel):
    icebreakers: list[str] = Field(min_length=3, max_length=3)


class ToneAnalysisResult(BaseModel):
    analysis: str = Field(min_length=5, max_length=140)


class ChatSuggestionsResult(BaseModel):
    suggestions: list[str] = Field(min_length=3, max_length=5)


@dataclass(frozen=True)
class UserProfileContext:
    user_id: int
    username: str
    bio_text: str
    vector_text: str | None = None


def _build_llm() -> ChatAnthropic:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    return ChatAnthropic(
        api_key=SecretStr(ANTHROPIC_API_KEY),
        model_name=ANTHROPIC_MODEL,
        temperature=0.2,
        timeout=30,
        stop=None,
        max_retries=0,
    )


def _invoke_with_retry(chain: Any, payload: dict[str, Any]) -> Any:
    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _run() -> Any:
        return chain.ainvoke(payload)

    return _run()


async def _fetch_user_profile(session: AsyncSession, user_id: int) -> UserProfileContext:
    user = await session.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise ValueError(f"User {user_id} not found")

    bio_text = f"Username: {user.username}. Bio: unavailable."
    vector_text = await _fetch_vector_text(user_id)
    return UserProfileContext(
        user_id=user.id,
        username=user.username,
        bio_text=bio_text,
        vector_text=vector_text,
    )


async def _fetch_vector_text(user_id: int) -> str | None:
    try:
        index = get_pinecone_index()
    except Exception:
        return None

    try:
        response = index.fetch(ids=[f"user:{user_id}:profile_text"], namespace=PINECONE_NAMESPACE)
    except Exception:
        return None

    vectors = getattr(response, "vectors", None) or {}
    vector = vectors.get(f"user:{user_id}:profile_text")
    if not vector:
        return None

    metadata = getattr(vector, "metadata", None) or {}
    text = metadata.get("text")
    return str(text) if text else None


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _sanitize_text(value: str, max_length: int) -> str:
    cleaned = SANITIZE_RE.sub(" ", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:max_length]


def _sanitize_recent_messages(recent_messages: list[Any]) -> list[dict[str, str]]:
    sanitized: list[dict[str, str]] = []
    for item in recent_messages[-MAX_CHAT_SUGGESTION_MESSAGES:]:
        if not isinstance(item, dict):
            continue
        role = _sanitize_text(str(item.get("role", "unknown")), 32)
        content = _sanitize_text(str(item.get("content", "")), MAX_CHAT_MESSAGE_LENGTH)
        if content:
            sanitized.append({"role": role, "content": content})
    return sanitized


async def moderate_text(message: str) -> ModerationResult:
    parser = PydanticOutputParser(pydantic_object=ModerationResult)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a chat safety moderator. Return only valid JSON.\n"
                "{format_instructions}\n"
                "Flag hate speech, harassment, threats, sexual exploitation, scams, crypto/investment fraud, phishing, "
                "money requests, off-platform payment tricks, and suspicious links.",
            ),
            (
                "human",
                "Message:\n{message}\n\n"
                "Respond strictly in JSON with is_flagged, flag_reason, and categories.",
            ),
        ]
    )
    chain = prompt.partial(format_instructions=parser.get_format_instructions()) | _build_llm() | parser
    return await _invoke_with_retry(chain, {"message": _sanitize_text(message, MAX_CHAT_MESSAGE_LENGTH)})


async def generate_icebreakers(session: AsyncSession, user_a_id: int, user_b_id: int) -> IcebreakerResult:
    parser = PydanticOutputParser(pydantic_object=IcebreakerResult)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You write personalized dating app openers. Return only valid JSON.\n{format_instructions}\n"
                "Create warm, specific, non-cringe icebreakers from profile context.",
            ),
            (
                "human",
                "User A profile JSON:\n{user_a}\n\nUser B profile JSON:\n{user_b}\n\n"
                "Write exactly 3 one-line openers for User A to send User B.",
            ),
        ]
    )
    chain = prompt.partial(format_instructions=parser.get_format_instructions()) | _build_llm() | parser

    user_a = await _fetch_user_profile(session, user_a_id)
    user_b = await _fetch_user_profile(session, user_b_id)
    payload = {
        "user_a": _json_text(
            {
                "id": user_a.user_id,
                "username": user_a.username,
                "bio_text": user_a.bio_text,
                "vector_text": user_a.vector_text,
            }
        ),
        "user_b": _json_text(
            {
                "id": user_b.user_id,
                "username": user_b.username,
                "bio_text": user_b.bio_text,
                "vector_text": user_b.vector_text,
            }
        ),
    }
    return await _invoke_with_retry(chain, payload)


async def generate_chat_suggestions(
    session: AsyncSession,
    user_id: int,
    match_id: int,
    match_user_id: int,
    recent_messages: list[Any],
    mode: str,
) -> ChatSuggestionsResult:
    parser = PydanticOutputParser(pydantic_object=ChatSuggestionsResult)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a smart dating conversation assistant. Return only valid JSON.\n{format_instructions}\n"
                "Generate concise, natural suggestions that improve conversation quality.\n"
                "Modes: icebreaker, reply, reengagement.\n"
                "Avoid explicit sexual content, harassment, scams, or manipulative language.\n"
                "Use only the recent context provided.",
            ),
            (
                "human",
                "Mode: {mode}\n\n"
                "Current user profile JSON:\n{user_profile}\n\n"
                "Match profile JSON:\n{match_profile}\n\n"
                "Recent messages JSON:\n{recent_messages}\n\n"
                "Return 3 to 5 short suggestions the user can send next.",
            ),
        ]
    )
    chain = prompt.partial(format_instructions=parser.get_format_instructions()) | _build_llm() | parser

    user_profile = await _fetch_user_profile(session, user_id)
    match_profile = await _fetch_user_profile(session, match_user_id)
    sanitized_messages = _sanitize_recent_messages(recent_messages)
    payload = {
        "mode": _sanitize_text(mode, 24),
        "user_profile": _json_text(
            {
                "id": user_profile.user_id,
                "username": user_profile.username,
                "bio_text": user_profile.bio_text,
                "vector_text": user_profile.vector_text,
            }
        ),
        "match_profile": _json_text(
            {
                "id": match_profile.user_id,
                "username": match_profile.username,
                "bio_text": match_profile.bio_text,
                "vector_text": match_profile.vector_text,
            }
        ),
        "recent_messages": _json_text(sanitized_messages),
    }
    return await _invoke_with_retry(chain, payload)


async def analyze_tone(draft_message: str) -> ToneAnalysisResult:
    parser = PydanticOutputParser(pydantic_object=ToneAnalysisResult)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a concise tone coach. Return only valid JSON.\n{format_instructions}\n"
                "Be brief, friendly, and specific. Do not over-explain.",
            ),
            (
                "human",
                "Draft message:\n{draft_message}\n\n"
                "Return a single short sentence like 'Sounds friendly!' or 'Might come across as too aggressive.'",
            ),
        ]
    )
    chain = prompt.partial(format_instructions=parser.get_format_instructions()) | _build_llm() | parser
    return await _invoke_with_retry(chain, {"draft_message": _sanitize_text(draft_message, MAX_CHAT_MESSAGE_LENGTH)})
