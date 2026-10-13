"""/family -- the household graph.

    POST   /family                    create a household; you become its first member
    GET    /family                    the graph: members, relationships, benefits
    POST   /family/members            add a relative (as a record, no login)
    POST   /family/relations          link two members (parent_of / spouse_of)
    POST   /family/invites            a one-time code letting a relative claim their node
    POST   /family/join               redeem a code with your own account
    POST   /family/benefits           record that a member already received a scheme
    PUT    /family/sharing            share (or stop sharing) your answers with the family
    GET    /family/suggestions        family facts relevant to one scheme, with sources
    GET    /family/eligibility        each visible member against every scheme
    POST   /family/leave              leave the household (POST: CORS allows no DELETE)

Every endpoint requires sign-in, and every read and write is confined to the
caller's own household -- a member id from someone else's family is
indistinguishable from one that doesn't exist (404 either way), so ids
can't be probed.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from api.auth.models import User
from api.auth.router import current_user, get_sessions
from api.family import derive
from api.family.models import (
    PREDICATES,
    BenefitRecord,
    Household,
    Invite,
    Member,
    Relation,
)
from api.rules.engine import SCHEME_SLUG, decide, load_rules
from api.rules.values import check_values, specs_for
from parse_scheme import repo_root

router = APIRouter(prefix="/family", tags=["family"])

INVITE_TTL = timedelta(days=7)
MAX_MEMBERS = 40           # a household, not a village


class CreateBody(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    my_name: str = Field(min_length=1, max_length=120)
    birth_year: int | None = None


class MemberBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    birth_year: int | None = None
    # Optionally, how they relate to you -- saves a second request.
    relation: str | None = Field(default=None, pattern="^(spouse|child|parent)$")
    profile: dict = Field(default_factory=dict, max_length=64)


class RelationBody(BaseModel):
    from_member: int
    predicate: str = Field(pattern="^(parent_of|spouse_of)$")
    to_member: int


class InviteBody(BaseModel):
    member_id: int


class JoinBody(BaseModel):
    code: str = Field(min_length=6, max_length=64)


class BenefitBody(BaseModel):
    member_id: int
    scheme: str = Field(max_length=64)


class SharingBody(BaseModel):
    share: bool


# -- helpers ----------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()


def _me(session, user: User) -> Member:
    member = session.scalar(select(Member).where(Member.user_id == user.id))
    if member is None:
        raise HTTPException(404, "You are not in a household yet")
    return member


def _member(session, household_id: int, member_id: int) -> Member:
    member = session.get(Member, member_id)
    if member is None or member.household_id != household_id:
        raise HTTPException(404, "No such member in your household")
    return member


def _check_birth_year(year: int | None) -> None:
    if year is None:
        return
    this_year = _now().year
    if not 1900 <= year <= this_year:  # this year: a newborn
        raise HTTPException(422, "birth_year looks wrong")


def _check_scheme(scheme: str) -> dict:
    if not SCHEME_SLUG.fullmatch(scheme):
        raise HTTPException(404, f"unknown scheme '{scheme}'")
    try:
        return load_rules(scheme, repo_root())
    except FileNotFoundError as exc:
        raise HTTPException(404, f"unknown scheme '{scheme}'") from exc


def _schemes() -> list[str]:
    root = repo_root() / "data" / "schemes"
    return sorted(
        d.name for d in root.iterdir()
        if d.name != "demo-scheme" and (d / "build").is_dir()
    )


def _clean_profile(profile: dict) -> dict:
    """Keep only attributes some scheme reads, each validated the same way
    /chat validates them. Nothing free-form is stored on a relative."""
    if not profile:
        return {}
    kept: dict = {}
    for scheme in _schemes():
        checked = check_values(specs_for(load_rules(scheme, repo_root())), profile)
        if checked.errors:
            raise HTTPException(422, "; ".join(
                f"{e.attribute}: {e.reason}" for e in checked.errors))
        kept.update(checked.values)
    return kept


def _graph(session, household_id: int, viewer: User, me: Member) -> dict:
    members = list(session.scalars(
        select(Member).where(Member.household_id == household_id).order_by(Member.id)))
    relations = list(session.scalars(
        select(Relation).where(Relation.household_id == household_id)))
    benefits = list(session.scalars(
        select(BenefitRecord).where(BenefitRecord.household_id == household_id)))
    labels = derive.relation_labels(me.id, relations)
    household = session.get(Household, household_id)
    return {
        "household": {"id": household.id, "name": household.name},
        "me": me.id,
        "members": [
            {
                "id": m.id, "name": m.name, "birth_year": m.birth_year,
                "relation": "self" if m.id == me.id else labels.get(m.id),
                # Whether this person has their own account -- never which.
                "has_account": m.user_id is not None,
                "shares_profile": m.shares_profile if m.user_id else None,
                "benefits": sorted(b.scheme for b in benefits if b.member_id == m.id),
            }
            for m in members
        ],
        "relations": [
            {"from": r.from_member, "predicate": r.predicate, "to": r.to_member}
            for r in relations
        ],
    }


def _link(session, household_id: int, a: int, predicate: str, b: int) -> None:
    if predicate not in PREDICATES:
        raise HTTPException(422, "unknown relationship")
    if a == b:
        raise HTTPException(422, "a person can't be related to themselves")
    relations = list(session.scalars(
        select(Relation).where(Relation.household_id == household_id)))
    if predicate == "spouse_of":
        exists = any(r.predicate == "spouse_of" and {r.from_member, r.to_member} == {a, b}
                     for r in relations)
    else:
        if derive.would_create_cycle(a, b, relations):
            raise HTTPException(422, "that would make someone their own ancestor")
        if any(r.predicate == "parent_of" and r.from_member == b and r.to_member == a
               for r in relations):
            raise HTTPException(422, "they are already recorded the other way round")
        parents = [r for r in relations if r.predicate == "parent_of" and r.to_member == b]
        if len(parents) >= 2 and all(p.from_member != a for p in parents):
            raise HTTPException(422, "that person already has two parents recorded")
        exists = any(r.predicate == predicate and r.from_member == a and r.to_member == b
                     for r in relations)
    if not exists:
        session.add(Relation(household_id=household_id, from_member=a,
                             predicate=predicate, to_member=b))


# -- endpoints --------------------------------------------------------------


@router.post("")
def create(body: CreateBody, user: User = Depends(current_user),
           sessions=Depends(get_sessions)) -> dict:
    _check_birth_year(body.birth_year)
    with sessions() as session:
        if session.scalar(select(Member).where(Member.user_id == user.id)):
            raise HTTPException(409, "You are already in a household. Leave it first.")
        household = Household(name=body.name, created_by=user.id)
        session.add(household)
        session.flush()
        me = Member(household_id=household.id, user_id=user.id, name=body.my_name,
                    birth_year=body.birth_year, added_by=user.id)
        session.add(me)
        session.commit()
        return _graph(session, household.id, user, me)


@router.get("")
def get_family(user: User = Depends(current_user), sessions=Depends(get_sessions)) -> dict:
    with sessions() as session:
        me = _me(session, user)
        return _graph(session, me.household_id, user, me)


@router.post("/members")
def add_member(body: MemberBody, user: User = Depends(current_user),
               sessions=Depends(get_sessions)) -> dict:
    _check_birth_year(body.birth_year)
    profile = _clean_profile(body.profile)
    with sessions() as session:
        me = _me(session, user)
        count = len(list(session.scalars(
            select(Member.id).where(Member.household_id == me.household_id))))
        if count >= MAX_MEMBERS:
            raise HTTPException(422, "this household is full")
        member = Member(household_id=me.household_id, name=body.name,
                        birth_year=body.birth_year, profile_json=json.dumps(profile),
                        added_by=user.id)
        session.add(member)
        session.flush()
        if body.relation == "spouse":
            _link(session, me.household_id, me.id, "spouse_of", member.id)
        elif body.relation == "child":
            _link(session, me.household_id, me.id, "parent_of", member.id)
        elif body.relation == "parent":
            _link(session, me.household_id, member.id, "parent_of", me.id)
        session.commit()
        return _graph(session, me.household_id, user, me)


@router.post("/relations")
def add_relation(body: RelationBody, user: User = Depends(current_user),
                 sessions=Depends(get_sessions)) -> dict:
    with sessions() as session:
        me = _me(session, user)
        _member(session, me.household_id, body.from_member)
        _member(session, me.household_id, body.to_member)
        _link(session, me.household_id, body.from_member, body.predicate, body.to_member)
        session.commit()
        return _graph(session, me.household_id, user, me)


@router.post("/invites")
def create_invite(body: InviteBody, user: User = Depends(current_user),
                  sessions=Depends(get_sessions)) -> dict:
    """A code to give a relative in person. Shown once; only its hash is kept."""
    with sessions() as session:
        me = _me(session, user)
        member = _member(session, me.household_id, body.member_id)
        if member.user_id is not None:
            raise HTTPException(409, "That person has already joined")
        code = secrets.token_hex(4).upper()  # 8 characters: easy to read out
        session.add(Invite(household_id=me.household_id, member_id=member.id,
                           code_hash=_hash(code), created_by=user.id,
                           expires_at=_now() + INVITE_TTL))
        session.commit()
        return {"code": code, "member_id": member.id,
                "expires_in_days": INVITE_TTL.days}


@router.post("/join")
def join(body: JoinBody, user: User = Depends(current_user),
         sessions=Depends(get_sessions)) -> dict:
    """Claim a member node as yourself. The only way an account enters a
    household -- nobody can add someone else's account."""
    with sessions() as session:
        if session.scalar(select(Member).where(Member.user_id == user.id)):
            raise HTTPException(409, "You are already in a household. Leave it first.")
        invite = session.scalar(select(Invite).where(Invite.code_hash == _hash(body.code)))
        expires = invite.expires_at if invite else None
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)  # SQLite drops tzinfo
        if invite is None or invite.used_at is not None or expires < _now():
            # One message for all three: don't tell a guesser which codes exist.
            raise HTTPException(404, "That code isn't valid")
        member = session.get(Member, invite.member_id)
        if member is None or member.user_id is not None:
            raise HTTPException(404, "That code isn't valid")
        member.user_id = user.id
        # Their own account now holds their answers; the record entered on
        # their behalf is cleared rather than silently kept alongside.
        member.profile_json = "{}"
        invite.used_at = _now()
        session.commit()
        return _graph(session, member.household_id, user, member)


