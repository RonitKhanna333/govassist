"""Tests for the provenance spine.

If these pass, "verbatim" means something. If any of them regress, every
downstream grounding guarantee in GovAssist is void -- so this file is
deliberately picky.
"""

import pytest

from normalize import (
    MatchStatus,
    find_context,
    normalize,
    normalize_aggressive,
    validate_quote,
)

SOURCE = """
2.1  All landholding farmers' families, which have cultivable landholding
in their names, shall be eligible to receive benefit under the scheme.

4.c  All Institutional Land holders and farmer families in which one or more
of its members paid Income Tax in last assessment year are excluded from the
benefit under the scheme.

5.  The benefit of Rs. 6000 per year shall be transferred in three equal
instal-
ments of Rs. 2000 each.
"""


class TestNormalize:
    def test_collapses_whitespace(self):
        assert normalize("a   b\n\nc\t d") == "a b c d"

    def test_folds_curly_quotes_and_dashes(self):
        assert normalize("“farmers’ families” – yes") == '"farmers\' families" - yes'

    def test_removes_soft_hyphen(self):
        assert normalize("elig­ible") == "eligible"

    def test_rejoins_linebreak_hyphenation(self):
        assert normalize("instal-\nments") == "instalments"

    def test_rejoins_linebreak_hyphenation_with_indent(self):
        assert normalize("instal-  \n   ments") == "instalments"

    def test_lowercases(self):
        assert normalize("ALL Landholding") == "all landholding"

    def test_nfkc_folds_compatibility_forms(self):
        # Fullwidth digits and ligatures are common in extracted PDFs.
        assert normalize("Ｒｓ． ６０００") == "rs. 6000"
        assert normalize("ofﬁce") == "office"

    def test_strips_zero_width_characters(self):
        assert normalize("far​mers") == "farmers"

    def test_normalize_is_idempotent(self):
        once = normalize(SOURCE)
        assert normalize(once) == once

    def test_aggressive_drops_hyphens_and_spaces(self):
        assert normalize_aggressive("self-employed person") == "selfemployedperson"


class TestValidateQuote:
    def test_exact_match(self):
        quote = "shall be eligible to receive benefit under the scheme"
        assert validate_quote(quote, SOURCE).status is MatchStatus.EXACT

    def test_match_across_a_line_break(self):
        # The source wraps between "landholding" and "in their names".
        quote = "which have cultivable landholding in their names"
        assert validate_quote(quote, SOURCE).status is MatchStatus.EXACT

    def test_match_when_quote_wraps_differently_than_source(self):
        quote = "All Institutional Land holders\nand farmer families"
        assert validate_quote(quote, SOURCE).status is MatchStatus.EXACT

    def test_accepts_markdown_blockquote_markers(self):
        quote = "> shall be eligible to receive benefit\n> under the scheme"
        assert validate_quote(quote, SOURCE).status is MatchStatus.EXACT

    def test_curly_quotes_in_quote_match_straight_in_source(self):
        quote = "landholding farmers’ families"
        assert validate_quote(quote, SOURCE).status is MatchStatus.EXACT

    def test_hyphenated_source_matches_unhyphenated_quote(self):
        # Source has "instal-\nments"; a human types "instalments".
        quote = "three equal instalments of Rs. 2000 each"
        assert validate_quote(quote, SOURCE).status is MatchStatus.EXACT

    def test_loose_match_is_flagged_not_silently_accepted(self):
        # Differs from source only by a space: "Land holders" vs "Landholders".
        quote = "All Institutional Landholders and farmer families"
        match = validate_quote(quote, SOURCE)
        assert match.status is MatchStatus.LOOSE
        assert match.ok is True
        assert match.needs_human is True

    # --- The tests that matter most: things that MUST be rejected -------------

    def test_absent_quote_is_rejected(self):
        quote = "farmers over the age of sixty shall receive a double benefit"
        assert validate_quote(quote, SOURCE).status is MatchStatus.MISSING

    def test_paraphrase_is_rejected(self):
        # Same meaning, different words. This is exactly what must never pass.
        quote = "Farmers who own land they can farm are eligible for the scheme."
        assert validate_quote(quote, SOURCE).status is MatchStatus.MISSING

    def test_altered_number_is_rejected(self):
        # A single digit changed -- the most dangerous possible corruption.
        quote = "The benefit of Rs. 8000 per year"
        assert validate_quote(quote, SOURCE).status is MatchStatus.MISSING

    def test_negation_flip_is_rejected(self):
        quote = "shall not be eligible to receive benefit under the scheme"
        assert validate_quote(quote, SOURCE).status is MatchStatus.MISSING

    def test_empty_quote_is_rejected(self):
        assert validate_quote("   ", SOURCE).status is MatchStatus.MISSING
        assert validate_quote("", SOURCE).ok is False

    def test_failure_reports_nearby_source_text(self):
        quote = "The benefit of Rs. 8000 per year shall be transferred"
        match = validate_quote(quote, SOURCE)
        assert match.status is MatchStatus.MISSING
        assert match.context is not None
        assert "6000" in match.context  # points the human at the real number


class TestFindContext:
    def test_returns_none_when_nothing_resembles_the_quote(self):
        assert find_context("zzz qqq xxx wholly unrelated", SOURCE) is None

    def test_anchors_on_a_short_prefix(self):
        ctx = find_context("All Institutional Land holders and WRONG TAIL", SOURCE)
        assert ctx is not None
        assert "income tax" in ctx


@pytest.mark.parametrize(
    "quote",
    [
        "shall be eligible to receive benefit under the scheme",
        "All Institutional Land holders",
        "three equal instalments",
    ],
)
def test_known_good_quotes_all_pass(quote):
    assert validate_quote(quote, SOURCE).ok
