"""Questions and corrections must never be recorded as answers.

Each of these was a real failure against the committed PMFME corpus, with
every other condition satisfied and one attribute missing:

    "Do I need to be over 18?"           -> recorded age 18
    "I am not 25, I am 17"               -> recorded age 25 -> ELIGIBLE
    "-25"                                -> recorded age 25
    "Is passing class 8 necessary or not?" -> recorded passed_class_8 false

No network: FakeLLM scripts every model call, and an empty FakeLLM raises
if the code under test calls a model it shouldn't.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.agents import conversation
from api.agents.phrases import phrase
from api.agents.router import Domain, route
from api.deps import get_language, get_llm
from api.language.service import LanguageService
from api.main import app
from api.rules.spoken import (
    AMBIGUOUS, NONE, QUESTION, VALUE, read_answer, read_number, read_yes_no,
)
from tests.api.test_agents import FakeLLM
from tests.api.test_chat_endpoint import FULLY_QUALIFYING_PROFILE

NUMBER = {"attribute": "age", "kind": "number"}
BOOLEAN = {"attribute": "passed_class_8", "kind": "boolean"}

WITHOUT_AGE = {k: v for k, v in FULLY_QUALIFYING_PROFILE.items() if k != "age"}
WITHOUT_CLASS_8 = {k: v for k, v in FULLY_QUALIFYING_PROFILE.items()
                   if k != "passed_class_8"}

# A question gets classified, then answered from clauses ("known": false is
# the honest "I don't have that").
QUESTION_TURN = ['{"type": "question", "value": 18}', '{"known": false}']


def _client(llm) -> TestClient:
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[get_language] = lambda: LanguageService(None)
    return TestClient(app)


def _say(llm, profile, message, scheme="pmfme"):
    response = _client(llm).post("/chat", json={
        "scheme": scheme, "profile": profile, "message": message,
    })
    assert response.status_code == 200, response.text
    return response.json()


# -- the parser on its own ---------------------------------------------------


@pytest.mark.parametrize("text,status", [
    ("Do I need to be over 18?", QUESTION),
    ("do i need to be over 18", QUESTION),          # Whisper drops the "?"
    ("ok what if I am 18", QUESTION),
    ("क्या 18 साल से ऊपर होना ज़रूरी है", QUESTION),
    ("I am not 25, I am 17", AMBIGUOUS),
    ("25 or 26", AMBIGUOUS),
    ("nahi, 17", AMBIGUOUS),
    ("I don't know", AMBIGUOUS),
    ("पता नहीं", AMBIGUOUS),
    ("hmm", NONE),
])
def test_numbers_that_are_not_one_clear_answer_are_not_values(text, status):
    assert read_number(text).status == status


@pytest.mark.parametrize("text,value", [
    ("25", 25), ("I am 25 years old.", 25), ("२५ साल", 25), ("੨੫", 25),
    ("௨௫", 25), ("twenty five", 25), ("17", 17), ("-25", -25),
    ("1,000", 1000),
])
def test_a_single_clear_number_is_read_with_its_sign(text, value):
    reading = read_number(text)
    assert (reading.status, reading.value) == (VALUE, value)


def test_separate_number_words_are_not_summed():
    # "one ... twenty" used to become 21.
    assert read_number("one son and twenty workers").status == AMBIGUOUS


@pytest.mark.parametrize("text,status", [
    ("Is passing class 8 necessary or not?", QUESTION),
    ("is it necessary", QUESTION),
    ("I'm not sure", AMBIGUOUS),
    ("I don't know", AMBIGUOUS),
    ("haan, nahi liya", AMBIGUOUS),
])
def test_yes_no_questions_and_hedges_are_not_values(text, status):
    assert read_yes_no(text).status == status


@pytest.mark.parametrize("text,value", [
    ("yes", True), ("no", False), ("हाँ जी", True), ("नहीं", False),
    ("ਹਾਂਜੀ", True), ("ਨਹੀਂ ਲਿਆ", False), ("ஆமாம்", True), ("இல்லை", False),
    ("I have never paid income tax", False),
])
def test_short_multilingual_answers_still_work(text, value):
    reading = read_yes_no(text)
    assert (reading.status, reading.value) == (VALUE, value)


def test_a_single_option_choice_answered_yes_records_the_option():
    field = {"attribute": "applicant_type", "kind": "choice",
             "options": ["individual"], "satisfied_by": "individual"}
    assert read_answer("haan", field).value == "individual"


# -- the classifier contract ---------------------------------------------------


@pytest.mark.parametrize("reply", [
    '{"type": "question", "value": 18}',
    '{"type": "chat", "value": "yes"}',
])
def test_a_classifier_value_is_ignored_unless_the_kind_is_answer(reply):
    intent = conversation.classify(FakeLLM([reply]), "How old are you?", "number", "x")
    assert intent.value is None


@pytest.mark.parametrize("raw", ['"NaN"', "NaN", "Infinity", "true", '"25 years"', '"abc"'])
def test_a_classifier_number_must_be_a_finite_number(raw):
    intent = conversation.classify(
        FakeLLM([f'{{"type": "answer", "value": {raw}}}']), "How old?", "number", "x")
    assert intent.value is None


def test_a_classifier_yes_for_a_number_question_is_not_a_number():
    intent = conversation.classify(
        FakeLLM(['{"type": "answer", "value": "yes"}']), "How old?", "number", "x")
    assert intent.value is None


# -- through /chat: questions never change the profile -------------------------


def test_a_question_about_the_age_rule_does_not_record_an_age():
    body = _say(FakeLLM(list(QUESTION_TURN)), WITHOUT_AGE, "Do I need to be over 18?")
    assert "age" not in body["profile"]
    assert body["verdict"] == "INSUFFICIENT_INFO"
    assert body["pending"]["fields"][0]["attribute"] == "age"


def test_a_question_classified_as_an_answer_still_records_nothing():
    # Even if the model says "answer: 18", the deterministic layer already
    # established this is a question.
    llm = FakeLLM(['{"type": "answer", "value": 18}', '{"known": false}'])
    body = _say(llm, WITHOUT_AGE, "Do I need to be over 18?")
    assert "age" not in body["profile"]


def test_a_correction_with_two_numbers_asks_for_clarification():
    body = _say(FakeLLM([]), WITHOUT_AGE, "I am not 25, I am 17")  # no model call
    assert "age" not in body["profile"]
    assert body["verdict"] == "INSUFFICIENT_INFO"
    assert phrase("clarify", "en") in body["bot_messages"]


def test_a_negative_age_is_not_turned_positive():
    body = _say(FakeLLM([]), WITHOUT_AGE, "-25")
    assert "age" not in body["profile"]
    assert phrase("clarify", "en") in body["bot_messages"]


def test_asking_whether_class_8_is_necessary_records_nothing():
    llm = FakeLLM(['{"type": "question", "value": "no"}', '{"known": false}'])
    body = _say(llm, WITHOUT_CLASS_8, "Is passing class 8 necessary or not?")
    assert "passed_class_8" not in body["profile"]
    assert body["verdict"] == "INSUFFICIENT_INFO"


def test_a_model_answer_with_an_out_of_domain_value_is_not_recorded():
    # Needs an answer the deterministic parser can't read, so the model is
    # consulted. ("pachchees" was used here until Hindi number words were
    # added to the parser; it now reads, correctly, as 25.)
    llm = FakeLLM(['{"type": "answer", "value": -3}', "{}"])
    body = _say(llm, WITHOUT_AGE, "umar kaafi ho gayi hai")
    assert "age" not in body["profile"]


def test_after_a_verdict_a_bare_yes_answers_nothing():
    """Found by exercising the live UI: at age 18 the verdict is already
    NOT_ELIGIBLE, the engine's next unknown condition is the family question
    nobody was shown, and "haan" was recorded as "yes, my family already
    took this help"."""
    decided = {k: v for k, v in FULLY_QUALIFYING_PROFILE.items()
               if k != "family_member_already_received_assistance"}
    decided["age"] = 18
    llm = FakeLLM(['{"type": "chat", "value": null}'])
    body = _say(llm, decided, "haan")
    assert "family_member_already_received_assistance" not in body["profile"]
    assert body["verdict"] == "NOT_ELIGIBLE"


