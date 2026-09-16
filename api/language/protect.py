"""Entity protection: the thing that stops translation corrupting the facts.

Machine translation will happily turn Rs.10.0 lakh into Rs.100 lakh, shift a
deadline by a month, and translate "PM-KISAN" into a literal phrase. Every
one of those is a wrong answer that reads perfectly fluently -- the worst
kind, because nothing downstream flags it.

So: before any translate() call, protected spans are replaced with sentinel
tokens; after it, they're restored. Sentinels are bracketed with U+27E6/27E7
(MATHEMATICAL WHITE SQUARE BRACKET) around a bare ASCII index. That choice
is deliberate -- no Indic NMT model reorders or translates a token that
contains no letters of any language it knows, and these brackets survive
round-tripping where ASCII [[0]] sometimes gets "helpfully" reformatted.

The invariant this module exists to hold, asserted in tests:

    restore(translate(protect(text))) preserves every protected entity
    byte-for-byte, or the translation is rejected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

OPEN, CLOSE = "⟦", "⟧"
# The "E" prefix is load-bearing, not decoration: without it the index digit
# sits at a word boundary, so the `number` pattern below matches it and
# re-protects the sentinel recursively, corrupting every entity after the
# first. With it, no pattern here can match inside a sentinel.
_SENTINEL_RE = re.compile(rf"{OPEN}\s*E(\d+)\s*{CLOSE}")

# Order matters: longest / most specific patterns first, so "Rs.10.0 lakh"
# is captured whole rather than as a bare number inside it.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("url", re.compile(r"https?://\S+")),
    # Currency with an Indian magnitude word attached.
    ("money", re.compile(
        r"(?:Rs\.?|₹|INR)\s*[\d,.]+(?:\s*(?:lakh|lakhs|crore|crores|thousand))?",
        re.IGNORECASE,
    )),
    ("percent", re.compile(r"\d+(?:\.\d+)?\s*%")),
    ("date", re.compile(
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"
        r"|\b\d{4}-\d{2}-\d{2}\b"
        r"|\b\d{1,2}(?:st|nd|rd|th)?\s+"
        r"(?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\b",
        re.IGNORECASE,
    )),
    ("clause_ref", re.compile(r"\b(?:Section|Clause|Para(?:graph)?)\s+[\w().]+",
                              re.IGNORECASE)),
    ("phone", re.compile(r"\b(?:\+91[-\s]?)?\d{10}\b")),
    ("number", re.compile(r"\b\d+(?:\.\d+)?\b")),
]


@dataclass
class Protected:
    text: str                   # text with sentinels substituted in
    entities: list[str]         # original spans, indexed by sentinel number

    def restore(self, translated: str) -> str:
        """Put the original spans back. Tolerates whitespace the model may
        have introduced inside a sentinel."""
        def swap(match: re.Match[str]) -> str:
            index = int(match.group(1))
            return self.entities[index] if index < len(self.entities) else match.group(0)

        return _SENTINEL_RE.sub(swap, translated)

    def survived(self, translated: str) -> bool:
        """Did every sentinel come back? A model that dropped or duplicated
        one has corrupted the answer, whatever the prose looks like."""
        found = sorted(int(m) for m in _SENTINEL_RE.findall(translated))
        return found == list(range(len(self.entities)))


def load_protected_terms(terms: list[str] | None = None) -> list[re.Pattern[str]]:
    """Scheme names, portal names, form names -- curated, never guessed.

    Sorted longest-first so "PM Formalisation of Micro Food Processing
    Enterprises" wins over a bare "PM" inside it.
    """
    if not terms:
        return []
    return [
        re.compile(re.escape(term), re.IGNORECASE)
        for term in sorted(terms, key=len, reverse=True)
    ]


def protect(text: str, extra_terms: list[str] | None = None) -> Protected:
    entities: list[str] = []
    working = text

    def substitute(pattern: re.Pattern[str], source: str) -> str:
        def swap(match: re.Match[str]) -> str:
            entities.append(match.group(0))
            return f"{OPEN}E{len(entities) - 1}{CLOSE}"
        return pattern.sub(swap, source)

    for pattern in load_protected_terms(extra_terms):
        working = substitute(pattern, working)

    for _, pattern in _PATTERNS:
        working = substitute(pattern, working)

    return Protected(text=working, entities=entities)
