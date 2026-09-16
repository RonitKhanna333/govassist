"""Auth: hashing, tokens, and the endpoints -- with the security properties
asserted explicitly, because these are the ones that fail silently.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.auth import router as auth_router_mod
from api.auth.security import (
    AuthConfigError,
    create_token,
    decode_token,
    hash_password,
    jwt_secret,
    verify_password,
)
from api.db import Base, get_engine, get_session_factory
from api.main import app

SECRET = "x" * 48


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)


@pytest.fixture
def client(monkeypatch):
    # get_engine picks StaticPool for :memory:, so the endpoint thread and
    # this one share a database -- see api/db.py.
    engine = get_engine("sqlite:///:memory:")
    from api.auth import models  # noqa: F401 -- registers the users table
    Base.metadata.create_all(engine)
    sessions = get_session_factory(engine)
    app.dependency_overrides[auth_router_mod.get_sessions] = lambda: sessions
    yield TestClient(app)
    app.dependency_overrides.pop(auth_router_mod.get_sessions, None)


# -- hashing ----------------------------------------------------------------


def test_hash_is_not_the_password():
    stored = hash_password("correct horse battery")
    assert "correct horse battery" not in stored


def test_same_password_hashes_differently_each_time():
    """Per-password salt. Without it a rainbow table works again."""
    a = hash_password("same-password-here")
    b = hash_password("same-password-here")
    assert a != b
    assert verify_password("same-password-here", a)
    assert verify_password("same-password-here", b)


def test_wrong_password_fails():
    stored = hash_password("the-real-password")
    assert not verify_password("the-wrong-password", stored)


def test_malformed_stored_hash_fails_closed():
    for junk in ["", "nonsense", "scrypt$only-two", "bcrypt$a$b"]:
        assert not verify_password("anything", junk)


# -- tokens ------------------------------------------------------------------


def test_token_round_trips():
    claims = decode_token(create_token(7, "a@b.com"))
    assert claims["sub"] == "7"
    assert claims["email"] == "a@b.com"


def test_token_signed_with_another_secret_is_rejected(monkeypatch):
    token = create_token(1, "a@b.com")
    monkeypatch.setenv("JWT_SECRET", "y" * 48)
    assert decode_token(token) is None


def test_tampered_token_is_rejected():
    token = create_token(1, "a@b.com")
    assert decode_token(token[:-3] + "aaa") is None


def test_missing_secret_raises_rather_than_defaulting(monkeypatch):
    """A hardcoded fallback would let anyone reading this public repo mint a
    token for any account."""
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(AuthConfigError):
        jwt_secret()


def test_short_secret_is_rejected(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "tooshort")
    with pytest.raises(AuthConfigError):
        jwt_secret()


# -- endpoints ---------------------------------------------------------------


def test_register_then_me(client):
    response = client.post("/auth/register", json={
        "email": "Ronit@Example.com", "password": "a-long-enough-pw",
    })
    assert response.status_code == 200
    token = response.json()["token"]
    assert response.json()["user"]["email"] == "ronit@example.com"  # lowercased

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "ronit@example.com"


def test_register_rejects_short_password(client):
    response = client.post("/auth/register", json={"email": "a@b.com", "password": "short"})
    assert response.status_code == 422


def test_register_rejects_bad_email(client):
    response = client.post("/auth/register", json={"email": "nope", "password": "a-long-enough-pw"})
    assert response.status_code == 422


def test_duplicate_registration_does_not_confirm_the_account_exists(client):
    client.post("/auth/register", json={"email": "a@b.com", "password": "a-long-enough-pw"})
    again = client.post("/auth/register", json={"email": "a@b.com", "password": "a-long-enough-pw"})
    assert again.status_code == 409
    assert "can't be registered" in again.json()["detail"]
    assert "already" not in again.json()["detail"].lower()


def test_login_succeeds_and_wrong_password_does_not(client):
    client.post("/auth/register", json={"email": "a@b.com", "password": "a-long-enough-pw"})

    ok = client.post("/auth/login", json={"email": "a@b.com", "password": "a-long-enough-pw"})
    assert ok.status_code == 200

    bad = client.post("/auth/login", json={"email": "a@b.com", "password": "wrong-password-x"})
    assert bad.status_code == 401


def test_unknown_user_and_wrong_password_are_indistinguishable(client):
    """Different wording tells an attacker which half they guessed right."""
    client.post("/auth/register", json={"email": "real@b.com", "password": "a-long-enough-pw"})

    wrong_pw = client.post("/auth/login", json={"email": "real@b.com", "password": "nope-nope-nope"})
    no_user = client.post("/auth/login", json={"email": "ghost@b.com", "password": "nope-nope-nope"})

    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json()["detail"] == no_user.json()["detail"]


def test_me_requires_a_token(client):
    assert client.get("/auth/me").status_code == 401


def test_me_rejects_a_garbage_token(client):
    response = client.get("/auth/me", headers={"Authorization": "Bearer not-a-token"})
    assert response.status_code == 401


def test_profile_saves_and_reloads(client):
    token = client.post("/auth/register", json={
        "email": "a@b.com", "password": "a-long-enough-pw",
    }).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    saved = client.put("/auth/profile", json={"profile": {"age": 25}}, headers=headers)
    assert saved.status_code == 200
    assert saved.json()["profile"] == {"age": 25}

    assert client.get("/auth/me", headers=headers).json()["profile"] == {"age": 25}


def test_profile_requires_auth(client):
    assert client.put("/auth/profile", json={"profile": {}}).status_code == 401


def test_chat_still_works_without_signing_in(client):
    """Auth is optional on purpose -- nobody should need an account to find
    out whether they qualify for a benefit."""
    response = client.post("/chat", json={"scheme": "pmfme", "profile": {}})
    assert response.status_code == 200
    assert response.json()["verdict"] == "INSUFFICIENT_INFO"
