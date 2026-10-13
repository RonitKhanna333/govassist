"""The two account paths share validated facts and deterministic verdicts."""
import json

import pytest
from fastapi.testclient import TestClient

from api.auth import router as auth
from api.auth.models import User
from api.db import get_engine, get_session_factory, init_db
from api.deps import get_llm
from api.main import app
from api.onboarding import interview, service
from api.onboarding.models import CallRecord
from api.rules.engine import decide
from api.voice import bland


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "x" * 48)
    monkeypatch.setenv("VOICE_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("VOICE_WEBHOOK_URL", "https://api.example/voice/webhook")
    engine = get_engine("sqlite:///:memory:")
    init_db(engine)
    sessions = get_session_factory(engine)
    app.dependency_overrides[auth.get_sessions] = lambda: sessions
    # The webhook calls this directly instead of depending on it.
    monkeypatch.setattr(auth, "get_sessions", lambda: sessions)
    with TestClient(app) as client:
        result = client.post("/auth/register", json={"display_name": "Asha",
                            "phone": "9876543210", "password": "a-long-password"})
        assert result.status_code == 200
        headers = {"Authorization": "Bearer " + result.json()["token"]}
        yield client, headers, sessions
    app.dependency_overrides.clear()
    engine.dispose()


def test_interview_requires_login(setup):
    client, _, _ = setup
    for path in ("/account/interview", "/account/dashboard"):
        assert client.get(path).status_code == 401
    assert client.post("/account/callback", json={"consent": True}).status_code == 401


def test_phone_login_and_general_profile_resume(setup):
    client, headers, _ = setup
    login = client.post("/auth/login", json={"phone": "+91 98765 43210", "password": "a-long-password"})
    assert login.status_code == 200
    first = client.get("/account/interview", headers=headers).json()
    assert first["question"]["attribute"] == "age"
    answered = client.post("/account/interview", headers=headers, json={"answers": {"age": 30}})
    assert answered.status_code == 200
    assert answered.json()["question"]["attribute"] != "age"
    assert client.get("/account/interview", headers=headers).json()["profile"] == {"age": 30}
    client.post("/account/interview", headers=headers, json={"answers": {"has_savings_bank_account": True}})
    dashboard = client.get("/account/dashboard", headers=headers).json()
    assert dashboard["profile"]["age"] == 30
    for result in dashboard["schemes"]:
        assert result["verdict"] == decide(result["scheme"], dashboard["profile"]).verdict.value
        for citation in result["citations"]:
            assert citation["quote"] and citation["source_url"]


@pytest.mark.parametrize("answers", [{"age": -1}, {"age": 25.5}, {"age": True},
                                       {"is_street_vendor": "true"}, {"made_up": True}])
def test_invalid_answers_cannot_change_profile(setup, answers):
    client, headers, _ = setup
    assert client.post("/account/interview", headers=headers, json={"answers": answers}).status_code == 422
    assert client.get("/auth/me", headers=headers).json()["profile"] == {}


def test_unknown_answer_stays_unknown_and_can_be_revisited(setup):
    client, headers, _ = setup
    state = client.post("/account/interview", headers=headers,
                        json={"answers": {}, "skipped": ["age"]}).json()
    assert "age" not in state["profile"]
    assert state["question"]["attribute"] != "age"
    assert client.get("/account/interview", headers=headers).json()["question"]["attribute"] == "age"


def test_nonfarmer_and_nonvendor_skip_followups():
    profile = {"age": 30, "owns_cultivable_land": False, "is_street_vendor": False}
    asked = []
    while (f := interview.next_field(profile, skipped=asked)) is not None:
        asked.append(f.attribute)
    assert "land_hectares" not in asked
    assert "vends_in_town_or_peri_urban" not in asked
    assert interview.order().index("is_government_employee") < interview.order().index("owns_cultivable_land")


def test_callback_requires_consent_uses_account_phone_and_attaches_result_tool(setup, monkeypatch):
    client, headers, sessions = setup
    sent = []
    monkeypatch.setattr(bland, "start_call", lambda **kwargs: sent.append(kwargs) or "call-123")
    assert client.post("/account/callback", headers=headers, json={"consent": False}).status_code == 422
    result = client.post("/account/callback", headers=headers, json={"consent": True, "locale": "en", "phone": "+19999999999"})
    assert result.status_code == 200
    assert sent[0]["phone"] == "+919876543210"
    assert sent[0]["scheme"] == "all"
    assert sent[0]["max_minutes"] == 10
    assert sent[0]["extra_tools"][0]["url"] == "https://api.example/voice/eligibility?token=test-secret"
    assert "Never add or remove a scheme" in sent[0]["task"]
    with sessions() as session:
        assert session.get(CallRecord, result.json()["id"]).user_id == 1
    assert client.post("/account/callback", headers=headers, json={"consent": True}).status_code == 409


def test_provider_failure_is_saved_and_retry_allowed(setup, monkeypatch):
    client, headers, _ = setup
    def fail(**kwargs):
        raise bland.VoiceError("No credit")
    monkeypatch.setattr(bland, "start_call", fail)
    assert client.post("/account/callback", headers=headers, json={"consent": True}).status_code == 503
    assert client.get("/account/dashboard", headers=headers).json()["calls"][0]["status"] == "failed"
    monkeypatch.setattr(bland, "start_call", lambda **kwargs: "call-retry")
    assert client.post("/account/callback", headers=headers, json={"consent": True}).status_code == 200


def test_provider_denial_returns_diagnostic_code_and_saves_failed_call(setup, monkeypatch):
    client, headers, _ = setup
    def fail(**kwargs):
        raise bland.VoiceError("Calling access denied", status_code=403, operation="GET /tools")
    monkeypatch.setattr(bland, "start_call", fail)
    response = client.post("/account/callback", headers=headers, json={"consent": True, "locale": "hi"})
    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "CALLBACK_PROVIDER_ACCESS_DENIED", "message": "Calling access denied",
        "provider_status": 403, "provider_operation": "GET /tools", "locale": "hi",
    }
    history = client.get("/account/dashboard", headers=headers).json()["calls"]
    assert history[0]["status"] == "failed"


