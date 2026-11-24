"""Finding each answer in a call transcript -- by pointing, never by judging.

Bland has no field for "return these answers in this shape", so after the
call we get a transcript and have to locate the answers in it. A model is
used for that one narrow job: for each question, say WHICH of the caller's
numbered lines answers it. It is not asked what the answer means, and it
never supplies the words.

Two things keep that honest:

* the words recorded are always the transcript's own line -- the model only
  gives a line number, so it can't put words in the caller's mouth, and it
  can't lose an answer by "correcting" a spelling (Bland writes हां, models
  write हाँ; an earlier quote-matching version discarded every real answer
  over exactly that);
* the line then goes through the same deterministic parser as a typed
  answer (`read_answers` -> api/rules/spoken.py), so "पता नहीं" stays
  unknown however the model labelled it.
"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher

from api.agents._json import extract_json
from api.agents.llm import LLMError, LLMProvider, Tier

log = logging.getLogger(__name__)

_SYSTEM = """You read a phone call transcript between a helpline agent and a \
caller. The caller's lines are numbered like [C3]. For each question id given, \
say which numbered caller line answers that question.

Rules:
- Answer with the line NUMBER only (3 for [C3]), never with words.
- Pick the caller line that replies to the agent asking that question. If the \
caller corrected themselves, pick the line with the corrected answer.
- If the caller never answered that question, or you are unsure, use null.

Return ONLY a JSON object mapping each question id to a line number or null, \
for example {"age": 3, "is_woman": null}."""


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


def _render(transcripts: list | None, concatenated: str | None) -> tuple[str, list[str]]:
    """The transcript with caller lines numbered [C1], [C2]...; and those lines."""
    lines: list[str] = []
    turns: list[str] = []
    for turn in transcripts or []:
        if not (isinstance(turn, dict) and turn.get("text")):
            continue
        if turn.get("user") == "user":
            turns.append(str(turn["text"]))
            lines.append(f"[C{len(turns)}] CALLER: {turn['text']}")
        elif turn.get("user") == "assistant":
            lines.append(f"AGENT: {turn['text']}")
    if not turns:
        for text in caller_turns(None, concatenated):
            turns.append(text)
            lines.append(f"[C{len(turns)}] CALLER: {text}")
    return "\n".join(lines), turns


def _coverage(ask: str, said: str) -> float:
    """Share of the question's characters the agent's line contains, in order."""
    ask = re.sub(r"\s*\([^)]*\)", "", ask).strip()  # agents drop "(पोस्ट ऑफ़िस)"
    if not ask:
        return 0.0
    blocks = SequenceMatcher(None, ask, said, autojunk=False).get_matching_blocks()
    return sum(b.size for b in blocks) / len(ask)


def match_by_question(questions: dict[str, str], transcripts: list | None) -> dict[str, str]:
    """No model: find the agent line that asks each question (the script's
    own wording) and take the caller's next line. A later re-ask wins, so a
    corrected answer is kept. Words are still the transcript's own."""
    found: dict[str, str] = {}
    turns = [t for t in transcripts or [] if isinstance(t, dict) and t.get("text")]
    for i, turn in enumerate(turns):
        if turn.get("user") != "assistant":
            continue
        score, attribute = max(((_coverage(ask, str(turn["text"])), attr)
                                for attr, ask in questions.items()), default=(0.0, None))
        if attribute is None or score < 0.8:
            continue
        reply = next((t for t in turns[i + 1:] if t.get("user") == "user"), None)
        if reply is not None:
            found[attribute] = str(reply["text"]).strip()
    return found


def find_answers(llm: LLMProvider, questions: dict[str, str],
                 transcripts: list | None, concatenated: str | None) -> dict[str, str]:
    """attribute -> the caller's own line, exactly as transcribed."""
    rendered, turns = _render(transcripts, concatenated)
    if not turns or not questions:
        log.info("extract: nothing to read (caller lines=%d)", len(turns))
        return {}
    # Fallback for anything the model fails on (seen live: no JSON at all).
    fallback = match_by_question(questions, transcripts)
    asked = "\n".join(f"- {attr}: {ask}" for attr, ask in questions.items())
    user = f"Questions:\n{asked}\n\nTranscript:\n{rendered}"
    try:
        raw = llm.complete(_SYSTEM, user, Tier.FAST)
    except LLMError as exc:
        log.warning("extract: model call failed: %s; matched %d by question",
                    type(exc).__name__, len(fallback))
        return fallback
    parsed = extract_json(raw)
    if not isinstance(parsed, dict):
        log.warning("extract: model did not return a JSON object; matched %d by question",
                    len(fallback))
        return fallback

    found: dict[str, str] = dict(fallback)
    for attribute, pointer in parsed.items():
        if attribute not in questions or pointer is None or isinstance(pointer, bool):
            continue
        index = _line_number(pointer)
        if index is not None and 1 <= index <= len(turns):
            found[attribute] = turns[index - 1].strip()
    log.info("extract: caller lines=%d, model pointed at %d, kept %d",
             len(turns), sum(v is not None for v in parsed.values()), len(found))
    return found


def _line_number(pointer) -> int | None:
    """3, "3", "C3", "[C3]" -> 3."""
    if isinstance(pointer, int):
        return pointer
    if isinstance(pointer, float) and pointer.is_integer():
        return int(pointer)
    if isinstance(pointer, str):
        digits = "".join(ch for ch in pointer if ch.isdigit())
        return int(digits) if digits else None
    return None
