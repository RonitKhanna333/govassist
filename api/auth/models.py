"""User accounts and their saved eligibility profile.

What is deliberately NOT stored here: any uploaded document, any extracted
document text, and any government ID number. The corpus design commits to
processing those in memory and discarding them, and a users table is
exactly where that promise quietly erodes -- so the schema has no column
that could hold one.

`profile_json` holds only the attribute values a person stated about
themselves (age, worker_count, ...) -- the same flat dict the rule engine
already evaluates. It exists so someone doesn't have to answer twelve
questions again on their next visit.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from api.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Stored lowercased so "A@b.com" and "a@b.com" cannot become two accounts.
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    locale: Mapped[str] = mapped_column(String(8), default="en")
    profile_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
