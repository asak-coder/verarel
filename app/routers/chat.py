from __future__ import annotations

import asyncio
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ALGORITHM, SECRET_KEY
from app.database import SessionLocal, get_db
from app.models.interaction import ChatMessage, Match
from app.services.nlp_service import analyze_tone, generate_chat_suggestions, generate_icebreakers, moderate_text
from app.services.redis_service import redis_service
from app.services.security_service import analyze_image_payload

router = APIRouter(prefix="/chat", tags=["chat"])


class IcebreakerRequest(BaseModel):
    user_a_id: int = Field(gt=0)
    user_b_id: int = Field(gt=0)

    model_config = ConfigDict(extra="forbid")


class IcebreakerResponse(BaseModel):
    icebreakers: list[str]

    model_config = ConfigDict(from_attributes=True)


class ToneCheckRequest(BaseModel):
    draft_message: str = Field(min_length=1, max_length=2000)

    model_config = ConfigDict(extra="forbid")


class ToneCheckResponse(BaseModel):
    analysis: str

    model_config = ConfigDict(from_attributes=True)


class ChatSuggestionsRequest(BaseModel):
    user_id: int = Field(gt=0)
    match_id: int = Field(gt=0)
    recent_messages: list[dict[str, Any]] = Field(default_factory=list)
    mode: str = Field(default="reply", min_length=3, max_length=32)

    model_config = ConfigDict(extra="forbid")


class ChatSuggestionsResponse(BaseModel):
    suggestions: list[str]
    cache_hit: bool = False

    model_config = ConfigDict(from_attributes=True)


@dataclass(slots=True)
class ActiveConnection:
    connection_id: str
    websocket: WebSocket
    user_id: int
    match_id: int


class ConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[int, dict[str, ActiveConnection]] = defaultdict(dict)
        self._lock = asyncio.Lock()

    async def connect(self, match_id: int, connection: ActiveConnection) -> None:
        async with self._lock:
            self._rooms[match_id][connection.connection_id] = connection
        await redis_service.add_socket_to_room(match_id, connection.connection_id)

    async def disconnect(self, match_id: int, connection_id: str) -> None:
        async with self._lock:
            room = self._rooms.get(match_id)
            if room and connection_id in room:
                room.pop(connection_id, None)
                if not room:
                    self._rooms.pop(match_id, None)
        await redis_service.remove_socket_from_room(match_id, connection_id)

    async def broadcast(self, match_id: int, message: dict[str, Any]) -> None:
        async with self._lock:
            recipients = list(self._rooms.get(match_id, {}).values())

        for connection in recipients:
            try:
                await connection.websocket.send_json(message)
            except Exception:
                await self.disconnect(match_id, connection.connection_id)


manager = ConnectionManager()


async def _authenticate_websocket(websocket: WebSocket) -> int:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        raise WebSocketDisconnect(code=1008)

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        subject = payload.get("sub")
        if not subject:
            raise ValueError("missing subject")
        return int(subject)
    except (JWTError, ValueError, TypeError):
        await websocket.close(code=1008)
        raise WebSocketDisconnect(code=1008)


async def _validate_match_access(session: AsyncSession, match_id: int, user_id: int) -> Match | None:
    match = await session.scalar(select(Match).where(Match.id == match_id))
    if match is None:
        return None
    if user_id not in {match.user_a_id, match.user_b_id}:
        return None
    return match


async def _persist_message(match_id: int, sender_id: int, message_text: str) -> ChatMessage:
    async with SessionLocal() as session:
        message = ChatMessage(
            match_id=match_id,
            sender_id=sender_id,
            message=message_text,
            created_at=datetime.now(timezone.utc),
        )
        session.add(message)
        await session.commit()
        await session.refresh(message)
        return message


def _is_image_payload(payload: dict[str, Any]) -> bool:
    return any(key in payload for key in ("image_base64", "image_data", "image_url"))


def _fallback_suggestions(mode: str) -> list[str]:
    if mode == "icebreaker":
        return [
            "Hey, I noticed your profile and wanted to say hi.",
            "What’s something you’ve been into lately?",
            "Any weekend plans you’re excited about?",
        ]
    if mode == "reengagement":
        return [
            "Hey! How’s your week going?",
            "What are you up to today?",
            "Thought I’d check in and say hi.",
        ]
    return [
        "That sounds interesting, tell me more.",
        "What happened next?",
        "What do you usually do in that situation?",
    ]


async def _generate_and_cache_chat_suggestions(
    user_id: int,
    match_id: int,
    recent_messages: list[dict[str, Any]],
    mode: str,
) -> None:
    async with SessionLocal() as session:
        match = await session.scalar(select(Match).where(Match.id == match_id))
        if match is None:
            return
        match_user_id = match.user_b_id if match.user_a_id == user_id else match.user_a_id
        try:
            result = await generate_chat_suggestions(
                session=session,
                user_id=user_id,
                match_id=match_id,
                match_user_id=match_user_id,
                recent_messages=recent_messages,
                mode=mode,
            )
            await redis_service.set_chat_suggestions(user_id, match_id, result.suggestions)
        except Exception:
            await redis_service.set_chat_suggestions(user_id, match_id, _fallback_suggestions(mode))


