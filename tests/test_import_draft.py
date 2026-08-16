"""Tests for the assistant-draft validation bridge.

The fabricated fixture is the important one: if these assertions ever pass
silently, an LLM could write GovAssist's eligibility rules from memory and
nothing would notice.
"""

import shutil
from pathlib import Path

import pytest

from import_draft import check, main, repair_message
from normalize import MatchStatus
from parse_scheme import load_scheme

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def demo_dir(tmp_path):
    target = tmp_path / "demo-scheme"
    shutil.copytree(FIXTURES / "demo-scheme", target)
    return target


@pytest.fixture
def fabricated_dir(tmp_path):
    """The fabricated scheme, wired to the demo scheme's real source text."""
    target = tmp_path / "fabricated-scheme"
    target.mkdir()
    shutil.copy(FIXTURES / "fabricated-scheme" / "scheme.md", target / "scheme.md")
    (target / "source").mkdir()
    shutil.copy(
        FIXTURES / "demo-scheme" / "source" / "guidelines-demo.txt",
        target / "source" / "guidelines-demo.txt",
    )
    text = (target / "scheme.md").read_text(encoding="utf-8")
    (target / "scheme.md").write_text(
        text.replace("../demo-scheme/source/", "source/"), encoding="utf-8"
    )
    return target


class TestGoodDraftPasses:
    def test_every_demo_clause_is_verbatim(self, demo_dir):
        scheme = load_scheme(demo_dir / "scheme.md")
        reports = check(scheme, demo_dir)
        assert len(reports) == 6
        assert all(r.status is MatchStatus.EXACT for r in reports), [
            (r.clause.id, r.status) for r in reports if r.status is not MatchStatus.EXACT
        ]

    def test_exit_code_zero(self, demo_dir, capsys):
        code = main(["--scheme", "demo-scheme", "--file", str(demo_dir / "scheme.md"),
                     "--root", str(demo_dir.parent.parent)])
        assert code == 0


class TestFabricatedDraftIsRejected:
    """Each of these is a real way an LLM corrupts a corpus."""

    def _reports(self, fabricated_dir):
        scheme = load_scheme(fabricated_dir / "scheme.md")
        return {r.clause.id: r for r in check(scheme, fabricated_dir)}

    def test_invented_rule_is_rejected(self, fabricated_dir):
        # A "senior bonus" that exists nowhere in the document.
        assert self._reports(fabricated_dir)["fabricated-senior-bonus"].failed

    def test_altered_number_is_rejected(self, fabricated_dir):
        # Rs. 6000 quietly became Rs. 8000.
        assert self._reports(fabricated_dir)["altered-benefit-amount"].failed

    def test_paraphrase_is_rejected(self, fabricated_dir):
        # Same meaning, cleaner wording -- still not a quote.
        assert self._reports(fabricated_dir)["paraphrased-eligibility"].failed

    def test_all_three_fail(self, fabricated_dir):
        reports = self._reports(fabricated_dir)
        assert sum(1 for r in reports.values() if r.failed) == 3

    def test_exit_code_is_nonzero(self, fabricated_dir):
        code = main([
            "--scheme", "fabricated-scheme",
            "--file", str(fabricated_dir / "scheme.md"),
            "--root", str(fabricated_dir.parent.parent),
        ])
        assert code == 1

    def test_failure_points_at_the_real_text(self, fabricated_dir):
        report = self._reports(fabricated_dir)["altered-benefit-amount"]
        assert report.context is not None
        assert "6000" in report.context   # shows the real number


class TestRepairMessage:
    def test_lists_only_failing_clauses(self, fabricated_dir):
        scheme = load_scheme(fabricated_dir / "scheme.md")
        message = repair_message(check(scheme, fabricated_dir))
        assert "altered-benefit-amount" in message
        assert "paraphrased-eligibility" in message

    def test_includes_real_source_text_for_repair(self, fabricated_dir):
        scheme = load_scheme(fabricated_dir / "scheme.md")
        message = repair_message(check(scheme, fabricated_dir))
        assert "6000" in message

    def test_tells_the_model_to_delete_unsupported_clauses(self, fabricated_dir):
        scheme = load_scheme(fabricated_dir / "scheme.md")
        message = repair_message(check(scheme, fabricated_dir))
        assert "delete" in message.lower()

    def test_empty_when_nothing_failed(self, demo_dir):
        scheme = load_scheme(demo_dir / "scheme.md")
        assert repair_message(check(scheme, demo_dir)) == ""


class TestEdgeCases:
    def test_clause_with_no_quote_fails(self, demo_dir):
        path = demo_dir / "scheme.md"
        path.write_text(
            path.read_text(encoding="utf-8")
            + "\n## empty-clause\n\n```yaml\ntype: benefit\nsource: guidelines-demo\n```\n\n**Plain:** nothing\n",
            encoding="utf-8",
        )
        reports = {r.clause.id: r for r in check(load_scheme(path), demo_dir)}
        assert reports["empty-clause"].failed
        assert "no blockquote" in reports["empty-clause"].note

    def test_missing_draft_file_exits_nonzero(self, tmp_path):
        assert main(["--scheme", "nope", "--root", str(tmp_path)]) == 1
