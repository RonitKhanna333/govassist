"""Validate an assistant-produced draft against the committed source text.

    python data/scripts/import_draft.py --scheme pm-kisan
    python data/scripts/import_draft.py --scheme pm-kisan --repair    # paste-back message

This is what makes it safe to let a chat assistant draft clauses. Its output is
treated as an untrusted proposal: every blockquote must prove itself against
`source/*.txt` before a human is asked to spend attention on it.

The failure modes it catches are exactly the ones a chat assistant produces:

  paraphrase          rewrote the rule in cleaner language
  invention           a threshold or date that is nowhere in the document
  quiet tidying       fixed the source's grammar, expanded an abbreviation,
                      or dropped an ellipsis
  wrong document      quoted from memory of a different scheme

`--repair` prints a message to paste back into the same chat: the clauses that
failed, and the real source text near each one. Most failures are line-break
artifacts and come back correct on the first retry.

Nothing here writes to `scheme.md`. It reports; `review.py` is where a human
decides.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import console
from normalize import MatchStatus, describe_failure, validate_quote
from parse_scheme import (
    Clause,
    Scheme,
    SchemeParseError,
    draft_path,
    load_scheme,
    repo_root,
    scheme_dir,
    scheme_path,
)


@dataclass
class ClauseReport:
    clause: Clause
    status: MatchStatus
    detail: str = ""
    note: str = ""
    context: str | None = None

    @property
    def failed(self) -> bool:
        return self.status is MatchStatus.MISSING


def resolve_source_text(scheme: Scheme, clause: Clause, directory: Path,
                        fallback: Path | None) -> tuple[str, str]:
    """Return (text, label) for the source a clause should validate against."""
    source = scheme.source(clause.source) if clause.source else None
    if source is not None and source.txt:
        base = scheme.path.parent if scheme.path else directory
        candidate = (base / source.txt).resolve()
        if candidate.exists():
            return candidate.read_text(encoding="utf-8", errors="replace"), source.id

    if fallback is not None:
        return fallback.read_text(encoding="utf-8", errors="replace"), fallback.stem

    raise SchemeParseError(
        f"clause '{clause.id}' cites source '{clause.source or '(none)'}' but no "
        "matching .txt was found -- run ingest.py, or add the source to the "
        "draft's frontmatter"
    )


def find_fallback_source(directory: Path) -> Path | None:
    candidates = sorted((directory / "source").glob("*.txt"))
    return candidates[0] if len(candidates) == 1 else None


def check(scheme: Scheme, directory: Path) -> list[ClauseReport]:
    fallback = find_fallback_source(directory)
    reports: list[ClauseReport] = []

    for clause in scheme.clauses:
        if not clause.quote.strip():
            reports.append(ClauseReport(
                clause, MatchStatus.MISSING,
                note="clause has no blockquote at all",
            ))
            continue

        try:
            text, label = resolve_source_text(scheme, clause, directory, fallback)
        except SchemeParseError as exc:
            reports.append(ClauseReport(clause, MatchStatus.MISSING, note=str(exc)))
            continue

        match = validate_quote(clause.quote, text)
        reports.append(ClauseReport(
            clause,
            match.status,
            detail=describe_failure(clause.quote, match) if not match.ok or match.needs_human else "",
            note=match.note or f"validated against {label}",
            context=match.context,
        ))

    return reports


def report(reports: list[ClauseReport], scheme: Scheme) -> str:
    lines: list[str] = []
    exact = [r for r in reports if r.status is MatchStatus.EXACT]
    loose = [r for r in reports if r.status is MatchStatus.LOOSE]
    missing = [r for r in reports if r.status is MatchStatus.MISSING]

    lines.append(f"scheme: {scheme.scheme}")
    lines.append(f"clauses: {len(reports)}")
    lines.append(f"  verbatim : {len(exact)}")
    lines.append(f"  flagged  : {len(loose)}   (matched only ignoring hyphens/spaces)")
    lines.append(f"  REJECTED : {len(missing)}")
    lines.append("")

    for item in reports:
        mark = {"exact": "ok  ", "loose": "WARN", "missing": "FAIL"}[item.status.value]
        lines.append(f"[{mark}] {item.clause.id}")
        if item.status is MatchStatus.EXACT:
            continue
        lines.append("")
        for line in (item.detail or item.note).splitlines():
            lines.append(f"    {line}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def repair_message(reports: list[ClauseReport]) -> str:
    """A message to paste back into the drafting chat."""
    broken = [r for r in reports if r.failed]
    if not broken:
        return ""

    lines = [
        "Some of the quotes you wrote do not appear in the source document.",
        "",
        "A quote must be copied character for character from the text I pasted.",
        "Do not fix the source's grammar, expand abbreviations, merge sentences,",
        "or add an ellipsis. If a rule is not present in the text I gave you,",
        "delete that clause rather than reconstructing it.",
        "",
        "Fix these clauses and return only the corrected sections:",
        "",
    ]

    for item in broken:
        lines.append(f"## {item.clause.id}")
        lines.append("")
        lines.append("You wrote:")
        lines.append(f"  {' '.join(item.clause.quote.split())[:400]}")
        lines.append("")
        if item.context:
            lines.append("The actual source text near it is:")
            lines.append(f"  {item.context[:700]}")
            lines.append("")
            lines.append("Quote verbatim from that.")
        else:
            lines.append("Nothing resembling this appears anywhere in the document.")
            lines.append("Delete this clause -- it is not supported by the source.")
        lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    console.setup()

    parser = argparse.ArgumentParser(
        description="Span-validate a drafted scheme file against its source text.",
    )
    parser.add_argument("--scheme", required=True)
    parser.add_argument("--file", help="draft to check (default: scheme.draft.md, "
                                       "falling back to scheme.md)")
    parser.add_argument("--repair", action="store_true",
                        help="print a paste-back message for the failing clauses")
    parser.add_argument("--strict", action="store_true",
                        help="treat flagged (loose) matches as failures too")
    parser.add_argument("--root")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else repo_root()

    if args.file:
        path = Path(args.file)
    else:
        path = draft_path(args.scheme, root)
        if not path.exists():
            path = scheme_path(args.scheme, root)

    if not path.exists():
        console.fail(f"no draft found at {path}")
        console.info("Save the assistant's output as scheme.draft.md in")
        console.info(f"  {scheme_dir(args.scheme, root)}")
        return 1

    # source/ and the report always live beside the file being checked, so
    # --file works from anywhere.
    directory = path.parent

    try:
        scheme = load_scheme(path)
    except SchemeParseError as exc:
        console.fail(f"could not parse {path.name}: {exc}")
        console.info("The assistant's output must start with '---' frontmatter and")
        console.info("use '## clause-id' section headings. Check the clause spec.")
        return 1

    if not scheme.clauses:
        console.fail("the draft contains no clause sections")
        return 1

    reports = check(scheme, directory)
    text = report(reports, scheme)

    console.heading(f"Span validation — {path.name}")
    print()
    print(text)

    report_path = directory / "draft-report.txt"
    report_path.write_text(text, encoding="utf-8", newline="\n")
    console.ok(f"report written to {report_path}")

    missing = [r for r in reports if r.status is MatchStatus.MISSING]
    loose = [r for r in reports if r.status is MatchStatus.LOOSE]

    if args.repair and missing:
        console.heading("Paste this back into the drafting chat")
        print()
        print(repair_message(reports))

    print()
    if missing:
        console.fail(f"{len(missing)} clause(s) are not grounded in the source")
        if not args.repair:
            console.info("Re-run with --repair to get a paste-back message.")
        console.info("These cannot enter the corpus until their quotes match.")
        return 1

    if loose:
        console.warn(f"{len(loose)} clause(s) matched only loosely -- review them")
        console.info("Usually a PDF line-break artifact; confirm nothing was reworded.")
        if args.strict:
            return 1

    console.ok("every quote is present in the source document")
    print()
    print("  Next -- the human gates:")
    print(f"    python data/scripts/review.py --scheme {args.scheme}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
