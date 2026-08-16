"""Tests for deterministic segmentation."""

from segment import Segment, apply_merge, apply_split, segment_text

DOC = """
DEMO WELFARE SCHEME
Operational Guidelines, 2024

1. INTRODUCTION

1.1 The scheme provides income support to eligible farmer families.

2. ELIGIBILITY

2.1 All landholding farmers' families shall be eligible.

2.2 The applicant shall have attained the age of eighteen years.

3. BENEFITS

3.1 The benefit of Rs. 6000 per year shall be transferred.

4. EXCLUSIONS

4.1 Institutional Land holders are excluded from the scheme.
"""


class TestSegmentText:
    def test_produces_segments(self):
        segments = segment_text(DOC, target=80, maximum=200)
        assert len(segments) > 1
        assert all(isinstance(s, Segment) for s in segments)

    def test_segments_are_indexed_from_one_and_contiguous(self):
        segments = segment_text(DOC, target=80, maximum=200)
        assert [s.index for s in segments] == list(range(1, len(segments) + 1))

    def test_no_text_is_lost(self):
        segments = segment_text(DOC, target=80, maximum=200)
        joined = "\n".join(s.text for s in segments)
        for sentence in [
            "All landholding farmers' families shall be eligible.",
            "The benefit of Rs. 6000 per year shall be transferred.",
            "Institutional Land holders are excluded from the scheme.",
        ]:
            assert sentence in joined

    def test_breaks_at_numbered_headings(self):
        segments = segment_text(DOC, target=60, maximum=150)
        firsts = [s.first_line for s in segments]
        assert any(f.startswith(("2.", "3.", "4.")) or f.isupper() for f in firsts)

    def test_is_deterministic(self):
        a = segment_text(DOC, target=80, maximum=200)
        b = segment_text(DOC, target=80, maximum=200)
        assert [(s.index, s.text) for s in a] == [(s.index, s.text) for s in b]

    def test_single_short_document_is_one_segment(self):
        assert len(segment_text("1. Short.\n", target=5000)) == 1

    def test_empty_document_yields_nothing(self):
        assert segment_text("\n\n   \n") == []

    def test_large_document_is_broken_up_even_without_headings(self):
        blob = "\n".join(f"line {i} of unstructured prose text here" for i in range(600))
        segments = segment_text(blob, target=1000, maximum=2000)
        assert len(segments) > 1


class TestMergeAndSplit:
    def _segments(self):
        return [
            Segment(1, "a", "alpha"),
            Segment(2, "b", "bravo"),
            Segment(3, "c", "charlie"),
            Segment(4, "d", "delta"),
        ]

    def test_merge_folds_into_the_preceding_segment(self):
        merged = apply_merge(self._segments(), "2,3")
        assert len(merged) == 2
        assert "alpha" in merged[0].text
        assert "bravo" in merged[0].text
        assert "charlie" in merged[0].text
        assert merged[1].text == "delta"

    def test_merge_reindexes(self):
        merged = apply_merge(self._segments(), "2")
        assert [s.index for s in merged] == list(range(1, len(merged) + 1))

    def test_merge_with_no_valid_targets_is_a_noop(self):
        assert len(apply_merge(self._segments(), "")) == 4

    def test_split_breaks_a_segment_at_an_offset(self):
        segments = [Segment(1, "x", "abcdefghij")]
        out = apply_split(segments, "1:5")
        assert len(out) == 2
        assert out[0].text == "abcde"
        assert out[1].text == "fghij"
        assert [s.index for s in out] == [1, 2]

    def test_split_preserves_all_content(self):
        segments = [Segment(1, "x", "hello world of text")]
        out = apply_split(segments, "1:5")
        assert "".join(s.text for s in out).replace(" ", "") == "helloworldoftext"
