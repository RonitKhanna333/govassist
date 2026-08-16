"""Gates 4 and 5: the human review that makes the corpus defensible.

    python data/scripts/review.py --scheme pm-kisan               # clauses  (gate 4)
    python data/scripts/review.py --scheme pm-kisan --conditions  # rule logic (gate 5)
    python data/scripts/review.py --scheme pm-kisan --only uncertain

Everything else in this toolchain checks that a quote *appears* in the source.
Only a person can check that the right thing was quoted, that the quote is
complete, and that the rule logic points the same direction as the sentence it
cites. Those are the two failure modes no automated gate will ever catch:

  a truncated quote      stopping before "...except where" inverts the rule
  an inverted comparison  `>=` where the document says "below"

The second one is why Gate 5 exists as a separate pass. Run it with fresh eyes,
ideally a different person than the one who accepted the clauses -- it is the
error with the worst consequence, telling someone they do not qualify when they
do, and it is invisible to every test in this repository.

Two safety properties:

  * Every decision is written to .state.json immediately, so Ctrl-C at clause 41
    of 60 loses nothing.
  * An edit that breaks the quote's match against the source is REFUSED. A
    reviewer tidying a quote to read better is the likeliest way to silently
    destroy provenance, so the tool does not permit it.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import console
from grammar import ExpressionError, referenced_attributes, validate_expr
from normalize import MatchStatus, describe_failure, normalize, validate_quote
from parse_scheme import (
    Clause,
    Scheme,
    SchemeParseError,
    dump_scheme,
    load_scheme,
    parse_scheme_text,
    repo_root,
    scheme_dir,
    scheme_path,
    draft_path,
)
from state import APPROVED, PENDING, REJECTED, load_state, summarize

CONTEXT = 260


def editor_command() -> list[str]:
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if editor:
        return editor.split()
    return ["notepad"] if os.name == "nt" else ["nano"]


def source_for(scheme: Scheme, clause: Clause, directory: Path) -> str | None:
    source = scheme.source(clause.source) if clause.source else None
    if source and source.txt:
        base = scheme.path.parent if scheme.path else directory
        candidate = base / source.txt
        if candidate.exists():
            return candidate.read_text(encoding="utf-8", errors="replace")
    candidates = sorted((directory / "source").glob("*.txt"))
    if len(candidates) == 1:
        return candidates[0].read_text(encoding="utf-8", errors="replace")
    return None


def show_context(quote: str, source: str) -> None:
    """Print the surrounding source text with the quoted span marked."""
    match = validate_quote(quote, source)
    normalized = normalize(source)

    if match.index is None:
        console.section("Source context")
        print(console.wrap(match.context or "(could not locate this text)"))
        return

    span = len(normalize(quote))
    start = max(0, match.index - CONTEXT)
    end = min(len(normalized), match.index + span + CONTEXT)

    before = normalized[start:match.index]
    quoted = normalized[match.index:match.index + span]
    after = normalized[match.index + span:end]

    console.section("Source context  (quoted span in >>markers<<)")
    print(console.wrap(f"...{before}>>{quoted}<<{after}..."))


def show_clause(scheme: Scheme, clause: Clause, source: str | None,
                position: int, total: int, state) -> None:
    console.heading(f"[{position}/{total}]  {clause.id}")

    status = state.clause_status(clause.id)
    flags = []
    if clause.uncertain:
        flags.append("UNCERTAIN")
    if status != PENDING:
        flags.append(f"previously {status}")

    print()
    print(f"  type    {clause.type}")
    print(f"  source  {clause.source or '(none)'}"
          + (f"   page {clause.page}" if clause.page else ""))
    print(f"  tests   {', '.join(clause.tests) if clause.tests else '(none)'}")
    if flags:
        print(f"  flags   {' · '.join(flags)}")
    if clause.note:
        print(f"  note    {clause.note}")

    if source is not None:
        match = validate_quote(clause.quote, source)
        if match.status is MatchStatus.EXACT:
            console.ok("quote is verbatim in the source")
        elif match.status is MatchStatus.LOOSE:
            console.warn("matched only ignoring hyphens/spaces -- check for rewording")
        else:
            console.fail("QUOTE NOT FOUND IN SOURCE -- this must not be accepted")
    else:
        console.warn("no source text available; cannot verify this quote")

    console.section("Quote")
    print(console.wrap(clause.quote))

    if source is not None:
        show_context(clause.quote, source)

    console.section("Plain")
    print(console.wrap(clause.plain or "(none)"))

    if clause.aliases:
        console.section("Aliases  (retrieval only -- never shown, never cited)")
        print(console.wrap(" · ".join(clause.aliases)))

    console.section("Check before accepting")
    console.bullet("is the quote COMPLETE? a truncated quote can invert the rule")
    console.bullet("does Plain add any number, date or condition not in the quote?")
    console.bullet("is the type right? an exclusion mislabelled as eligibility flips it")
    console.bullet("do the tests attributes match what the clause turns on?")


def edit_clause(clause: Clause, source: str | None) -> tuple[Clause, bool]:
    """Open the clause in $EDITOR. Refuses edits that break the quote."""
    scratch = Scheme(scheme="scratch", clauses=[clause])
    body = dump_scheme(scratch).split("---\n", 2)[-1].lstrip("\n")

    handle, tmp = tempfile.mkstemp(suffix=".md", text=True)
    path = Path(tmp)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(
                "<!-- Edit this clause, save, and close the editor.\n"
                "     The quote must stay verbatim: an edit that no longer matches\n"
                "     the source document will be refused. -->\n\n" + body
            )
        subprocess.run([*editor_command(), str(path)], check=False)
        text = path.read_text(encoding="utf-8")
    finally:
        path.unlink(missing_ok=True)

    text = "\n".join(ln for ln in text.splitlines() if not ln.strip().startswith("<!--")
                     and not ln.strip().startswith("     ")
                     and not ln.strip().endswith("-->"))

    try:
        edited = parse_scheme_text("---\nscheme: scratch\n---\n\n" + text)
    except SchemeParseError as exc:
        console.fail(f"could not parse your edit: {exc}")
        console.info("clause unchanged")
        return clause, False

    if not edited.clauses:
        console.fail("your edit contains no clause section -- clause unchanged")
        return clause, False

    updated = edited.clauses[0]

    if source is not None:
        match = validate_quote(updated.quote, source)
        if not match.ok:
            console.heading("EDIT REFUSED")
            print()
            print(console.wrap(
                "The quote you saved no longer appears in the source document. "
                "The corpus only holds text that is provably in the source, so "
                "this edit cannot be kept."
            ))
            print()
            for line in describe_failure(updated.quote, match).splitlines():
                print(f"  {line}")
            print()
            console.info("If the source itself is wrong or mangled, fix the .txt")
            console.info("and note hand_corrected in the meta -- never the quote.")
            return clause, False

    return updated, True


def review_clauses(scheme: Scheme, directory: Path, state, only: str | None,
                   reviewer: str) -> bool:
    pending = [
        clause for clause in scheme.clauses
        if state.clause_status(clause.id) == PENDING
        or (only == "all")
        or (only == "uncertain" and clause.uncertain)
    ]
    if only == "uncertain":
        pending = [c for c in scheme.clauses if c.uncertain]
    elif only == "all":
        pending = list(scheme.clauses)

    if not pending:
        console.ok("every clause already has a decision")
        console.info("use --only all to review them again")
        return True

    total = len(pending)
    index = 0
    while index < total:
        clause = pending[index]
        source = source_for(scheme, clause, directory)
        show_clause(scheme, clause, source, index + 1, total, state)

        print()
        choice = console.key(
            "[a]ccept  [e]dit  [r]eject  [s]kip  [b]ack  [q]uit+save", "aersbq"
        )

        if choice == "a":
            if source is not None and not validate_quote(clause.quote, source).ok:
                console.fail("refusing to accept a clause whose quote is not in the source")
                console.info("edit the quote, or reject the clause")
                continue
            state.set_clause(clause.id, APPROVED, by=reviewer)
            console.ok(f"accepted {clause.id}")
            index += 1
        elif choice == "r":
            note = console.ask("why? (optional)")
            state.set_clause(clause.id, REJECTED, by=reviewer, note=note)
            console.ok(f"rejected {clause.id}")
            index += 1
        elif choice == "e":
            updated, changed = edit_clause(clause, source)
            if changed:
                position = scheme.clauses.index(clause)
                scheme.clauses[position] = updated
                pending[index] = updated
                console.ok("edit accepted (quote still matches the source)")
        elif choice == "s":
            index += 1
        elif choice == "b":
            index = max(0, index - 1)
        elif choice == "q":
            print()
            console.info("progress saved; re-run to continue where you left off")
            return False

    return True


def review_conditions(scheme: Scheme, state, reviewer: str) -> bool:
    if not scheme.conditions:
        console.warn("this scheme has no conditions to review")
        return True

    console.heading("GATE 5 — Rule logic")
    print()
    print(console.wrap(
        "A clause can be quoted perfectly while its expression inverts the rule. "
        "No test in this repository can catch that. Read each expression against "
        "the sentence it cites, not against your memory of it."
    ))

    total = len(scheme.conditions)
    for position, condition in enumerate(scheme.conditions, start=1):
        console.heading(f"[{position}/{total}]  {condition.id}")

        clause = scheme.clause(condition.clause)
        print()
        print(f"  expr    {condition.expr}")
        print(f"  clause  {condition.clause}"
              + ("" if clause else "   <- NO SUCH CLAUSE"))
        if condition.asks:
            print(f"  asks    {condition.asks}")

        problems = validate_expr(condition.expr)
        if problems:
            console.fail(problems[0])
        else:
            try:
                console.info(f"reads: {', '.join(referenced_attributes(condition.expr))}")
            except ExpressionError:
                pass

        if clause is not None:
            console.section("The clause it cites")
            print(console.wrap(clause.quote))
            if clause.type == "exclusion":
                print()
                console.warn("this is an EXCLUSION clause")
                console.info("the condition must be TRUE when the person is NOT excluded")
        else:
            console.fail("this condition points at a clause that does not exist")

        console.section("Check")
        console.bullet("comparison direction: 'below X' is  < X , not <= and not >")
        console.bullet("boundary: 'up to 2' is inclusive (<= 2); 'less than 2' is not")
        console.bullet("exclusions negated correctly (must be false to qualify)")
        console.bullet("every threshold in the expr appears in the quote")

        print()
        choice = console.key("[a]ccept  [r]eject  [s]kip  [q]uit+save", "arsq")
        if choice == "a":
            state.set_condition(condition.id, APPROVED, by=reviewer)
            console.ok(f"accepted {condition.id}")
        elif choice == "r":
            note = console.ask("what is wrong? (optional)")
            state.set_condition(condition.id, REJECTED, by=reviewer, note=note)
            console.ok(f"rejected {condition.id}")
        elif choice == "q":
            print()
            console.info("progress saved")
            return False

    return True


def promote(scheme: Scheme, state, root: Path) -> Path:
    """Write scheme.md containing only the accepted clauses."""
    accepted = set(state.accepted_clauses())
    kept = [c for c in scheme.clauses if c.id in accepted]
    dropped = [c.id for c in scheme.clauses if c.id not in accepted]

    final = Scheme(
        scheme=scheme.scheme, name_en=scheme.name_en, tier=scheme.tier,
        version=scheme.version, effective_from=scheme.effective_from,
        effective_to=scheme.effective_to, authority=scheme.authority,
        license=scheme.license, sources=scheme.sources,
        conditions=scheme.conditions, decision=scheme.decision, clauses=kept,
    )

    target = scheme_path(scheme.scheme, root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dump_scheme(final), encoding="utf-8", newline="\n")

    if dropped:
        console.warn(f"left out {len(dropped)} clause(s): {', '.join(dropped)}")
    return target


def main(argv: list[str] | None = None) -> int:
    console.setup()

    parser = argparse.ArgumentParser(
        description="Interactive human review of drafted clauses and rule logic.",
    )
    parser.add_argument("--scheme", required=True)
    parser.add_argument("--conditions", action="store_true",
                        help="review rule logic (gate 5) instead of clauses")
    parser.add_argument("--only", choices=["pending", "uncertain", "all"],
                        default="pending")
    parser.add_argument("--reviewer", help="your name, recorded with each decision")
    parser.add_argument("--file", help="file to review (default: draft, else scheme.md)")
    parser.add_argument("--status", action="store_true", help="show progress and exit")
    parser.add_argument("--root")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else repo_root()
    directory = scheme_dir(args.scheme, root)
    state = load_state(args.scheme, directory)

    if args.status:
        console.heading(f"Review status — {args.scheme}")
        print()
        print(summarize(state))
        return 0

    if args.file:
        path = Path(args.file)
    else:
        path = draft_path(args.scheme, root)
        if not path.exists():
            path = scheme_path(args.scheme, root)
    if not path.exists():
        console.fail(f"nothing to review at {path}")
        return 1

    try:
        scheme = load_scheme(path)
    except SchemeParseError as exc:
        console.fail(f"could not parse {path.name}: {exc}")
        return 1

    reviewer = args.reviewer or console.ask("Your name (recorded with each decision)",
                                            default="")
    if not reviewer:
        console.fail("a reviewer name is required -- approvals must be attributable")
        return 1

    if args.conditions:
        finished = review_conditions(scheme, state, reviewer)
        if finished:
            print()
            if console.confirm("Is every rule expression correct?", gate="5"):
                state.set_gate("5_conditions", APPROVED, by=reviewer)
                console.ok("gate 5 approved")
                print()
                print("  Next:")
                print(f"    python data/scripts/validate.py --scheme {args.scheme}")
            else:
                state.set_gate("5_conditions", REJECTED, by=reviewer)
        return 0

    finished = review_clauses(scheme, directory, state, args.only, reviewer)
    if not finished:
        return 0

    undecided = [c.id for c in scheme.clauses if state.clause_status(c.id) == PENDING]
    if undecided:
        console.warn(f"{len(undecided)} clause(s) still undecided -- re-run to finish")
        return 0

    console.heading("GATE 4 — Clause review")
    print()
    print(f"  accepted: {len(state.accepted_clauses())} of {len(scheme.clauses)}")
    print()
    print(console.wrap(
        "One last question, and it is the one automation cannot help with: is "
        "anything MISSING? The draft only proposed what it found. Read the "
        "source's eligibility and exclusion sections yourself and add any rule "
        "it skipped -- an omission is invisible to every check in this system."
    ))

    if not console.confirm("Is the clause set complete and correct?", gate="4"):
        state.set_gate("4_clauses", REJECTED, by=reviewer)
        console.info("nothing promoted; re-run when the gaps are filled")
        return 0

    state.set_gate("4_clauses", APPROVED, by=reviewer)
    target = promote(scheme, state, root)
    console.ok(f"wrote {target}")
    print()
    print("  Next -- review the rule logic, ideally a different person:")
    print(f"    python data/scripts/review.py --scheme {args.scheme} --conditions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
