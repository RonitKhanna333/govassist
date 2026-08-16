"""Text normalization and span validation -- the provenance spine.

Every claim GovAssist can make must trace to a verbatim quote from a committed
source document. This module is what "verbatim" actually means in code, so it is
the first thing built and the first thing tested.

The problem it solves: PDF text extraction mangles text in predictable ways
(mid-word line breaks, soft hyphens, curly quotes, ligatures, collapsed columns).
A quote a human copied is *the same text* as the source even when the bytes
differ. Normalization makes both sides comparable without ever loosening what
"same" means.

Two canonical forms, both EXACT matches -- there is no edit-distance threshold
and no fuzzy matching anywhere in this file:

  STANDARD    NFKC, soft hyphens removed, quotes/dashes folded to ASCII,
              line-break hyphenation rejoined, whitespace collapsed, lowercased.
  AGGRESSIVE  Additionally removes every hyphen and every space.

A STANDARD match is an unambiguous pass. An AGGRESSIVE-only match means the
quote and the source differ solely in hyphenation or spacing -- almost always a
PDF artifact, but it is surfaced as LOOSE so a human looks at it rather than
being silently accepted.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

SOFT_HYPHEN = "­"

# Characters PDF extractors and word processors substitute freely. Folding these
# is not a semantic change, so it cannot mask a paraphrase.
_CHAR_SUBS = {
    "“": '"',   # left double quote
    "”": '"',   # right double quote
    "„": '"',   # low double quote
    "‘": "'",   # left single quote
    "’": "'",   # right single quote / apostrophe
    "‚": "'",
    "–": "-",   # en dash
    "—": "-",   # em dash
    "−": "-",   # minus sign
    "…": "...",  # ellipsis
    " ": " ",   # non-breaking space
    "​": "",    # zero-width space
    "‌": "",    # zero-width non-joiner
    "‍": "",    # zero-width joiner
    "﻿": "",    # BOM
}

# Rejoins "eligi-\nble" -> "eligible". MUST run before whitespace collapse,
# because after collapse there is no newline left to anchor on.
_LINEBREAK_HYPHEN = re.compile(r"-[ \t]*\r?\n[ \t]*")
_WHITESPACE = re.compile(r"\s+")


class MatchStatus(str, Enum):
    EXACT = "exact"      # matched under STANDARD normalization
    LOOSE = "loose"      # matched only after also ignoring hyphens/spaces
    MISSING = "missing"  # not present in the source -- reject


@dataclass
class QuoteMatch:
    """Result of checking one quote against one source document."""

    status: MatchStatus
    index: int | None = None      # offset into the normalized source
    context: str | None = None    # nearby real source text, for repair/reporting
    note: str | None = None

    @property
    def ok(self) -> bool:
        """True if the quote is present. LOOSE counts as present but flagged."""
        return self.status is not MatchStatus.MISSING

    @property
    def needs_human(self) -> bool:
        return self.status is MatchStatus.LOOSE


def normalize(text: str) -> str:
    """Canonical form for COMPARISON ONLY.

    Never store or display the result -- the corpus always keeps the original
    text so citations stay faithful to the source.
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.replace(SOFT_HYPHEN, "")
    for src, dst in _CHAR_SUBS.items():
        text = text.replace(src, dst)
    text = _LINEBREAK_HYPHEN.sub("", text)   # before whitespace collapse
    text = _WHITESPACE.sub(" ", text)
    # Lowercased deliberately: PDF extraction produces small-caps and OCR case
    # noise. Letter case is not a provenance question -- rewording is, and
    # lowercasing cannot hide rewording.
    return text.strip().lower()


def normalize_aggressive(text: str) -> str:
    """STANDARD, plus every hyphen and space removed.

    Absorbs the residual hyphenation and spacing disagreements between a quote
    typed on one line and a source that wrapped it. Still an exact match on the
    resulting string -- no similarity scoring.
    """
    return normalize(text).replace("-", "").replace(" ", "")


def _blockquote_to_text(quote: str) -> str:
    """Strip Markdown blockquote markers so callers can pass raw '> ' lines."""
    lines = [re.sub(r"^\s*>\s?", "", ln) for ln in quote.splitlines()]
    return "\n".join(lines)


def find_context(needle: str, haystack: str, window: int = 150) -> str | None:
    """Locate the source text nearest to a failed quote.

    Tries progressively shorter prefixes of the quote as an anchor. This is what
    turns "validation failed" into a message someone can act on, and it feeds
    the automated repair loop as well as the human-facing error.
    """
    n_needle = normalize(needle)
    n_hay = normalize(haystack)
    if not n_needle:
        return None

    words = n_needle.split()
    anchor_at = -1
    for count in (12, 9, 7, 5, 3, 2):
        if len(words) < count:
            continue
        anchor_at = n_hay.find(" ".join(words[:count]))
        if anchor_at >= 0:
            break

    if anchor_at < 0:
        return None

    start = max(0, anchor_at - window)
    end = min(len(n_hay), anchor_at + len(n_needle) + window)
    return n_hay[start:end]


def validate_quote(quote: str, source: str) -> QuoteMatch:
    """Check that `quote` appears verbatim in `source`.

    Accepts either a raw quote or Markdown blockquote lines ('> ...').
    """
    quote = _blockquote_to_text(quote)

    n_quote = normalize(quote)
    if not n_quote:
        return QuoteMatch(MatchStatus.MISSING, note="quote is empty")

    n_source = normalize(source)
    index = n_source.find(n_quote)
    if index >= 0:
        return QuoteMatch(MatchStatus.EXACT, index=index)

    a_quote = normalize_aggressive(quote)
    a_source = normalize_aggressive(source)
    if a_quote and a_quote in a_source:
        return QuoteMatch(
            MatchStatus.LOOSE,
            context=find_context(quote, source),
            note=(
                "matched only after ignoring hyphens and spaces -- usually a PDF "
                "line-break artifact, but confirm the quote was not reworded"
            ),
        )

    return QuoteMatch(
        MatchStatus.MISSING,
        context=find_context(quote, source),
        note="quote not found in source document",
    )


def describe_failure(quote: str, match: QuoteMatch, width: int = 78) -> str:
    """Human-readable explanation of a failed or flagged match.

    A bare "validation failed" costs an hour of guessing; showing both
    normalized strings makes the cause obvious in seconds.
    """
    lines: list[str] = []
    lines.append(f"status: {match.status.value}")
    if match.note:
        lines.append(f"reason: {match.note}")
    lines.append("")
    lines.append("your quote, normalized:")
    lines.extend(_wrap(normalize(_blockquote_to_text(quote)), width, "  "))
    lines.append("")
    if match.context:
        lines.append("nearest source text, normalized:")
        lines.extend(_wrap(match.context, width, "  "))
        lines.append("")
        lines.append("fix: copy the quote from the source .txt, not the PDF viewer.")
    else:
        lines.append("no similar text found anywhere in the source document.")
        lines.append("fix: this clause may belong to a different document, or the")
        lines.append("     quote may have been written from memory rather than copied.")
    return "\n".join(lines)


def _wrap(text: str, width: int, indent: str) -> list[str]:
    out, line = [], indent
    for word in text.split():
        if len(line) + len(word) + 1 > width and line != indent:
            out.append(line)
            line = indent
        line += ("" if line == indent else " ") + word
    if line != indent:
        out.append(line)
    return out or [indent + "(empty)"]
