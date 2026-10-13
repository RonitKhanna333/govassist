"""The phone channel: script generation, guards, and a replayed call.

No network and no telephony account: a call's webhook is just JSON, so the
whole path -- heard answers to verdict to SMS text -- is exercised by
posting the payload a provider would post.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.deps import get_language
from api.language.service import LanguageService
from api.main import app
from api.routers import voice
from api.voice import bland, script

SECRET = "test-secret"
MY_NUMBER = "+919000000000"


@pytest.fixture
def client():
    app.dependency_overrides[get_language] = lambda: LanguageService(None)
    return TestClient(app)


def _post_call(client, **over):
    body = {"scheme": "pmsby", "locale": "hi", "phone": MY_NUMBER, "consent": True}
    body.update(over)
    return client.post("/voice/call", json=body)


def _webhook(client, heard, scheme="pmsby", locale="hi", phone=MY_NUMBER):
    payload = {"call_id": "c1", "to": phone, "analysis": heard,
               "metadata": {"scheme": scheme, "locale": locale}}
    with patch.dict("os.environ", {"VOICE_WEBHOOK_SECRET": SECRET}):
        return client.post(f"/voice/webhook?token={SECRET}", json=payload)


# -- the script comes from the rules, not from prose ------------------------


def test_the_script_asks_every_attribute_the_rules_test():
    task = script.build_task("pmsby", "hi")
    for ask in ("बैंक", "उम्र", "अपने-आप काटने"):
        assert ask in task


def test_the_script_forbids_stating_eligibility():
    """The call collects answers; the rule engine decides. If this line ever
    leaves the prompt, an AI's guess reaches someone as a government answer."""
    hindi = script.build_task("pm-kmy", "hi")
    assert "पात्र है या नहीं" in hindi
    assert "नतीजा आपको मैसेज पर" in hindi
    english = script.build_task("pm-kmy", "en")
    never = english.split("Never:")[1]
    assert "whether they qualify" in never


def test_the_script_forbids_asking_for_otp_or_money():
    assert "OTP" in script.build_task("apy", "hi")


def test_a_new_scheme_needs_no_new_prompt():
    """Four schemes were added without touching this module."""
    for scheme in ("pmfme", "pmsby", "pmjjby", "apy", "pm-kmy"):
        assert script.build_task(scheme, "hi")
        assert script.answer_schema(scheme, "hi")["properties"]


def test_numbers_are_asked_for_as_numbers():
    properties = script.answer_schema("pm-kmy", "hi")["properties"]
    assert properties["land_hectares"]["type"] == ["number", "null"]
    assert properties["owns_cultivable_land"]["type"] == ["string", "null"]


def test_calls_are_refused_in_untested_languages(client):
    assert client.get("/voice/script?scheme=pmsby&locale=ta").status_code == 422


# -- guards -----------------------------------------------------------------


def test_a_call_without_recorded_consent_is_refused(client):
    response = _post_call(client, consent=False)
    assert response.status_code == 422
    assert "consent" in response.json()["detail"]


def test_an_empty_allowlist_calls_nobody():
    """Default-deny: a public /voice/call with a key and no allowlist is a
    robocaller waiting to be found."""
    with patch.dict("os.environ", {"BLAND_API_KEY": "k", "VOICE_ALLOWED_NUMBERS": ""}):
        with pytest.raises(bland.VoiceError, match="no number may be called"):
            bland.check_number(MY_NUMBER)


def test_a_number_outside_the_allowlist_is_refused():
    with patch.dict("os.environ", {"VOICE_ALLOWED_NUMBERS": MY_NUMBER}):
        with pytest.raises(bland.VoiceError, match="not in VOICE_ALLOWED_NUMBERS"):
            bland.check_number("+919111111111")
        assert bland.check_number(MY_NUMBER) == MY_NUMBER


@pytest.mark.parametrize("bad", ["9000000000", "+91 900", "hello", "+0123456789"])
def test_malformed_numbers_are_refused(bad):
    with patch.dict("os.environ", {"VOICE_ALLOWED_NUMBERS": MY_NUMBER}):
        with pytest.raises(bland.VoiceError):
            bland.check_number(bad)


