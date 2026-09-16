"""api/rules/forms.py -- deriving the answer control from the rule itself.

These exist because of two bugs found by using the deployed app, not by
reading code: a question that repeated forever, and an answer whose
polarity was silently inverted.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app
from api.rules.forms import answer_yes_no, derive_fields, unresolved_fields


def _by_attr(fields):
    return {f.attribute: f for f in fields}


# -- deriving fields ---------------------------------------------------------


def test_boolean_comparison_yields_a_boolean_field():
    field = derive_fields("profile.is_unincorporated == true")[0]
    assert field.attribute == "is_unincorporated"
    assert field.kind == "boolean"


def test_string_equality_yields_a_choice():
    field = derive_fields('profile.applicant_type == "individual"')[0]
    assert field.kind == "choice"
    assert field.options == ["individual"]
    assert field.satisfied_by == "individual"


def test_numeric_comparison_yields_a_number_with_its_bound():
    field = derive_fields("profile.age >= 18")[0]
    assert field.kind == "number"
    assert field.comparator == ">="
    assert field.bound == 18


def test_membership_yields_every_option():
    field = derive_fields('profile.category in ["sc", "st", "obc"]')[0]
    assert field.kind == "choice"
    assert field.options == ["sc", "st", "obc"]


def test_compound_condition_yields_one_field_per_attribute():
    fields = _by_attr(derive_fields(
        "profile.is_unincorporated == true and profile.worker_count < 10",
    ))
    assert set(fields) == {"is_unincorporated", "worker_count"}
    assert fields["is_unincorporated"].kind == "boolean"
    assert fields["worker_count"].kind == "number"


def test_already_answered_attributes_drop_out():
    remaining = unresolved_fields(
        "profile.is_unincorporated == true and profile.worker_count < 10",
        {"is_unincorporated": True},
    )
    assert [f.attribute for f in remaining] == ["worker_count"]


# -- yes/no mapping ----------------------------------------------------------


def test_yes_sets_a_boolean_true_and_no_sets_it_false():
    expr = "profile.is_unincorporated == true"
    assert answer_yes_no(expr, {}, True) == {"is_unincorporated": True}
    assert answer_yes_no(expr, {}, False) == {"is_unincorporated": False}


def test_yes_is_not_inverted_by_a_negatively_phrased_rule():
    """The bug this guards is the whole reason this file exists.

    "Has anyone in your family already received this?" tests
    `already_received == false`. Mapping Yes to the value that *satisfies*
    the condition would record "yes they did" as false -- calling an
    ineligible person eligible, silently.
    """
    expr = "profile.family_member_already_received_assistance == false"
    assert answer_yes_no(expr, {}, True) == {
        "family_member_already_received_assistance": True,
    }
    assert answer_yes_no(expr, {}, False) == {
        "family_member_already_received_assistance": False,
    }


def test_yes_picks_the_named_option_for_a_choice():
    expr = 'profile.applicant_type == "individual"'
    assert answer_yes_no(expr, {}, True) == {"applicant_type": "individual"}


def test_no_to_a_choice_records_a_refusal_rather_than_staying_unknown():
    """Otherwise the condition never resolves and the question repeats."""
    expr = 'profile.applicant_type == "individual"'
    assert answer_yes_no(expr, {}, False) == {"applicant_type": "__other__"}


def test_yes_no_refuses_to_guess_a_number():
    """"Yes" cannot mean "9 workers". Returning {} makes the caller ask."""
    assert answer_yes_no("profile.worker_count < 10", {}, True) == {}


# -- end to end: the loop actually terminates ------------------------------


def test_answering_advances_instead_of_repeating_forever():
    client = TestClient(app)
    profile: dict = {}
    asked: list[str] = []

    for _ in range(20):
        response = client.post("/chat", json={"scheme": "pmfme", "profile": profile}).json()
        if response["verdict"] != "INSUFFICIENT_INFO":
            break

        pending = response["pending"]
        asked.append(pending["condition_id"])

        values: dict = {}
        for f in pending["fields"]:
            if f["kind"] == "number":
                bound = f["bound"]
                values[f["attribute"]] = bound - 1 if f["comparator"] == "<" else bound
            elif f["kind"] == "boolean":
                values[f["attribute"]] = True
            elif f["kind"] == "choice":
                values[f["attribute"]] = f["satisfied_by"]

        profile = client.post("/chat", json={
            "scheme": "pmfme", "profile": profile, "answers": values,
        }).json()["profile"]

    # Every question asked was a different one -- no repeats.
    assert len(asked) == len(set(asked)), f"repeated a question: {asked}"
    assert response["verdict"] in {"ELIGIBLE", "NOT_ELIGIBLE"}


def test_yes_no_path_reaches_a_verdict_without_any_llm():
    """No GROQ_API_KEY is set in the test environment -- the point is that
    the deterministic path never needed one."""
    client = TestClient(app)
    profile: dict = {}

    for _ in range(20):
        response = client.post("/chat", json={"scheme": "pmfme", "profile": profile}).json()
        if response["verdict"] != "INSUFFICIENT_INFO":
            break
        pending = response["pending"]
        if any(f["kind"] == "number" for f in pending["fields"]):
            values = {}
            for f in pending["fields"]:
                if f["kind"] == "number":
                    bound = f["bound"]
                    values[f["attribute"]] = bound - 1 if f["comparator"] == "<" else bound
                elif f["kind"] == "boolean":
                    values[f["attribute"]] = True
            profile = client.post("/chat", json={
                "scheme": "pmfme", "profile": profile, "answers": values,
            }).json()["profile"]
        else:
            profile = client.post("/chat", json={
                "scheme": "pmfme", "profile": profile, "answer": "yes",
            }).json()["profile"]

    assert response["verdict"] in {"ELIGIBLE", "NOT_ELIGIBLE"}
    assert response["citations"]
