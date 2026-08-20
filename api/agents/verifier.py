"""Checks a drafted answer for claims the evidence doesn't support.

Uses the REASONING tier, same as composer.py, for the same reason: this is
the other of the two places an LLM can change what a user is told, and it's
the one place that catches the composer inventing something. "Be strict,
not generous" is in the prompt itself (verifier.v1.txt) -- an uncertain
verifier is a verifier that rubber-stamps.
"""

from __future__ import annotations

from dataclasses import dataclass

from api.agents._json import extract_json
from api.agents.llm import LLMError, LLMProvider, Tier
from api.agents.prompts import load as load_prompt
from api.rules.engine import Citation

_SYSTEM = load_prompt("verifier")


@dataclass
class VerificationResult:
    ok: bool
    unsupported_claims: list[str]
    checked: bool  # False if the verifier itself couldn't run (LLM failure) --
                   # distinct from `ok`, because "couldn't check" must never be
                   # treated the same as "checked, and it's fine"


def verify(llm: LLMProvider, draft: str, citations: list[Citation]) -> VerificationResult:
    facts = "\n".join(f"- {c.plain}" for c in citations)
    user = f"Drafted answer:\n{draft}\n\nFacts:\n{facts}"

    try:
        raw = llm.complete(_SYSTEM, user, Tier.REASONING)
    except LLMError:
        return VerificationResult(ok=False, unsupported_claims=[], checked=False)

    parsed = extract_json(raw)
    if not isinstance(parsed, list):
        # The verifier didn't return a parseable claim list -- treat as
        # "could not check", never as "everything is fine".
        return VerificationResult(ok=False, unsupported_claims=[], checked=False)

    unsupported = [
        item.get("claim", "") for item in parsed
        if isinstance(item, dict) and item.get("status") == "UNSUPPORTED"
    ]
    return VerificationResult(ok=not unsupported, unsupported_claims=unsupported, checked=True)
