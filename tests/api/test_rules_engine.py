"""api/rules/engine.py -- plumbing tests. Eligibility LOGIC is grammar.py's
job and is covered by tests/test_grammar.py; these tests exist to catch
mistakes in loading, citation resolution, and the CLI, not in evaluation
itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.rules.engine import decide


def _write_scheme(root: Path, scheme: str, conditions: list[dict], decision: str,
                   clauses: list[dict]) -> None:
    build_dir = root / "data" / "schemes" / scheme / "build"
    build_dir.mkdir(parents=True)
    (build_dir / "rules.v1.json").write_text(json.dumps({
        "scheme": scheme, "name_en": scheme, "tier": 1, "version": 1,
        "effective_from": None, "effective_to": None, "authority": "Test Ministry",
        "decision": decision, "conditions": conditions, "sources": [],
    }), encoding="utf-8")
    (build_dir / "clauses.jsonl").write_text(
        "".join(json.dumps(c) + "\n" for c in clauses), encoding="utf-8",
    )


@pytest.fixture
def synthetic_scheme(tmp_path: Path) -> Path:
    _write_scheme(
        tmp_path, "testscheme",
        conditions=[
            {"id": "is_adult", "expr": "profile.age >= 18",
             "clause": "age-rule", "asks": "How old are you?"},
            {"id": "not_excluded", "expr": "profile.already_claimed == false",
             "clause": "exclusion-rule", "asks": "Have you already claimed this?"},
        ],
        decision="ALL(conditions)",
        clauses=[
            {"id": "age-rule", "quote": "Must be 18 or older.",
             "plain": "You must be an adult.", "source_url": "https://example.gov/doc.pdf",
             "page": 1},
            {"id": "exclusion-rule", "quote": "Prior claimants are excluded.",
             "plain": "You cannot claim twice.", "source_url": "https://example.gov/doc.pdf",
             "page": 2},
        ],
    )
    return tmp_path


def test_insufficient_info_when_profile_empty(synthetic_scheme):
    result = decide("testscheme", {}, root=synthetic_scheme)
    assert result.verdict.value == "INSUFFICIENT_INFO"
    assert set(result.missing_attributes) == {"age", "already_claimed"}
    assert result.next_question in ("How old are you?", "Have you already claimed this?")
    assert result.citations == []  # nothing decisive yet -- nothing to cite


def test_eligible_cites_every_decisive_clause(synthetic_scheme):
    result = decide("testscheme", {"age": 30, "already_claimed": False}, root=synthetic_scheme)
    assert result.verdict.value == "ELIGIBLE"
    assert {c.clause_id for c in result.citations} == {"age-rule", "exclusion-rule"}
    for c in result.citations:
        assert c.source_url == "https://example.gov/doc.pdf"


def test_not_eligible_still_cites_the_deciding_clause(synthetic_scheme):
    result = decide("testscheme", {"age": 15, "already_claimed": False}, root=synthetic_scheme)
    assert result.verdict.value == "NOT_ELIGIBLE"
    cited = {c.clause_id for c in result.citations}
    assert "age-rule" in cited  # the clause that actually failed must be cited


def test_partial_profile_asks_for_what_is_missing_not_all_of_it(synthetic_scheme):
    result = decide("testscheme", {"age": 30}, root=synthetic_scheme)
    assert result.verdict.value == "INSUFFICIENT_INFO"
    assert result.missing_attributes == ["already_claimed"]
    assert result.next_question == "Have you already claimed this?"


def test_missing_build_output_raises_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="run 'python data/scripts/build.py"):
        decide("nonexistent-scheme", {}, root=tmp_path)


# -- Integration: against the real, committed pmfme corpus --------------


def test_real_pmfme_empty_profile_asks_first_question():
    result = decide("pmfme", {})
    assert result.verdict.value == "INSUFFICIENT_INFO"
    assert result.next_question
    assert result.citations == []


def test_real_pmfme_fully_qualifying_individual_is_eligible():
    profile = {
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
    result = decide("pmfme", profile)
    assert result.verdict.value == "ELIGIBLE"
    assert len(result.citations) == 8
    # every citation must trace to the real committed source
    for c in result.citations:
        assert c.source_url == "https://pmfme.mofpi.gov.in/newsletters/docs/SchemeGuidelines.pdf"
        assert c.quote  # never an empty citation


def test_real_pmfme_underage_is_not_eligible_and_cites_the_age_clause():
    profile = {
        "applicant_type": "individual",
        "is_existing_micro_food_processing_unit": True,
        "identified_in_slup_or_verified": True,
        "is_unincorporated": True,
        "worker_count": 5,
        "has_enterprise_ownership_right": True,
        "age": 16,
        "passed_class_8": True,
        "family_member_already_received_assistance": False,
        "will_formalize": True,
        "own_contribution_percent": 10,
        "will_take_bank_loan": True,
    }
    result = decide("pmfme", profile)
    assert result.verdict.value == "NOT_ELIGIBLE"
    assert "individual-age-and-education" in {c.clause_id for c in result.citations}
