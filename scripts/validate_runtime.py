from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.database import Base
from app.models.interaction import ChatMessage, Match, SwipeInteraction
from app.models.profile import Profile
from app.models.user import User
from app.services.redis_service import RedisService
from app.services.s3_service import S3PresignedPostRequest, S3Service, s3_service


@dataclass(frozen=True, slots=True)
class ColumnExpectation:
    name: str
    type_fragment: str
    nullable: bool | None = None
    server_default_contains: str | None = None


EXPECTED_TABLES: dict[str, list[ColumnExpectation]] = {
    "users": [
        ColumnExpectation("id", "INTEGER", nullable=False),
        ColumnExpectation("email", "VARCHAR", nullable=False),
        ColumnExpectation("username", "VARCHAR", nullable=False),
        ColumnExpectation("password_hash", "VARCHAR", nullable=False),
        ColumnExpectation("is_active", "BOOLEAN", nullable=False),
        ColumnExpectation("is_verified", "BOOLEAN", nullable=False),
        ColumnExpectation("location", "geometry", nullable=True),
        ColumnExpectation("created_at", "TIMESTAMP", nullable=False),
        ColumnExpectation("updated_at", "TIMESTAMP", nullable=False),
    ],
    "profiles": [
        ColumnExpectation("id", "INTEGER", nullable=False),
        ColumnExpectation("user_id", "INTEGER", nullable=False),
        ColumnExpectation("display_name", "VARCHAR", nullable=False),
        ColumnExpectation("bio", "TEXT", nullable=False),
        ColumnExpectation("interests", "JSON", nullable=False),
        ColumnExpectation("reputation_score", "INTEGER", nullable=False),
        ColumnExpectation("reliability_tier", "VARCHAR", nullable=False),
        ColumnExpectation("created_at", "TIMESTAMP", nullable=False),
        ColumnExpectation("updated_at", "TIMESTAMP", nullable=False),
    ],
    "swipe_interactions": [
        ColumnExpectation("id", "INTEGER", nullable=False),
        ColumnExpectation("swiper_id", "INTEGER", nullable=False),
        ColumnExpectation("target_user_id", "INTEGER", nullable=False),
        ColumnExpectation("action", "VARCHAR", nullable=False),
        ColumnExpectation("source", "VARCHAR", nullable=False),
        ColumnExpectation("created_at", "TIMESTAMP", nullable=False),
    ],
    "matches": [
        ColumnExpectation("id", "INTEGER", nullable=False),
        ColumnExpectation("user_a_id", "INTEGER", nullable=False),
        ColumnExpectation("user_b_id", "INTEGER", nullable=False),
        ColumnExpectation("status", "VARCHAR", nullable=False),
        ColumnExpectation("created_at", "TIMESTAMP", nullable=False),
    ],
    "chat_messages": [
        ColumnExpectation("id", "INTEGER", nullable=False),
        ColumnExpectation("match_id", "INTEGER", nullable=False),
        ColumnExpectation("sender_id", "INTEGER", nullable=False),
        ColumnExpectation("message", "TEXT", nullable=False),
        ColumnExpectation("created_at", "TIMESTAMP", nullable=False),
    ],
}


def _url() -> str:
    url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("TEST_DATABASE_URL or DATABASE_URL is required")
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _check_model_names() -> list[str]:
    expected = {"users", "profiles", "swipe_interactions", "matches", "chat_messages"}
    actual = {User.__tablename__, Profile.__tablename__, SwipeInteraction.__tablename__, Match.__tablename__, ChatMessage.__tablename__}
    return sorted(expected - actual)


def _normalize_type(value: Any) -> str:
    return str(value).lower()


def _validate_columns(columns: list[dict[str, Any]], expectations: list[ColumnExpectation]) -> list[str]:
    issues: list[str] = []
    by_name = {column["name"]: column for column in columns}
    for expectation in expectations:
        column = by_name.get(expectation.name)
        if column is None:
            issues.append(f"missing column {expectation.name}")
            continue
        column_type = _normalize_type(column["type"])
        if expectation.type_fragment.lower() not in column_type:
            issues.append(f"{expectation.name} type mismatch: expected {expectation.type_fragment}, got {column_type}")
        if expectation.nullable is not None and bool(column["nullable"]) != expectation.nullable:
            issues.append(f"{expectation.name} nullable mismatch: expected {expectation.nullable}, got {column['nullable']}")
        if expectation.server_default_contains:
            default = str(column.get("default") or column.get("server_default") or "").lower()
            if expectation.server_default_contains.lower() not in default:
                issues.append(f"{expectation.name} default mismatch: expected {expectation.server_default_contains}, got {default}")
    return issues


async def _get_table_columns(conn: AsyncConnection, table_name: str) -> list[dict[str, Any]]:
    query = text(
        """
        SELECT
            column_name AS name,
            data_type AS type,
            is_nullable AS nullable,
            column_default AS default
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = :table_name
        ORDER BY ordinal_position
        """
    )
    result = await conn.execute(query, {"table_name": table_name})
    rows = result.mappings().all()
    return [dict(row) for row in rows]


async def validate_schema(engine: AsyncEngine) -> list[str]:
    issues: list[str] = []
    async with engine.connect() as conn:
        for table_name, expectations in EXPECTED_TABLES.items():
            columns = await _get_table_columns(conn, table_name)
            if not columns:
                issues.append(f"missing table {table_name}")
                continue
            issues.extend(f"{table_name}: {issue}" for issue in _validate_columns(columns, expectations))
    return issues


async def validate_redis() -> list[str]:
    issues: list[str] = []
    service = RedisService()
    try:
        client = await service.connect()
        pong = await cast(Any, client.ping())
        if pong is not True:
            issues.append(f"redis ping returned {pong!r}")
        published = await client.publish("validation:test", '{"ok":true}')
        if published < 0:
            issues.append(f"redis publish returned {published}")
    except Exception as exc:
        issues.append(f"redis validation failed: {exc}")
    finally:
        await service.close()
    return issues


async def validate_s3() -> list[str]:
    issues: list[str] = []
    if s3_service is None:
        issues.append("s3 service unavailable because credentials or boto3 are missing")
        return issues

    try:
        result = s3_service.create_presigned_post(
            S3PresignedPostRequest(user_id=1, content_type="image/jpeg", filename="photo.jpg")
        )
        if not result.upload_url.startswith("http"):
            issues.append("presigned URL is invalid")
        if "Content-Type" not in result.upload_fields:
            issues.append("presigned fields missing Content-Type")
    except Exception as exc:
        issues.append(f"s3 validation failed: {exc}")
    return issues


async def main() -> None:
    engine = create_async_engine(_url(), echo=False, pool_pre_ping=True)
    issues = []
    issues.extend(_check_model_names())
    issues.extend(await validate_schema(engine))
    issues.extend(await validate_redis())
    issues.extend(await validate_s3())

    if issues:
        print("VALIDATION FAILED")
        for issue in issues:
            print(f"- {issue}")
        raise SystemExit(1)

    print("VALIDATION PASSED")
    print("ORM schema, Redis async checks, and S3 presign validation all passed.")


if __name__ == "__main__":
    asyncio.run(main())
