"""Tests for scheme.md parsing, serialization, and gate state."""

from pathlib import Path

import pytest

from parse_scheme import (
    Clause,
    SchemeParseError,
    dump_scheme,
    load_scheme,
    parse_scheme_text,
    source_text,
)
from state import APPROVED, GateNotApproved, PENDING, load_state

FIXTURES = Path(__file__).parent / "fixtures"
DEMO = FIXTURES / "demo-scheme" / "scheme.md"


@pytest.fixture
def demo():
    return load_scheme(DEMO)


class TestFrontmatter:
    def test_reads_scheme_metadata(self, demo):
        assert demo.scheme == "demo-scheme"
        assert demo.name_en == "Demo Welfare Scheme"
        assert demo.tier == 1
        assert demo.decision == "ALL(conditions)"

    def test_reads_sources(self, demo):
        source = demo.source("guidelines-demo")
        assert source is not None
        assert source.txt == "source/guidelines-demo.txt"

    def test_reads_conditions(self, demo):
        ids = [c.id for c in demo.conditions]
        assert ids == ["landholding", "adult", "not_income_tax_payer",
                       "not_government_employee"]
        assert demo.conditions[0].clause == "landholding-basic"
        assert demo.conditions[0].asks

    def test_missing_frontmatter_is_an_error(self):
        with pytest.raises(SchemeParseError, match="frontmatter"):
            parse_scheme_text("## clause\n\n> text\n")

    def test_missing_scheme_key_is_an_error(self):
        with pytest.raises(SchemeParseError, match="scheme"):
            parse_scheme_text("---\nname_en: x\n---\n")


class TestClauses:
    def test_parses_all_clauses(self, demo):
        assert demo.clause_ids == [
            "landholding-basic", "age-minimum", "benefit-amount",
            "exclusion-income-tax", "exclusion-government-employee",
            "documents-required",
        ]

    def test_parses_clause_metadata(self, demo):
        clause = demo.clause("exclusion-income-tax")
        assert clause.type == "exclusion"
        assert clause.source == "guidelines-demo"
        assert clause.tests == ["paid_income_tax_last_year"]

    def test_parses_multiline_quote(self, demo):
        quote = demo.clause("landholding-basic").quote
        assert quote.startswith("All landholding farmers' families")
        assert "shall be eligible" in quote
        assert ">" not in quote  # markers stripped

    def test_parses_plain(self, demo):
        assert demo.clause("age-minimum").plain.startswith("You must be at least")

    def test_parses_aliases_including_indic_scripts(self, demo):
        aliases = demo.clause("landholding-basic").aliases
        assert "we own farm land" in aliases
        assert "ਸਾਡੀ ਆਪਣੀ ਜ਼ਮੀਨ ਹੈ" in aliases
        assert "मेरे पास खेती की ज़मीन है" in aliases

    def test_empty_aliases_is_empty_list(self):
        text = (
            "---\nscheme: x\n---\n\n## c\n\n```yaml\ntype: benefit\n```\n\n> hi\n"
        )
        assert parse_scheme_text(text).clause("c").aliases == []

    def test_duplicate_clause_id_is_an_error(self):
        text = "---\nscheme: x\n---\n\n## c\n\n> a\n\n## c\n\n> b\n"
        with pytest.raises(SchemeParseError, match="duplicate"):
            parse_scheme_text(text)


class TestRoundTrip:
    def test_dump_then_parse_preserves_everything(self, demo):
        reparsed = parse_scheme_text(dump_scheme(demo))
        assert reparsed.scheme == demo.scheme
        assert reparsed.clause_ids == demo.clause_ids
        assert [c.id for c in reparsed.conditions] == [c.id for c in demo.conditions]
        for original in demo.clauses:
            copy = reparsed.clause(original.id)
            assert copy.quote == original.quote
            assert copy.plain == original.plain
            assert copy.aliases == original.aliases
            assert copy.type == original.type
            assert copy.tests == original.tests

    def test_dump_is_deterministic(self, demo):
        assert dump_scheme(demo) == dump_scheme(demo)

    def test_dump_is_stable_across_a_round_trip(self, demo):
        once = dump_scheme(demo)
        assert dump_scheme(parse_scheme_text(once)) == once

    def test_uncertain_flag_survives(self):
        scheme = parse_scheme_text("---\nscheme: x\n---\n")
        scheme.clauses.append(
            Clause(id="c", quote="q", type="benefit", uncertain=True,
                   note="table was mangled")
        )
        reparsed = parse_scheme_text(dump_scheme(scheme))
        assert reparsed.clause("c").uncertain is True
        assert reparsed.clause("c").note == "table was mangled"

    def test_handles_crlf_input(self, demo):
        crlf = DEMO.read_text(encoding="utf-8").replace("\n", "\r\n")
        assert parse_scheme_text(crlf).clause_ids == demo.clause_ids


class TestSourceText:
    def test_reads_the_validation_target(self, demo):
        text = source_text(demo, "guidelines-demo")
        assert "All landholding farmers' families" in text

    def test_unknown_source_id_is_an_error(self, demo):
        with pytest.raises(SchemeParseError, match="unknown source"):
            source_text(demo, "nope")


class TestState:
    def test_gates_start_pending(self, tmp_path):
        state = load_state("demo", tmp_path)
        assert state.gate_status("0_source") == PENDING
        assert not state.is_approved("0_source")

    def test_approval_is_recorded_with_who_and_when(self, tmp_path):
        state = load_state("demo", tmp_path)
        state.set_gate("0_source", APPROVED, by="ronit")
        entry = state.data["gates"]["0_source"]
        assert entry["status"] == APPROVED
        assert entry["by"] == "ronit"
        assert entry["at"]

    def test_state_persists_across_loads(self, tmp_path):
        load_state("demo", tmp_path).set_gate("1_identity", APPROVED, by="bhavneet")
        assert load_state("demo", tmp_path).is_approved("1_identity")

    def test_require_blocks_on_unapproved_gate(self, tmp_path):
        state = load_state("demo", tmp_path)
        with pytest.raises(GateNotApproved, match="2_extraction"):
            state.require("2_extraction")

    def test_require_passes_once_approved(self, tmp_path):
        state = load_state("demo", tmp_path)
        state.set_gate("2_extraction", APPROVED, by="shreyas")
        state.require("2_extraction")

    def test_clause_decisions_persist_immediately(self, tmp_path):
        state = load_state("demo", tmp_path)
        state.set_clause("landholding-basic", APPROVED, by="ronit", edited=True)
        reloaded = load_state("demo", tmp_path)
        assert reloaded.clause_status("landholding-basic") == APPROVED
        assert reloaded.clause("landholding-basic")["edited"] is True
        assert reloaded.accepted_clauses() == ["landholding-basic"]

    def test_writes_are_atomic(self, tmp_path):
        # After many writes there should be exactly one state file and no
        # leftover temp files from interrupted saves.
        state = load_state("demo", tmp_path)
        for index in range(25):
            state.set_clause(f"clause-{index}", APPROVED, by="ronit")
        assert [p.name for p in tmp_path.iterdir()] == [".state.json"]
