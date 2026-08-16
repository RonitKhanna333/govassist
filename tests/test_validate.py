"""Tests for the acceptance gates and the build projections.

The fabricated-scheme assertions are the meta-test for the whole system: if
validate.py ever passes that fixture, the grounding guarantee is gone.
"""

import json
import shutil
from pathlib import Path

import pytest

import build as build_mod
import validate as validate_mod
from parse_scheme import load_scheme
from state import APPROVED, load_state

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def demo_dir(tmp_path):
    target = tmp_path / "data" / "schemes" / "demo-scheme"
    target.parent.mkdir(parents=True)
    shutil.copytree(FIXTURES / "demo-scheme", target)
    return target


@pytest.fixture
def fabricated_dir(tmp_path):
    target = tmp_path / "data" / "schemes" / "fabricated-scheme"
    target.parent.mkdir(parents=True)
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


def codes(result, check=None):
    return [f.where for f in result.errors if check is None or f.check == check]


class TestValidDemoScheme:
    def test_passes(self, demo_dir):
        result = validate_mod.validate_scheme(demo_dir / "scheme.md")
        assert result.ok, [(f.check, f.where, f.message) for f in result.errors]

    def test_exit_code_zero(self, demo_dir):
        assert validate_mod.main(["--file", str(demo_dir / "scheme.md")]) == 0


class TestFabricatedSchemeIsRejected:
    """The meta-test. If this ever passes, the corpus guarantee is void."""

    @pytest.fixture
    def result(self, fabricated_dir):
        return validate_mod.validate_scheme(fabricated_dir / "scheme.md")

    def test_fails_overall(self, result):
        assert not result.ok

    def test_invented_clause_is_caught(self, result):
        assert "fabricated-senior-bonus" in codes(result, "quotes")

    def test_altered_number_is_caught(self, result):
        assert "altered-benefit-amount" in codes(result, "quotes")

    def test_paraphrase_is_caught(self, result):
        assert "paraphrased-eligibility" in codes(result, "quotes")

    def test_dangling_condition_reference_is_caught(self, result):
        assert "dangling" in codes(result, "conditions")

    def test_exit_code_is_nonzero(self, fabricated_dir):
        assert validate_mod.main(["--file", str(fabricated_dir / "scheme.md")]) == 1

    def test_failure_output_explains_itself(self, fabricated_dir, capsys):
        validate_mod.main(["--file", str(fabricated_dir / "scheme.md")])
        out = capsys.readouterr().out
        assert "6000" in out          # shows the real source number
        assert "FAIL" in out


class TestIndividualChecks:
    def test_corrupting_one_character_fails(self, demo_dir):
        path = demo_dir / "scheme.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("Rs. 6000", "Rs. 6001"), encoding="utf-8")
        result = validate_mod.validate_scheme(path)
        assert "benefit-amount" in codes(result, "quotes")

    def test_unknown_source_id_fails(self, demo_dir):
        path = demo_dir / "scheme.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("source: guidelines-demo\npage: 1\ntests:\n- age",
                                     "source: nonexistent\npage: 1\ntests:\n- age", 1),
                        encoding="utf-8")
        result = validate_mod.validate_scheme(path)
        assert codes(result, "sources")

    def test_illegal_expression_fails(self, demo_dir):
        path = demo_dir / "scheme.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace("expr: profile.age >= 18",
                         "expr: __import__('os').system('echo pwned') == 0"),
            encoding="utf-8",
        )
        result = validate_mod.validate_scheme(path)
        assert "adult" in codes(result, "expressions")

    def test_unknown_clause_type_fails(self, demo_dir):
        path = demo_dir / "scheme.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("type: benefit", "type: nonsense", 1),
                        encoding="utf-8")
        assert codes(validate_mod.validate_scheme(path), "shape")

    def test_checksum_mismatch_is_reported_when_pdf_present(self, demo_dir):
        (demo_dir / "source" / "guidelines-demo.pdf").write_bytes(b"not the real pdf")
        result = validate_mod.validate_scheme(demo_dir / "scheme.md")
        assert "guidelines-demo" in codes(result, "checksums")

    def test_unreviewed_clause_in_scheme_is_flagged(self, demo_dir):
        state = load_state("demo-scheme", demo_dir)
        state.set_clause("landholding-basic", APPROVED, by="ronit")
        result = validate_mod.validate_scheme(demo_dir / "scheme.md")
        # Every other clause is in scheme.md but was never accepted.
        assert "age-minimum" in codes(result, "review")


