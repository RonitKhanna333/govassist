"""The conversational layer: what did the person just say, and what now.

Before this, every message was only ever mined for an answer to the question
on screen. "What documents do I need?" extracted nothing, so the same
question came straight back; after a verdict, anything typed re-sent the
identical explanation. That is a form with a text box, not a conversation.

Two jobs, both deliberately narrow:

* `classify` -- is this an answer to the pending question, a question of
  their own, or chat? One FAST-tier call, and only when the deterministic
  parser in api/rules/spoken.py couldn't place the message on its own.
* `answer_question` -- answer from the scheme's own clauses and nothing else,
  then run the same verifier the verdict explanation goes through. If the
  clauses don't cover it, the answer is a plain "I don't have that" -- never
  an improvisation.

Neither job decides eligibility. The rule engine still does that, from
recorded answers only.

Retrieval note: the whole clause set is passed rather than a retrieved
subset. With 28 clauses that is small enough to fit comfortably and avoids a
retriever that could silently drop the one clause that mattered; embedding
retrieval (docs/phase2-design.md) becomes necessary when schemes get large.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from api.agents import verifier
from api.agents._json import extract_json
from api.agents.llm import LLMError, LLMProvider, Tier
from api.agents.prompts import load as load_prompt
from api.rules.engine import Citation

_INTENT = load_prompt("intent")
_ANSWER = load_prompt("answer_question")


@dataclass
class Intent:
    kind: str                 # "answer" | "question" | "chat"
    value: object = None      # True / False / number, when kind == "answer"


def classify(llm: LLMProvider, pending_question: str | None,
             pending_kind: str | None, message: str) -> Intent:
    """Degrades to "question" rather than "chat" when the model can't be
    reached: a real question answered with "I don't have that" is a smaller
    failure than a real question ignored."""
    user = (
        f"Question the helper asked: {pending_question or '(none -- the check is finished)'}\n"
        f"Kind of answer expected: {pending_kind or 'none'}\n"
        f"Person's message: {message}"
    )
    try:
        parsed = extract_json(llm.complete(_INTENT, user, Tier.FAST))
    except LLMError:
        return Intent("question")

    if not isinstance(parsed, dict):
        return Intent("question")

    kind = parsed.get("type")
    if kind not in ("answer", "question", "chat"):
        kind = "question"

    raw = parsed.get("value")
    value: object = None
    if pending_kind == "number":
        try:
            number = float(raw)
            value = int(number) if number.is_integer() else number
        except (TypeError, ValueError):
            value = None
    elif isinstance(raw, str) and raw.lower() in ("yes", "no"):
        value = raw.lower() == "yes"
    elif isinstance(raw, bool):
        value = raw

    return Intent(kind, value)


@dataclass
class Reply:
    text: str | None                       # None -> caller shows "I don't have that"
    citations: list[Citation] = field(default_factory=list)
    # Rate limited. Distinct from "unknown": saying "I don't have that
    # information" when the real cause was a throttle tells the person the
    # scheme doesn't cover something it may well cover.
    busy: bool = False


def answer_question(llm: LLMProvider, question: str,
                    clauses: list[Citation]) -> Reply:
    if not clauses:
        return Reply(None)

    by_id = {c.clause_id: c for c in clauses}
    facts = "\n".join(f"[{c.clause_id}] {c.plain}" for c in clauses)
    base = f"Question: {question}\n\nFacts:\n{facts}"

    avoid: list[str] = []
    for _ in range(2):
        user = base
        if avoid:
            listed = "\n".join(f"- {claim}" for claim in avoid)
            user += (
                "\n\nYour previous answer included these claims, which the facts do "
                f"not support. Leave them out entirely:\n{listed}"
            )

        try:
            parsed = extract_json(llm.complete(_ANSWER, user, Tier.REASONING))
        except LLMError as exc:
            return Reply(None, busy=exc.rate_limited)

        if not isinstance(parsed, dict) or not parsed.get("known"):
            return Reply(None)

        text = str(parsed.get("answer") or "").strip()
        used = [by_id[i] for i in parsed.get("used") or [] if i in by_id]
        if not text or not used:
            # An answer that cites nothing is an answer that can't be checked.
            return Reply(None)

        # Same gate as the verdict explanation: every claim must be in the
        # facts it says it used.
        check = verifier.verify(llm, text, used)
        if check.ok:
            return Reply(text, used)
        if not check.checked:
            return Reply(None, busy=check.busy)

        # When every flagged claim is a verbatim sentence of the answer, cut
        # them: the rest was already checked and passed. Saves two model
        # calls, which matters on a rate-limited free tier.
        trimmed = text
        if check.unsupported_claims and all(
            claim.strip() and claim.strip() in trimmed for claim in check.unsupported_claims
        ):
            for claim in check.unsupported_claims:
                trimmed = trimmed.replace(claim.strip(), "")
            trimmed = " ".join(trimmed.split())
            if len(trimmed) >= 20:
                return Reply(trimmed, used)

        # One recompose, naming what to drop -- same as the verdict path.
        # The first attempt at "how much will I get?" was right about the 35%
        # subsidy and the Rs 10 lakh cap, then added one speculative sentence;
        # discarding the whole answer for that turned a good reply into "I
        # don't have that information", which was simply false.
        avoid = check.unsupported_claims

    return Reply(None)
