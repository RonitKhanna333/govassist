"""Every interview call, with what was asked and what was heard.

The transcript is kept alongside the answers taken from it because the
answers are an interpretation: if a verdict is ever questioned, the person
(or a reviewer) can see the exact words it came from. Nothing else is
stored -- no recording, no document, no ID number.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from api.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CallRecord(Base):
    __tablename__ = "call_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True,
                                                nullable=True)
    call_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True,
                                                nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default="interview")
    locale: Mapped[str] = mapped_column(String(8), default="hi")
    # requested -> completed | not_answered | failed
    status: Mapped[str] = mapped_column(String(16), default="requested")
    # [{"who": "agent"|"caller", "text": "..."}]
    transcript_json: Mapped[str] = mapped_column(Text, default="[]")
    # attribute -> the caller's own words, quote-checked against the transcript
    heard_json: Mapped[str] = mapped_column(Text, default="{}")
    # attribute -> value our parser read from those words
    answers_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                          nullable=True)
