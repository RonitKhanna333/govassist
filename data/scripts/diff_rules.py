"""Show what changed between two versions of a scheme's rules.

    python data/scripts/diff_rules.py --scheme pm-kisan --from 1 --to 2

Government rules change quietly -- a threshold moves, an exclusion is added, a
deadline shifts -- and the person who needed to know finds out after they have
missed it. Version-to-version diffs are how GovAssist can say *when* a rule
changed and *what* it used to say.

Reads the committed `build/rules.v{n}.json` files, so it reports what the system
actually decided with, not what anyone remembers authoring. Doubles as the
changelog when a scheme's guidelines are reissued.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import console
from parse_scheme import repo_root, scheme_dir


def load_rules(directory: Path, version: int) -> dict:
    path = directory / "build" / f"rules.v{version}.json"
    if not path.exists():
        available = sorted(p.name for p in (directory / "build").glob("rules.v*.json"))
        raise SystemExit(
            f"no such rule pack: {path}\n"
            + (f"  available: {', '.join(available)}" if available
               else "  run build.py first")
        )
    return json.loads(path.read_text(encoding="utf-8"))


def index(rules: dict) -> dict[str, dict]:
    return {condition["id"]: condition for condition in rules.get("conditions", [])}


def diff(old: dict, new: dict) -> list[tuple[str, str, str]]:
    """Return (change, condition_id, detail) triples."""
    before, after = index(old), index(new)
    changes: list[tuple[str, str, str]] = []

    for condition_id in sorted(set(after) - set(before)):
        condition = after[condition_id]
        changes.append(("added", condition_id,
                        f"{condition['expr']}   [cites {condition['clause']}]"))

    for condition_id in sorted(set(before) - set(after)):
        condition = before[condition_id]
        changes.append(("removed", condition_id,
                        f"{condition['expr']}   [cited {condition['clause']}]"))

    for condition_id in sorted(set(before) & set(after)):
        was, now = before[condition_id], after[condition_id]
        for field in ("expr", "clause", "asks"):
            if was.get(field) != now.get(field):
                changes.append((
                    "changed", condition_id,
                    f"{field}:\n      was: {was.get(field)}\n      now: {now.get(field)}",
                ))

    for field in ("decision", "effective_from", "effective_to", "authority", "tier"):
        if old.get(field) != new.get(field):
            changes.append(("scheme", field,
                            f"was: {old.get(field)}\n      now: {new.get(field)}"))

    return changes


def main(argv: list[str] | None = None) -> int:
    console.setup()

    parser = argparse.ArgumentParser(description="Diff two versions of a rule pack.")
    parser.add_argument("--scheme", required=True)
    parser.add_argument("--from", dest="old", type=int, required=True)
    parser.add_argument("--to", dest="new", type=int, required=True)
    parser.add_argument("--root")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else repo_root()
    directory = scheme_dir(args.scheme, root)

    old = load_rules(directory, args.old)
    new = load_rules(directory, args.new)
    changes = diff(old, new)

    console.heading(f"{args.scheme}:  v{args.old} → v{args.new}")

    if not changes:
        print()
        console.ok("no differences in rule logic")
        return 0

    for kind, target, detail in changes:
        print()
        print(f"  [{kind}] {target}")
        for line in detail.splitlines():
            print(f"      {line}")

    print()
    counts: dict[str, int] = {}
    for kind, _, _ in changes:
        counts[kind] = counts.get(kind, 0) + 1
    print("  " + ", ".join(f"{count} {kind}" for kind, count in sorted(counts.items())))
    print()
    console.info("Anyone assessed under the older version may now get a different")
    console.info("answer. Re-check the golden personas before shipping this change.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
