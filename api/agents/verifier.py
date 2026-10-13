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

    unsupported = _unsupported_claims(extract_json(raw), factual=bool(draft.strip()))
    if unsupported is None:
        # Anything malformed means the check did not happen. Never "fine by
        # default": `[]`, `{"claims_checked": 0}` and `[{"status": "UNKNOWN"}]`
        # each used to come back as checked-and-fine for a factual draft.
        return VerificationResult(ok=False, unsupported_claims=[], checked=False)
    return VerificationResult(
        ok=not unsupported, unsupported_claims=unsupported, checked=True,
    )


_V1_STATUSES = {"SUPPORTED", "UNSUPPORTED"}


def _unsupported_claims(parsed: object, factual: bool) -> list[str] | None:
    """The unsupported claims from a well-formed result, or None if the
    result does not prove a check actually ran.

    v2 asks for {"claims_checked": n, "unsupported": [...]} rather than an
    entry per claim. The old shape echoed every claim in full, which blew the
    output budget on a long answer and came back truncated. `claims_checked`
    is what distinguishes "ran, found nothing" from "never ran", which an
    empty list alone cannot express -- so it must be a real count, and a
    factual draft must have had at least one claim checked.
    """
    if isinstance(parsed, dict):
        count = parsed.get("claims_checked")
        listed = parsed.get("unsupported")
        # bool is an int in Python; `true` is not a count.
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            return None
        if factual and count < 1:
            return None
        if not isinstance(listed, list):
            return None  # must be present, even when empty
        if not all(isinstance(c, str) and c.strip() for c in listed):
            return None
        if len(listed) > count:
            return None  # more failures than claims checked: incoherent
        return [c.strip() for c in listed]

    # The v1 per-claim list, so an older prompt still verifies -- but only
    # when every entry is a claim with a status this code knows.
    if isinstance(parsed, list):
        if factual and not parsed:
            return None
        claims: list[str] = []
        for item in parsed:
            if not isinstance(item, dict) or item.get("status") not in _V1_STATUSES:
                return None
            claim = item.get("claim")
            if not isinstance(claim, str) or not claim.strip():
                return None
            if item["status"] == "UNSUPPORTED":
                claims.append(claim.strip())
        return claims

    return None
