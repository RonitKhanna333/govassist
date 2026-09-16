"""Auth endpoints: register, login, me, and a saved profile.

Auth is optional for this product, by design. Someone checking whether they
qualify for a government benefit should not have to create an account to
find out -- /chat stays open. Signing in only buys persistence of the
answers you already gave.
"""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select

from api.auth.models import User
from api.auth.security import (
    AuthConfigError,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from api.db import get_session_factory, init_db

router = APIRouter(prefix="/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 10


def get_sessions():
    init_db()
    return get_session_factory()


def _public(user: User) -> dict:
    return {
        "id": user.id, "email": user.email,
        "display_name": user.display_name, "locale": user.locale,
        "profile": json.loads(user.profile_json or "{}"),
    }


def current_user(
    authorization: str | None = Header(default=None),
    sessions=Depends(get_sessions),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Not signed in")

    try:
        claims = decode_token(authorization.split(" ", 1)[1].strip())
    except AuthConfigError as exc:
        # Misconfiguration is a server fault, not the caller's -- saying 401
        # here would send someone chasing their own credentials.
        raise HTTPException(500, str(exc)) from exc

    if not claims:
        raise HTTPException(401, "Session expired or invalid")

    with sessions() as session:
        user = session.get(User, int(claims["sub"]))
    if user is None:
        raise HTTPException(401, "Session expired or invalid")
    return user


@router.post("/register")
def register(body: dict, sessions=Depends(get_sessions)) -> dict:
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))

    if not _EMAIL_RE.match(email):
        raise HTTPException(422, "That doesn't look like an email address.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            422, f"Use at least {MIN_PASSWORD_LENGTH} characters for your password.",
        )

    try:
        with sessions() as session:
            if session.scalar(select(User).where(User.email == email)):
                # Same wording as a wrong password on login, and a 409 rather
                # than a distinct message, so this endpoint isn't a way to
                # enumerate who has an account.
                raise HTTPException(409, "That email can't be registered.")

            user = User(
                email=email,
                password_hash=hash_password(password),
                display_name=(str(body.get("display_name") or "").strip() or None),
                locale=str(body.get("locale") or "en")[:8],
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            token = create_token(user.id, user.email)
            return {"token": token, "user": _public(user)}
    except AuthConfigError as exc:
        raise HTTPException(500, str(exc)) from exc


@router.post("/login")
def login(body: dict, sessions=Depends(get_sessions)) -> dict:
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))

    try:
        with sessions() as session:
            user = session.scalar(select(User).where(User.email == email))
            # One message for "no such user" and "wrong password", always --
            # different wording tells an attacker which half they guessed.
            if user is None or not verify_password(password, user.password_hash):
                raise HTTPException(401, "Email or password is incorrect.")
            return {"token": create_token(user.id, user.email), "user": _public(user)}
    except AuthConfigError as exc:
        raise HTTPException(500, str(exc)) from exc


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return _public(user)


@router.put("/profile")
def save_profile(body: dict, user: User = Depends(current_user),
                 sessions=Depends(get_sessions)) -> dict:
    """Persist the attributes someone already answered, so a return visit
    doesn't start from zero. Values only -- never a document."""
    profile = body.get("profile")
    if not isinstance(profile, dict):
        raise HTTPException(422, "profile must be an object")

    with sessions() as session:
        stored = session.get(User, user.id)
        stored.profile_json = json.dumps(profile)
        if body.get("locale"):
            stored.locale = str(body["locale"])[:8]
        session.commit()
        session.refresh(stored)
        return _public(stored)
