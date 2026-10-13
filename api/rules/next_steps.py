"""'What should I do next?' -- a checklist built only from official text.

A verdict tells someone whether they qualify; it doesn't help them apply.
This turns a decided case into the next steps: what they could receive,
which documents to keep ready, where and how to apply, what happens after,
and -- just as important -- what is still unclear and should be confirmed.

Nothing here is generated. Every step is a committed clause (plain gloss,
verbatim quote, page, official source URL), chosen per scheme by
data/next_steps.json. When the reviewed corpus doesn't say something --
APY's guidelines, for instance, never say where to enrol -- the checklist
reports that gap and points to the official document and the authority
named in the scheme's frontmatter, rather than filling it from memory.

No model is involved, so the checklist works with zero secrets, exactly
like the verdict and citations.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from api.rules.engine import EngineResult, load_clauses, load_rules

SECTIONS = ("benefits", "documents", "apply", "after", "good_to_know")

# Which clause types may appear in each section. Enforced in tests, and
# again here, so a mis-filed id can never present an exclusion as a step.
SECTION_TYPES = {
    "benefits": {"benefit"},
    "documents": {"document"},
    "apply": {"procedure"},
    "after": {"procedure", "benefit"},
    "good_to_know": {"exclusion", "procedure"},
}

# Sections whose absence a person needs to hear about: without them they
# cannot act. A missing "good to know" is not a gap worth reporting.
REQUIRED_FOR_APPLYING = ("documents", "apply")


@lru_cache(maxsize=1)
def checklist_map() -> dict:
    path = Path(__file__).resolve().parents[2] / "data" / "next_steps.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _step(row: dict) -> dict:
    return {
        "clause_id": row["id"],
        "plain": row["plain"],
        "quote": row["quote"],
        "page": row.get("page"),
        "source_url": row["source_url"],
        "uncertain": bool(row.get("uncertain")),
    }


def build(scheme: str, result: EngineResult, root: Path, reviewed: bool) -> dict | None:
    """The checklist for a decided case, or None while questions remain."""
    verdict = result.verdict.value
    if verdict not in ("ELIGIBLE", "NOT_ELIGIBLE"):
        return None

    rules = load_rules(scheme, root)
    clauses = load_clauses(scheme, root)
    chosen = checklist_map().get(scheme, {})
    sources = rules.get("sources") or []

    sections: list[dict] = []
    gaps: list[str] = []
    if verdict == "ELIGIBLE":
        for key in SECTIONS:
            items = [
                _step(clauses[cid]) for cid in chosen.get(key, [])
                if cid in clauses and clauses[cid].get("type") in SECTION_TYPES[key]
            ]
            if items:
                sections.append({"key": key, "items": items})
            elif key in REQUIRED_FOR_APPLYING:
                gaps.append(key)

    # What still needs a person to confirm, most important first.
    confirm: list[dict] = []
    if not reviewed:
        confirm.append({"kind": "review_pending"})
    if verdict == "NOT_ELIGIBLE":
        for citation in result.failed_citations:
            row = clauses.get(citation.clause_id)
            if row:
                confirm.append({"kind": "failed", **_step(row)})
    seen = {item.get("clause_id") for item in confirm}
    for citation in result.citations:
        row = clauses.get(citation.clause_id)
        if row and row.get("uncertain") and row["id"] not in seen:
            confirm.append({"kind": "uncertain", **_step(row)})
            seen.add(row["id"])

    return {
        "status": verdict.lower(),
        "sections": sections,
        "gaps": gaps,
        "confirm": confirm,
        "authority": rules.get("authority"),
        "sources": [{"id": s.get("id"), "url": s.get("url")} for s in sources if s.get("url")],
    }
