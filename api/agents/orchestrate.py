"""The two loops from docs/phase2-design.md's sequence diagram, as one unit.

    draft -> verify -> [unsupported claim found] -> recompose once -> verify
                                                                          |
                                          [still unsupported, or verifier
                                           itself couldn't run] -> honest
                                           "not confident" fallback

This is deliberately its own module, separate from the FastAPI route, so the
compose/verify/recompose/fallback sequence is unit-testable with a scripted
FakeLLM (see tests/api/test_agents.py) without touching HTTP at all.
"""

from __future__ import annotations

from api.agents import composer, verifier
from api.agents.llm import LLMProvider
from api.rules.engine import Citation

FALLBACK_UNVERIFIED = (
    "I can't confidently answer that from what I have -- rather than guess, "
    "I'd rather say so plainly. Please check the official portal or a "
    "professional for this one."
)


def compose_verified_answer(llm: LLMProvider, verdict: str,
                            citations: list[Citation]) -> str:
    draft = composer.draft_answer(llm, verdict, citations)
    if draft == composer.FALLBACK_NO_EVIDENCE:
        return draft  # nothing to verify -- the composer already declined

    result = verifier.verify(llm, draft, citations)
    if result.ok:
        return draft
    if not result.checked:
        # The verifier couldn't run at all -- an unverified answer must never
        # ship silently just because the check itself failed.
        return FALLBACK_UNVERIFIED

    draft = composer.draft_answer(llm, verdict, citations, avoid=result.unsupported_claims)
    if draft == composer.FALLBACK_NO_EVIDENCE:
        return draft

    result = verifier.verify(llm, draft, citations)
    if result.ok:
        return draft

    return FALLBACK_UNVERIFIED