@router.post("/benefits")
def record_benefit(body: BenefitBody, user: User = Depends(current_user),
                   sessions=Depends(get_sessions)) -> dict:
    _check_scheme(body.scheme)
    with sessions() as session:
        me = _me(session, user)
        member = _member(session, me.household_id, body.member_id)
        # A member with an account speaks for themselves.
        if member.user_id is not None and member.user_id != user.id:
            raise HTTPException(403, "Only they can record that for themselves")
        exists = session.scalar(select(BenefitRecord).where(
            BenefitRecord.member_id == member.id, BenefitRecord.scheme == body.scheme))
        if not exists:
            session.add(BenefitRecord(household_id=me.household_id, member_id=member.id,
                                      scheme=body.scheme, recorded_by=user.id))
            session.commit()
        return _graph(session, me.household_id, user, me)


@router.put("/sharing")
def set_sharing(body: SharingBody, user: User = Depends(current_user),
                sessions=Depends(get_sessions)) -> dict:
    with sessions() as session:
        me = _me(session, user)
        me.shares_profile = body.share
        session.commit()
        return _graph(session, me.household_id, user, me)


@router.get("/suggestions")
def get_suggestions(scheme: str, user: User = Depends(current_user),
                    sessions=Depends(get_sessions)) -> dict:
    """Family facts for one scheme, with who they came from. Never applied:
    the person still answers the question; this only reminds them."""
    _check_scheme(scheme)
    with sessions() as session:
        me = _me(session, user)
        members = list(session.scalars(
            select(Member).where(Member.household_id == me.household_id)))
        relations = list(session.scalars(
            select(Relation).where(Relation.household_id == me.household_id)))
        benefits = list(session.scalars(
            select(BenefitRecord).where(BenefitRecord.household_id == me.household_id)))
        found = derive.suggestions(scheme, me.id, members, relations, benefits)
        return {"scheme": scheme, "suggestions": [s.to_dict() for s in found]}


