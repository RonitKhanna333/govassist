"""Household graph tables: members are nodes, relationships are edges.

Stored in the same database as accounts and the scheme graph, as plain
tables rather than a graph database: a family is tens of nodes, and every
traversal here is one or two hops, which SQL does without help.

Only two relationship predicates are stored -- `parent_of` and `spouse_of`.
Everything else (child, sibling, grandparent) is derived by traversal, so
the graph cannot hold two edges that contradict each other ("A is B's
sibling" but they share no parent).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.db import Base

PREDICATES = ("parent_of", "spouse_of")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Household(Base):
    __tablename__ = "households"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Member(Base):
    """A person in a household. `user_id` is set only once that person has
    joined with their own account; until then the node is a record someone
    else entered, and it has no login."""

    __tablename__ = "household_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"), index=True)
    # One household per account: a person belongs to one family record.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, unique=True,
    )
    name: Mapped[str] = mapped_column(String(120))
    # Year only. A full date of birth is identifying and no rule needs it.
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Attributes for members WITHOUT an account, entered by whoever added
    # them. A member with an account uses their own saved profile instead.
    profile_json: Mapped[str] = mapped_column(Text, default="{}")
    # Whether a member with an account lets the household see their saved
    # answers. Off by default: joining a family is not consenting to share.
    shares_profile: Mapped[bool] = mapped_column(Boolean, default=False)
    added_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Relation(Base):
    __tablename__ = "household_relations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"), index=True)
    from_member: Mapped[int] = mapped_column(ForeignKey("household_members.id"), index=True)
    predicate: Mapped[str] = mapped_column(String(16))
    to_member: Mapped[int] = mapped_column(ForeignKey("household_members.id"), index=True)

    __table_args__ = (
        UniqueConstraint("from_member", "predicate", "to_member", name="uq_relation"),
    )


class BenefitRecord(Base):
    """That a member has already received a scheme -- the fact family-level
    rules turn on. Who recorded it is kept, because a record about someone
    else is a claim, not a certainty."""

    __tablename__ = "household_benefits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"), index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("household_members.id"), index=True)
    scheme: Mapped[str] = mapped_column(String(64))
    recorded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        UniqueConstraint("member_id", "scheme", name="uq_benefit"),
    )


class Invite(Base):
    """A one-time code that lets a person claim a member node as themselves.

    Only a hash is stored, so a leaked database does not hand out working
    invites. Codes expire and are single-use.
    """

    __tablename__ = "household_invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"), index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("household_members.id"))
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
