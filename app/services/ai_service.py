from __future__ import annotations

import json
import os
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20240620")


class CompatibilityOutput(BaseModel):
    compatibility_score: int = Field(ge=1, le=100)
    match_reason: str = Field(min_length=20, max_length=500)


class IcebreakerOutput(BaseModel):
    icebreakers: list[str] = Field(min_length=3, max_length=3)


class ModerationOutput(BaseModel):
    is_flagged: bool
    flag_reason: str = Field(min_length=5, max_length=300)
    categories: list[str] = Field(default_factory=list)


def _build_llm() -> ChatAnthropic:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    return ChatAnthropic(
        api_key=ANTHROPIC_API_KEY,
        model=ANTHROPIC_MODEL,
        temperature=0.2,
        max_retries=0,
    )


def _extract_json_text(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
    return stripped


def _invoke_with_retry(chain: Any, payload: dict[str, Any]) -> Any:
    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _run() -> Any:
        return chain.invoke(payload)

    return _run()


def build_compatibility_chain() -> Any:
    parser = PydanticOutputParser(pydantic_object=CompatibilityOutput)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a matchmaking analyst. Return only valid JSON that matches the schema.\n{format_instructions}",
            ),
            (
                "human",
                "User A profile:\n{user_a}\n\nUser B profile:\n{user_b}\n\nVector similarity context:\n{vector_context}\n\n"
                "Produce a compatibility score from 1-100 and a concise reason.",
            ),
        ]
    )
    return prompt.partial(format_instructions=parser.get_format_instructions()) | _build_llm() | parser


def build_icebreaker_chain() -> Any:
    parser = PydanticOutputParser(pydantic_object=IcebreakerOutput)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You generate concise personalized opening messages. Output only valid JSON.\n{format_instructions}",
            ),
            (
                "human",
                "Profile 1:\n{user_a}\n\nProfile 2:\n{user_b}\n\nGenerate exactly 3 icebreakers that feel contextual, warm, and not generic.",
            ),
        ]
    )
    return prompt.partial(format_instructions=parser.get_format_instructions()) | _build_llm() | parser


def build_moderation_chain() -> Any:
    parser = PydanticOutputParser(pydantic_object=ModerationOutput)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a moderation reviewer. Evaluate for safety/compliance and output only JSON.\n{format_instructions}",
            ),
            (
                "human",
                "Bio text:\n{bio}\n\nImage description (dummy image-to-text):\n{image_description}\n\n"
                "Flag explicit sexual content, hate, harassment, scams, minors, self-harm, or illegal content.",
            ),
        ]
    )
    return prompt.partial(format_instructions=parser.get_format_instructions()) | _build_llm() | parser


def generate_compatibility(user_a: dict[str, Any], user_b: dict[str, Any], vector_context: dict[str, Any]) -> CompatibilityOutput:
    chain = build_compatibility_chain()
    return _invoke_with_retry(
        chain,
        {
            "user_a": json.dumps(user_a, ensure_ascii=False),
            "user_b": json.dumps(user_b, ensure_ascii=False),
            "vector_context": json.dumps(vector_context, ensure_ascii=False),
        },
    )


def generate_icebreakers(user_a: dict[str, Any], user_b: dict[str, Any]) -> IcebreakerOutput:
    chain = build_icebreaker_chain()
    return _invoke_with_retry(
        chain,
        {
            "user_a": json.dumps(user_a, ensure_ascii=False),
            "user_b": json.dumps(user_b, ensure_ascii=False),
        },
    )


def moderate_content(bio: str, image_description: str) -> ModerationOutput:
    chain = build_moderation_chain()
    return _invoke_with_retry(chain, {"bio": bio, "image_description": image_description})
