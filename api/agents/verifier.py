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

_SYSTEM = load_prompt("verifier", 2)


@dataclass
class VerificationResult:
    ok: bool
    unsupported_claims: list[str]
    checked: bool  # False if the verifier itself couldn't run (LLM failure) --
                   # distinct from `ok`, because "couldn't check" must never be
                   # treated the same as "checked, and it's fine"
    busy: bool = False  # the check didn't run because of a rate limit


def verify(llm: LLMProvider, draft: str, citations: list[Citation],
           verdict: str | None = None) -> VerificationResult:
    # The verifier must see exactly what the composer saw, determination
    # included. Given only the rule text, it correctly flagged a correct
    # explanation of a denial as unsupported -- "you do not meet this" is an
    # assertion about the person, and the clause alone never says they
    # failed it. The engine's finding is the missing half of the evidence.
    from api.agents.composer import determination_facts

    lines = [f"- {f}" for f in determination_facts(verdict or "", bool(citations))]
    lines += [f"- {c.plain}" for c in citations]
    facts = "\n".join(lines)
    user = f"Drafted answer:\n{draft}\n\nFacts:\n{facts}"

    try:
        raw = llm.complete(_SYSTEM, user, Tier.REASONING)
    except LLMError as exc:
        return VerificationResult(ok=False, unsupported_claims=[], checked=False,
                                  busy=getattr(exc, "rate_limited", False))

    parsed = extract_json(raw)

    # v2 asks for {"claims_checked": n, "unsupported": [...]} rather than an
    # entry per claim. The old shape echoed every claim in full, which blew
    # the output budget on a long answer and came back truncated -- parsed as
    # "couldn't check", withholding a correct explanation. `claims_checked`
    # is what distinguishes "ran, found nothing" from "never ran", which an
    # empty list alone cannot express.
    if isinstance(parsed, dict) and "claims_checked" in parsed:
        raw_unsupported = parsed.get("unsupported") or []
        unsupported = [str(c) for c in raw_unsupported if str(c).strip()]
        return VerificationResult(
            ok=not unsupported, unsupported_claims=unsupported, checked=True,
        )

    # Tolerate the v1 per-claim list so an older prompt still verifies.
    if isinstance(parsed, list):
        unsupported = [
            item.get("claim", "") for item in parsed
            if isinstance(item, dict) and item.get("status") == "UNSUPPORTED"
        ]
        return VerificationResult(
            ok=not unsupported, unsupported_claims=unsupported, checked=True,
        )

    # Anything else means the check did not happen. Never "fine by default".
    return VerificationResult(ok=False, unsupported_claims=[], checked=False)
