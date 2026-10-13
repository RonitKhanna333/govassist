"""A drafted answer must not reach a person through a malformed verifier
response. Each malformed shape below used to return ok=True, checked=True.
"""

from __future__ import annotations

import pytest

from api.agents import conversation, orchestrate, verifier
from tests.api.test_agents import CITATIONS, FakeLLM

DRAFT = "You qualify because you are an adult."

MALFORMED = [
    "[]",
    "{}",
    '{"claims_checked": 0}',
    '{"claims_checked": 0, "unsupported": []}',
    '{"claims_checked": null, "unsupported": []}',
    '{"claims_checked": true, "unsupported": []}',
    '{"claims_checked": "3", "unsupported": []}',
    '{"claims_checked": -1, "unsupported": []}',
    '{"claims_checked": 2}',
    '{"claims_checked": 2, "unsupported": null}',
    '{"claims_checked": 2, "unsupported": "none"}',
    '{"claims_checked": 2, "unsupported": [3]}',
    '{"claims_checked": 1, "unsupported": ["a", "b"]}',
    '{"unsupported": []}',
    '[{"status": "UNKNOWN"}]',
    '[{"claim": "x", "status": "MAYBE"}]',
    '[{"claim": "x"}]',
    '[{"status": "SUPPORTED"}]',
    '["SUPPORTED"]',
    '[{"claim": "x", "status": "SUPPORTED"}, {"status": "UNKNOWN"}]',
    "SUPPORTED",
    "null",
]


@pytest.mark.parametrize("raw", MALFORMED)
def test_malformed_results_are_not_checked(raw):
    result = verifier.verify(FakeLLM([raw]), DRAFT, CITATIONS, "ELIGIBLE")
    assert result.checked is False
    assert result.ok is False


@pytest.mark.parametrize("raw", MALFORMED)
def test_a_verdict_explanation_cannot_escape_through_a_malformed_result(raw):
    answer = orchestrate.compose_verified_answer(
        FakeLLM([DRAFT, raw]), "ELIGIBLE", CITATIONS)
    assert answer == orchestrate.FALLBACK_UNVERIFIED


@pytest.mark.parametrize("raw", MALFORMED)
def test_a_question_reply_cannot_escape_through_a_malformed_result(raw):
    llm = FakeLLM([
        '{"known": true, "answer": "Adults can apply.", "used": ["age-rule"]}', raw,
    ])
    reply = conversation.answer_question(llm, "Who can apply?", CITATIONS)
    assert reply.text is None


@pytest.mark.parametrize("raw", [
    '{"claims_checked": 2, "unsupported": []}',
    '[{"claim": "adult", "status": "SUPPORTED"}]',
])
def test_well_formed_supported_results_still_pass(raw):
    result = verifier.verify(FakeLLM([raw]), DRAFT, CITATIONS, "ELIGIBLE")
    assert (result.ok, result.checked) == (True, True)
    assert orchestrate.compose_verified_answer(
        FakeLLM([DRAFT, raw]), "ELIGIBLE", CITATIONS) == DRAFT


@pytest.mark.parametrize("raw", [
    '{"claims_checked": 2, "unsupported": ["you are an adult"]}',
    '[{"claim": "you are an adult", "status": "UNSUPPORTED"}]',
])
def test_well_formed_unsupported_results_trigger_one_recompose(raw):
    result = verifier.verify(FakeLLM([raw]), DRAFT, CITATIONS, "ELIGIBLE")
    assert result.checked and not result.ok
    assert result.unsupported_claims == ["you are an adult"]

    llm = FakeLLM([DRAFT, raw, "Better draft.", '{"claims_checked": 1, "unsupported": []}'])
    assert orchestrate.compose_verified_answer(llm, "ELIGIBLE", CITATIONS) == "Better draft."
    assert "you are an adult" in llm.calls[2][1]  # told what to drop


def test_an_empty_draft_may_report_zero_claims():
    result = verifier.verify(FakeLLM(['{"claims_checked": 0, "unsupported": []}']),
                             "", CITATIONS, "ELIGIBLE")
    assert result.checked and result.ok
