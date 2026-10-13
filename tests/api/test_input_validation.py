"""Malformed input is a 422 (or a clarification), never a crash or a verdict.

Before: `message: 42` and `profile: 42` were HTTP 500s, `worker_count: -5`
passed `< 10` and returned ELIGIBLE, and `passed_class_8: "true"` returned
NOT_ELIGIBLE. Legitimate ineligible answers must still produce their
legitimate NOT_ELIGIBLE -- input domains are not eligibility thresholds.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.agents.llm import Tier
from api.deps import get_language, get_llm
from api.language.service import LanguageService
from api.main import app
from api.rules.engine import load_rules
from api.rules.values import check_value, check_values, specs_for
from parse_scheme import repo_root
from tests.api.test_agents import FakeLLM
from tests.api.test_chat_endpoint import FULLY_QUALIFYING_PROFILE as QUALIFYING

VERIFIED = ["Because of the facts.", '{"claims_checked": 1, "unsupported": []}']


def _client(llm=None) -> TestClient:
    app.dependency_overrides[get_llm] = lambda: llm or FakeLLM([])
    app.dependency_overrides[get_language] = lambda: LanguageService(None)
    return TestClient(app, raise_server_exceptions=False)


def _post(body, llm=None):
    return _client(llm).post("/chat", json={"scheme": "pmfme", **body})


# -- request shape ----------------------------------------------------------------


@pytest.mark.parametrize("body", [
    {"message": 42},
    {"message": ["yes"]},
    {"profile": 42},
    {"profile": "age=25"},
    {"profile": [1, 2]},
    {"answers": 7},
    {"start": "yes"},
    {"answer": "maybe"},
    {"locale": 5},
    {"scheme": 42},
    {"scheme": None},
    {"message": "x" * 1001},
    {"profile": {f"k{i}": True for i in range(65)}},
])
def test_wrong_request_types_are_422_not_500(body):
    assert _post(body).status_code == 422


def test_null_optional_fields_mean_absent():
    response = _post({"profile": None, "message": None, "answers": None,
                      "locale": None})
    assert response.status_code == 200
    assert response.json()["verdict"] == "INSUFFICIENT_INFO"


def test_a_null_attribute_means_not_answered_yet():
    response = _post({"profile": {**QUALIFYING, "age": None}})
    assert response.status_code == 200
    assert response.json()["pending"]["fields"][0]["attribute"] == "age"


# -- attribute values ------------------------------------------------------------------


@pytest.mark.parametrize("attribute,value", [
    ("worker_count", -5),
    ("worker_count", 2.5),
    ("worker_count", True),          # a boolean is not a count
    ("worker_count", "5"),
    ("age", -1),
    ("age", 25.5),
    ("age", False),
    ("own_contribution_percent", 150),
    ("own_contribution_percent", -10),
    ("passed_class_8", "true"),
    ("passed_class_8", 1),           # a number is not a boolean
    ("passed_class_8", 0),
    ("applicant_type", "company"),
    ("applicant_type", True),
])
@pytest.mark.parametrize("where", ["profile", "answers"])
def test_malformed_values_are_rejected_with_the_attribute_named(attribute, value, where):
    base = {k: v for k, v in QUALIFYING.items() if k != attribute}
    body = {"profile": base, "answers": {attribute: value}} if where == "answers" \
        else {"profile": {**base, attribute: value}}
    response = _post(body, FakeLLM(list(VERIFIED)))
    assert response.status_code == 422
    assert attribute in response.json()["detail"]


def test_nonfinite_values_from_json_are_rejected():
    # Python's json accepts NaN/Infinity literals; the API must not.
    response = _client().post(
        "/chat", content='{"scheme": "pmfme", "profile": {"age": NaN}}',
        headers={"Content-Type": "application/json"})
    assert response.status_code == 422


@pytest.mark.parametrize("attribute,value", [
    ("worker_count", 12), ("age", 16), ("age", 18), ("own_contribution_percent", 5),
    ("passed_class_8", False), ("applicant_type", "__other__"),
])
def test_legitimate_ineligible_answers_still_decide_not_eligible(attribute, value):
    response = _post({"profile": {**QUALIFYING, attribute: value}},
                     FakeLLM(list(VERIFIED)))
    assert response.status_code == 200
    assert response.json()["verdict"] == "NOT_ELIGIBLE"


def test_whole_numbers_sent_as_floats_are_accepted():
    response = _post({"profile": {**QUALIFYING, "worker_count": 5.0}},
                     FakeLLM(list(VERIFIED)))
    assert response.status_code == 200
    assert response.json()["profile"]["worker_count"] == 5


def test_unknown_attributes_are_dropped_not_echoed():
    response = _post({"profile": {"favourite_colour": "blue"}})
    assert response.status_code == 200
    assert "favourite_colour" not in response.json()["profile"]


# -- the same path covers model output ------------------------------------------------------


class _NluReturns:
    """Intent says 'answer, but no value'; extraction then returns `extracted`."""

    def __init__(self, extracted: str):
        self._replies = ['{"type": "answer", "value": null}', extracted]

    def complete(self, system: str, user: str, tier: Tier) -> str:
        return self._replies.pop(0)


@pytest.mark.parametrize("extracted", [
    '{"worker_count": -5}', '{"worker_count": "5"}', '{"passed_class_8": "true"}',
    '{"age": NaN}', '{"age": Infinity}', '{"worker_count": true}',
])
def test_nlu_extraction_values_get_the_same_checks(extracted):
    body = _post({"profile": {}, "message": "something it cannot place"},
                 _NluReturns(extracted)).json()
    assert body["profile"] == {}


def test_valid_nlu_extraction_is_still_used():
    body = _post({"profile": {}, "message": "I have five workers"},
                 _NluReturns('{"worker_count": 5}')).json()
    assert body["profile"] == {"worker_count": 5}


# -- the specification comes only from committed data ------------------------------------------


@pytest.mark.parametrize("slug", ["pmfme", "apy", "pmsby", "pmjjby", "pm-kmy"])
def test_every_attribute_a_scheme_reads_has_a_spec(slug):
    rules = load_rules(slug, repo_root())
    specs = specs_for(rules)
    read = {a for c in rules["conditions"] for a in c["reads"]}
    assert read == set(specs)


def test_domains_are_not_thresholds():
    """The engine, not validation, says 16 is too young."""
    specs = specs_for(load_rules("pmfme", repo_root()))
    assert check_value(specs["age"], 16) == (16, None)
    assert check_value(specs["worker_count"], 50) == (50, None)
    assert check_values(specs, {"age": 0}).values == {"age": 0}


def test_number_fields_tell_the_ui_their_domain():
    body = _post({"profile": {k: v for k, v in QUALIFYING.items() if k != "worker_count"}}).json()
    field = body["pending"]["fields"][0]
    assert field["attribute"] == "worker_count"
    assert (field["integer"], field["minimum"]) == (True, 0)
