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

    FAST is for high-volume, low-difficulty calls (NLU extraction,
    routing), where a smaller model is enough to pull `age: 25` out of a
    sentence. REASONING is for the two places an LLM can change what a user
    is told (composer, verifier), where quality matters more than
    throughput.

    Which concrete model serves each tier is deliberately not stated here --
    see _DEFAULT_MODELS below for why that would go stale.
    """

    FAST = "fast"
    REASONING = "reasoning"


# Model ids are a moving target -- Groq retires and renames them, and these
# are NOT the ones this file originally shipped with. It launched with
# llama-3.1-8b-instant / llama-3.3-70b-versatile, which had been withdrawn by
# the time the key was first used in anger: every call returned 404, the
# composer swallowed it as "no grounded facts", and the cause looked exactly
# like a missing API key.
#
# So: treat these as config, not fact. `GET /health?probe=llm` reports what
# the provider actually said, and `GROQ_MODEL_FAST` / `GROQ_MODEL_REASONING`
# override them without a code change. The live list is at
# https://api.groq.com/openai/v1/models.
_DEFAULT_MODELS = {
    Tier.FAST: "openai/gpt-oss-20b",
    Tier.REASONING: "openai/gpt-oss-120b",
}

_MODEL_ENV = {
    Tier.FAST: "GROQ_MODEL_FAST",
    Tier.REASONING: "GROQ_MODEL_REASONING",
}


def model_for(tier: Tier) -> str:
    return os.environ.get(_MODEL_ENV[tier]) or _DEFAULT_MODELS[tier]


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
                    "model": model_for(tier),
                    "temperature": 0,
                    # Without an explicit ceiling the verifier's JSON came
                    # back truncated mid-object, which parsed as "couldn't
                    # check" and withheld a perfectly good answer. Cheap
                    # headroom beats a silent failure.
                    "max_tokens": 2000,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=self._timeout,
            )
            if response.status_code == 404:
                # The single most misleading failure this client can produce:
                # a retired model id looks identical to a broken key from the
                # outside, because both end as the composer's fallback.
                raise LLMError(
                    f"Groq has no model '{model_for(tier)}' (HTTP 404). The key is "
                    f"probably fine -- model ids get retired. Check "
                    f"https://api.groq.com/openai/v1/models and override with "
                    f"{_MODEL_ENV[tier]}."
                )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise LLMError(f"Groq request failed: {exc}") from exc

        data = response.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"unexpected Groq response shape: {data}") from exc