def test_free_text_extraction_never_overwrites_a_given_answer():
    profile = {"age": 30}
    llm = FakeLLM(['{"type": "answer", "value": null}', '{"age": 99}'])
    body = _say(llm, profile, "something unclear")
    assert body["profile"]["age"] == 30


# -- end to end: PMFME age boundary through spoken answers ----------------------


VERIFIED = ["Explanation drawn from the facts.", '{"claims_checked": 1, "unsupported": []}']


@pytest.mark.parametrize("said,age,verdict", [
    ("17", 17, "NOT_ELIGIBLE"),
    ("18", 18, "NOT_ELIGIBLE"),   # "above 18 years" is exclusive
    ("19", 19, "ELIGIBLE"),
    ("मेरी उम्र १९ साल है", 19, "ELIGIBLE"),
])
def test_pmfme_age_answers_decide_on_the_reviewed_boundary(said, age, verdict):
    body = _say(FakeLLM(list(VERIFIED)), WITHOUT_AGE, said)
    assert body["verdict"] == verdict
    assert body["profile"]["age"] == age
    assert "individual-age-and-education" in {c["clause_id"] for c in body["citations"]}


def test_pmfme_with_age_missing_asks_for_it():
    body = _client(FakeLLM([])).post(
        "/chat", json={"scheme": "pmfme", "profile": WITHOUT_AGE}).json()
    assert body["verdict"] == "INSUFFICIENT_INFO"
    assert body["pending"]["fields"][0]["attribute"] == "age"


