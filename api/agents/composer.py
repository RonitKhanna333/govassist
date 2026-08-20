"""Drafts the English explanation of a verdict -- from evidence, not memory.

Uses the REASONING tier (llama-3.3-70b-versatile): this is one of the two
places (with verifier.py) an LLM can actually change what a user is told,
so it gets the tier with better quality, not the tier with the bigger free
daily cap. See docs/phase2-design.md.

The evidence it drafts from is exactly `api.rules.engine.decide()`'s own
`citations` -- the clauses that actually decided the verdict, already
resolved with their real quotes and source. Nothing here re-derives or
re-fetches evidence; if the composer and the verifier ever draw from
different evidence sets, the verification step stops meaning anything.
"""

from __future__ import annotations

from api.agents.llm import LLMError, LLMProvider, Tier
from api.agents.prompts import load as load_prompt
from api.rules.engine import Citation

_SYSTEM = load_prompt("composer")

FALLBACK_NO_EVIDENCE = (
    "I reached a decision but don't have grounded facts to explain it with. "
    "Rather than guess, I'll say so plainly: please check the official portal "
    "or a professional for this one."
)


def draft_answer(llm: LLMProvider, verdict: str, citations: list[Citation],
                 avoid: list[str] | None = None) -> str:
    """`avoid` is set on the one recompose pass (see agents/orchestrate.py)
    after the verifier found unsupported claims in a first draft -- told to
    the composer explicitly rather than silently retried, so a second wrong
    guess is less likely than a blind retry would produce."""
    if not citations:
        return FALLBACK_NO_EVIDENCE

    facts = "\n".join(f"- {c.plain}" for c in citations)
    user = f"Verdict: {verdict}\n\nFacts:\n{facts}"
    if avoid:
        avoided = "\n".join(f"- {claim}" for claim in avoid)
        user += (
            f"\n\nYour previous draft included claims not supported by the facts "
            f"above. Do not repeat them:\n{avoided}"
        )

    try:
        return llm.complete(_SYSTEM, user, Tier.REASONING).strip()
    except LLMError:
        return FALLBACK_NO_EVIDENCE
