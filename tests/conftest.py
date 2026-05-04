from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import create_access_token, hash_password
from app.database import Base, get_db
from app.main import app as fastapi_app
from app.models.interaction import ChatMessage, Match, SwipeInteraction
from app.models.profile import Profile
from app.models.reputation import derive_reliability_tier
from app.models.user import User
from app.services import redis_service as redis_module
from app.services.redis_service import RedisService


@dataclass(frozen=True, slots=True)
class SeededTestUser:
    id: int
    email: str
    username: str
    display_name: str
    bio: str


TEST_USER_PASSWORD = "Password123!"
TEST_DATABASE_URL_ENV = "TEST_DATABASE_URL"
TEST_REDIS_URL_ENV = "TEST_REDIS_URL"


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required test environment variable: {name}. Load .env.test before running pytest.")
    return value


@pytest.fixture(scope="session")
def app() -> FastAPI:
    return fastapi_app


@pytest.fixture(scope="session")
def test_db_url() -> str:
    return _require_env(TEST_DATABASE_URL_ENV)


@pytest.fixture(scope="session")
def test_redis_url() -> str:
    return _require_env(TEST_REDIS_URL_ENV)


@pytest.fixture(scope="session")
def live_ai() -> bool:
    value = os.getenv("RUN_LIVE_AI_TESTS", "")
    return value.lower() in {"1", "true", "yes", "on"}


@pytest.fixture(scope="session")
def auth_headers_factory() -> Callable[[int], dict[str, str]]:
    def _factory(user_id: int) -> dict[str, str]:
        token = create_access_token(subject=str(user_id))
        return {"Authorization": f"Bearer {token}"}

    return _factory


@pytest_asyncio.fixture(scope="session")
async def test_engine(test_db_url: str):
    engine = create_async_engine(test_db_url, echo=False, pool_pre_ping=True)

    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("SELECT 1"))
    except OperationalError as exc:
        await engine.dispose()
        raise RuntimeError(
            "Unable to connect to the test database. Ensure Docker Compose is running and TEST_DATABASE_URL points to the Postgres container."
        ) from exc

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def test_sessionmaker(test_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session")
async def redis_test_service(test_redis_url: str) -> AsyncGenerator[RedisService, None]:
    service = RedisService(url=test_redis_url)
    try:
        client = await service.connect()
        client.ping()
    except Exception as exc:
        raise RuntimeError(
            "Unable to connect to Redis for tests. Ensure Docker Compose is running and TEST_REDIS_URL points to the Redis container."
        ) from exc

    yield service

    client = await service.connect()
    await client.flushdb()
    await service.close()


@pytest_asyncio.fixture(autouse=True)
async def _override_dependencies(
    app: FastAPI,
    test_sessionmaker: async_sessionmaker[AsyncSession],
    redis_test_service: RedisService,
):
    original_redis_service = redis_module.redis_service

    async def _override_db_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_sessionmaker() as session:
            try:
                yield session
            finally:
                await session.close()

    app.dependency_overrides[get_db] = _override_db_session
    redis_module.redis_service = redis_test_service
    yield
    app.dependency_overrides.pop(get_db, None)
    redis_module.redis_service = original_redis_service


@asynccontextmanager
async def _override_db_session(test_sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with test_sessionmaker() as session:
        try:
            yield session
        finally:
            await session.close()


@pytest_asyncio.fixture(autouse=True)
async def clean_database(test_engine):
    async with test_engine.begin() as conn:
        await conn.execute(delete(ChatMessage))
        await conn.execute(delete(SwipeInteraction))
        await conn.execute(delete(Match))
        await conn.execute(delete(Profile))
        await conn.execute(delete(User))
    yield
    async with test_engine.begin() as conn:
        await conn.execute(delete(ChatMessage))
        await conn.execute(delete(SwipeInteraction))
        await conn.execute(delete(Match))
        await conn.execute(delete(Profile))
        await conn.execute(delete(User))


@pytest_asyncio.fixture()
async def db_session(test_sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncGenerator[AsyncSession, None]:
    async with test_sessionmaker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture()
async def seeded_users(db_session: AsyncSession) -> dict[str, SeededTestUser]:
    users = [
        ("ava_chen", "ava.chen@example.com", "ava_chen", "Ava Chen", "Coffee enthusiast, weekend hiker, and product designer."),
        ("noah_patel", "noah.patel@example.com", "noah_patel", "Noah Patel", "Food explorer, calm communicator, and sunrise runner."),
        ("mia_khan", "mia.khan@example.com", "mia_khan", "Mia Khan", "Reads sci-fi, likes museums, and builds side projects."),
    ]

    seeded: dict[str, SeededTestUser] = {}
    for username, email, handle, display_name, bio in users:
        user = User(
            email=email,
            username=handle,
            password_hash=hash_password(TEST_USER_PASSWORD),
            is_active=True,
            is_verified=False,
        )
        db_session.add(user)
        await db_session.flush()

        profile = Profile(
            user_id=user.id,
            display_name=display_name,
            bio=bio,
            interests=["coffee", "travel", "music"],
            reputation_score=100,
            reliability_tier=derive_reliability_tier(100),
        )
        db_session.add(profile)
        await db_session.flush()

        seeded[username] = SeededTestUser(
            id=user.id,
            email=user.email,
            username=user.username,
            display_name=profile.display_name,
            bio=profile.bio,
        )

    await db_session.commit()
    return seeded


@pytest_asyncio.fixture()
async def async_client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
