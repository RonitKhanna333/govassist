"""Slot-filler: pulls stated profile attributes out of free text.

Never asserts a fact about a rule -- only about the person, and only what
they actually said. Uses the FAST tier (llama-3.1-8b-instant): this is
extraction, not reasoning, and it's the highest-call-volume LLM use in the
whole flow (every turn with a message touches it), so it's exactly the case
the fast tier's generous free daily cap is for.

Degrades to "nothing extracted" rather than failing the whole turn: a
missed attribute just means the rule engine asks for it explicitly next,
which is the correct fallback the rule engine already has built in.
"""

from __future__ import annotations

from api.agents._json import extract_json
from api.agents.llm import LLMError, LLMProvider, Tier
from api.agents.prompts import load as load_prompt

_SYSTEM = load_prompt("nlu")


def extract_attributes(llm: LLMProvider, message: str,
                       known_attributes: list[str]) -> dict:
    """Returns a dict of attribute -> value for whatever `message` states,
    restricted to `known_attributes`. Never raises -- see module docstring."""
    if not message.strip() or not known_attributes:
        return {}

    user = (
        f"Attribute names this scheme cares about: {', '.join(sorted(known_attributes))}\n\n"
        f"Message: {message}"
    )

    try:
        raw = llm.complete(_SYSTEM, user, Tier.FAST)
    except LLMError:
        return {}

    parsed = extract_json(raw)
    if not isinstance(parsed, dict):
        return {}

    # Defense in depth: never let a hallucinated key leak into the profile,
    # even though the prompt already says to use only the given names.
    return {k: v for k, v in parsed.items() if k in known_attributes}