def test_the_webhook_rejects_a_wrong_token(client):
    with patch.dict("os.environ", {"VOICE_WEBHOOK_SECRET": SECRET}):
        response = client.post("/voice/webhook?token=guess", json={})
    assert response.status_code == 401


def test_the_webhook_is_closed_when_no_secret_is_set(client):
    with patch.dict("os.environ", {}, clear=False):
        import os
        os.environ.pop("VOICE_WEBHOOK_SECRET", None)
        assert client.post("/voice/webhook", json={}).status_code == 503


def test_calling_without_a_key_says_so(client):
    import os
    os.environ.pop("BLAND_API_KEY", None)
    with patch.dict("os.environ", {"VOICE_ALLOWED_NUMBERS": MY_NUMBER}):
        response = _post_call(client)
    assert response.status_code == 503
    assert "BLAND_API_KEY" in response.json()["detail"]


def test_a_placed_call_sends_the_script_and_schema(client):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update({"url": url, "payload": json, "headers": headers})

        class R:
            status_code = 200

            @staticmethod
            def json():
                return {"call_id": "call_123"}
        return R()

    env = {"BLAND_API_KEY": "k", "VOICE_ALLOWED_NUMBERS": MY_NUMBER,
           "VOICE_WEBHOOK_URL": "https://api.example/voice/webhook",
           "VOICE_WEBHOOK_SECRET": SECRET}
    with patch.dict("os.environ", env), \
         patch("api.voice.bland.requests.post", side_effect=fake_post):
        body = _post_call(client).json()

    assert body["call_id"] == "call_123"
    assert captured["payload"]["phone_number"] == MY_NUMBER
    assert captured["payload"]["language"] == "hin"
    assert "उम्र" in captured["payload"]["task"]
    assert "age" in captured["payload"]["analysis_schema"]["properties"]
    assert captured["payload"]["webhook"].endswith(f"token={SECRET}")
    # The key goes in the header, never in a URL or a log line.
    assert "k" not in captured["url"]


# -- a replayed call --------------------------------------------------------


def test_a_whole_call_produces_a_verdict_and_a_hindi_message(client):
    heard = {
        "has_bank_or_post_office_account": "हाँ जी, मेरा खाता है",
        "age": 30,
        "consents_to_auto_debit": "हाँ, कटवा दीजिए",
    }
    body = _webhook(client, heard).json()
    assert body["verdict"] == "ELIGIBLE"
    assert body["profile"] == {"has_bank_or_post_office_account": True,
                               "age": 30, "consents_to_auto_debit": True}
    assert "पात्र लगते हैं" in body["message"]
    assert "jansuraksha.gov.in" in body["message"]
    assert body["sms"] == "not_configured"


def test_a_denial_message_carries_the_rule_that_failed(client):
    body = _webhook(client, {"owns_cultivable_land": "हाँ", "land_hectares": 4,
                             "age": 30, "in_other_pension_or_social_security_scheme": "नहीं",
                             "is_institutional_landholder": "नहीं",
                             "holds_or_held_public_office": "नहीं",
                             "is_government_employee": "नहीं",
                             "paid_income_tax_last_year": "नहीं",
                             "is_practising_professional": "नहीं"},
                   scheme="pm-kmy").json()
    assert body["verdict"] == "NOT_ELIGIBLE"
    assert "पात्र नहीं लगते" in body["message"]
    assert "pmkisan.gov.in" in body["message"]


def test_an_answer_the_parser_cannot_read_is_never_guessed(client):
    """8 kHz audio mishears. "maybe" must not become a recorded yes, and a
    verdict must not be invented from it."""
    body = _webhook(client, {"has_bank_or_post_office_account": "पता नहीं",
                             "age": "bees pachees ke beech"}).json()
    assert body["profile"] == {}
    assert sorted(body["unparsed"]) == ["age", "has_bank_or_post_office_account"]
    assert body["verdict"] == "INSUFFICIENT_INFO"
    assert "नहीं मिल सके" in body["message"]


