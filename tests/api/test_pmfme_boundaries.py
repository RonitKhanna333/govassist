"""Regression coverage for the reviewed PMFME comparison boundaries."""

from __future__ import annotations

from api.rules.engine import decide, load_rules
from parse_scheme import repo_root


QUALIFYING_PROFILE = {
    "applicant_type": "individual",
    "is_existing_micro_food_processing_unit": True,
    "identified_in_slup_or_verified": True,
    "is_unincorporated": True,
    "worker_count": 5,
    "has_enterprise_ownership_right": True,
    "age": 19,
    "passed_class_8": True,
    "family_member_already_received_assistance": False,
    "will_formalize": True,
    "own_contribution_percent": 10,
    "will_take_bank_loan": True,
}


def with_age(age: int) -> dict:
    return {**QUALIFYING_PROFILE, "age": age}


def test_age_17_fails():
    assert decide("pmfme", with_age(17)).verdict.value == "NOT_ELIGIBLE"


def test_age_18_fails_at_the_exclusive_boundary():
    assert decide("pmfme", with_age(18)).verdict.value == "NOT_ELIGIBLE"


def test_age_19_passes_when_every_other_condition_passes():
    assert decide("pmfme", with_age(19)).verdict.value == "ELIGIBLE"


def test_missing_age_is_unknown_not_a_failed_condition():
    profile = {key: value for key, value in QUALIFYING_PROFILE.items() if key != "age"}
    result = decide("pmfme", profile)
    assert result.verdict.value == "INSUFFICIENT_INFO"
    assert "age" in result.missing_attributes


def test_age_failure_returns_the_age_clause_citation():
    result = decide("pmfme", with_age(18))
    age_citations = [
        citation for citation in result.citations
        if citation.clause_id == "individual-age-and-education"
    ]
    assert len(age_citations) == 1
    assert "above 18 years" in age_citations[0].quote
    assert age_citations[0].page == 7
    assert age_citations[0].source_url.endswith("SchemeGuidelines.pdf")


def test_worker_count_10_fails_the_exclusive_upper_bound():
    assert decide("pmfme", {**QUALIFYING_PROFILE, "worker_count": 10}).verdict.value == "NOT_ELIGIBLE"


def test_contribution_of_exactly_10_percent_passes_and_9_fails():
    assert decide("pmfme", {**QUALIFYING_PROFILE, "own_contribution_percent": 10}).verdict.value == "ELIGIBLE"
    assert decide("pmfme", {**QUALIFYING_PROFILE, "own_contribution_percent": 9}).verdict.value == "NOT_ELIGIBLE"


def test_already_assisted_family_fails_the_negated_exclusion():
    assert decide(
        "pmfme", {**QUALIFYING_PROFILE, "family_member_already_received_assistance": True}
    ).verdict.value == "NOT_ELIGIBLE"


def test_pmfme_boundary_operators_match_the_source_language():
    rules = load_rules("pmfme", repo_root())
    expressions = {condition["id"]: condition["expr"] for condition in rules["conditions"]}
    assert expressions["applicant_age_and_education"] == (
        "profile.age > 18 and profile.passed_class_8 == true"
    )
    assert expressions["unincorporated_and_under_ten_workers"] == (
        "profile.is_unincorporated == true and profile.worker_count < 10"
    )
    assert expressions["willing_to_formalize_and_contribute"] == (
        "profile.will_formalize == true and profile.own_contribution_percent >= 10 "
        "and profile.will_take_bank_loan == true"
    )
    assert expressions["one_person_per_family_only"] == (
        "profile.family_member_already_received_assistance == false"
    )
