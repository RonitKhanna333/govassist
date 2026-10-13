"""A review counts only if a person approved exactly what is committed now.

All state written here goes to a temporary copy of the demo fixture. The
real data/schemes/*/.state.json files are only ever read.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import review
import validate
from parse_scheme import load_scheme, repo_root
from review_binding import (
    STALE,
    UNATTRIBUTED,
    UNBOUND,
    VALID,
    assess_scheme,
    binding,
    clause_fingerprint,
    clause_set_fingerprint,
    condition_fingerprint,
    condition_set_fingerprint,
    is_attributable,
    scheme_content,
)
from state import APPROVED, load_state

FIXTURES = Path(__file__).parent / "fixtures"
HUMAN = "Asha Verma"


@pytest.fixture
def demo_dir(tmp_path):
    target = tmp_path / "data" / "schemes" / "demo-scheme"
    target.parent.mkdir(parents=True)
    shutil.copytree(FIXTURES / "demo-scheme", target)
    return target


def _bound_state(scheme, by: str = HUMAN) -> dict:
    """What review.py writes after a complete, genuine review."""
    clauses, conditions, decision = scheme_content(scheme)
    by_id = {c["id"]: c for c in clauses}
    entry = {"status": APPROVED, "by": by, "at": "2026-10-13T00:00:00+00:00"}
    return {
        "gates": {
            "4_clauses": {**entry, **binding(clause_set_fingerprint(clauses))},
            "5_conditions": {**entry, **binding(
                condition_set_fingerprint(conditions, decision, by_id))},
        },
        "clauses": {c["id"]: {**entry, **binding(clause_fingerprint(c))} for c in clauses},
        "conditions": {c["id"]: {**entry, **binding(condition_fingerprint(c, by_id))}
                       for c in conditions},
    }


def _write_state(directory: Path, data: dict) -> None:
    (directory / ".state.json").write_text(json.dumps(data), encoding="utf-8")


def _edit_scheme(directory: Path, old: str, new: str) -> None:
    path = directory / "scheme.md"
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# -- attribution -------------------------------------------------------------


@pytest.mark.parametrize("name", [
    "Codex", "codex", "Claude (AI assistant, on request) -- needs human confirmation",
    "ChatGPT", "GitHub Copilot", "review-bot", "automation", "unknown", "", None,
    "Actual Human Reviewer Name",
])
def test_agent_and_placeholder_names_are_not_attributable(name):
    assert is_attributable(name) is False


@pytest.mark.parametrize("name", ["Asha Verma", "thorb", "Ronit Khanna", "Shreyas"])
def test_ordinary_names_are_attributable(name):
    assert is_attributable(name) is True


# -- the assessment ------------------------------------------------------------


def test_a_complete_bound_human_review_counts(demo_dir):
    scheme = load_scheme(demo_dir / "scheme.md")
    result = assess_scheme(scheme, _bound_state(scheme))
    assert result.reviewed is True
    assert set(result.gates.values()) == {VALID}


def test_legacy_records_without_a_binding_are_pending(demo_dir):
    scheme = load_scheme(demo_dir / "scheme.md")
    legacy = _bound_state(scheme)
    for section in ("gates", "clauses", "conditions"):
        for entry in legacy[section].values():
            entry.pop("binding"), entry.pop("content_sha256")
    result = assess_scheme(scheme, legacy)
    assert result.reviewed is False
    assert result.gates == {"4_clauses": UNBOUND, "5_conditions": UNBOUND}


def test_an_agent_attributed_gate_is_pending_even_with_a_binding(demo_dir):
    scheme = load_scheme(demo_dir / "scheme.md")
    data = _bound_state(scheme)
    data["gates"]["4_clauses"]["by"] = "Codex"
    result = assess_scheme(scheme, data)
    assert result.reviewed is False
    assert result.gates["4_clauses"] == UNATTRIBUTED
    assert any("Codex" in reason for reason in result.reasons)


def test_a_changed_expression_invalidates_its_condition_and_gate_5(demo_dir):
    scheme = load_scheme(demo_dir / "scheme.md")
    data = _bound_state(scheme)
    _edit_scheme(demo_dir, "profile.age >= 18", "profile.age > 18")
    changed = load_scheme(demo_dir / "scheme.md")

    result = assess_scheme(changed, data)
    assert result.reviewed is False
    assert result.gates["5_conditions"] == STALE
    assert result.gates["4_clauses"] == VALID
    assert STALE in result.conditions.values()


def test_a_changed_clause_gloss_invalidates_the_clause_and_gate_4(demo_dir):
    scheme = load_scheme(demo_dir / "scheme.md")
    data = _bound_state(scheme)
    clause = scheme.clauses[0]
    _edit_scheme(demo_dir, clause.plain.split("\n")[0][:30],
                 "An edited gloss nobody reviewed")
    result = assess_scheme(load_scheme(demo_dir / "scheme.md"), data)
    assert result.gates["4_clauses"] == STALE
    assert result.clauses[clause.id] == STALE


# -- validate.py ---------------------------------------------------------------


def test_validate_warns_by_default_and_fails_the_release_gate(demo_dir):
    scheme = load_scheme(demo_dir / "scheme.md")
    data = _bound_state(scheme, by="Codex")
    _write_state(demo_dir, data)

    lenient = validate.validate_scheme(demo_dir / "scheme.md")
    assert lenient.ok
    assert any("pending human review" in f.message for f in lenient.warnings)

    strict = validate.validate_scheme(demo_dir / "scheme.md", require_review=True)
    assert not strict.ok
    assert any("Codex" in f.message for f in strict.errors)


def test_validate_release_gate_passes_a_valid_human_review(demo_dir):
    scheme = load_scheme(demo_dir / "scheme.md")
    _write_state(demo_dir, _bound_state(scheme))
    result = validate.validate_scheme(demo_dir / "scheme.md", require_review=True)
    assert not [f for f in result.errors if f.check == "review"]


# -- review.py records the binding --------------------------------------------------


def test_review_tool_binds_condition_approvals_to_what_was_shown(demo_dir, monkeypatch):
    scheme = load_scheme(demo_dir / "scheme.md")
    state = load_state("demo-scheme", demo_dir)
    monkeypatch.setattr(review.console, "key", lambda *a, **k: "a")
    assert review.review_conditions(scheme, state, HUMAN) is True

    reloaded = load_state("demo-scheme", demo_dir)
    result = assess_scheme(scheme, reloaded.data)
    assert set(result.conditions.values()) == {VALID}
    entry = next(iter(reloaded.data["conditions"].values()))
    assert entry["by"] == HUMAN and entry["binding"] == 1 and entry["content_sha256"]


def test_review_tool_reopens_clauses_whose_approval_no_longer_counts(demo_dir):
    scheme = load_scheme(demo_dir / "scheme.md")
    state = load_state("demo-scheme", demo_dir)
    clause = scheme.clauses[0]
    state.set_clause(clause.id, APPROVED, by="Codex")
    assert review.needs_review(state, clause) is True


def test_review_tool_refuses_an_agent_as_reviewer(demo_dir, capsys):
    code = review.main(["--scheme", "demo-scheme", "--reviewer", "Codex",
                        "--root", str(demo_dir.parent.parent.parent)])
    assert code == 1
    assert "not a person" in capsys.readouterr().out


def test_review_tool_refuses_piped_answers(demo_dir, capsys, monkeypatch):
    monkeypatch.setattr(review.sys.stdin, "isatty", lambda: False, raising=False)
    code = review.main(["--scheme", "demo-scheme", "--reviewer", HUMAN,
                        "--root", str(demo_dir.parent.parent.parent)])
    assert code == 1
    assert "interactive terminal" in capsys.readouterr().out


# -- the API reads the same thing validate.py does -------------------------------------


def test_build_data_fingerprints_match_scheme_md_for_every_committed_scheme():
    """The API judges reviews from build/; validate.py from scheme.md. If the
    fingerprints ever diverged, a valid review would read as stale (or the
    reverse) in one of the two places."""
    from api.rules.engine import load_clauses, load_rules

    root = repo_root()
    for path in sorted((root / "data" / "schemes").glob("*/scheme.md")):
        slug = path.parent.name
        clauses, conditions, decision = scheme_content(load_scheme(path))
        rows = load_clauses(slug, root)
        built = [{"id": r["id"], "type": r["type"], "source": r["source_id"],
                  "quote": r["quote"], "plain": r["plain"], "tests": r["tests"]}
                 for r in rows.values()]
        assert clause_set_fingerprint(built) == clause_set_fingerprint(clauses), slug
        rules = load_rules(slug, root)
        by_id = {c["id"]: c for c in built}
        assert condition_set_fingerprint(
            [{"id": c["id"], "expr": c["expr"], "clause": c["clause"]}
             for c in rules["conditions"]], rules["decision"], by_id,
        ) == condition_set_fingerprint(conditions, decision, by_id), slug


def test_pmfme_is_reported_pending_with_the_reasons_named():
    from api.routers.chat import review_assessment

    result = review_assessment("pmfme")
    assert result.reviewed is False
    assert result.gates["4_clauses"] == UNATTRIBUTED      # recorded as "Codex"
    assert result.gates["5_conditions"] == UNBOUND        # predates age > 18
    assert result.conditions["applicant_age_and_education"] == UNBOUND