def test_a_no_is_recorded_as_a_no(client):
    body = _webhook(client, {"has_bank_or_post_office_account": "नहीं, खाता नहीं है",
                             "age": 30, "consents_to_auto_debit": "हाँ"}).json()
    assert body["profile"]["has_bank_or_post_office_account"] is False
    assert body["verdict"] == "NOT_ELIGIBLE"


def test_answers_for_attributes_the_scheme_does_not_test_are_ignored(client):
    """The platform returning something unexpected must not write it into a
    profile the rule engine then evaluates."""
    body = _webhook(client, {"age": 30, "secret_admin_flag": "yes",
                             "worker_count": 3}).json()
    assert body["profile"] == {"age": 30}


def test_a_choice_answer_maps_to_the_scheme_value(client):
    body = _webhook(client, {"applicant_type": "हाँ"}, scheme="pmfme").json()
    assert body["profile"]["applicant_type"] == "individual"


def test_a_spoken_no_to_a_choice_records_the_other_option(client):
    body = _webhook(client, {"applicant_type": "नहीं"}, scheme="pmfme").json()
    assert body["profile"]["applicant_type"] == "__other__"


def test_the_message_is_english_when_the_call_was_english(client):
    body = _webhook(client, {"has_bank_or_post_office_account": "yes",
                             "age": 30, "consents_to_auto_debit": "yes"},
                    locale="en").json()
    assert "APPEAR ELIGIBLE" in body["message"]


def test_the_sms_never_claims_a_decision(client):
    """Wording is load-bearing: this is guidance, not a government decision."""
    for locale, expected in (("en", "not a decision"), ("hi", "कोई फ़ैसला")):
        body = _webhook(client, {"has_bank_or_post_office_account": "yes", "age": 30,
                                 "consents_to_auto_debit": "yes"}, locale=locale).json()
        assert expected in body["message"]


def test_the_webhook_refuses_an_unknown_scheme(client):
    payload = {"to": MY_NUMBER, "analysis": {}, "metadata": {"scheme": "../etc"}}
    with patch.dict("os.environ", {"VOICE_WEBHOOK_SECRET": SECRET}):
        assert client.post(f"/voice/webhook?token={SECRET}",
                           json=payload).status_code == 404


def test_sms_is_attempted_when_configured(client):
    sent = {}

    def fake_post(url, auth=None, data=None, timeout=None):
        sent.update(data)

        class R:
            status_code = 201
        return R()

    env = {"TWILIO_ACCOUNT_SID": "sid", "TWILIO_AUTH_TOKEN": "tok",
           "TWILIO_FROM_NUMBER": "+15550001111", "VOICE_WEBHOOK_SECRET": SECRET}
    with patch.dict("os.environ", env), \
         patch("api.voice.sms.requests.post", side_effect=fake_post):
        body = _webhook(client, {"age": 30}).json()
    assert body["sms"] == "sent"
    assert sent["To"] == MY_NUMBER


def test_read_answers_accepts_booleans_from_the_platform():
    profile, unparsed = voice.read_answers(
        "pmsby", {"has_bank_or_post_office_account": True, "age": 19.0,
                  "consents_to_auto_debit": False})
    assert profile == {"has_bank_or_post_office_account": True, "age": 19.0,
                       "consents_to_auto_debit": False}
    assert unparsed == []


# -- sounding human, and recovering from a bad line -------------------------


def test_mishearing_is_recovered_politely_and_never_guessed():
    """The line is often poor. The agent blames the line, asks again, and
    after three tries leaves the answer blank rather than guessing."""
    hindi = script.build_task("pmsby", "hi")
    assert "अंदाज़ा कभी न लगाएँ" in hindi
    assert "लाइन में आवाज़ थोड़ी कट गई" in hindi
    assert "मैं ठीक से सुन नहीं पाया" in hindi
    assert "ख़ाली छोड़ दें" in hindi


