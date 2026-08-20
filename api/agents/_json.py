"""Pulling a JSON value out of an LLM's text response.

Models reliably wrap JSON in markdown fences even when told not to, and
occasionally add a sentence before or after it. Both nlu.py and verifier.py
need exactly this same tolerant extraction, so it lives once here.
"""

from __future__ import annotations

import json
import re

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json(text: str) -> object | None:
    """Best-effort JSON extraction. Returns None rather than raising --
    callers treat 'the model didn't return parseable JSON' as a normal
    degrade-gracefully case, not an exception to propagate."""
    candidates = [text.strip()]
    fence_match = _FENCE.search(text)
    if fence_match:
        candidates.insert(0, fence_match.group(1).strip())

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    # last resort: the first {...} or [...] span in the text
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue

    return None
