"""The rule engine -- a thin wrapper, not a reimplementation.

Every decision is made by data/scripts/grammar.py's `evaluate_conditions`:
the same restricted, three-valued, tested-187-times interpreter the corpus
toolchain uses to validate rule packs, now given a live profile instead of a
static file. This module's only job is the plumbing grammar.py doesn't do:
load build/rules.v{n}.json off disk, resolve each decisive condition's
`clause` id to an actual citation (quote, page, source URL) via
clauses.jsonl, and hand back something an agent or a CLI can use directly.

If you find yourself writing eligibility logic in this file, stop -- it
belongs in grammar.py, reviewed the same way every rule condition already is.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import api._corpus_bridge  # noqa: F401 -- must run before importing grammar
import grammar  # noqa: E402
from parse_scheme import repo_root  # noqa: E402


@dataclass
class Citation:
    clause_id: str
    quote: str
    plain: str
    source_url: str
    page: int | None


@dataclass
class EngineResult:
    scheme: str
    version: int
    verdict: grammar.Verdict
    missing_attributes: list[str]
    next_question: str | None
    citations: list[Citation] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scheme": self.scheme,
            "version": self.version,
            "verdict": self.verdict.value,
            "missing_attributes": self.missing_attributes,
            "next_question": self.next_question,
            "citations": [c.__dict__ for c in self.citations],
        }


def _latest_json(scheme_dir: Path, prefix: str) -> Path | None:
    candidates = sorted(scheme_dir.glob(f"build/{prefix}.v*.json"))
    return candidates[-1] if candidates else None


def load_rules(scheme: str, root: Path) -> dict:
    scheme_dir = root / "data" / "schemes" / scheme
    path = _latest_json(scheme_dir, "rules")
    if path is None:
        raise FileNotFoundError(
            f"no build/rules.v*.json for '{scheme}' -- run "
            f"'python data/scripts/build.py --scheme {scheme}' first"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load_clauses(scheme: str, root: Path) -> dict[str, dict]:
    path = root / "data" / "schemes" / scheme / "build" / "clauses.jsonl"
    if not path.exists():
        raise FileNotFoundError(
            f"no build/clauses.jsonl for '{scheme}' -- run "
            f"'python data/scripts/build.py --scheme {scheme}' first"
        )
    clauses: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            clauses[row["id"]] = row
    return clauses


def decide(scheme: str, profile: dict, root: Path | None = None) -> EngineResult:
    """Evaluate `profile` against `scheme`'s current committed rule pack.

    `profile` is a flat dict of attribute -> value, matching the attribute
    vocabulary in the scheme's conditions (`age`, `annual_income`, ...). An
    attribute simply absent from `profile` is treated as not-yet-known, not
    as False -- see grammar.py's UNKNOWN for why that distinction is the
    whole point.
    """
    root = root or repo_root()
    rules = load_rules(scheme, root)
    clauses = load_clauses(scheme, root)

    decision = grammar.evaluate_conditions(
        rules["conditions"], profile, rules["decision"],
    )

    # Cite only the conditions that actually decided the outcome -- a
    # condition still UNKNOWN told us nothing yet, so it earns no citation.
    citations: list[Citation] = []
    for result in decision.results:
        if result.value is grammar.UNKNOWN or not result.clause:
            continue
        row = clauses.get(result.clause)
        if row is None:
            continue  # a condition citing a clause that build.py already
                      # would have rejected at validate.py -- defensive only
        citations.append(Citation(
            clause_id=row["id"], quote=row["quote"], plain=row["plain"],
            source_url=row["source_url"], page=row["page"],
        ))

    return EngineResult(
        scheme=scheme,
        version=rules["version"],
        verdict=decision.verdict,
        missing_attributes=decision.missing_attributes,
        next_question=decision.next_questions[0] if decision.next_questions else None,
        citations=citations,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate a profile against a scheme's committed rule pack.",
    )
    parser.add_argument("--scheme", required=True)
    parser.add_argument("--profile", required=True,
                        help="JSON object, e.g. '{\"age\": 25, \"is_unincorporated\": true}'")
    parser.add_argument("--root")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else repo_root()
    try:
        profile = json.loads(args.profile)
    except json.JSONDecodeError as exc:
        parser.error(f"--profile is not valid JSON: {exc}")
        return 2

    try:
        result = decide(args.scheme, profile, root)
    except FileNotFoundError as exc:
        print(f"[FAIL] {exc}")
        return 1

    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
