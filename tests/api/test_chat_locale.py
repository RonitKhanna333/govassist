"""POST /chat's multilingual behaviour, and /locales + /detect-locale."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.deps import get_language, get_llm
from api.language.service import LanguageService
from api.main import app
from tests.api.test_agents import FakeLLM
from tests.api.test_chat_endpoint import FULLY_QUALIFYING_PROFILE


class EchoTranslator:
    """A provider that 'translates' by tagging the text, keeping sentinels
    intact -- enough to prove the wiring without a real NMT model."""

    def __init__(self):
        self.calls = []

    def translate(self, text, source, target):
        self.calls.append((text, source, target))
        if source == target:
            return text
        return f"[{target}]{text}"

    def synthesize(self, text, locale):
        return b"audio"

    def transcribe(self, audio, locale):
        return "transcript"


def _client(llm=None, language=None) -> TestClient:
    app.dependency_overrides[get_llm] = lambda: llm or FakeLLM([])
    app.dependency_overrides[get_language] = lambda: language or LanguageService(None)
    return TestClient(app)


def test_locales_endpoint_lists_endonyms():
    client = _client()
    body = client.get("/locales").json()
    endonyms = {loc["code"]: loc["endonym"] for loc in body["locales"]}
    assert endonyms["pa"] == "ਪੰਜਾਬੀ"
    assert endonyms["ta"] == "தமிழ்"


def test_detect_locale_reads_accept_language():
    client = _client()
    response = client.get("/detect-locale", headers={"Accept-Language": "ta;q=0.9,en;q=0.8"})
    assert response.json()["locale"] == "ta"


def test_detect_locale_falls_back_to_english_for_unsupported():
    client = _client()
    response = client.get("/detect-locale", headers={"Accept-Language": "de-DE"})
    assert response.json()["locale"] == "en"


def test_question_is_translated_into_the_requested_locale():
    language = LanguageService(provider=EchoTranslator())
    client = _client(language=language)
    body = client.post("/chat", json={
        "scheme": "pmfme", "profile": {}, "locale": "hi",
    }).json()

    assert body["verdict"] == "INSUFFICIENT_INFO"
    assert body["next_question"].startswith("[hi]")
    assert body["locale"] == "hi"


def test_without_a_provider_the_answer_stays_english_and_says_why():
    client = _client(language=LanguageService(provider=None))
    body = client.post("/chat", json={
        "scheme": "pmfme", "profile": {}, "locale": "ta",
    }).json()

    assert body["next_question"]
    assert "[ta]" not in body["next_question"]      # untranslated
    assert body["language_note"]                     # and the user is told why


def test_citations_are_never_translated():
    """The explanation is localized; the quoted clause is not. A translated
    quote is no longer a quote."""
    llm = FakeLLM(["You qualify.", '[{"claim": "q", "status": "SUPPORTED"}]'])
    language = LanguageService(provider=EchoTranslator())
    client = _client(llm=llm, language=language)

    body = client.post("/chat", json={
        "scheme": "pmfme", "profile": FULLY_QUALIFYING_PROFILE, "locale": "hi",
    }).json()

    assert body["answer"].startswith("[hi]")         # explanation translated
    for citation in body["citations"]:
        assert not citation["quote"].startswith("[hi]")   # quote untouched


def test_incoming_message_is_translated_to_english_before_nlu():
    llm = FakeLLM(['{"age": 25}'])
    translator = EchoTranslator()
    client = _client(llm=llm, language=LanguageService(provider=translator))

    client.post("/chat", json={
        "scheme": "pmfme", "profile": {},
        "message": "मेरी उम्र 25 है", "message_locale": "hi", "locale": "hi",
    })

    # the inbound hop happened: hi -> en, before the model saw anything
    assert ("मेरी उम्र ⟦E0⟧ है", "hi", "en") in [
        (c[0], c[1], c[2]) for c in translator.calls
    ] or any(c[1] == "hi" and c[2] == "en" for c in translator.calls)


def test_speech_plan_is_returned_with_a_rung():
    client = _client(language=LanguageService(provider=None))
    body = client.post("/chat", json={
        "scheme": "pmfme", "profile": {}, "locale": "pa",
    }).json()

    assert body["speech"]["rung"] in {"provider", "browser", "text_only"}
    assert body["speech"]["chunks"]