class TestBuild:
    def test_writes_all_three_projections(self, demo_dir):
        scheme = load_scheme(demo_dir / "scheme.md")
        build_mod.write(scheme, demo_dir, check_only=False)
        assert (demo_dir / "build" / "rules.v1.json").exists()
        assert (demo_dir / "build" / "graph.v1.json").exists()
        assert (demo_dir / "build" / "clauses.jsonl").exists()

    def test_output_is_byte_identical_across_runs(self, demo_dir):
        scheme = load_scheme(demo_dir / "scheme.md")
        first = build_mod.outputs(scheme)
        second = build_mod.outputs(scheme)
        assert first == second

    def test_check_detects_stale_output(self, demo_dir):
        scheme = load_scheme(demo_dir / "scheme.md")
        build_mod.write(scheme, demo_dir, check_only=False)
        ok, stale = build_mod.write(scheme, demo_dir, check_only=True)
        assert ok and not stale

        path = demo_dir / "build" / "rules.v1.json"
        path.write_text(path.read_text(encoding="utf-8").replace("18", "21"),
                        encoding="utf-8")
        ok, stale = build_mod.write(scheme, demo_dir, check_only=True)
        assert not ok and "rules.v1.json" in stale

    def test_rules_carry_every_condition_with_its_clause(self, demo_dir):
        rules = build_mod.build_rules(load_scheme(demo_dir / "scheme.md"))
        assert len(rules["conditions"]) == 4
        assert all(c["clause"] for c in rules["conditions"])
        assert rules["decision"] == "ALL(conditions)"

    def test_rules_record_which_attributes_each_condition_reads(self, demo_dir):
        rules = build_mod.build_rules(load_scheme(demo_dir / "scheme.md"))
        landholding = next(c for c in rules["conditions"] if c["id"] == "landholding")
        assert landholding["reads"] == ["owns_cultivable_land"]

    def test_every_condition_node_is_grounded_in_a_clause(self, demo_dir):
        graph = build_mod.build_graph(load_scheme(demo_dir / "scheme.md"))
        conditions = {n["id"] for n in graph["nodes"] if n["type"] == "Condition"}
        grounded = {e["from"] for e in graph["edges"] if e["predicate"] == "GROUNDED_IN"}
        assert conditions <= grounded

    def test_every_clause_node_reaches_a_source_document(self, demo_dir):
        graph = build_mod.build_graph(load_scheme(demo_dir / "scheme.md"))
        clauses = {n["id"] for n in graph["nodes"] if n["type"] == "Clause"}
        from_source = {e["from"] for e in graph["edges"] if e["predicate"] == "FROM"}
        assert clauses <= from_source

    def test_exclusion_clauses_get_exclusion_edges(self, demo_dir):
        graph = build_mod.build_graph(load_scheme(demo_dir / "scheme.md"))
        excluded = {e["to"] for e in graph["edges"] if e["predicate"] == "EXCLUDES"}
        assert "clause:exclusion-income-tax" in excluded
        assert "clause:exclusion-government-employee" in excluded

    def test_graph_ordering_is_stable(self, demo_dir):
        scheme = load_scheme(demo_dir / "scheme.md")
        a = build_mod.build_graph(scheme)
        b = build_mod.build_graph(scheme)
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    def test_clause_rows_embed_plain_and_aliases_not_the_quote(self, demo_dir):
        rows = {r["id"]: r for r in
                build_mod.build_clauses(load_scheme(demo_dir / "scheme.md"))}
        row = rows["landholding-basic"]
        assert row["plain"] in row["embedding_text"]
        assert row["aliases"][0] in row["embedding_text"]
        # The citation text must not be what drives retrieval.
        assert row["quote"] not in row["embedding_text"]

    def test_clause_rows_keep_the_verbatim_quote_for_citation(self, demo_dir):
        rows = {r["id"]: r for r in
                build_mod.build_clauses(load_scheme(demo_dir / "scheme.md"))}
        assert rows["benefit-amount"]["quote"].startswith("The benefit of Rs. 6000")

    def test_indic_aliases_survive_the_build(self, demo_dir):
        rows = {r["id"]: r for r in
                build_mod.build_clauses(load_scheme(demo_dir / "scheme.md"))}
        aliases = rows["landholding-basic"]["aliases"]
        assert any("ਜ਼ਮੀਨ" in a for a in aliases)
        assert any("ज़मीन" in a for a in aliases)


class TestDiffRules:
    def test_reports_added_removed_and_changed(self):
        import diff_rules

        old = {"decision": "ALL(conditions)", "conditions": [
            {"id": "a", "expr": "profile.age >= 60", "clause": "c1", "asks": ""},
            {"id": "b", "expr": "profile.x == true", "clause": "c2", "asks": ""},
        ]}
        new = {"decision": "ALL(conditions)", "conditions": [
            {"id": "a", "expr": "profile.age >= 65", "clause": "c1", "asks": ""},
            {"id": "c", "expr": "profile.y == true", "clause": "c3", "asks": ""},
        ]}
        kinds = {(kind, target) for kind, target, _ in diff_rules.diff(old, new)}
        assert ("added", "c") in kinds
        assert ("removed", "b") in kinds
        assert ("changed", "a") in kinds

    def test_identical_versions_have_no_changes(self):
        import diff_rules

        rules = {"decision": "ALL(conditions)", "conditions": [
            {"id": "a", "expr": "profile.age >= 60", "clause": "c1", "asks": ""},
        ]}
        assert diff_rules.diff(rules, rules) == []
