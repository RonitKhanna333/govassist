"""Splitting text into TTS-sized pieces, per script.

Two reasons this isn't `text.split(".")`:

1. Devanagari and Gurmukhi end sentences with a danda (।), not a full stop.
   Splitting Hindi or Punjabi on "." alone yields one giant unsplittable
   blob, which then exceeds the TTS payload limit and fails as a whole
   instead of streaming.
2. Time-to-first-audio is what makes voice feel responsive. Synthesising
   sentence one and starting playback while the rest renders in the
   background needs sentence boundaries that are actually correct for the
   script being spoken.

A sentence longer than `max_chars` on its own is split at clause boundaries
rather than mid-word, and if it still doesn't fit it is returned oversized
for the caller to drop to text -- never truncated, because truncated audio
of an eligibility rule is a wrong answer delivered confidently.
"""

from __future__ import annotations

import re

from api.language.registry import get

DEFAULT_MAX_CHARS = 400
_CLAUSE_BREAKS = (";", ",", " -- ", " — ")


def split_sentences(text: str, locale: str) -> list[str]:
    terminators = get(locale).sentence_terminators
    pattern = "|".join(re.escape(t) for t in terminators)
    parts = re.split(rf"(?<=(?:{pattern}))\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _split_long(sentence: str, max_chars: int) -> list[str]:
    if len(sentence) <= max_chars:
        return [sentence]

    for marker in _CLAUSE_BREAKS:
        if marker in sentence:
            pieces, current = [], ""
            for piece in sentence.split(marker):
                candidate = f"{current}{marker}{piece}" if current else piece
                if len(candidate) > max_chars and current:
                    pieces.append(current.strip())
                    current = piece
                else:
                    current = candidate
            if current.strip():
                pieces.append(current.strip())
            if all(len(p) <= max_chars for p in pieces):
                return pieces

    # Nothing safe to split on. Hand it back whole and oversized -- the
    # caller decides to drop to text rather than speak half a rule.
    return [sentence]


def chunk_for_tts(text: str, locale: str,
                  max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    """Sentence-aligned chunks, each within `max_chars` where possible."""
    chunks: list[str] = []
    current = ""

    for sentence in split_sentences(text, locale):
        for piece in _split_long(sentence, max_chars):
            if not current:
                current = piece
            elif len(current) + 1 + len(piece) <= max_chars:
                current = f"{current} {piece}"
            else:
                chunks.append(current)
                current = piece

    if current:
        chunks.append(current)
    return chunks
