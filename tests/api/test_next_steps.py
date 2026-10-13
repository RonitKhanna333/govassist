"""'What should I do next?' -- every step must be a committed, official clause.

The checklist's promise is that nothing in it is invented: each step is a
clause from the span-validated corpus, shown with its verbatim quote and
official source, and anything the corpus doesn't cover is reported as a gap.
These tests hold data/next_steps.json and the builder to that.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from api.deps import get_language, get_llm
from api.language.service import LanguageService
from api.main import app
from api.rules import next_steps
from api.rules.engine import decide, load_clauses, load_rules
from parse_scheme import repo_root
from tests.api.test_agents import FakeLLM
from tests.api.test_chat_endpoint import FULLY_QUALIFYING_PROFILE

ROOT = repo_root()
MAPPED = sorted(next_steps.checklist_map())
VERIFIED = ["Because of the facts.", '{"claims_checked": 1, "unsupported": []}']

ELIGIBLE_PROFILES = {
    "pmfme": FULLY_QUALIFYING_PROFILE,
    "apy": {"is_indian_citizen": True, "has_savings_bank_account": True, "age": 30,
            "ever_paid_income_tax": False},
    "pm-kmy": {"owns_cultivable_land": True, "land_hectares": 1, "age": 30,
               "in_other_pension_or_social_security_scheme": False,
               "is_institutional_landholder": False, "holds_or_held_public_office": False,
               "is_government_employee": False, "paid_income_tax_last_year": False,
               "is_practising_professional": False},
    "pmjjby": {"has_bank_or_post_office_account": True, "age": 30,
               "consents_to_auto_debit": True},
    "pmsby": {"has_bank_or_post_office_account": True, "age": 30,
              "consents_to_auto_debit": True},
}


def _client(llm=None, language=None) -> TestClient:
    app.dependency_overrides[get_llm] = lambda: llm or FakeLLM(list(VERIFIED))
    app.dependency_overrides[get_language] = lambda: language or LanguageService(None)
    return TestClient(app)


# -- the mapping can only point at real, correctly typed clauses ----------------------


def test_every_served_scheme_has_a_checklist_entry():
    served = {s["id"] for s in _client().get("/schemes").json()["schemes"]}
    assert served == set(MAPPED)


@pytest.mark.parametrize("slug", MAPPED)
def test_every_mapped_id_is_a_committed_clause_of_the_right_type(slug):
    clauses = load_clauses(slug, ROOT)
    mapping = next_steps.checklist_map()[slug]
    assert set(mapping) == set(next_steps.SECTIONS)
    for section, ids in mapping.items():
        for clause_id in ids:
            assert clause_id in clauses, f"{slug}/{section}: no clause {clause_id!r}"
            assert clauses[clause_id]["type"] in next_steps.SECTION_TYPES[section], (
                f"{slug}/{section}: {clause_id} is a {clauses[clause_id]['type']}")


def test_the_mapping_file_carries_no_text_of_its_own():
    """Ids only -- any prose here would be an unsourced fact."""
    data = json.loads((ROOT / "data" / "next_steps.json").read_text(encoding="utf-8"))
    for slug, sections in data.items():
        if slug.startswith("_"):
            continue
        for ids in sections.values():
            assert all(isinstance(i, str) and " " not in i for i in ids)


# -- what a person sees ---------------------------------------------------------------


@pytest.mark.parametrize("slug", MAPPED)
def test_every_step_is_shown_with_its_verbatim_official_quote(slug):
    result = decide(slug, ELIGIBLE_PROFILES[slug])
    assert result.verdict.value == "ELIGIBLE"
    checklist = next_steps.build(slug, result, ROOT, reviewed=False)
    clauses = load_clauses(slug, ROOT)
    official = {s["url"] for s in load_rules(slug, ROOT)["sources"]}

    steps = [i for s in checklist["sections"] for i in s["items"]]
    assert steps, f"{slug}: an eligible person should get at least one step"
    for step in steps:
        row = clauses[step["clause_id"]]
        assert step["quote"] == row["quote"]
        assert step["plain"] == row["plain"]
        assert step["source_url"] in official
    assert checklist["sources"] and checklist["authority"]


def test_pmfme_lists_its_documents_and_admits_where_to_apply_is_not_covered():
    checklist = next_steps.build("pmfme", decide("pmfme", FULLY_QUALIFYING_PROFILE),
                                 ROOT, reviewed=False)
    sections = {s["key"]: [i["clause_id"] for i in s["items"]] for s in checklist["sections"]}
    assert sections["documents"] == ["loan-documents-required"]
    assert "apply" not in sections
    assert checklist["gaps"] == ["apply"]
    assert checklist["authority"] == "Ministry of Food Processing Industries"


def test_apy_reports_both_gaps_because_its_source_says_neither():
    checklist = next_steps.build("apy", decide("apy", ELIGIBLE_PROFILES["apy"]),
                                 ROOT, reviewed=False)
    assert checklist["gaps"] == ["documents", "apply"]


def test_an_unreviewed_scheme_always_asks_for_confirmation():
    checklist = next_steps.build("pmfme", decide("pmfme", FULLY_QUALIFYING_PROFILE),
                                 ROOT, reviewed=False)
    assert checklist["confirm"][0] == {"kind": "review_pending"}
    reviewed = next_steps.build("pmfme", decide("pmfme", FULLY_QUALIFYING_PROFILE),
                                ROOT, reviewed=True)
    assert {"kind": "review_pending"} not in reviewed["confirm"]


def test_not_eligible_gets_no_application_steps_only_what_to_check():
    result = decide("pmfme", {**FULLY_QUALIFYING_PROFILE, "age": 17})
    checklist = next_steps.build("pmfme", result, ROOT, reviewed=False)
    assert checklist["status"] == "not_eligible"
    assert checklist["sections"] == [] and checklist["gaps"] == []
    failed = [c for c in checklist["confirm"] if c["kind"] == "failed"]
    assert [c["clause_id"] for c in failed] == ["individual-age-and-education"]
    assert "above 18 years" in failed[0]["quote"]


def test_uncertain_cited_clauses_are_flagged_for_confirmation(monkeypatch):
    real = load_clauses("pmfme", ROOT)
    flagged = {k: {**v, "uncertain": k == "individual-existing-unit"} for k, v in real.items()}
    monkeypatch.setattr(next_steps, "load_clauses", lambda *a: flagged)
    checklist = next_steps.build("pmfme", decide("pmfme", FULLY_QUALIFYING_PROFILE),
                                 ROOT, reviewed=True)
    assert [c["clause_id"] for c in checklist["confirm"]] == ["individual-existing-unit"]


def test_a_mis_filed_id_is_never_shown(monkeypatch):
    """Even if the mapping is wrong, an exclusion never appears as a step."""
    monkeypatch.setattr(next_steps, "checklist_map", lambda: {
        "pmfme": {"documents": ["individual-one-person-per-family"], "apply": [],
                  "benefits": [], "after": [], "good_to_know": []}})
    checklist = next_steps.build("pmfme", decide("pmfme", FULLY_QUALIFYING_PROFILE),
                                 ROOT, reviewed=True)
    assert checklist["sections"] == []
    assert checklist["gaps"] == ["documents", "apply"]


def test_no_checklist_while_questions_remain():
    assert next_steps.build("pmfme", decide("pmfme", {}), ROOT, reviewed=True) is None


# -- through /chat ------------------------------------------------------------------------


def test_chat_returns_the_checklist_with_the_verdict_and_needs_no_model_for_it():
    body = _client().post("/chat", json={
        "scheme": "pmfme", "profile": FULLY_QUALIFYING_PROFILE}).json()
    assert body["verdict"] == "ELIGIBLE"
    keys = [s["key"] for s in body["next_steps"]["sections"]]
    assert keys == ["benefits", "documents", "after", "good_to_know"]


def test_chat_has_no_checklist_mid_conversation():
    body = _client(FakeLLM([])).post("/chat", json={"scheme": "pmfme", "profile": {}}).json()
    assert body["next_steps"] is None


class TaggingTranslator(LanguageService):
    """Stands in for a translation provider, to show what gets translated."""

    def __init__(self):
        super().__init__(None)

    def translate(self, text, target, source="en"):
        from api.language.service import Rung, TranslationResult
        return TranslationResult(text=f"[{target}] {text}", locale=target,
                                 rung=Rung.PROVIDER)


def test_glosses_are_localized_but_quotes_stay_verbatim():
    body = _client(language=TaggingTranslator()).post("/chat", json={
        "scheme": "pmfme", "profile": FULLY_QUALIFYING_PROFILE, "locale": "hi"}).json()
    step = body["next_steps"]["sections"][1]["items"][0]
    row = load_clauses("pmfme", ROOT)[step["clause_id"]]
    assert step["plain"] == f"[hi] {row['plain']}"
    assert step["quote"] == row["quote"]
