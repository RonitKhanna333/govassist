"""The acceptance gates. Run in CI on every pull request.

    python data/scripts/validate.py --scheme pm-kisan
    python data/scripts/validate.py --all

Eight checks, each of which corresponds to a way the corpus could quietly stop
being trustworthy:

  1  every blockquote appears verbatim in its source .txt
  2  every condition points at a clause that exists in the same file
  3  every clause cites a source declared in the frontmatter
  4  every source checksum matches the committed PDF
  5  every expression parses under the restricted grammar
  6  clause ids are unique and attribute naming is consistent
  7  clause types are recognised and clauses carry the fields they need
  8  the corpus agrees with the recorded review decisions

Exit code is 1 if anything fails, so CI blocks the merge.

Every span failure prints both normalized strings and the nearest source text.
A bare "validation failed" costs an hour of guessing; showing the two strings
side by side usually makes the cause obvious in seconds.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass, field
from pathlib import Path

import console
from grammar import referenced_attributes, validate_expr
from normalize import MatchStatus, describe_failure, validate_quote
from parse_scheme import (
    CLAUSE_TYPES,
    Scheme,
    SchemeParseError,
    load_scheme,
    repo_root,
    scheme_dir,
)
from state import APPROVED, load_state

SEVERITY_ERROR = "error"
SEVERITY_WARN = "warn"


@dataclass
class Finding:
    check: str
    severity: str
    where: str
    message: str
    detail: str = ""


@dataclass
class Result:
    scheme: str
    findings: list[Finding] = field(default_factory=list)

    def error(self, check: str, where: str, message: str, detail: str = "") -> None:
        self.findings.append(Finding(check, SEVERITY_ERROR, where, message, detail))

    def warn(self, check: str, where: str, message: str, detail: str = "") -> None:
        self.findings.append(Finding(check, SEVERITY_WARN, where, message, detail))

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == SEVERITY_ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == SEVERITY_WARN]

    @property
    def ok(self) -> bool:
        return not self.errors


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------


def check_quotes(scheme: Scheme, directory: Path, result: Result) -> None:
    """1 -- the provenance check. Everything else is bookkeeping next to this."""
    for clause in scheme.clauses:
        if not clause.quote.strip():
            result.error("quotes", clause.id, "clause has no blockquote")
            continue

        source = scheme.source(clause.source)
        if source is None:
            continue  # reported by check_sources

        base = scheme.path.parent if scheme.path else directory
        txt = base / source.txt
        if not txt.exists():
            result.error("quotes", clause.id,
                         f"source text not found: {source.txt}")
            continue

        text = txt.read_text(encoding="utf-8", errors="replace")
        match = validate_quote(clause.quote, text)

        if match.status is MatchStatus.MISSING:
            result.error("quotes", clause.id,
                         "quote does not appear in the source document",
                         describe_failure(clause.quote, match))
        elif match.status is MatchStatus.LOOSE:
            result.warn("quotes", clause.id,
                        "quote matched only after ignoring hyphens and spaces",
                        describe_failure(clause.quote, match))


def check_condition_clauses(scheme: Scheme, result: Result) -> None:
    """2 -- every rule must trace to a clause in this same file."""
    known = set(scheme.clause_ids)
    for condition in scheme.conditions:
        if not condition.clause:
            result.error("conditions", condition.id,
                         "condition has no 'clause' -- every rule must cite one")
        elif condition.clause not in known:
            result.error("conditions", condition.id,
                         f"cites clause '{condition.clause}', which does not exist")


def check_sources(scheme: Scheme, result: Result) -> None:
    """3 -- every clause names a declared source."""
    known = {s.id for s in scheme.sources}
    if not scheme.sources:
        result.error("sources", scheme.scheme, "frontmatter declares no sources")
        return
    for clause in scheme.clauses:
        if not clause.source:
            result.error("sources", clause.id, "clause does not name a source")
        elif clause.source not in known:
            result.error("sources", clause.id,
                         f"cites source '{clause.source}', not declared in frontmatter")


def check_checksums(scheme: Scheme, directory: Path, result: Result) -> None:
    """4 -- the committed PDF is the one the corpus was authored from."""
    base = scheme.path.parent if scheme.path else directory
    for source in scheme.sources:
        if not source.checksum:
            result.warn("checksums", source.id, "no checksum recorded")
            continue
        pdf = base / source.pdf if source.pdf else None
        if pdf is None or not pdf.exists():
            result.warn("checksums", source.id,
                        f"source PDF not committed: {source.pdf or '(none)'}")
            continue
        digest = hashlib.sha256()
        with pdf.open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        actual = "sha256:" + digest.hexdigest()
        if actual != source.checksum:
            result.error(
                "checksums", source.id,
                "the committed PDF does not match the recorded checksum",
                f"recorded: {source.checksum}\nactual:   {actual}\n"
                "The source document changed after the corpus was authored. "
                "Re-review the clauses against the new version before updating "
                "the checksum.",
            )


def check_expressions(scheme: Scheme, result: Result) -> None:
    """5 -- rule packs are data and must not be able to execute anything."""
    for condition in scheme.conditions:
        if not condition.expr.strip():
            result.error("expressions", condition.id, "condition has no expression")
            continue
        for problem in validate_expr(condition.expr):
            result.error("expressions", condition.id, problem,
                         f"expr: {condition.expr}")


def check_consistency(scheme: Scheme, result: Result) -> None:
    """6 -- ids unique, attribute vocabulary consistent."""
    seen: set[str] = set()
    for clause in scheme.clauses:
        if clause.id in seen:
            result.error("consistency", clause.id, "duplicate clause id")
        seen.add(clause.id)

    condition_ids: set[str] = set()
    for condition in scheme.conditions:
        if condition.id in condition_ids:
            result.error("consistency", condition.id, "duplicate condition id")
        condition_ids.add(condition.id)

    # Attributes named in expressions should also appear in the cited clause's
    # `tests`. A mismatch usually means the clause and the rule drifted apart.
    for condition in scheme.conditions:
        if validate_expr(condition.expr):
            continue
        used = set(referenced_attributes(condition.expr))
        clause = scheme.clause(condition.clause)
        if clause is None:
            continue
        declared = set(clause.tests)
        missing = used - declared
        if missing:
            result.warn(
                "consistency", condition.id,
                f"expression reads {sorted(missing)} but clause "
                f"'{clause.id}' does not list them in tests",
            )


def check_clause_shape(scheme: Scheme, result: Result) -> None:
    """7 -- clauses carry what downstream consumers need."""
    for clause in scheme.clauses:
        if clause.type not in CLAUSE_TYPES:
            result.error("shape", clause.id,
                         f"unknown type '{clause.type}' "
                         f"(expected one of: {', '.join(sorted(CLAUSE_TYPES))})")
        if not clause.plain.strip():
            result.warn("shape", clause.id,
                        "no Plain gloss -- the composer has nothing to paraphrase")
        if not clause.aliases:
            result.warn("shape", clause.id,
                        "no Aliases -- retrieval will rely on formal wording only")
        if clause.uncertain:
            result.warn("shape", clause.id,
                        f"flagged uncertain: {clause.note or 'no note given'}")


def check_review_state(scheme: Scheme, directory: Path, result: Result) -> None:
    """8 -- the corpus matches what was actually reviewed."""
    state = load_state(scheme.scheme, directory)

    if not state.is_approved("4_clauses"):
        result.warn("review", scheme.scheme,
                    "gate 4 (clause review) is not approved")
    if not state.is_approved("5_conditions"):
        result.warn("review", scheme.scheme,
                    "gate 5 (rule logic review) is not approved")

    accepted = set(state.accepted_clauses())
    if not accepted:
        return

    for clause in scheme.clauses:
        if clause.id not in accepted:
            result.error("review", clause.id,
                         "clause is in scheme.md but was never accepted by a reviewer")

    present = set(scheme.clause_ids)
    for clause_id in sorted(accepted - present):
        result.warn("review", clause_id,
                    "clause was accepted but is not in scheme.md")


def validate_scheme(path: Path) -> Result:
    scheme = load_scheme(path)
    directory = path.parent
    result = Result(scheme=scheme.scheme)

    check_quotes(scheme, directory, result)
    check_condition_clauses(scheme, result)
    check_sources(scheme, result)
    check_checksums(scheme, directory, result)
    check_expressions(scheme, result)
    check_consistency(scheme, result)
    check_clause_shape(scheme, result)
    check_review_state(scheme, directory, result)

    return result


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def report(result: Result) -> None:
    console.heading(f"validate — {result.scheme}")

    if not result.findings:
        print()
        console.ok("all checks passed")
        return

    for finding in result.errors + result.warnings:
        print()
        label = "FAIL" if finding.severity == SEVERITY_ERROR else "warn"
        print(f"  [{label}] {finding.check}: {finding.where}")
        print(f"         {finding.message}")
        if finding.detail:
            print()
            for line in finding.detail.splitlines():
                print(f"           {line}")

    print()
    print(f"  {len(result.errors)} error(s), {len(result.warnings)} warning(s)")


def main(argv: list[str] | None = None) -> int:
    console.setup()

    parser = argparse.ArgumentParser(description="Validate corpus acceptance gates.")
    parser.add_argument("--scheme", help="slug to validate")
    parser.add_argument("--all", action="store_true", help="validate every scheme")
    parser.add_argument("--file", help="validate a specific scheme.md")
    parser.add_argument("--strict", action="store_true",
                        help="treat warnings as failures")
    parser.add_argument("--root")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else repo_root()

    paths: list[Path] = []
    if args.file:
        paths = [Path(args.file)]
    elif args.all:
        paths = sorted((root / "data" / "schemes").glob("*/scheme.md"))
        if not paths:
            console.warn("no schemes found under data/schemes/")
            return 0
    elif args.scheme:
        paths = [scheme_dir(args.scheme, root) / "scheme.md"]
    else:
        parser.error("give --scheme, --file, or --all")

    failed = 0
    total_warnings = 0
    for path in paths:
        if not path.exists():
            console.fail(f"no such file: {path}")
            failed += 1
            continue
        try:
            result = validate_scheme(path)
        except SchemeParseError as exc:
            console.heading(f"validate — {path.parent.name}")
            print()
            console.fail(f"could not parse: {exc}")
            failed += 1
            continue

        report(result)
        total_warnings += len(result.warnings)
        if not result.ok:
            failed += 1

    print()
    if failed:
        console.fail(f"{failed} of {len(paths)} scheme(s) failed validation")
        return 1
    if args.strict and total_warnings:
        console.fail(f"{total_warnings} warning(s) with --strict")
        return 1
    console.ok(f"{len(paths)} scheme(s) passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
