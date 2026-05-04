from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from geoalchemy2 import WKTElement
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.security import hash_password
from app.database import Base, SessionLocal, engine
from app.models.profile import Profile
from app.models.user import User

DEFAULT_PASSWORD = "TestPassword123!"
DEFAULT_CITY_CENTER = {
    "name": "Bengaluru City Center",
    "latitude": 12.9716,
    "longitude": 77.5946,
}

SEED_USERS: list[dict[str, Any]] = [
    {
        "email": "ava.chen@example.com",
        "username": "ava_chen",
        "display_name": "Ava Chen",
        "bio": (
            "Ava is a backend engineer who loves turning messy systems into calm, reliable products. "
            "She spends her weekdays designing APIs, reviewing database plans, and obsessing over clean architecture, "
            "then unwinds with long hikes, quiet coffee shops, and minimalist design blogs. "
            "Her ideal weekend involves an early trail head, a good thermos of coffee, and a slow dinner with one or two close friends. "
            "She is thoughtful, steady, and very much the kind of person who values depth over noise."
        ),
        "interests": ["backend engineering", "hiking", "coffee shops", "minimalist design"],
        "latitude": 12.9658,
        "longitude": 77.6021,
    },
    {
        "email": "noah.patel@example.com",
        "username": "noah_patel",
        "display_name": "Noah Patel",
        "bio": (
            "Noah is a platform engineer who gets genuine joy from optimizing infrastructure and solving problems before anyone else notices them. "
            "He likes long mountain walks, cooking elaborate breakfasts, and spending Saturday afternoons reading code and books in equal measure. "
            "Friends describe him as calm, funny in a dry way, and happiest when plans are simple, flexible, and grounded. "
            "He is looking for someone who enjoys quiet routines, shared ambition, and the occasional spontaneous road trip to a hiking trail."
        ),
        "interests": ["platform engineering", "mountain walks", "cooking", "reading"],
        "latitude": 12.9784,
        "longitude": 77.5857,
    },
    {
        "email": "maya.fernandez@example.com",
        "username": "maya_fernandez",
        "display_name": "Maya Fernandez",
        "bio": (
            "Maya is a nightlife DJ and event curator who thrives on packed dance floors, late-night energy, and the rush of live crowds. "
            "She spends her evenings mixing sets, scouting new venues, and chasing the next unforgettable party atmosphere. "
            "Her social life is loud, fast, and full of last-minute plans, rooftop afterparties, and friends who are always one step into the night. "
            "She is magnetic, extroverted, and loves people who can keep up with a very vivid calendar."
        ),
        "interests": ["DJing", "event curation", "nightlife", "live music"],
        "latitude": 12.9602,
        "longitude": 77.6204,
    },
    {
        "email": "ethan.roy@example.com",
        "username": "ethan_roy",
        "display_name": "Ethan Roy",
        "bio": (
            "Ethan is a deeply introverted bookworm who finds comfort in silence, structure, and long evenings spent with a novel and tea. "
            "He works in technical writing, enjoys museums on weekday mornings, and prefers one-on-one conversation over any crowded social scene. "
            "His happiest nights are usually spent at home, annotated paperback in hand, with lo-fi music playing softly in the background. "
            "He values predictability, emotional restraint, and relationships that grow slowly through trust and shared intellectual curiosity."
        ),
        "interests": ["books", "museums", "tea", "technical writing"],
        "latitude": 12.9851,
        "longitude": 77.6119,
    },
    {
        "email": "samira.khan@example.com",
        "username": "samira_khan",
        "display_name": "Samira Khan",
        "bio": (
            "Samira is a wildcard product designer with a resume that jumps from hospitality to UX to community organizing. "
            "She is equally happy sketching interface ideas in a notebook, trying an experimental food stall, or suddenly booking a train ticket for a weekend in a new city. "
            "Her taste is eclectic, her energy shifts with the room, and she has a talent for making almost any conversation unexpectedly interesting. "
            "She can be thoughtful and adventurous in the same breath, which makes her difficult to classify and fun to get to know."
        ),
        "interests": ["product design", "UX", "food exploration", "travel"],
        "latitude": 12.9689,
        "longitude": 77.5788,
    },
]


@dataclass(frozen=True)
class SeedUser:
    email: str
    username: str
    display_name: str
    bio: str
    interests: list[str]
    latitude: float
    longitude: float


def build_seed_users() -> list[SeedUser]:
    return [
        SeedUser(
            email=row["email"],
            username=row["username"],
            display_name=row["display_name"],
            bio=row["bio"],
            interests=row["interests"],
            latitude=row["latitude"],
            longitude=row["longitude"],
        )
        for row in SEED_USERS
    ]


async def ensure_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def clear_tables() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE profiles RESTART IDENTITY CASCADE"))
        await conn.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))


async def seed_users() -> None:
    seed_users_data = build_seed_users()
    hashed_password = hash_password(DEFAULT_PASSWORD)

    async with SessionLocal() as session:
        for person in seed_users_data:
            location = WKTElement(f"POINT({person.longitude} {person.latitude})", srid=4326)
            user = User(
                email=person.email,
                username=person.username,
                password_hash=hashed_password,
                is_active=True,
                is_verified=True,
                location=location,
            )
            user.profile = Profile(
                display_name=person.display_name,
                bio=person.bio,
                interests=person.interests,
            )
            session.add(user)

        await session.commit()


async def verify_seed() -> list[dict[str, Any]]:
    async with SessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT
                    u.id,
                    u.email,
                    u.username,
                    u.is_active,
                    u.is_verified,
                    p.display_name,
                    p.bio,
                    p.interests
                FROM users u
                JOIN profiles p ON p.user_id = u.id
                ORDER BY u.id ASC
                """
            )
        )
        return [dict(row) for row in result.mappings().all()]


async def main() -> None:
    await ensure_schema()
    await clear_tables()
    await seed_users()

    rows = await verify_seed()
    print(f"Seeded {len(rows)} users and profiles successfully.")
    print(f"Default login password for all users: {DEFAULT_PASSWORD}")
    print(
        "City center reference: "
        f"{DEFAULT_CITY_CENTER['name']} "
        f"({DEFAULT_CITY_CENTER['latitude']}, {DEFAULT_CITY_CENTER['longitude']})"
    )
    for row in rows:
        print(
            f"- {row['username']} <{row['email']}> "
            f"display_name={row['display_name']} active={row['is_active']} verified={row['is_verified']}"
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (SQLAlchemyError, OSError) as exc:
        print(f"Seeding failed: {exc}")
        raise
