"""Tests for the review gates.

The behaviours worth defending here are the refusals: a reviewer must not be
able to accept an ungrounded clause, and must not be able to "tidy" a quote out
of alignment with its source.
"""

import shutil
from pathlib import Path

import pytest

import review
from parse_scheme import Clause, Scheme, load_scheme
from state import APPROVED, PENDING, REJECTED, load_state

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def demo_dir(tmp_path):
    target = tmp_path / "data" / "schemes" / "demo-scheme"
    target.parent.mkdir(parents=True)
    shutil.copytree(FIXTURES / "demo-scheme", target)
    return target


@pytest.fixture
def scheme(demo_dir):
    return load_scheme(demo_dir / "scheme.md")


@pytest.fixture
def source(demo_dir):
    return (demo_dir / "source" / "guidelines-demo.txt").read_text(encoding="utf-8")


class TestSourceResolution:
    def test_finds_the_cited_source(self, scheme, demo_dir):
        clause = scheme.clause("landholding-basic")
        text = review.source_for(scheme, clause, demo_dir)
        assert text is not None
        assert "All landholding farmers' families" in text

    def test_falls_back_to_the_only_source_present(self, scheme, demo_dir):
        clause = Clause(id="x", quote="anything", source="")
        assert review.source_for(scheme, clause, demo_dir) is not None


class TestEditRefusal:
    """The tool must not let a reviewer break provenance by tidying a quote."""

    def _edit_with(self, monkeypatch, new_body: str):
        def fake_run(cmd, check=False):
            Path(cmd[-1]).write_text(new_body, encoding="utf-8")
            return None
        monkeypatch.setattr(review.subprocess, "run", fake_run)

    def test_accepts_an_edit_that_keeps_the_quote_verbatim(self, monkeypatch, scheme,
                                                           source):
        clause = scheme.clause("landholding-basic")
        self._edit_with(monkeypatch, (
            "## landholding-basic\n\n"
            "```yaml\ntype: eligibility\nsource: guidelines-demo\npage: 1\n"
            "tests:\n- owns_cultivable_land\n```\n\n"
            "> All landholding farmers' families, which have cultivable landholding\n"
            "> in their names, shall be eligible to receive benefit under the scheme.\n\n"
            "**Plain:** A clearer gloss written by the reviewer.\n"
        ))
        updated, changed = review.edit_clause(clause, source)
        assert changed is True
        assert updated.plain == "A clearer gloss written by the reviewer."

    def test_refuses_an_edit_that_paraphrases_the_quote(self, monkeypatch, scheme,
                                                       source, capsys):
        clause = scheme.clause("landholding-basic")
        original_quote = clause.quote
        self._edit_with(monkeypatch, (
            "## landholding-basic\n\n"
            "```yaml\ntype: eligibility\nsource: guidelines-demo\n```\n\n"
            "> Farmers who own land they can cultivate are eligible.\n\n"
            "**Plain:** x\n"
        ))
        updated, changed = review.edit_clause(clause, source)
        assert changed is False
        assert updated.quote == original_quote
        assert "EDIT REFUSED" in capsys.readouterr().out

    def test_refuses_an_edit_that_changes_a_number(self, monkeypatch, scheme, source):
        clause = scheme.clause("benefit-amount")
        self._edit_with(monkeypatch, (
            "## benefit-amount\n\n"
            "```yaml\ntype: benefit\nsource: guidelines-demo\n```\n\n"
            "> The benefit of Rs. 9000 per year shall be transferred in three equal\n"
            "> instalments of Rs. 3000 each, directly to the bank account of the\n"
            "> beneficiary.\n\n"
            "**Plain:** x\n"
        ))
        _, changed = review.edit_clause(clause, source)
        assert changed is False

    def test_unparseable_edit_leaves_the_clause_alone(self, monkeypatch, scheme, source):
        clause = scheme.clause("age-minimum")
        self._edit_with(monkeypatch, "this is not a clause section at all")
        updated, changed = review.edit_clause(clause, source)
        assert changed is False
        assert updated.quote == clause.quote


class TestPromote:
    def test_writes_only_accepted_clauses(self, demo_dir, scheme, tmp_path):
        state = load_state("demo-scheme", demo_dir)
        for clause_id in ["landholding-basic", "age-minimum"]:
            state.set_clause(clause_id, APPROVED, by="ronit")

        target = review.promote(scheme, state, tmp_path)
        promoted = load_scheme(target)
        assert promoted.clause_ids == ["landholding-basic", "age-minimum"]

    def test_preserves_frontmatter(self, demo_dir, scheme, tmp_path):
        state = load_state("demo-scheme", demo_dir)
        state.set_clause("landholding-basic", APPROVED, by="ronit")
        promoted = load_scheme(review.promote(scheme, state, tmp_path))
        assert promoted.scheme == "demo-scheme"
        assert promoted.authority == "Department of Demonstration Affairs"
        assert len(promoted.conditions) == 4
        assert promoted.sources[0].id == "guidelines-demo"

    def test_rejected_clauses_are_dropped(self, demo_dir, scheme, tmp_path):
        state = load_state("demo-scheme", demo_dir)
        state.set_clause("landholding-basic", APPROVED, by="ronit")
        state.set_clause("benefit-amount", REJECTED, by="ronit")
        promoted = load_scheme(review.promote(scheme, state, tmp_path))
        assert "benefit-amount" not in promoted.clause_ids


class TestStatusReporting:
    def test_status_exits_cleanly(self, demo_dir, capsys):
        code = review.main([
            "--scheme", "demo-scheme", "--status",
            "--root", str(demo_dir.parent.parent.parent),
        ])
        assert code == 0
        assert "demo-scheme" in capsys.readouterr().out

    def test_reviewer_name_is_required(self, demo_dir, capsys, monkeypatch):
        monkeypatch.setattr(review.console, "ask", lambda *a, **k: "")
        code = review.main([
            "--scheme", "demo-scheme",
            "--root", str(demo_dir.parent.parent.parent),
        ])
        assert code == 1
        assert "attributable" in capsys.readouterr().out


class TestGateStateIntegration:
    def test_decisions_survive_a_restart(self, demo_dir):
        state = load_state("demo-scheme", demo_dir)
        state.set_clause("age-minimum", APPROVED, by="shreyas")
        assert load_state("demo-scheme", demo_dir).clause_status("age-minimum") == APPROVED

    def test_undecided_clauses_stay_pending(self, demo_dir):
        state = load_state("demo-scheme", demo_dir)
        assert state.clause_status("documents-required") == PENDING