def test_numbers_are_read_back_for_confirmation():
    assert "सही सुना मैंने?" in script.build_task("pm-kmy", "hi")
    assert "did I get that" in script.build_task("pm-kmy", "en")


def test_the_agent_stops_someone_reading_out_a_secret_number():
    """People do volunteer OTPs and Aadhaar numbers to anyone official-
    sounding. The agent must stop them, not just avoid asking."""
    hindi = script.build_task("apy", "hi")
    assert "यह नंबर मुझे मत बताइए" in hindi
    english = script.build_task("apy", "en")
    assert "Please don't" in english and "Do not repeat or record it" in english


def test_the_agent_admits_it_is_automated_if_asked():
    assert "स्वचालित सहायक" in script.build_task("pmsby", "hi")
    assert "automated assistant" in script.build_task("pmsby", "en")


def test_scheme_questions_go_to_the_grounded_tool():
    for locale in ("hi", "en"):
        assert "scheme_info" in script.build_task("pmsby", locale)


# -- /voice/ask: questions during the call ----------------------------------


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, system, user, tier):
        self.calls.append(user)
        return self.replies.pop(0)


def _ask(client, question, llm, locale="en", token=SECRET):
    from api.deps import get_llm
    app.dependency_overrides[get_llm] = lambda: llm
    with patch.dict("os.environ", {"VOICE_WEBHOOK_SECRET": SECRET}):
        return client.post(f"/voice/ask?token={token}",
                           json={"question": question, "scheme": "pmsby",
                                 "locale": locale})


def test_a_question_mid_call_gets_a_grounded_answer(client):
    llm = FakeLLM([
        '{"known": true, "answer": "The premium is Rs. 20 a year.", "used": ["pmsby-premium"]}',
        '{"claims_checked": 1, "unsupported": []}',
    ])
    body = _ask(client, "how much do I pay?", llm).json()
    assert body == {"answer": "The premium is Rs. 20 a year.", "grounded": True,
                    "clauses": ["pmsby-premium"]}
    # The model was given the scheme's own clauses to answer from.
    assert "pmsby-premium" in llm.calls[0]


def test_a_question_the_clauses_cannot_answer_is_admitted_not_invented(client):
    llm = FakeLLM(['{"known": false, "answer": "", "used": []}'])
    body = _ask(client, "will I get a free tractor?", llm, locale="hi").json()
    assert body["grounded"] is False
    assert "जानकारी मेरे पास नहीं है" in body["answer"]


def test_an_unsupported_claim_never_reaches_the_caller(client):
    llm = FakeLLM([
        '{"known": true, "answer": "Lots of money.", "used": []}',
    ])
    body = _ask(client, "how much?", llm).json()
    assert body["grounded"] is False


def test_the_ask_tool_needs_the_secret(client):
    """Otherwise it is a free, public LLM endpoint."""
    response = _ask(client, "hi", FakeLLM([]), token="guess")
    assert response.status_code == 401


def test_the_call_carries_the_ask_tool_only_when_it_is_authenticated(client):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(json)

        class R:
            status_code = 200

            @staticmethod
            def json():
                return {"call_id": "c"}
        return R()

    env = {"BLAND_API_KEY": "k", "VOICE_ALLOWED_NUMBERS": MY_NUMBER,
           "VOICE_WEBHOOK_URL": "https://api.example/voice/webhook"}
    import os
    os.environ.pop("VOICE_WEBHOOK_SECRET", None)
    with patch.dict("os.environ", env),          patch("api.voice.bland.requests.post", side_effect=fake_post):
        body = _post_call(client).json()
    assert body["answers_questions"] is False
    assert "tools" not in captured

    with patch.dict("os.environ", {**env, "VOICE_WEBHOOK_SECRET": SECRET}),          patch("api.voice.bland.requests.post", side_effect=fake_post):
        body = _post_call(client).json()
    assert body["answers_questions"] is True
    tool = captured["tools"][0]
    assert tool["name"] == "scheme_info"
    assert tool["url"] == f"https://api.example/voice/ask?token={SECRET}"
    assert tool["body"]["scheme"] == "pmsby"
