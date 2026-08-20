"""POST /chat, end to end through FastAPI's TestClient -- against the real,
committed pmfme corpus, with a scripted FakeLLM standing in for Groq.

No network call anywhere in this file. That's the point of api/deps.py's
`get_llm` being an overridable dependency.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.deps import get_llm
from api.main import app
from tests.api.test_agents import FakeLLM

FULLY_QUALIFYING_PROFILE = {
    "applicant_type": "individual",
    "is_existing_micro_food_processing_unit": True,
    "identified_in_slup_or_verified": True,
    "is_unincorporated": True,
    "worker_count": 5,
    "has_enterprise_ownership_right": True,
    "age": 25,
    "passed_class_8": True,
    "family_member_already_received_assistance": False,
    "will_formalize": True,
    "own_contribution_percent": 10,
    "will_take_bank_loan": True,
}


def _client(llm) -> TestClient:
    app.dependency_overrides[get_llm] = lambda: llm
    return TestClient(app)


def test_health():
    client = _client(FakeLLM([]))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_insufficient_info_asks_a_real_question_no_llm_needed():
    client = _client(FakeLLM([]))  # would raise if the LLM were called at all
    response = client.post("/chat", json={"scheme": "pmfme", "profile": {}})
    body = response.json()

    assert response.status_code == 200
    assert body["verdict"] == "INSUFFICIENT_INFO"
    assert body["next_question"]
    assert body["citations"] == []
    assert body["answer"] is None


def test_eligible_profile_produces_a_verified_answer_with_real_citations():
    llm = FakeLLM([
        "You qualify because you meet every requirement for individual units.",
        '[{"claim": "you qualify", "status": "SUPPORTED"}]',
    ])
    client = _client(llm)
    response = client.post("/chat", json={
        "scheme": "pmfme", "profile": FULLY_QUALIFYING_PROFILE,
    })
    body = response.json()

    assert body["verdict"] == "ELIGIBLE"
    assert body["answer"] == "You qualify because you meet every requirement for individual units."
    assert len(body["citations"]) == 8
    for c in body["citations"]:
        assert c["source_url"] == "https://pmfme.mofpi.gov.in/newsletters/docs/SchemeGuidelines.pdf"


def test_not_eligible_still_cites_the_deciding_clause():
    llm = FakeLLM([
        "You don't qualify because you're under 18.",
        '[{"claim": "under 18", "status": "SUPPORTED"}]',
    ])
    client = _client(llm)
    underage = {**FULLY_QUALIFYING_PROFILE, "age": 16}
    response = client.post("/chat", json={"scheme": "pmfme", "profile": underage})
    body = response.json()

    assert body["verdict"] == "NOT_ELIGIBLE"
    assert "individual-age-and-education" in {c["clause_id"] for c in body["citations"]}


def test_unverified_answer_falls_back_honestly_rather_than_shipping_a_guess():
    llm = FakeLLM([
        "a draft with something invented",
        '[{"claim": "invented", "status": "UNSUPPORTED"}]',
        "still bad",
        '[{"claim": "still invented", "status": "UNSUPPORTED"}]',
    ])
    client = _client(llm)
    response = client.post("/chat", json={
        "scheme": "pmfme", "profile": FULLY_QUALIFYING_PROFILE,
    })
    body = response.json()

    assert body["verdict"] == "ELIGIBLE"  # the rule engine still decided correctly
    from api.agents.orchestrate import FALLBACK_UNVERIFIED
    assert body["answer"] == FALLBACK_UNVERIFIED  # but the explanation was withheld


def test_message_extracts_attributes_via_nlu_and_merges_into_profile():
    llm = FakeLLM(['{"age": 25}'])  # only the NLU call -- still INSUFFICIENT_INFO after
    client = _client(llm)
    response = client.post("/chat", json={
        "scheme": "pmfme", "profile": {}, "message": "I am 25 years old",
    })
    body = response.json()

    assert body["profile"]["age"] == 25
    assert body["verdict"] == "INSUFFICIENT_INFO"  # still missing everything else


def test_itr_query_is_stubbed_not_routed_to_the_scheme_engine():
    client = _client(FakeLLM([]))
    response = client.post("/chat", json={
        "scheme": "pmfme", "profile": {}, "message": "which ITR form should I file",
    })
    body = response.json()

    assert body["supported"] is False
    assert body["domain"] == "itr"
    assert body["verdict"] is None


def test_unknown_scheme_is_a_404_not_a_silent_empty_result():
    client = _client(FakeLLM([]))
    response = client.post("/chat", json={"scheme": "does-not-exist", "profile": {}})
    assert response.status_code == 404


def test_missing_scheme_field_is_a_422():
    client = _client(FakeLLM([]))
    response = client.post("/chat", json={"profile": {}})
    assert response.status_code == 422
