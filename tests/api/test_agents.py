"""router, nlu, composer, verifier, orchestrate -- all against a FakeLLM.

None of this touches the network or needs GROQ_API_KEY. That's the entire
point of the LLMProvider protocol in api/agents/llm.py: every place that
calls an LLM takes the interface, not the Groq client, so its logic is
testable deterministically.
"""

from __future__ import annotations

from api.agents import composer, nlu, orchestrate, verifier
from api.agents.llm import LLMError, Tier
from api.agents.router import Domain, route
from api.rules.engine import Citation


class FakeLLM:
    """Returns scripted responses in order, one per call. Records every
    call's (system, user, tier) so a test can assert what was asked."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[tuple[str, str, Tier]] = []

    def complete(self, system: str, user: str, tier: Tier) -> str:
        self.calls.append((system, user, tier))
        if not self._responses:
            raise LLMError("FakeLLM ran out of scripted responses")
        return self._responses.pop(0)


class AlwaysFailsLLM:
    def complete(self, system: str, user: str, tier: Tier) -> str:
        raise LLMError("simulated network failure")


CITATIONS = [
    Citation(clause_id="age-rule", quote="Must be 18+.", plain="You must be an adult.",
             source_url="https://example.gov/doc.pdf", page=1),
    Citation(clause_id="excl-rule", quote="Prior claimants excluded.",
             plain="You cannot claim twice.", source_url="https://example.gov/doc.pdf", page=2),
]


# -- router --------------------------------------------------------------


def test_router_sends_scheme_queries_to_scheme_domain():
    result = route("am I eligible for PM-KISAN")
    assert result.domain == Domain.SCHEME
    assert result.supported


def test_router_stubs_itr_queries():
    result = route("which ITR form should I file this year")
    assert result.domain == Domain.ITR
    assert not result.supported
    assert result.message


def test_router_stubs_gst_queries():
    result = route("when is my GSTR due")
    assert result.domain == Domain.GST
    assert not result.supported


# -- nlu -------------------------------------------------------------------


def test_nlu_extracts_only_known_attributes():
    llm = FakeLLM(['{"age": 25, "unknown_attr": true}'])
    result = nlu.extract_attributes(llm, "I am 25 years old", ["age", "worker_count"])
    assert result == {"age": 25}  # unknown_attr silently dropped, not just trusted


def test_nlu_handles_markdown_fenced_json():
    llm = FakeLLM(['```json\n{"age": 30}\n```'])
    result = nlu.extract_attributes(llm, "I'm 30", ["age"])
    assert result == {"age": 30}


def test_nlu_returns_empty_on_unparseable_response():
    llm = FakeLLM(["not json at all"])
    result = nlu.extract_attributes(llm, "I'm 30", ["age"])
    assert result == {}


def test_nlu_degrades_gracefully_when_llm_fails():
    result = nlu.extract_attributes(AlwaysFailsLLM(), "I'm 30", ["age"])
    assert result == {}


def test_nlu_skips_the_call_entirely_on_empty_message():
    llm = FakeLLM([])  # would raise if called
    result = nlu.extract_attributes(llm, "", ["age"])
    assert result == {}
    assert llm.calls == []


# -- composer ----------------------------------------------------------------


def test_composer_drafts_from_citations():
    llm = FakeLLM(["You qualify because you're an adult and haven't claimed before."])
    draft = composer.draft_answer(llm, "ELIGIBLE", CITATIONS)
    assert "adult" in draft
    # the facts, not the quotes, are what reached the model
    assert "You must be an adult." in llm.calls[0][1]
    assert "Must be 18+." not in llm.calls[0][1]


def test_composer_declines_with_no_citations_rather_than_calling_the_llm():
    llm = FakeLLM([])
    draft = composer.draft_answer(llm, "ELIGIBLE", [])
    assert draft == composer.FALLBACK_NO_EVIDENCE
    assert llm.calls == []


def test_composer_falls_back_when_llm_fails():
    draft = composer.draft_answer(AlwaysFailsLLM(), "ELIGIBLE", CITATIONS)
    assert draft == composer.FALLBACK_NO_EVIDENCE


def test_composer_avoid_list_reaches_the_prompt_on_recompose():
    llm = FakeLLM(["a cleaner draft"])
    composer.draft_answer(llm, "ELIGIBLE", CITATIONS, avoid=["you get exactly Rs 50,000"])
    assert "Rs 50,000" in llm.calls[0][1]


# -- verifier ------------------------------------------------------------


def test_verifier_passes_a_fully_supported_draft():
    llm = FakeLLM(['[{"claim": "you are an adult", "status": "SUPPORTED"}]'])
    result = verifier.verify(llm, "You are an adult.", CITATIONS)
    assert result.ok
    assert result.checked
    assert result.unsupported_claims == []


def test_verifier_flags_an_unsupported_claim():
    llm = FakeLLM([
        '[{"claim": "you are an adult", "status": "SUPPORTED"}, '
        '{"claim": "you get Rs 50000", "status": "UNSUPPORTED"}]'
    ])
    result = verifier.verify(llm, "You are an adult and get Rs 50000.", CITATIONS)
    assert not result.ok
    assert result.checked
    assert result.unsupported_claims == ["you get Rs 50000"]


def test_verifier_treats_unparseable_response_as_not_checked_not_ok():
    llm = FakeLLM(["I refuse to answer in JSON"])
    result = verifier.verify(llm, "some draft", CITATIONS)
    assert not result.ok
    assert not result.checked  # critical: "couldn't check" != "checked and fine"


def test_verifier_treats_llm_failure_as_not_checked():
    result = verifier.verify(AlwaysFailsLLM(), "some draft", CITATIONS)
    assert not result.ok
    assert not result.checked


# -- orchestrate: the two loops together ------------------------------------


def test_orchestrate_returns_the_draft_when_verifier_passes_first_try():
    llm = FakeLLM([
        "a good draft",
        '[{"claim": "fine", "status": "SUPPORTED"}]',
    ])
    answer = orchestrate.compose_verified_answer(llm, "ELIGIBLE", CITATIONS)
    assert answer == "a good draft"
    assert len(llm.calls) == 2  # compose, verify -- no recompose needed


def test_orchestrate_recomposes_once_then_succeeds():
    llm = FakeLLM([
        "a draft with an invented number",
        '[{"claim": "invented number", "status": "UNSUPPORTED"}]',
        "a cleaner draft",
        '[{"claim": "fine", "status": "SUPPORTED"}]',
    ])
    answer = orchestrate.compose_verified_answer(llm, "ELIGIBLE", CITATIONS)
    assert answer == "a cleaner draft"
    assert len(llm.calls) == 4  # compose, verify, recompose, verify


def test_orchestrate_falls_back_after_recompose_still_fails():
    llm = FakeLLM([
        "bad draft",
        '[{"claim": "x", "status": "UNSUPPORTED"}]',
        "still bad",
        '[{"claim": "y", "status": "UNSUPPORTED"}]',
    ])
    answer = orchestrate.compose_verified_answer(llm, "ELIGIBLE", CITATIONS)
    assert answer == orchestrate.FALLBACK_UNVERIFIED


def test_orchestrate_falls_back_immediately_when_verifier_cannot_run():
    llm = FakeLLM(["a draft", "not json"])
    answer = orchestrate.compose_verified_answer(llm, "ELIGIBLE", CITATIONS)
    assert answer == orchestrate.FALLBACK_UNVERIFIED
    assert len(llm.calls) == 2  # never blindly recomposes on an unchecked draft


def test_orchestrate_never_calls_the_llm_with_no_citations():
    llm = FakeLLM([])
    answer = orchestrate.compose_verified_answer(llm, "ELIGIBLE", [])
    assert answer == composer.FALLBACK_NO_EVIDENCE
    assert llm.calls == []
