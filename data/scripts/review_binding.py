"""Is a recorded review still a review of what is committed now?

A gate approval in .state.json used to count as soon as its status said
"approved". That missed two things that both happened in this repository:

* **Who.** PMFME's Gate 4 and 24 clause approvals are recorded as "Codex";
  APY/PMJJBY/PMSBY gates say "Claude (AI assistant, on request) -- needs
  human confirmation". The gates exist so an approval is attributable to a
  person who actually looked; an agent's name is not that.
* **What.** PMFME's age condition changed from `profile.age >= 18` to
  `profile.age > 18` after Gate 5 was approved. The old approval kept
  counting for an expression nobody had reviewed.

So a decision is now valid only when it is (1) approved, (2) attributed to
a name that is not a known agent/automation label, and (3) bound to a
SHA-256 fingerprint of the exact content the reviewer was shown, which must
equal the fingerprint of the content committed today. Historical records
are never rewritten: a record without a binding is simply "unbound", which
means pending, never approved.

Fingerprints are computed from plain dicts so the same function serves
scheme.md (review.py, validate.py) and the generated build/ files the API
reads -- build.py copies `quote`, `plain`, `tests`, `expr` and `clause`
through unchanged, so both sides hash identically.

This module cannot prove a human made a decision; nothing in a file can.
It can refuse records that are visibly not human, and refuse records that
describe different content. review.py adds the rest by requiring an
interactive terminal and an explicit reviewer name.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

BINDING_VERSION = 1

# Valid per-item outcomes.
VALID = "valid"
PENDING = "pending"            # no decision, or not approved
UNATTRIBUTED = "unattributed"  # approved by an agent/automation label
UNBOUND = "unbound"            # approved before content binding existed
STALE = "stale"                # approved, but for different content

_NON_HUMAN = re.compile(
    r"codex|claude|chatgpt|\bgpt\b|copilot|gemini|\bllm\b|assistant|"
    r"\bagent\b|\bbot\b|automat|needs human confirmation|github-actions",
    re.IGNORECASE,
)
_PLACEHOLDER_NAMES = {"", "unknown", "root", "system", "admin", "user",
                      "reviewer", "actual human reviewer name"}


def is_attributable(by: Any) -> bool:
    """A name that could belong to a person. Not proof that it does."""
    if not isinstance(by, str):
        return False
    name = by.strip()
    if name.lower() in _PLACEHOLDER_NAMES:
        return False
    return not _NON_HUMAN.search(name)


def _sha(payload: Any) -> str:
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _squash(text: str | None) -> str:
    return " ".join((text or "").split())


def clause_payload(clause: dict) -> dict:
    """What a Gate 4 reviewer is shown for one clause and accepts."""
    return {
        "id": clause["id"],
        "type": clause.get("type") or "",
        "source": clause.get("source") or clause.get("source_id") or "",
        "quote": clause.get("quote") or "",
        "plain": _squash(clause.get("plain")),
        "tests": sorted(clause.get("tests") or []),
    }


def clause_fingerprint(clause: dict) -> str:
    return _sha(clause_payload(clause))


def condition_fingerprint(condition: dict, clauses_by_id: dict[str, dict]) -> str:
    """What a Gate 5 reviewer is shown for one condition: the expression
    and the exact quote it is checked against."""
    cited = clauses_by_id.get(condition.get("clause") or "") or {}
    return _sha({
        "id": condition["id"],
        "expr": _squash(condition.get("expr")),
        "clause": condition.get("clause") or "",
        "quote": cited.get("quote") or "",
    })


def clause_set_fingerprint(clauses: Iterable[dict]) -> str:
    """Gate 4 asks whether the clause SET is complete and correct."""
    return _sha(sorted(clause_fingerprint(c) for c in clauses))


def condition_set_fingerprint(conditions: Iterable[dict], decision: str,
                              clauses_by_id: dict[str, dict]) -> str:
    return _sha({
        "decision": _squash(decision),
        "conditions": sorted(condition_fingerprint(c, clauses_by_id)
                             for c in conditions),
    })


def binding(fingerprint: str) -> dict:
    """The fields review.py stores with a decision."""
    return {"binding": BINDING_VERSION, "content_sha256": fingerprint}


def judge(entry: dict | None, fingerprint: str) -> str:
    entry = entry or {}
    if entry.get("status") != "approved":
        return PENDING
    if not is_attributable(entry.get("by")):
        return UNATTRIBUTED
    if entry.get("binding") != BINDING_VERSION or not entry.get("content_sha256"):
        return UNBOUND
    if entry["content_sha256"] != fingerprint:
        return STALE
    return VALID


_EXPLAIN = {
    PENDING: "has no approval",
    UNATTRIBUTED: "is attributed to {by!r}, which is not an attributable human reviewer",
    UNBOUND: "was recorded without a content binding, so it cannot show what was reviewed",
    STALE: "was approved for different content than is committed now",
}


@dataclass
class Assessment:
    reviewed: bool
    gates: dict[str, str] = field(default_factory=dict)
    clauses: dict[str, str] = field(default_factory=dict)
    conditions: dict[str, str] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"reviewed": self.reviewed, "gates": self.gates,
                "reasons": self.reasons}


def assess(state: dict, clauses: list[dict], conditions: list[dict],
           decision: str) -> Assessment:
    """Judge every Gate 4/5 decision against the committed content."""
    by_id = {c["id"]: c for c in clauses}
    gates = state.get("gates") or {}
    clause_records = state.get("clauses") or {}
    condition_records = state.get("conditions") or {}

    result = Assessment(reviewed=False)

    def note(kind: str, name: str, verdict: str, entry: dict | None) -> None:
        if verdict != VALID:
            result.reasons.append(
                f"{kind} {name} " + _EXPLAIN[verdict].format(by=(entry or {}).get("by"))
            )

    for gate, fingerprint in (
        ("4_clauses", clause_set_fingerprint(clauses)),
        ("5_conditions", condition_set_fingerprint(conditions, decision, by_id)),
    ):
        verdict = judge(gates.get(gate), fingerprint)
        result.gates[gate] = verdict
        note("gate", gate, verdict, gates.get(gate))

    for clause in clauses:
        verdict = judge(clause_records.get(clause["id"]), clause_fingerprint(clause))
        result.clauses[clause["id"]] = verdict
        note("clause", clause["id"], verdict, clause_records.get(clause["id"]))

    for condition in conditions:
        verdict = judge(condition_records.get(condition["id"]),
                        condition_fingerprint(condition, by_id))
        result.conditions[condition["id"]] = verdict
        note("condition", condition["id"], verdict, condition_records.get(condition["id"]))

    result.reviewed = not result.reasons
    return result


# -- adapters ---------------------------------------------------------------


def scheme_content(scheme) -> tuple[list[dict], list[dict], str]:
    """(clauses, conditions, decision) from a parse_scheme.Scheme."""
    clauses = [{"id": c.id, "type": c.type, "source": c.source, "quote": c.quote,
                "plain": c.plain, "tests": list(c.tests)} for c in scheme.clauses]
    conditions = [{"id": c.id, "expr": c.expr, "clause": c.clause}
                  for c in scheme.conditions]
    return clauses, conditions, scheme.decision


def assess_scheme(scheme, state: dict) -> Assessment:
    return assess(state, *scheme_content(scheme))
