from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, PrimaryKeyConstraint, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CompatibilityScore(Base):
    __tablename__ = "compatibility"
    __table_args__ = (
        PrimaryKeyConstraint("user_id_1", "user_id_2", name="pk_compatibility_user_pair"),
    )

    user_id_1: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    user_id_2: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    cache_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