def test_hinglish_callback_uses_latin_script_and_keeps_account_identity(setup, monkeypatch):
    client, headers, sessions = setup
    sent = []
    monkeypatch.setattr(bland, "start_call", lambda **kwargs: sent.append(kwargs) or "call-hinglish")
    response = client.post("/account/callback", headers=headers,
                           json={"consent": True, "locale": "hi", "call_language": "hi-Latn"})
    assert response.status_code == 200
    call = sent[0]
    assert call["locale"] == "hi-Latn"
    assert call["phone"] == "+919876543210"
    assert "Aapki umar kitni hai?" in call["task"]
    assert "Never add or remove a scheme" in call["task"]
    assert not any("\u0900" <= char <= "\u097f" for char in call["task"])
    assert call["metadata"]["call_language"] == "hi-Latn"
    assert call["metadata"]["locale"] == "en"
    tool = call["extra_tools"][0]
    assert tool["body"]["locale"] == "hi-Latn"
    assert tool["input_schema"]["properties"]["age"]["description"] == "Aapki umar kitni hai?"
    with sessions() as session:
        assert session.get(CallRecord, response.json()["id"]).locale == "hi-Latn"


def test_callback_rejects_unknown_call_language_before_contacting_provider(setup, monkeypatch):
    client, headers, _ = setup
    sent = []
    monkeypatch.setattr(bland, "start_call", lambda **kwargs: sent.append(kwargs))
    assert client.post("/account/callback", headers=headers,
                       json={"consent": True, "call_language": "made-up"}).status_code == 422
    assert sent == []


def test_hinglish_eligibility_result_is_server_text_and_uncertainty_stays_unknown(setup):
    client, _, _ = setup
    result = client.post("/voice/eligibility?token=test-secret", json={
        "locale": "hi-Latn", "answers": {"age": "tees", "is_street_vendor": "haan ji",
                                         "has_bank_or_post_office_account": "pata nahi"},
    })
    assert result.status_code == 200
    text = result.json()["result"]
    assert "Aapke jawaabon" in text
    assert "sarkari faisla nahi" in text
    assert not any("\u0900" <= c <= "\u097f" for c in text)
    profile, unparsed = service.read_answers({"age": "tees", "is_street_vendor": "haan ji",
                                            "has_bank_or_post_office_account": "pata nahi"})
    assert profile == {"age": 30, "is_street_vendor": True}
    assert unparsed == ["has_bank_or_post_office_account"]


def test_hinglish_webhook_preserves_transcript_and_only_saves_verified_values(setup, monkeypatch):
    client, headers, _ = setup
    sent = []
    monkeypatch.setattr(bland, "start_call", lambda **kwargs: sent.append(kwargs) or "call-hinglish-saved")
    client.post("/account/callback", headers=headers,
                json={"consent": True, "call_language": "hi-Latn"})
    class QuotingHinglishLLM:
        def complete(self, *args):
            return json.dumps({"age": "tees", "is_street_vendor": "haan ji",
                               "has_bank_or_post_office_account": "pata nahi", "worker_count": "99"})
    app.dependency_overrides[get_llm] = lambda: QuotingHinglishLLM()
    result = client.post("/voice/webhook?token=test-secret", json={
        "call_id": "call-hinglish-saved", "metadata": sent[0]["metadata"],
        "status": "completed", "answered_by": "human", "transcripts": [
            {"user": "assistant", "text": "Aapki umar kitni hai?"}, {"user": "user", "text": "tees"},
            {"user": "assistant", "text": "Kya aap sadak par bechte hain?"}, {"user": "user", "text": "haan ji"},
            {"user": "assistant", "text": "Kya aapka bank account hai?"}, {"user": "user", "text": "pata nahi"},
        ],
    })
    assert result.status_code == 200
    data = client.get("/account/dashboard", headers=headers).json()
    assert data["profile"] == {"age": 30, "is_street_vendor": True}
    call = data["calls"][0]
    assert call["locale"] == "hi-Latn"
    assert call["transcript"][1]["text"] == "tees"
    assert call["heard"]["has_bank_or_post_office_account"] == "pata nahi"
    assert "worker_count" not in call["answers"]


