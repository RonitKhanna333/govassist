"""The conversational layer, spoken-answer parsing, /transcribe, and the
difference between "busy" and "unknown". No network anywhere.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.agents import composer, conversation
from api.agents.llm import GroqLLM, LLMError, Tier
from api.deps import get_language, get_llm
from api.language.service import LanguageService
from api.main import app
from api.rules.engine import Citation
from api.rules.spoken import parse_number, parse_yes_no
from tests.api.test_agents import FakeLLM


class RateLimitedLLM:
    def complete(self, system, user, tier):
        error = LLMError("429")
        error.rate_limited = True
        raise error


def _client(llm=None, language=None) -> TestClient:
    app.dependency_overrides[get_llm] = lambda: llm or FakeLLM([])
    app.dependency_overrides[get_language] = lambda: language or LanguageService(None)
    return TestClient(app)


CLAUSES = [Citation("benefit", "q", "You can get a 35% subsidy.", "https://x", 1)]


# -- spoken answers: the tokenizer bug ---------------------------------------


@pytest.mark.parametrize("text,expected", [
    ("हाँ जी", True), ("नहीं", False), ("haan ji", True), ("nahi", False),
    ("ਹਾਂਜੀ", True), ("ਨਹੀਂ ਲਿਆ", False), ("ஆமாம்", True), ("இல்லை", False),
    ("yes I have", True), ("no", False),
])
def test_yes_no_in_every_script(text, expected):
    """Python's \\w excludes combining marks, so a word-matching tokenizer
    shredded "हाँ" into "ह" and no Indic answer ever matched. Every one of
    these returned None before the fix."""
    assert parse_yes_no(text) is expected


@pytest.mark.parametrize("text", ["I am not sure", "हाँ, नहीं लिया", "", "hmm"])
def test_ambiguous_or_empty_answers_are_not_guessed(text):
    assert parse_yes_no(text) is None


@pytest.mark.parametrize("text,expected", [
    ("25", 25), ("२५ साल", 25), ("੨੫", 25), ("௨௫", 25),
    ("twenty five", 25), ("I am 25 years old.", 25), ("nine", 9),
])
def test_numbers_in_every_script(text, expected):
    assert parse_number(text) == expected


# -- the chat flow --------------------------------------------------------------


def test_start_greets_then_asks():
    body = _client().post("/chat", json={
        "scheme": "pmfme", "profile": {}, "start": True, "locale": "hi",
    }).json()
    assert len(body["bot_messages"]) == 2
    assert body["bot_messages"][0].startswith("नमस्ते")
    assert body["bot_messages"][1] == body["next_question"]


def test_a_spoken_hindi_yes_is_recorded_with_no_model_call():
    llm = FakeLLM([])  # would raise if called
    body = _client(llm=llm).post("/chat", json={
        "scheme": "pmfme", "profile": {}, "message": "हाँ जी",
        "locale": "hi", "message_locale": "hi",
    }).json()
    assert body["profile"]["applicant_type"] == "individual"
    assert body["acknowledged"] is True
    assert body["bot_messages"][-1].startswith("ठीक है।")
    assert llm.calls == []


def test_a_typed_number_answers_a_number_question():
    profile = {"applicant_type": "individual",
               "is_existing_micro_food_processing_unit": True,
               "identified_in_slup_or_verified": True,
               "is_unincorporated": True}
    body = _client().post("/chat", json={
        "scheme": "pmfme", "profile": profile, "message": "9",
    }).json()
    assert body["profile"]["worker_count"] == 9


def test_a_question_is_answered_and_the_flow_resumes():
    """The complaint that prompted the conversational layer: a question used
    to be mined for an answer, find none, and get the same prompt back."""
    llm = FakeLLM([
        '{"type": "question", "value": null}',
        '{"known": true, "answer": "You can get a 35% subsidy.", "used": ["individual-capital-subsidy"]}',
        '{"claims_checked": 1, "unsupported": []}',
    ])
    body = _client(llm=llm).post("/chat", json={
        "scheme": "pmfme", "profile": {}, "message": "how much money will I get?",
    }).json()
    assert body["bot_messages"][0] == "You can get a 35% subsidy."
    assert body["reply"] == "You can get a 35% subsidy."
    # ...and the conversation carries on with the question it was on.
    assert body["bot_messages"][1] == body["next_question"]
    assert body["reply_citations"][0]["clause_id"] == "individual-capital-subsidy"


def test_a_question_after_a_verdict_does_not_resend_the_verdict():
    """After a verdict, every message used to re-send the identical
    explanation -- the "fixed answers" complaint."""
    from tests.api.test_chat_endpoint import FULLY_QUALIFYING_PROFILE
    llm = FakeLLM([
        '{"type": "question", "value": null}',
        '{"known": true, "answer": "You can get a 35% subsidy.", "used": ["individual-capital-subsidy"]}',
        '{"claims_checked": 1, "unsupported": []}',
    ])
    body = _client(llm=llm).post("/chat", json={
        "scheme": "pmfme", "profile": FULLY_QUALIFYING_PROFILE,
        "message": "how much will I get?",
    }).json()
    assert body["verdict"] == "ELIGIBLE"
    assert body["answer"] is None
    assert body["bot_messages"] == ["You can get a 35% subsidy."]


def test_an_unanswerable_question_says_so_plainly():
    llm = FakeLLM([
        '{"type": "question", "value": null}',
        '{"known": false, "answer": "", "used": []}',
    ])
    body = _client(llm=llm).post("/chat", json={
        "scheme": "pmfme", "profile": {}, "message": "can I get a tractor?",
    }).json()
    assert "don't have that information" in body["bot_messages"][0]


def test_a_rate_limit_is_reported_as_busy_not_as_unknown():
    """Saying "I don't have that information" under a throttle tells the
    person the scheme doesn't cover something it may well cover."""
    body = _client(llm=RateLimitedLLM()).post("/chat", json={
        "scheme": "pmfme", "profile": {}, "message": "how much money will I get?",
    }).json()
    assert "a lot of questions" in body["bot_messages"][0]
    assert "don't have that information" not in body["bot_messages"][0]


