"""data/attributes.json -- the plain-language question bank.

This exists because the app shipped asking people whether their unit was
"identified in the SLUP for an ODOP product or verified by the Resource
Person". The project's whole premise is replacing a jargon-heavy PDF, so
retyping its vocabulary into a chat box is the one failure that defeats the
point.
"""

from __future__ import annotations

import json

import pytest

from api.rules.engine import known_attributes, load_rules
from api.rules.forms import attribute_registry, derive_fields
from parse_scheme import repo_root

# Terms an applicant has no reason to know. Not exhaustive -- a tripwire, so
# wording that drifts back toward the source document fails loudly.
JARGON = [
    "slup", "odop", "resource person", "unincorporated", "enterprise",
    "assessment year", "institutional", "formalisation", "formalization",
    "standard pass", "viii", "subsidy component", "beneficiary",
]


@pytest.fixture(scope="module")
def registry():
    return attribute_registry()


def test_registry_loads():
    assert attribute_registry(), "data/attributes.json did not load"


def test_readme_keys_are_excluded(registry):
    assert not any(k.startswith("_") for k in registry)


def test_every_asked_attribute_has_a_plain_question(registry):
    """An attribute with no entry falls back to the government's wording,
    which is exactly what this file exists to avoid."""
    rules = load_rules("pmfme", repo_root())
    missing = [a for a in known_attributes(rules) if a not in registry]
    assert not missing, f"no plain-language question for: {missing}"


def test_no_question_contains_jargon(registry):
    offenders = []
    for attribute, entry in registry.items():
        ask = (entry.get("ask") or "").lower()
        for term in JARGON:
            if term in ask:
                offenders.append(f"{attribute}: {term!r} in ask")
    assert not offenders, "jargon reached a question: " + "; ".join(offenders)


def test_questions_are_short_enough_to_read_aloud(registry):
    """These get spoken by TTS to people who may not read comfortably."""
    for attribute, entry in registry.items():
        words = len((entry.get("ask") or "").split())
        assert 0 < words <= 20, f"{attribute}: question is {words} words"


def test_every_question_ends_as_a_question(registry):
    for attribute, entry in registry.items():
        assert (entry.get("ask") or "").strip().endswith("?"), attribute


def test_help_text_exists_wherever_a_term_needs_explaining(registry):
    """The two genuinely unavoidable government concepts must be explained
    in the help text even though the question itself avoids naming them."""
    for attribute in ("identified_in_slup_or_verified", "own_contribution_percent"):
        assert registry[attribute].get("help"), f"{attribute} needs help text"


def test_number_questions_carry_a_unit(registry):
    """"How many?" without a unit leaves someone guessing what to type."""
    rules = load_rules("pmfme", repo_root())
    for condition in rules["conditions"]:
        for f in derive_fields(condition["expr"]):
            if f.kind == "number" and f.attribute in registry:
                assert f.unit, f"{f.attribute} is numeric but has no unit"


def test_fields_carry_the_plain_wording_through():
    fields = {f.attribute: f for f in derive_fields(
        "profile.is_unincorporated == true and profile.worker_count < 10",
    )}
    assert fields["worker_count"].ask == "How many people work in your business?"
    assert fields["worker_count"].unit == "people"
    assert fields["is_unincorporated"].help


def test_compound_conditions_split_into_separate_questions():
    """One rule, two things to ask a person. A single Yes/No cannot answer
    "unincorporated AND fewer than 10 workers"."""
    fields = derive_fields(
        "profile.is_unincorporated == true and profile.worker_count < 10",
    )
    assert len(fields) == 2
    assert all(f.ask for f in fields)


def test_negatively_phrased_question_keeps_its_polarity(registry):
    """The dangerous one. "Has anyone in your family already taken money
    from this scheme?" must stay phrased about the ATTRIBUTE -- yes means
    they did, which disqualifies. Rewording it to "is your family free of
    previous claims?" would silently invert every answer.
    """
    ask = registry["family_member_already_received_assistance"]["ask"].lower()
    assert "already" in ask
    # A question phrased around the absence of a claim inverts the meaning.
    for inverted in ("free of", "no one", "nobody", "have not", "haven't"):
        assert inverted not in ask, f"polarity may be inverted: {inverted!r}"


def test_registry_is_valid_json_with_a_readme():
    path = repo_root() / "data" / "attributes.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "_README" in data, "the polarity warning must stay in the file"
    readme = " ".join(data["_README"]).lower()
    assert "polarity" in readme


# -- profile summary: nothing internal reaches the screen ------------------


def test_summary_never_shows_the_other_sentinel():
    """__other__ is how the engine records "not this option". Showing it
    verbatim leaks an internal token into the interface."""
    from api.rules.forms import summarize_profile
    rows = summarize_profile({"applicant_type": "__other__"})
    assert rows[0]["value"] == "No"
    assert "__other__" not in str(rows)


def test_summary_never_shows_a_raw_attribute_name(registry):
    from api.rules.forms import summarize_profile
    rows = summarize_profile({"worker_count": 9, "passed_class_8": True})
    labels = [r["label"] for r in rows]
    assert "worker_count" not in labels
    assert "People working" in labels


def test_summary_renders_booleans_as_yes_and_no():
    from api.rules.forms import summarize_profile
    rows = {r["attribute"]: r["value"] for r in summarize_profile(
        {"passed_class_8": True, "will_take_bank_loan": False},
    )}
    assert rows["passed_class_8"] == "Yes"
    assert rows["will_take_bank_loan"] == "No"


def test_summary_attaches_units_to_numbers():
    from api.rules.forms import summarize_profile
    rows = {r["attribute"]: r["value"] for r in summarize_profile(
        {"worker_count": 9, "age": 25},
    )}
    assert rows["worker_count"] == "9 people"
    assert rows["age"] == "25 years"


def test_every_attribute_has_a_label_for_the_summary(registry):
    missing = [a for a, e in registry.items() if not e.get("label")]
    assert not missing, f"no summary label for: {missing}"
