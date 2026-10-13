"""Optional accounts: saving a profile from the browser, and registration
that never leaves an unusable account behind. In-memory SQLite only.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from api.auth import router as auth_router_mod
from api.auth.models import User
from api.db import Base, get_engine, get_session_factory
from api.main import app

ALLOWED = "http://localhost:3000"
SECRET = "s" * 48


@pytest.fixture
def sessions():
    engine = get_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = get_session_factory(engine)
    app.dependency_overrides[auth_router_mod.get_sessions] = lambda: factory
    yield factory
    app.dependency_overrides.pop(auth_router_mod.get_sessions, None)


def _users(sessions) -> int:
    with sessions() as session:
        return session.scalar(select(func.count()).select_from(User))


def _preflight(origin: str):
    return TestClient(app).options("/auth/profile", headers={
        "Origin": origin,
        "Access-Control-Request-Method": "PUT",
        "Access-Control-Request-Headers": "authorization,content-type",
    })


# -- CORS for PUT /auth/profile ----------------------------------------------------------


@pytest.mark.parametrize("origin", [
    ALLOWED,
    "https://govassist-web-git-main-ronit-khannas-projects.vercel.app",
    "https://govassist-web-git-feature-x-ronit-khannas-projects.vercel.app",
])
def test_put_preflight_is_allowed_for_the_frontend(origin):
    response = _preflight(origin)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "PUT" in response.headers["access-control-allow-methods"]
    assert response.headers["access-control-allow-credentials"] == "true"


@pytest.mark.parametrize("origin", [
    "https://evil.example",
    "https://some-other-project.vercel.app",
    "http://localhost:3001",
])
def test_put_preflight_is_still_refused_for_other_origins(origin):
    response = _preflight(origin)
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_methods_nobody_uses_stay_disallowed():
    response = TestClient(app).options("/auth/profile", headers={
        "Origin": ALLOWED, "Access-Control-Request-Method": "DELETE",
    })
    assert response.status_code == 400


def test_a_browser_can_save_and_reload_its_profile(monkeypatch, sessions):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    client = TestClient(app)
    token = client.post("/auth/register", json={
        "email": "asha@example.com", "password": "a-long-enough-pw",
    }, headers={"Origin": ALLOWED}).json()["token"]
    headers = {"Authorization": f"Bearer {token}", "Origin": ALLOWED}

    saved = client.put("/auth/profile", json={
        "profile": {"age": 25, "passed_class_8": True}, "locale": "hi",
    }, headers=headers)
    assert saved.status_code == 200
    assert saved.headers["access-control-allow-origin"] == ALLOWED

    me = client.get("/auth/me", headers=headers).json()
    assert me["profile"] == {"age": 25, "passed_class_8": True}
    assert me["locale"] == "hi"


@pytest.mark.parametrize("profile", [42, [1], {"age": {"nested": 1}}, {"age": [25]}])
def test_profile_save_rejects_non_answers(monkeypatch, sessions, profile):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    client = TestClient(app)
    token = client.post("/auth/register", json={
        "email": "b@example.com", "password": "a-long-enough-pw",
    }).json()["token"]
    response = client.put("/auth/profile", json={"profile": profile},
                          headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 422


# -- registration is atomic with token issuance -------------------------------------------


@pytest.mark.parametrize("secret", [None, "too-short"])
def test_bad_signing_config_creates_no_account(monkeypatch, sessions, secret):
    if secret is None:
        monkeypatch.delenv("JWT_SECRET", raising=False)
    else:
        monkeypatch.setenv("JWT_SECRET", secret)
    response = TestClient(app).post("/auth/register", json={
        "email": "asha@example.com", "password": "a-long-enough-pw",
    })
    assert response.status_code == 500
    assert "JWT_SECRET" in response.json()["detail"]
    assert _users(sessions) == 0

    # Fixing the configuration and retrying works -- no 409 for a ghost account.
    monkeypatch.setenv("JWT_SECRET", SECRET)
    retry = TestClient(app).post("/auth/register", json={
        "email": "asha@example.com", "password": "a-long-enough-pw",
    })
    assert retry.status_code == 200
    assert retry.json()["token"]
    assert _users(sessions) == 1


def test_a_failure_while_signing_rolls_the_account_back(monkeypatch, sessions):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    from api.auth.security import AuthConfigError

    def broken(*args, **kwargs):
        raise AuthConfigError("signing failed")

    monkeypatch.setattr(auth_router_mod, "create_token", broken)
    response = TestClient(app).post("/auth/register", json={
        "email": "asha@example.com", "password": "a-long-enough-pw",
    })
    assert response.status_code == 500
    assert _users(sessions) == 0


def test_an_unexpected_failure_after_flush_rolls_back(monkeypatch, sessions):
    monkeypatch.setenv("JWT_SECRET", SECRET)

    def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(auth_router_mod, "create_token", broken)
    response = TestClient(app, raise_server_exceptions=False).post("/auth/register", json={
        "email": "asha@example.com", "password": "a-long-enough-pw",
    })
    assert response.status_code == 500
    assert _users(sessions) == 0


def test_a_concurrent_duplicate_is_a_clean_409(monkeypatch, sessions):
    """Two registrations for one email can both pass the "does this email
    exist?" check. Simulate the loser of that race deterministically: the
    check sees nothing, the unique index decides, and the response is the
    same 409 as an ordinary duplicate -- not a 500, and no second row."""
    monkeypatch.setenv("JWT_SECRET", SECRET)
    client = TestClient(app)
    assert client.post("/auth/register", json={
        "email": "same@example.com", "password": "a-long-enough-pw",
    }).status_code == 200

    from sqlalchemy.orm import Session
    monkeypatch.setattr(Session, "scalar", lambda self, *a, **k: None)
    response = client.post("/auth/register", json={
        "email": "same@example.com", "password": "a-long-enough-pw",
    })
    assert response.status_code == 409
    assert response.json()["detail"] == "That email can't be registered."
    monkeypatch.undo()
    assert _users(sessions) == 1