class QuotingLLM:
    def complete(self, *args):
        return json.dumps({"age": "30", "has_bank_or_post_office_account": "not sure",
                           "worker_count": "99", "is_street_vendor": "yes"})


def test_webhook_keeps_transcript_rejects_invented_answers_and_is_idempotent(setup, monkeypatch):
    client, headers, _ = setup
    monkeypatch.setattr(bland, "start_call", lambda **kwargs: "call-complete")
    requested = client.post("/account/callback", headers=headers, json={"consent": True}).json()
    client.post("/account/interview", headers=headers, json={"answers": {"is_indian_citizen": True}})
    app.dependency_overrides[get_llm] = lambda: QuotingLLM()
    payload = {"call_id": "call-complete", "metadata": {"kind": "interview", "locale": "en", "record_id": requested["id"], "user_id": 999},
               "status": "completed", "answered_by": "human", "transcripts": [
                   {"user": "assistant", "text": "How old are you?"}, {"user": "user", "text": "30"},
                   {"user": "assistant", "text": "Do you have a bank account?"}, {"user": "user", "text": "not sure"},
                   {"user": "assistant", "text": "Do you sell on the street?"}, {"user": "user", "text": "yes"}]}
    result = client.post("/voice/webhook?token=test-secret", json=payload)
    assert result.status_code == 200, result.text
    assert result.json()["recorded"] == {"age": 30, "is_street_vendor": True}
    dashboard = client.get("/account/dashboard", headers=headers).json()
    assert dashboard["profile"] == {"is_indian_citizen": True, "age": 30, "is_street_vendor": True}
    assert dashboard["calls"][0]["transcript"][-1] == {"who": "caller", "text": "yes"}
    assert dashboard["calls"][0]["heard"]["has_bank_or_post_office_account"] == "not sure"
    client.post("/account/interview", headers=headers, json={"answers": {"age": 31}})
    assert client.post("/voice/webhook?token=test-secret", json=payload).json()["duplicate"] is True
    assert client.get("/auth/me", headers=headers).json()["profile"]["age"] == 31


def test_webhook_cannot_invent_an_account_call(setup):
    client, _, _ = setup
    assert client.post("/voice/webhook?token=test-secret", json={"call_id": "unknown-call", "status": "failed",
                       "metadata": {"kind": "interview", "user_id": 1}}).status_code == 404


def test_call_history_is_private(setup, monkeypatch):
    client, headers, _ = setup
    monkeypatch.setattr(bland, "start_call", lambda **kwargs: "private-call")
    client.post("/account/callback", headers=headers, json={"consent": True})
    other = client.post("/auth/register", json={"display_name": "Other", "phone": "9876543211", "password": "other-password"}).json()
    dashboard = client.get("/account/dashboard", headers={"Authorization": "Bearer " + other["token"]}).json()
    assert dashboard["calls"] == []


def test_call_numeric_answers_use_same_input_domain():
    values, invalid = service.read_answers({"age": 25.5, "own_contribution_percent": 101})
    assert values == {}
    assert set(invalid) == {"age", "own_contribution_percent"}


def test_hindi_callback_sends_only_ascii_to_the_provider(setup, monkeypatch):
    """Bland's Cloudflare rejected every Hindi callback from Vercel with
    "Attention Required" (HTTP 403) while Hinglish ones went through: it
    blocks Devanagari request bodies from our host. A Hindi call now sends
    its script and tools romanized, but stays a Hindi call, so the agent
    speaks Hindi and the transcript comes back in Devanagari."""
    client, headers, _ = setup
    sent = []
    monkeypatch.setattr(bland, "start_call", lambda **kwargs: sent.append(kwargs) or "call-hi")
    response = client.post("/account/callback", headers=headers,
                           json={"consent": True, "locale": "hi", "call_language": "hi"})
    assert response.status_code == 200
    call = sent[0]
    assert call["locale"] == "hi"                    # still a Hindi call
    assert call["metadata"]["locale"] == "hi"        # answers parsed as Hindi
    assert call["task"].isascii()
    assert "pure spoken Hindi" in call["task"]
    assert "Never add or remove a scheme" in call["task"]
    assert json.dumps(call["extra_tools"], ensure_ascii=False).isascii()


@pytest.mark.parametrize("locale", ["hi", "hi-Latn"])
def test_tool_definitions_for_hindi_are_ascii(locale):
    tool = bland.tool_definition("https://x/voice/ask?token=t", "all", locale)
    assert json.dumps(tool, ensure_ascii=False).isascii()
    elig = bland.eligibility_tool_definition("https://x/voice/eligibility", locale, {"age": "Aapki umar?"})
    assert json.dumps(elig, ensure_ascii=False).isascii()
