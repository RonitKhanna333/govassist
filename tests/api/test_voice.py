"""The phone channel: script generation, guards, and a replayed call.

No network and no telephony account: a call's webhook is just JSON, so the
whole path -- heard answers to verdict to SMS text -- is exercised by
posting the payload a provider would post.
"""

from __future__ import annotations

from unittest.mock import patch
import json as json_codec

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
    payload = {"call_id": "c1", "to": phone, "answers": heard,
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
        assert script.questions(scheme, "hi")


def test_numbers_are_asked_for_as_numbers():
    kinds = {q["attribute"]: q["kind"] for q in script.questions("pm-kmy", "hi")}
    assert kinds["land_hectares"] == "number"
    assert kinds["owns_cultivable_land"] == "boolean"


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
    payload = {"to": MY_NUMBER, "answers": {}, "metadata": {"scheme": "../etc"}}
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
        assert "GovAssist scheme info" in script.build_task("pmsby", locale)


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




# -- the Bland API as documented (docs.bland.ai, Oct 2026) -------------------


class FakeBland:
    """Records every request; answers like Bland's documented endpoints."""

    def __init__(self, tools=None):
        self.requests = []
        self.tools = list(tools or [])

    def __call__(self, method, url, headers=None, json=None, timeout=None, data=None):
        if data is not None:
            json = json_codec.loads(data)
        self.requests.append((method, url, json, headers))
        path = url.split("/v1", 1)[1]
        body = {"status": "success"}
        if method == "GET" and path == "/tools":
            body["tools"] = self.tools
        elif method == "POST" and path == "/tools":
            body["tool_id"] = "TL-new"
            self.tools.append({"tool_id": "TL-new", "tool": json})
        elif method == "POST" and path == "/calls":
            body.update({"call_id": "call_123", "message": "Call successfully queued."})
        elif method == "GET" and path == "/me":
            body.update({"status": "active", "billing": {"current_balance": 1.97},
                         "total_calls": 0})
        elif method == "GET" and path == "/voices":
            body["voices"] = [{"id": "v-hi", "name": "Priya", "tags": ["Hindi"]},
                              {"id": "v-en", "name": "Karen", "tags": ["English"]}]

        class R:
            status_code = 200

            @staticmethod
            def json():
                return body
        return R()

    def calls(self):
        return [r for r in self.requests if r[0] == "POST" and r[1].endswith("/calls")]


CALL_ENV = {"BLAND_API_KEY": "k", "VOICE_ALLOWED_NUMBERS": MY_NUMBER,
            "VOICE_WEBHOOK_URL": "https://api.example/voice/webhook",
            "VOICE_WEBHOOK_SECRET": SECRET}


@pytest.mark.parametrize("status", [401, 403])
@pytest.mark.parametrize("html", [False, True])
def test_provider_access_denial_keeps_reason_but_redacts_secrets(status, html, caplog):
    class Response:
        status_code = status
        headers = {"Content-Type": "text/html" if html else "application/json"}
        text = "<title>403 Forbidden</title><body>sensitive provider body</body>"
        def json(self):
            if html:
                raise ValueError("HTML error with sensitive contents")
            return {"message": "Account flagged; key=secret-key; webhook=https://api.example?token=webhook-secret; phone=+919000000000; email=user@example.com"}
    with patch.dict("os.environ", {"BLAND_API_KEY": " secret-key ", "VOICE_WEBHOOK_SECRET": "webhook-secret"}), \
         patch("api.voice.bland.requests.request", return_value=Response()) as request:
        with pytest.raises(bland.VoiceError) as caught:
            bland._request("GET", "/tools")
    assert caught.value.status_code == status
    assert caught.value.operation == "GET /tools"
    assert "No callback was confirmed" in str(caught.value)
    assert request.call_args.kwargs["headers"]["Authorization"] == "secret-key"
    assert f"GET /tools (HTTP {status})" in caplog.text
    assert "secret-key" not in caplog.text
    assert "webhook-secret" not in caplog.text + str(caught.value)
    assert "+919000000000" not in caplog.text + str(caught.value)
    assert "user@example.com" not in caplog.text + str(caught.value)
    assert "sensitive" not in caplog.text + str(caught.value)
    assert ("title: 403 Forbidden" if html else "Account flagged") in str(caught.value)


def test_denial_extracts_auth_failure_from_json_errors():
    class Response:
        headers = {"Content-Type": "application/json"}
    reason = bland._safe_denial_reason(Response(), {"errors": [{"error": "AUTH_FAILURE", "message": "Unauthorized"}]})
    assert reason == "Unauthorized"


def test_denial_message_is_bounded_and_cannot_inject_log_lines():
    class Response:
        headers = {}
    reason = bland._safe_denial_reason(Response(), {"message": "Denied\nInjected line " + "x" * 1000})
    assert len(reason) == 500
    assert "\n" not in reason


@pytest.mark.parametrize("locale", ["hi", "en"])
def test_interview_wire_encoding_preserves_text_and_uses_utf8_bytes(locale):
    payload = {"task": script.build_interview_task(locale, ""), "language": bland.LANGUAGE[locale]}
    class Response:
        status_code = 200
        def json(self):
            return {"call_id": "test-call"}
    with patch.dict("os.environ", {"BLAND_API_KEY": "test-key"}), \
         patch("api.voice.bland.requests.request", return_value=Response()) as request:
        bland._request("POST", "/calls", json=payload)
    wire = request.call_args.kwargs["data"]
    assert isinstance(wire, bytes)
    assert json_codec.loads(wire) == payload
    assert request.call_args.kwargs["headers"]["Content-Type"] == "application/json"
    if locale == "hi":
        assert "नमस्ते".encode("utf-8") in wire
        assert b"\\u0928" not in wire
        assert len(wire) < len(json_codec.dumps(payload).encode("utf-8")) * 0.6


def test_provider_get_requests_do_not_send_a_json_body():
    class Response:
        status_code = 200
        def json(self):
            return {"status": "active"}
    with patch.dict("os.environ", {"BLAND_API_KEY": "test-key"}), \
         patch("api.voice.bland.requests.request", return_value=Response()) as request:
        bland._request("GET", "/me")
    assert request.call_args.kwargs["data"] is None


def test_hinglish_interview_covers_current_questions_and_preserves_conditional_flow():
    from api.onboarding import service
    from api.voice.hinglish import QUESTIONS
    assert set(QUESTIONS) == set(service.fields("en"))
    task = script.build_interview_task("hi-Latn", "आशा")
    for question in QUESTIONS.values():
        assert question in task
    assert "skip questions" in task
    assert "Never ask for an OTP" in task
    assert "GovAssist eligibility" in task
    assert not any("\u0900" <= char <= "\u097f" for char in task)


def test_hinglish_provider_payload_sets_documented_latin_hindi_language():
    with patch.dict("os.environ", CALL_ENV):
        payload = bland.call_payload(MY_NUMBER, script.build_interview_task("hi-Latn"),
                                     None, "hi-Latn", {}, [])
    assert payload["language"] == "hi-Latn"
    assert "Aapki umar kitni hai?" in payload["task"]


def _place(client, fake, env=CALL_ENV):
    bland._tool_ids.clear()
    with patch.dict("os.environ", env), \
         patch("api.voice.bland.requests.request", side_effect=fake):
        return _post_call(client)


def test_a_call_uses_only_documented_fields(client):
    fake = FakeBland()
    body = _place(client, fake).json()
    assert body["call_id"] == "call_123"
    _, url, payload, headers = fake.calls()[0]
    assert url == "https://api.bland.ai/v1/calls"
    assert payload["language"] == "hi"           # not "hin"
    assert "analysis_schema" not in payload      # not a Bland field
    assert payload["max_duration"] <= 4          # credit is scarce
    assert payload["wait_for_greeting"] is True
    assert payload["phone_number"] == MY_NUMBER
    assert "उम्र" in payload["task"]
    assert payload["webhook"].endswith(f"token={SECRET}")
    assert headers["Authorization"] == "k"       # raw key, no "Bearer"


def test_the_question_tool_is_created_once_and_passed_by_id(client):
    fake = FakeBland()
    _place(client, fake)
    created = [r for r in fake.requests if r[0] == "POST" and r[1].endswith("/tools")]
    assert len(created) == 1
    tool = created[0][2]
    assert tool["url"] == f"https://api.example/voice/ask?token={SECRET}"
    assert tool["method"] == "POST"
    assert tool["body"] == {"question": "{{input.question}}", "scheme": "pmsby", "locale": "hi"}
    assert tool["response"] == {"answer": "$.answer"}
    assert tool["timeout"] >= 15000              # /voice/ask takes ~9 s
    assert fake.calls()[0][2]["tools"] == ["TL-new"]

    # a second call reuses it rather than creating another
    _place(client, fake)
    assert len([r for r in fake.requests if r[0] == "POST" and r[1].endswith("/tools")]) == 1


def test_an_existing_tool_is_found_after_a_cold_start(client):
    url = f"https://api.example/voice/ask?token={SECRET}"
    fake = FakeBland(tools=[{"tool_id": "TL-old",
                             "tool": {"name": "GovAssist scheme info pmsby hi", "url": url}}])
    _place(client, fake)
    assert not [r for r in fake.requests if r[0] == "POST" and r[1].endswith("/tools")]
    assert fake.calls()[0][2]["tools"] == ["TL-old"]


def test_a_tool_pointing_at_an_old_url_is_not_reused(client):
    fake = FakeBland(tools=[{"tool_id": "TL-stale",
                             "tool": {"name": "GovAssist scheme info pmsby hi",
                                      "url": "https://old/voice/ask?token=x"}}])
    _place(client, fake)
    assert fake.calls()[0][2]["tools"] == ["TL-new"]


def test_without_a_secret_the_call_carries_no_tool(client):
    import os
    os.environ.pop("VOICE_WEBHOOK_SECRET", None)
    env = {k: v for k, v in CALL_ENV.items() if k != "VOICE_WEBHOOK_SECRET"}
    fake = FakeBland()
    body = _place(client, fake, env).json()
    assert body["answers_questions"] is False
    assert "tools" not in fake.calls()[0][2]
    assert not [r for r in fake.requests if r[1].endswith("/tools")]


def test_a_refused_number_never_creates_a_tool_or_a_call(client):
    fake = FakeBland()
    env = {**CALL_ENV, "VOICE_ALLOWED_NUMBERS": "+919111111111"}
    assert _place(client, fake, env).status_code == 503
    assert fake.requests == []


def test_bland_errors_are_reported(client):
    def refuse(method, url, headers=None, json=None, timeout=None, data=None):
        class R:
            status_code = 400

            @staticmethod
            def json():
                return {"status": "error", "message": "Insufficient balance"}
        return R()
    bland._tool_ids.clear()
    with patch.dict("os.environ", CALL_ENV), \
         patch("api.voice.bland.requests.request", side_effect=refuse):
        response = _post_call(client)
    assert response.status_code == 503
    assert "Insufficient balance" in response.json()["detail"]


# -- /voice/check: everything short of a call, free -----------------------


def test_check_reports_balance_tools_and_hindi_voices_without_calling(client):
    fake = FakeBland()
    bland._tool_ids.clear()
    with patch.dict("os.environ", CALL_ENV), \
         patch("api.voice.bland.requests.request", side_effect=fake):
        body = client.get(f"/voice/check?token={SECRET}").json()
    assert body["ready"] is True, body["problems"]
    assert body["account"]["balance"] == 1.97
    assert body["hindi_voices"] == [{"id": "v-hi", "name": "Priya", "tags": ["Hindi"]}]
    assert body["tools"]["pmsby"] == "TL-new"
    assert fake.calls() == []                     # no call placed


def test_check_names_what_is_missing(client):
    import os
    for key in ("BLAND_API_KEY", "VOICE_ALLOWED_NUMBERS", "VOICE_WEBHOOK_URL"):
        os.environ.pop(key, None)
    with patch.dict("os.environ", {"VOICE_WEBHOOK_SECRET": SECRET}):
        body = client.get(f"/voice/check?token={SECRET}").json()
    assert body["ready"] is False
    joined = " ".join(body["problems"])
    assert "BLAND_API_KEY" in joined and "VOICE_ALLOWED_NUMBERS" in joined


def test_check_needs_the_secret(client):
    with patch.dict("os.environ", {"VOICE_WEBHOOK_SECRET": SECRET}):
        assert client.get("/voice/check?token=no").status_code == 401


# -- answers found in the transcript ---------------------------------------

from api.voice import extract  # noqa: E402

TRANSCRIPTS = [
    {"user": "assistant", "text": "नमस्ते! क्या आपका अपना बैंक खाता है?"},
    {"user": "user", "text": "हाँ जी, खाता है"},
    {"user": "assistant", "text": "अच्छा, आपकी उम्र कितनी है?"},
    {"user": "user", "text": "पैंतीस साल, 35"},
    {"user": "assistant", "text": "क्या आप बैंक को हर साल पैसा काटने देंगे?"},
    {"user": "user", "text": "पता नहीं जी"},
]


def test_answers_are_found_and_parsed_from_the_transcript(client):
    from api.deps import get_llm
    llm = FakeLLM(['{"has_bank_or_post_office_account": "हाँ जी, खाता है", '
                   '"age": "पैंतीस साल, 35", "consents_to_auto_debit": "पता नहीं जी"}'])
    app.dependency_overrides[get_llm] = lambda: llm
    payload = {"call_id": "c", "to": MY_NUMBER, "status": "completed",
               "answered_by": "human", "transcripts": TRANSCRIPTS,
               "metadata": {"scheme": "pmsby", "locale": "hi"}}
    with patch.dict("os.environ", {"VOICE_WEBHOOK_SECRET": SECRET}):
        body = client.post(f"/voice/webhook?token={SECRET}", json=payload).json()
    assert body["profile"] == {"has_bank_or_post_office_account": True, "age": 35}
    assert body["unparsed"] == ["consents_to_auto_debit"]   # "पता नहीं" -> unknown
    assert body["verdict"] == "INSUFFICIENT_INFO"


def test_a_quote_the_caller_never_said_is_discarded():
    """The model can't put words in the caller's mouth."""
    llm = FakeLLM(['{"has_bank_or_post_office_account": "हाँ", '
                   '"age": "40", "consents_to_auto_debit": "हाँ बिल्कुल"}'])
    found = extract.find_answers(llm, {"has_bank_or_post_office_account": "q",
                                       "age": "q", "consents_to_auto_debit": "q"},
                                 TRANSCRIPTS, None)
    assert "age" not in found                       # "40" was never said
    assert "consents_to_auto_debit" not in found    # nor "हाँ बिल्कुल"


def test_the_agents_words_are_not_the_callers():
    llm = FakeLLM(['{"age": "आपकी उम्र कितनी है"}'])
    assert extract.find_answers(llm, {"age": "q"}, TRANSCRIPTS, None) == {}


def test_an_unanswered_call_texts_nobody(client):
    payload = {"call_id": "c", "to": MY_NUMBER, "status": "no-answer",
               "answered_by": "no-answer", "metadata": {"scheme": "pmsby"}}
    with patch.dict("os.environ", {"VOICE_WEBHOOK_SECRET": SECRET}):
        body = client.post(f"/voice/webhook?token={SECRET}", json=payload).json()
    assert body == {"scheme": "pmsby", "locale": "hi", "verdict": None,
                    "answered": False, "sms": "skipped"}


def test_flat_transcript_fallback():
    flat = "assistant: आपकी उम्र?\nuser: तीस साल\n"
    assert extract.caller_turns(None, flat) == ["तीस साल"]


def test_call_detail_shows_transcript_and_extraction(client):
    from api.deps import get_llm
    llm = FakeLLM(['{"age": "पैंतीस साल, 35"}'])
    app.dependency_overrides[get_llm] = lambda: llm
    call = {"status": "completed", "answered_by": "human", "call_length": 1.2,
            "price": 0.03, "transcripts": TRANSCRIPTS,
            "metadata": {"scheme": "pmsby", "locale": "hi"}}

    def fake(method, url, headers=None, json=None, timeout=None, data=None):
        class R:
            status_code = 200

            @staticmethod
            def json():
                return call
        return R()
    with patch.dict("os.environ", CALL_ENV),          patch("api.voice.bland.requests.request", side_effect=fake):
        body = client.get(f"/voice/calls/2e5f056a-4071-4a89-b072-780e68a565a1?token={SECRET}").json()
    assert body["profile"] == {"age": 35}
    assert body["caller_turns"][0] == "हाँ जी, खाता है"


def test_call_detail_needs_the_secret(client):
    with patch.dict("os.environ", {"VOICE_WEBHOOK_SECRET": SECRET}):
        assert client.get("/voice/calls/abcdefgh12?token=no").status_code == 401


def test_the_agent_never_hangs_up_on_silence():
    """The first real call ended after one unanswered age question, with the
    agent deciding the line was bad. Silence skips a question; it never ends
    the call."""
    hindi = script.build_task("pmsby", "hi")
    assert "कॉल कभी ख़ुद से ख़त्म न करें" in hindi
    assert "आप मुझे सुन पा रहे हैं?" in hindi
    english = script.build_task("pmsby", "en")
    assert "Never end the call yourself because of silence" in english
