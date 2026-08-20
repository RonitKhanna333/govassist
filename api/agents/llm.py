"""Groq, and only Groq -- two tiers, picked by task, per docs/phase2-design.md.

Everything that calls an LLM in this codebase does it through the
`LLMProvider` protocol below, never by importing this module's `GroqLLM`
directly. That is what makes composer.py, verifier.py, and nlu.py testable
without a network call or an API key: tests inject a `FakeLLM` (see
tests/api/test_agents.py) that returns canned, deterministic text.

Reads GROQ_API_KEY from the environment lazily, at call time -- importing
this module never fails just because a key isn't set. Only actually calling
`GroqLLM.complete()` without one raises a clear error.

Uses Groq's OpenAI-compatible REST endpoint via `requests` (already a
dependency) rather than the `groq` SDK, specifically to avoid adding a new
dependency for a single POST request.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Protocol

import requests

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


class Tier(str, Enum):
    """Which of Groq's free-tier budgets a call should spend.

    FAST is for high-volume, low-difficulty calls (NLU extraction, routing)
    -- llama-3.1-8b-instant, a generous free daily cap.
    REASONING is for the two places an LLM can change what a user is told
    (composer, verifier) -- llama-3.3-70b-versatile, a tighter free daily
    cap, spent where quality actually matters.

    See docs/phase2-design.md ("LLM provider -- Groq, two tiers") for the
    numbers behind this split, and re-check them at groq.com before relying
    on a specific figure -- free-tier limits move.
    """

    FAST = "fast"
    REASONING = "reasoning"


_MODELS = {
    Tier.FAST: "llama-3.1-8b-instant",
    Tier.REASONING: "llama-3.3-70b-versatile",
}


class LLMError(RuntimeError):
    """Raised on a missing key, a network failure, or a non-2xx response.

    Deliberately one exception type for all three -- callers (composer,
    verifier, nlu) should treat "the LLM didn't answer" as one condition to
    degrade gracefully from, not branch on which specific thing went wrong.
    """


class LLMProvider(Protocol):
    def complete(self, system: str, user: str, tier: Tier) -> str:
        """Return the model's text response. Raises LLMError on failure."""
        ...


class GroqLLM:
    """The only production LLMProvider. Temperature 0 -- these calls
    explain or extract, they don't need creativity, and reproducibility
    matters more than variety when the output can affect what a user is
    told about their eligibility."""

    def __init__(self, api_key: str | None = None, timeout: float = 30.0) -> None:
        self._api_key = api_key  # if None, read from env lazily per call
        self._timeout = timeout

    def _key(self) -> str:
        key = self._api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise LLMError(
                "GROQ_API_KEY is not set. Get a free key at https://console.groq.com "
                "and export it -- this codebase calls no other LLM provider."
            )
        return key

    def complete(self, system: str, user: str, tier: Tier) -> str:
        try:
            response = requests.post(
                GROQ_CHAT_URL,
                headers={"Authorization": f"Bearer {self._key()}"},
                json={
                    "model": _MODELS[tier],
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise LLMError(f"Groq request failed: {exc}") from exc

        data = response.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"unexpected Groq response shape: {data}") from exc