def test_a_rate_limited_verdict_says_busy_not_no_grounded_facts():
    from tests.api.test_chat_endpoint import FULLY_QUALIFYING_PROFILE
    body = _client(llm=RateLimitedLLM()).post("/chat", json={
        "scheme": "pmfme", "profile": FULLY_QUALIFYING_PROFILE,
    }).json()
    assert body["verdict"] == "ELIGIBLE"      # the engine needed no model
    assert "a lot of questions" in body["answer"]


def test_unplaceable_answer_says_it_did_not_understand():
    llm = FakeLLM(['{"type": "answer", "value": null}', "{}"])
    body = _client(llm=llm).post("/chat", json={
        "scheme": "pmfme", "profile": {}, "message": "blue",
    }).json()
    assert "didn't catch that" in body["bot_messages"][0]


def test_summary_and_pending_are_localized():
    body = _client().post("/chat", json={
        "scheme": "pmfme", "profile": {"applicant_type": "individual"}, "locale": "pa",
    }).json()
    assert body["profile_summary"][0]["value"] == "ਹਾਂ"
    assert body["pending"]["fields"][0]["ask"].startswith("ਕੀ")


# -- the question-answer recompose ------------------------------------------


def test_a_partly_unsupported_answer_is_recomposed_not_discarded():
    llm = FakeLLM([
        '{"known": true, "answer": "35% subsidy. Also a free tractor.", "used": ["benefit"]}',
        '{"claims_checked": 2, "unsupported": ["Also a free tractor."]}',
        '{"known": true, "answer": "35% subsidy.", "used": ["benefit"]}',
        '{"claims_checked": 1, "unsupported": []}',
    ])
    reply = conversation.answer_question(llm, "how much?", CLAUSES)
    assert reply.text == "35% subsidy."
    assert "tractor" in llm.calls[2][1]      # the retry was told what to drop


def test_a_verbatim_unsupported_sentence_is_cut_without_another_call():
    llm = FakeLLM([
        '{"known": true, "answer": "You get a 35% subsidy on the cost. Also a free tractor.", "used": ["benefit"]}',
        '{"claims_checked": 2, "unsupported": ["Also a free tractor."]}',
    ])
    reply = conversation.answer_question(llm, "how much?", CLAUSES)
    assert reply.text == "You get a 35% subsidy on the cost."
    assert len(llm.calls) == 2


def test_an_answer_citing_nothing_is_refused():
    llm = FakeLLM(['{"known": true, "answer": "Lots.", "used": []}'])
    assert conversation.answer_question(llm, "how much?", CLAUSES).text is None


# -- llm client: 429 --------------------------------------------------------