@router.get("/eligibility")
def family_eligibility(user: User = Depends(current_user),
                       sessions=Depends(get_sessions)) -> dict:
    """Every member whose answers the caller may see, against every scheme.

    The same `decide()` as /chat. A member whose answers are private shows
    as private, not as "not eligible" -- absence of data is not a verdict.
    """
    with sessions() as session:
        me = _me(session, user)
        members = list(session.scalars(
            select(Member).where(Member.household_id == me.household_id).order_by(Member.id)))
        user_ids = [m.user_id for m in members if m.user_id]
        profiles = {
            u.id: u.profile_json
            for u in session.scalars(select(User).where(User.id.in_(user_ids)))
        } if user_ids else {}
        schemes = _schemes()
        out = []
        for member in members:
            profile = derive.visible_profile(member, user.id, profiles)
            if profile is None:
                out.append({"member_id": member.id, "name": member.name,
                            "private": True, "schemes": {}})
                continue
            out.append({
                "member_id": member.id, "name": member.name, "private": False,
                "schemes": {s: decide(s, profile).verdict.value for s in schemes},
            })
        return {"members": out}


@router.post("/leave")
def leave(user: User = Depends(current_user), sessions=Depends(get_sessions)) -> dict:
    """Leave the household. Your node stays as a plain record (the family
    tree shouldn't lose a parent), but your account is unlinked and nothing
    of yours stays visible. The last account to leave deletes the household."""
    with sessions() as session:
        me = _me(session, user)
        household_id = me.household_id
        me.user_id = None
        me.shares_profile = False
        me.profile_json = "{}"
        session.flush()
        remaining = session.scalar(select(Member.id).where(
            Member.household_id == household_id, Member.user_id.is_not(None)))
        if remaining is None:
            for table in (Invite, BenefitRecord, Relation, Member):
                session.execute(delete(table).where(table.household_id == household_id))
            session.execute(delete(Household).where(Household.id == household_id))
        session.commit()
        return {"left": True, "household_deleted": remaining is None}