@router.post("/icebreakers", response_model=IcebreakerResponse, status_code=status.HTTP_200_OK)
async def get_icebreakers(
    request: IcebreakerRequest,
    db: AsyncSession = Depends(get_db),
) -> IcebreakerResponse:
    try:
        result = await generate_icebreakers(db, request.user_a_id, request.user_b_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to generate icebreakers") from exc

    return IcebreakerResponse(icebreakers=result.icebreakers)


@router.post("/tone-check", response_model=ToneCheckResponse, status_code=status.HTTP_200_OK)
async def get_tone_check(request: ToneCheckRequest) -> ToneCheckResponse:
    try:
        result = await analyze_tone(request.draft_message)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to analyze tone") from exc

    return ToneCheckResponse(analysis=result.analysis)


@router.get("/suggestions/{match_id}", response_model=ChatSuggestionsResponse, status_code=status.HTTP_200_OK)
@router.get("/api/chat/suggestions/{match_id}", response_model=ChatSuggestionsResponse, include_in_schema=False)
async def get_chat_suggestions(match_id: int, user_id: int = Query(gt=0), db: AsyncSession = Depends(get_db)) -> ChatSuggestionsResponse:
    match = await db.scalar(select(Match).where(Match.id == match_id))
    if match is None or user_id not in {match.user_a_id, match.user_b_id}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")
    cached = await redis_service.get_chat_suggestions(user_id, match_id)
    if cached is not None:
        return ChatSuggestionsResponse(suggestions=cached, cache_hit=True)
    await _generate_and_cache_chat_suggestions(
        user_id=user_id,
        match_id=match_id,
        recent_messages=[],
        mode="icebreaker" if not await db.scalar(select(ChatMessage.id).where(ChatMessage.match_id == match_id)) else "reply",
    )
    fallback = await redis_service.get_chat_suggestions(user_id, match_id) or _fallback_suggestions("reply")
    return ChatSuggestionsResponse(suggestions=fallback, cache_hit=False)


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_chat_suggestions_async(
    request: ChatSuggestionsRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    match = await db.scalar(select(Match).where(Match.id == request.match_id))
    if match is None or request.user_id not in {match.user_a_id, match.user_b_id}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")
    background_tasks.add_task(
        _generate_and_cache_chat_suggestions,
        request.user_id,
        request.match_id,
        request.recent_messages,
        request.mode,
    )
    return {"status": "queued"}


@router.websocket("/ws/{match_id}")
async def websocket_chat(websocket: WebSocket, match_id: int) -> None:
    user_id = await _authenticate_websocket(websocket)

    async with SessionLocal() as session:
        match = await _validate_match_access(session, match_id, user_id)
    if match is None:
        await websocket.close(code=1008)
        raise WebSocketDisconnect(code=1008)

    await websocket.accept()
    connection_id = str(uuid.uuid4())
    active_connection = ActiveConnection(
        connection_id=connection_id,
        websocket=websocket,
        user_id=user_id,
        match_id=match_id,
    )
    await manager.connect(match_id, active_connection)

    try:
        while True:
            raw_message = await websocket.receive_text()
            try:
                payload = json.loads(raw_message)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "detail": "Invalid JSON payload"})
                continue

            message_text = str(payload.get("message", "")).strip()
            image_base64 = payload.get("image_base64")
            image_data = payload.get("image_data")
            image_url = payload.get("image_url")

            if not message_text and not _is_image_payload(payload):
                await websocket.send_json({"type": "error", "detail": "Message cannot be empty"})
                continue

            outgoing: dict[str, Any] = {
                "type": "message",
                "match_id": match_id,
                "sender_id": user_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            if message_text:
                moderation_result = await moderate_text(message_text)
                if moderation_result.is_flagged:
                    await websocket.send_json(
                        {
                            "type": "system_warning",
                            "detail": moderation_result.flag_reason,
                            "categories": moderation_result.categories,
                        }
                    )
                    continue

                persisted = await _persist_message(match_id, user_id, message_text)
                outgoing.update(
                    {
                        "message_id": persisted.id,
                        "message": message_text,
                        "created_at": persisted.created_at.isoformat() if persisted.created_at else datetime.now(timezone.utc).isoformat(),
                    }
                )

            if _is_image_payload(payload):
                moderation_source = str(image_base64 or image_data or image_url or "")
                moderation_result = await analyze_image_payload(moderation_source)
                outgoing.update(
                    {
                        "content_type": "image",
                        "image_url": image_url,
                        "image_base64": None if moderation_result.is_nsfw else image_base64,
                        "image_data": None if moderation_result.is_nsfw else image_data,
                        "moderation": {
                            "is_nsfw": moderation_result.is_nsfw,
                            "confidence": moderation_result.confidence,
                            "labels": moderation_result.labels,
                        },
                    }
                )
                if moderation_result.is_nsfw:
                    outgoing["display_mode"] = "blur"

            await manager.broadcast(match_id, outgoing)
            background_mode = "icebreaker" if not message_text else "reply"
            background_task_payload = [{"role": "user", "content": message_text}] if message_text else []
            asyncio.create_task(
                _generate_and_cache_chat_suggestions(
                    user_id=user_id,
                    match_id=match_id,
                    recent_messages=background_task_payload,
                    mode=background_mode,
                )
            )
    except WebSocketDisconnect:
        pass
    except BrokenPipeError:
        pass
    finally:
        await manager.disconnect(match_id, connection_id)