def test_429_is_retried_then_succeeds():
    llm = GroqLLM(api_key="k")
    limited = MagicMock(status_code=429, headers={"retry-after": "0"})
    ok = MagicMock(status_code=200, json=lambda: {"choices": [{"message": {"content": "hi"}}]})
    ok.raise_for_status = lambda: None
    with patch("api.agents.llm.requests.post", side_effect=[limited, ok]), \
         patch("api.agents.llm.time.sleep"):
        assert llm.complete("s", "u", Tier.FAST) == "hi"


def test_persistent_429_raises_a_rate_limited_error():
    llm = GroqLLM(api_key="k")
    limited = MagicMock(status_code=429, headers={"retry-after": "0"})
    with patch("api.agents.llm.requests.post", return_value=limited), \
         patch("api.agents.llm.time.sleep"):
        with pytest.raises(LLMError) as caught:
            llm.complete("s", "u", Tier.FAST)
    assert caught.value.rate_limited is True


def test_composer_returns_the_busy_marker_under_a_rate_limit():
    assert composer.draft_answer(RateLimitedLLM(), "ELIGIBLE", CLAUSES) == composer.FALLBACK_BUSY


# -- /transcribe ------------------------------------------------------------


class FakeTranscriber:
    supports_tts = False

    def __init__(self):
        self.calls = []

    def translate(self, text, source, target):
        return text

    def transcribe(self, audio, locale, mime="audio/webm", filename="speech.webm"):
        self.calls.append((len(audio), locale, mime, filename))
        return "हाँ जी"


def test_transcribe_returns_text_for_hindi():
    provider = FakeTranscriber()
    client = _client(language=LanguageService(provider=provider))
    response = client.post("/transcribe?locale=hi", content=b"fake-audio",
                           headers={"Content-Type": "audio/webm;codecs=opus"})
    assert response.status_code == 200
    assert response.json() == {"text": "हाँ जी", "locale": "hi"}
    assert provider.calls == [(10, "hi", "audio/webm", "speech.webm")]


def test_transcribe_refuses_languages_not_yet_enabled():
    """Voice is Hindi (and English) only for now, by decision."""
    client = _client(language=LanguageService(provider=FakeTranscriber()))
    response = client.post("/transcribe?locale=ta", content=b"x",
                           headers={"Content-Type": "audio/webm"})
    assert response.status_code == 422


def test_transcribe_rejects_empty_audio():
    client = _client(language=LanguageService(provider=FakeTranscriber()))
    response = client.post("/transcribe?locale=hi", content=b"",
                           headers={"Content-Type": "audio/webm"})
    assert response.status_code == 422


def test_transcribe_without_a_provider_says_why():
    client = _client(language=LanguageService(provider=None))
    response = client.post("/transcribe?locale=hi", content=b"x",
                           headers={"Content-Type": "audio/webm"})
    assert response.status_code == 503
    assert "isn't configured" in response.json()["detail"]


def test_locales_report_which_languages_have_voice_input():
    body = _client().get("/locales").json()
    voice = {loc["code"]: loc["voice_input"] for loc in body["locales"]}
    assert voice == {"en": True, "hi": True, "pa": False, "ta": False}


# -- /speak and Whisper's non-speech filter ----------------------------------


def test_speak_returns_mp3_for_hindi():
    async def fake(text, locale):
        return b"ID3fake"
    with patch("api.language.tts.synthesize", side_effect=fake):
        response = _client().post("/speak", json={"text": "नमस्ते", "locale": "hi"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == b"ID3fake"


def test_speak_refuses_languages_without_a_server_voice():
    assert _client().post("/speak", json={"text": "x", "locale": "ta"}).status_code == 422


def test_whisper_drops_segments_that_are_not_speech():
    from api.language.providers.groq import GroqLanguageProvider
    ok = MagicMock(status_code=200)
    ok.raise_for_status = lambda: None
    ok.json = lambda: {"text": "करते हैं हाँ", "segments": [
        {"text": "करते हैं", "no_speech_prob": 0.9, "avg_logprob": -0.2},
        {"text": " हाँ", "no_speech_prob": 0.1, "avg_logprob": -0.3},
    ]}
    with patch.dict("os.environ", {"GROQ_API_KEY": "k"}), \
         patch("api.language.providers.groq.requests.post", return_value=ok):
        assert GroqLanguageProvider().transcribe(b"x", "hi") == "हाँ"
