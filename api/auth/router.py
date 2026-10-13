"""Auth endpoints: register, login, me, and a saved profile.

Auth is optional for this product, by design. Someone checking whether they
qualify for a government benefit should not have to create an account to
find out -- /chat stays open. Signing in only buys persistence of the
answers you already gave.
"""

from __future__ import annotations

import json
import logging
import math
import re

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from api.auth.models import User
from api.auth.security import (
    AuthConfigError,
    create_token,
    decode_token,
    hash_password,
    jwt_secret,
    verify_password,
)
from api.db import (
    DatabaseConfigError,
    describe_connection_error,
    get_session_factory,
    init_db,
)
from api.rate_limit import auth_rate_limiter, enforce

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 10
# scrypt cost scales with input length only slightly, but there is no reason
# to hash a megabyte "password".
MAX_PASSWORD_LENGTH = 256


class RegisterBody(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)
    display_name: str | None = Field(default=None, max_length=120)
    locale: str | None = Field(default=None, max_length=16)


class LoginBody(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class ProfileBody(BaseModel):
    profile: dict = Field(max_length=64)
    locale: str | None = Field(default=None, max_length=16)


def get_sessions():
    """Accounts need a real database. On a serverless host without
    DATABASE_URL that's a configuration problem, and saying so beats the
    bare 500 a read-only filesystem would otherwise produce."""
    try:
        init_db()
        return get_session_factory()
    except DatabaseConfigError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 -- any failure here is "no database"
        # A wrong password, host or malformed URL otherwise surfaces as a
        # bare 500 with nothing to go on. Log the type (not the text, which
        # can carry the URL); tell the caller the cause.
        log.warning("database unavailable: %s", type(exc).__name__)
        raise HTTPException(503, describe_connection_error(exc)) from exc


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


def _require_signing_config() -> None:
    """Fail before any write or hash if tokens can't be issued.

    Registration used to commit the account and only then try to sign a
    token: with JWT_SECRET missing it answered 500 but kept the user, and the
    retry after fixing the config hit 409 for an account nobody could use.
    """
    try:
        jwt_secret()
    except AuthConfigError as exc:
        raise HTTPException(500, str(exc)) from exc


_DUPLICATE = "That email can't be registered."


@router.post("/register", dependencies=[Depends(enforce(auth_rate_limiter))])
def register(body: RegisterBody, sessions=Depends(get_sessions)) -> dict:
    email = body.email.strip().lower()
    password = body.password

    if not _EMAIL_RE.match(email):
        raise HTTPException(422, "That doesn't look like an email address.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            422, f"Use at least {MIN_PASSWORD_LENGTH} characters for your password.",
        )
    _require_signing_config()

    with sessions() as session:
        if session.scalar(select(User).where(User.email == email)):
            # Same wording as a wrong password on login, and a 409 rather
            # than a distinct message, so this endpoint isn't a way to
            # enumerate who has an account.
            raise HTTPException(409, _DUPLICATE)

        user = User(
            email=email,
            password_hash=hash_password(password),
            display_name=((body.display_name or "").strip() or None),
            locale=(body.locale or "en")[:8],
        )
        try:
            session.add(user)
            session.flush()  # assigns the id without committing
            token = create_token(user.id, user.email)
            session.commit()
        except IntegrityError as exc:
            # Two registrations for one email raced past the check above;
            # the unique index decides, and the loser gets the same 409.
            session.rollback()
            raise HTTPException(409, _DUPLICATE) from exc
        except AuthConfigError as exc:
            session.rollback()
            raise HTTPException(500, str(exc)) from exc
        except BaseException:
            session.rollback()
            raise
        session.refresh(user)
        return {"token": token, "user": _public(user)}


@router.post("/login", dependencies=[Depends(enforce(auth_rate_limiter))])
def login(body: LoginBody, sessions=Depends(get_sessions)) -> dict:
    email = body.email.strip().lower()
    password = body.password
    _require_signing_config()

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
def save_profile(body: ProfileBody, user: User = Depends(current_user),
                 sessions=Depends(get_sessions)) -> dict:
    """Persist the attributes someone already answered, so a return visit
    doesn't start from zero. Values only -- never a document."""
    profile = body.profile
    if not all(v is None or isinstance(v, (bool, int, str))
               or (isinstance(v, float) and math.isfinite(v))
               for v in profile.values()):
        raise HTTPException(422, "profile values must be plain answers")

    with sessions() as session:
        stored = session.get(User, user.id)
        stored.profile_json = json.dumps(profile)
        if body.locale:
            stored.locale = body.locale[:8]
        session.commit()
        session.refresh(stored)
        return _public(stored)