def test_complete_pmfme_flow_from_empty_profile_by_buttons_and_speech():
    """Every condition answered in turn, the way the UI does it, ending in a
    verified, cited verdict."""
    client = _client(FakeLLM(list(VERIFIED)))
    profile: dict = {}
    body = client.post("/chat", json={"scheme": "pmfme", "profile": profile,
                                      "start": True}).json()
    spoken = {"age": "19 saal", "worker_count": "5",
              "own_contribution_percent": "10"}
    for _ in range(20):
        if body["verdict"] != "INSUFFICIENT_INFO":
            break
        field = body["pending"]["fields"][0]
        attribute = field["attribute"]
        if attribute in spoken:
            request = {"message": spoken[attribute]}
        elif field["kind"] == "choice":
            request = {"answers": {attribute: field["satisfied_by"]}}
        else:
            yes = attribute != "family_member_already_received_assistance"
            request = {"message": "haan" if yes else "nahi"}
        body = client.post("/chat", json={"scheme": "pmfme",
                                          "profile": body["profile"], **request}).json()
    assert body["verdict"] == "ELIGIBLE"
    assert body["profile"]["age"] == 19
    assert body["answer"] == VERIFIED[0]
    assert len(body["citations"]) == 8


# -- routing keeps the scheme's own tax questions in the scheme --------------------


def test_apy_income_tax_answer_stays_in_the_scheme():
    profile = {"is_indian_citizen": True, "has_savings_bank_account": True, "age": 30}
    body = _say(FakeLLM([]), profile, "I have never paid income tax", scheme="apy")
    assert body["domain"] == "scheme"
    assert body["profile"]["ever_paid_income_tax"] is False
    assert body["verdict"] in ("ELIGIBLE", "NOT_ELIGIBLE")


def test_a_pmfme_question_mentioning_gst_is_answered_as_a_scheme_question():
    llm = FakeLLM(['{"type": "question", "value": null}', '{"known": false}'])
    body = _say(llm, {}, "Do I need GST registration to apply for PMFME?")
    assert body["domain"] == "scheme"
    assert body["supported"] is True


@pytest.mark.parametrize("query,domain", [
    ("which ITR form should I file this year", Domain.ITR),
    ("help me file my GST return", Domain.GST),
    ("how do I get a TDS refund", Domain.ITR),
])
def test_real_filing_requests_still_go_to_the_stub(query, domain):
    result = route(query, "pmfme")
    assert result.domain == domain and not result.supported


@pytest.mark.parametrize("query", [
    "I have never paid income tax",
    "I paid income tax last year",
    "Do I need GST registration to apply for PMFME?",
    "is gst needed for this scheme",
])
def test_mentioning_a_tax_is_not_a_filing_request(query):
    assert route(query, "apy").domain == Domain.SCHEME
