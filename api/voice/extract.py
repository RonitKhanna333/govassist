"""Finding each answer in a call transcript -- by quoting, never by judging.

Bland has no field for "return these answers in this shape", so after the
call we get a transcript and have to locate the answers in it. A model is
used for that one narrow job: for each question, point at the words the
CALLER said in reply. It is not asked what the answer means.

Two checks keep that honest:

* every quote must appear verbatim in one of the caller's own turns -- a
  quote that doesn't is discarded, so an invented "haan ji" can't become a
  recorded yes;
* the quote then goes through the same deterministic parser as a typed
  answer (`read_answers` -> api/rules/spoken.py), so "पता नहीं" stays
  unknown however the model labelled it.
"""

from __future__ import annotations

import unicodedata

from api.agents.llm import LLMError, LLMProvider, Tier
from api.agents._json import extract_json

_SYSTEM = """You read a phone call transcript between a helpline agent and a \
caller. For each question id given, find what the CALLER said in reply to that \
question.

Rules:
- Copy the caller's words exactly as they appear in the transcript, in the \
same script and spelling. Do not translate, correct or summarise.
- Use only lines spoken by the caller, never the agent.
- If the caller did not answer that question, or the answer is unclear, use null.
- If the caller corrected themselves, copy the corrected answer.

Return ONLY a JSON object mapping each question id to the copied words or null."""


def _norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split()).lower()


def caller_turns(transcripts: list | None, concatenated: str | None) -> list[str]:
    """The caller's lines. Bland marks them user == "user"."""
    turns = []
    for turn in transcripts or []:
        if isinstance(turn, dict) and turn.get("user") == "user" and turn.get("text"):
            turns.append(str(turn["text"]))
    if not turns and concatenated:
        # Fallback: "user: ..." lines in the flat transcript.
        for line in concatenated.splitlines():
            head, _, rest = line.partition(":")
            if head.strip().lower() == "user" and rest.strip():
                turns.append(rest.strip())
    return turns


def _render(transcripts: list | None, concatenated: str | None) -> str:
    lines = []
    for turn in transcripts or []:
        if isinstance(turn, dict) and turn.get("text") and turn.get("user") in ("user", "assistant"):
            who = "CALLER" if turn["user"] == "user" else "AGENT"
            lines.append(f"{who}: {turn['text']}")
    return "\n".join(lines) or (concatenated or "")


def find_answers(llm: LLMProvider, questions: dict[str, str],
                 transcripts: list | None, concatenated: str | None) -> dict[str, str]:
    """attribute -> the caller's own words. Unverifiable quotes are dropped."""
    turns = caller_turns(transcripts, concatenated)
    if not turns or not questions:
        return {}
    asked = "\n".join(f"- {attr}: {ask}" for attr, ask in questions.items())
    user = f"Questions:\n{asked}\n\nTranscript:\n{_render(transcripts, concatenated)}"
    try:
        parsed = extract_json(llm.complete(_SYSTEM, user, Tier.FAST))
    except LLMError:
        return {}
    if not isinstance(parsed, dict):
        return {}

    said = [_norm(t) for t in turns]
    found: dict[str, str] = {}
    for attribute, quote in parsed.items():
        if attribute not in questions or not isinstance(quote, str) or not quote.strip():
            continue
        if any(_norm(quote) in turn for turn in said):
            found[attribute] = quote.strip()
    return found
