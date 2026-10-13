"""Costly routes are limited before they spend anything, the provider probe
is for operators, and oversized bodies never reach a route. Offline: every
provider is a mock that counts calls.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.auth import router as auth_router_mod
from api.body_limit import AUDIO_BODY_LIMIT, JSON_BODY_LIMIT
from api.db import Base, get_engine, get_session_factory
from api.deps import get_language, get_llm
from api.language.service import LanguageService
from api.main import app
from api.rate_limit import (
    auth_rate_limiter, chat_rate_limiter, probe_rate_limiter, speak_rate_limiter,
    transcribe_rate_limiter,
)
from tests.api.test_agents import FakeLLM

TOKEN = "t" * 32


class CountingLanguage(LanguageService):
    def __init__(self):
        super().__init__(None)
        self.transcriptions = 0

    def transcribe(self, audio, locale, mime, filename):
        self.transcriptions += 1
        return "haan"


@pytest.fixture
def language():
    fake = CountingLanguage()
    app.dependency_overrides[get_language] = lambda: fake
    app.dependency_overrides[get_llm] = lambda: FakeLLM([])
    yield fake
    app.dependency_overrides.pop(get_language, None)


@pytest.fixture
def sessions():
    engine = get_engine("sqlite:///:memory:")
    from api.auth import models  # noqa: F401
    Base.metadata.create_all(engine)
    factory = get_session_factory(engine)
    app.dependency_overrides[auth_router_mod.get_sessions] = lambda: factory
    yield factory
    app.dependency_overrides.pop(auth_router_mod.get_sessions, None)


def _limit(monkeypatch, limiter, n):
    monkeypatch.setattr(limiter, "limit", n)


def _assert_429(response):
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) >= 1


# -- per-route limits ---------------------------------------------------------------


def test_transcribe_is_limited_before_the_provider_is_called(monkeypatch, language):
    _limit(monkeypatch, transcribe_rate_limiter, 2)
    client = TestClient(app)
    for _ in range(2):
        assert client.post("/transcribe?locale=hi", content=b"audio",
                           headers={"Content-Type": "audio/webm"}).status_code == 200
    _assert_429(client.post("/transcribe?locale=hi", content=b"audio",
                            headers={"Content-Type": "audio/webm"}))
    assert language.transcriptions == 2


def test_speak_is_limited_before_synthesis(monkeypatch):
    _limit(monkeypatch, speak_rate_limiter, 1)
    with patch("api.language.tts.synthesize", return_value=b"mp3") as synth:
        client = TestClient(app)
        assert client.post("/speak", json={"text": "नमस्ते", "locale": "hi"}).status_code == 200
        _assert_429(client.post("/speak", json={"text": "नमस्ते", "locale": "hi"}))
    assert synth.call_count == 1


def test_login_is_limited_before_any_password_hashing(monkeypatch, sessions):
    monkeypatch.setenv("JWT_SECRET", "x" * 48)
    _limit(monkeypatch, auth_rate_limiter, 2)
    with patch.object(auth_router_mod, "verify_password", return_value=False) as check:
        client = TestClient(app)
        for _ in range(2):
            client.post("/auth/login", json={"email": "a@b.co", "password": "p" * 12})
        _assert_429(client.post("/auth/login", json={"email": "a@b.co", "password": "p" * 12}))
    assert check.call_count <= 2


def test_register_is_limited_before_hashing(monkeypatch, sessions):
    monkeypatch.setenv("JWT_SECRET", "x" * 48)
    _limit(monkeypatch, auth_rate_limiter, 1)
    with patch.object(auth_router_mod, "hash_password", return_value="scrypt$a$b") as hashed:
        client = TestClient(app)
        client.post("/auth/register", json={"email": "a@b.co", "password": "p" * 12})
        _assert_429(client.post("/auth/register", json={"email": "c@d.co", "password": "p" * 12}))
    assert hashed.call_count == 1


def test_buckets_are_independent(monkeypatch, language):
    _limit(monkeypatch, speak_rate_limiter, 1)
    with patch("api.language.tts.synthesize", return_value=b"mp3"):
        client = TestClient(app)
        client.post("/speak", json={"text": "hi", "locale": "en"})
        _assert_429(client.post("/speak", json={"text": "hi", "locale": "en"}))
    assert client.post("/chat", json={"scheme": "pmfme", "profile": {}}).status_code == 200


def test_chat_still_returns_429_with_retry_after(monkeypatch, language):
    _limit(monkeypatch, chat_rate_limiter, 1)
    client = TestClient(app)
    client.post("/chat", json={"scheme": "pmfme", "profile": {}})
    _assert_429(client.post("/chat", json={"scheme": "pmfme", "profile": {}}))


# -- the diagnostic probe ---------------------------------------------------------------


def test_plain_health_stays_open_and_unlimited(monkeypatch):
    _limit(monkeypatch, probe_rate_limiter, 1)
    client = TestClient(app)
    assert all(client.get("/health").status_code == 200 for _ in range(5))


@pytest.mark.parametrize("configured,sent", [
    ("", ""),              # no token configured: the probe is off
    ("", "anything"),
    (TOKEN, ""),           # anonymous caller
    (TOKEN, "wrong-token-value-here"),
    ("short", "short"),    # a guessable token is treated as unset
])
def test_probe_refuses_anonymous_callers_without_calling_groq(monkeypatch, configured, sent):
    monkeypatch.setenv("GOVASSIST_DIAGNOSTIC_TOKEN", configured)
    with patch("api.agents.llm.GroqLLM.complete") as complete:
        response = TestClient(app).get("/health?probe=llm",
                                       headers={"X-Diagnostic-Token": sent})
    assert response.status_code == 403
    complete.assert_not_called()


def test_probe_works_for_an_operator_and_is_limited(monkeypatch):
    monkeypatch.setenv("GOVASSIST_DIAGNOSTIC_TOKEN", TOKEN)
    _limit(monkeypatch, probe_rate_limiter, 1)
    with patch("api.agents.llm.GroqLLM.complete", return_value="ok") as complete:
        client = TestClient(app)
        first = client.get("/health?probe=llm", headers={"X-Diagnostic-Token": TOKEN})
        assert first.json()["llm_probe"] == {"ok": True, "reply": "ok"}
        _assert_429(client.get("/health?probe=llm", headers={"X-Diagnostic-Token": TOKEN}))
    assert complete.call_count == 1


# -- payload bounds -----------------------------------------------------------------------


def test_an_oversized_json_body_is_413_before_parsing():
    response = TestClient(app).post(
        "/chat", content=b'{"scheme":"pmfme","message":"' + b"a" * JSON_BODY_LIMIT + b'"}',
        headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_an_oversized_chunked_body_is_413_too():
    def chunks():
        for _ in range(JSON_BODY_LIMIT // 1024 + 2):
            yield b"a" * 1024
    response = TestClient(app).post("/chat", content=chunks(),
                                    headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_audio_gets_its_larger_allowance(language):
    response = TestClient(app).post(
        "/transcribe?locale=hi", content=b"a" * (JSON_BODY_LIMIT * 2),
        headers={"Content-Type": "audio/webm"})
    assert response.status_code == 200
    too_big = TestClient(app).post(
        "/transcribe?locale=hi", content=b"a" * (AUDIO_BODY_LIMIT + 1),
        headers={"Content-Type": "audio/webm"})
    assert too_big.status_code == 413


def test_speak_text_is_bounded():
    with patch("api.language.tts.synthesize", return_value=b"mp3") as synth:
        response = TestClient(app).post("/speak", json={"text": "a" * 2001, "locale": "en"})
    assert response.status_code == 422
    synth.assert_not_called()


def test_a_413_still_carries_cors_headers_for_the_frontend():
    response = TestClient(app).post(
        "/chat", content=b"a" * (JSON_BODY_LIMIT + 1),
        headers={"Content-Type": "application/json", "Origin": "http://localhost:3000"})
    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
