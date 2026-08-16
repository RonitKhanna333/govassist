"""Gate state: who approved what, and where to resume.

Two jobs:

1. **Record the human gates.** Nothing enters the corpus unreviewed, and this
   file is the evidence. Every approval carries a name and a timestamp, so a
   reviewer can be asked "did you actually read clause 34?" and the answer is
   checkable rather than a matter of memory.

2. **Make review resumable.** Nobody reviews sixty clauses in one sitting.
   Every decision is written immediately and atomically, so Ctrl-C never loses
   work and the next session picks up at the first pending item.

Writes go to a temp file in the same directory and are then replaced into
position, so an interrupted write can never leave a truncated state file.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_FILENAME = ".state.json"

GATES = {
    "0_source": "Source selection -- is this the canonical official document?",
    "1_identity": "Document identity -- right scheme, right version, complete?",
    "2_extraction": "Extraction quality -- is the .txt readable where it matters?",
    "3_segments": "Segmentation -- is any rule split across a boundary?",
    "4_clauses": "Clause review -- every quote verbatim, every gloss faithful",
    "5_conditions": "Rule logic -- comparison directions and boundaries correct",
    "6_commit": "Pre-commit -- validated, built, and reviewed by a second person",
}

PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_reviewer() -> str:
    return (
        os.environ.get("GOVASSIST_REVIEWER")
        or os.environ.get("USERNAME")
        or os.environ.get("USER")
        or "unknown"
    )


@dataclass
class State:
    slug: str
    path: Path
    data: dict[str, Any]

    # -- gates ------------------------------------------------------------

    def gate(self, name: str) -> dict:
        return self.data.setdefault("gates", {}).setdefault(name, {"status": PENDING})

    def gate_status(self, name: str) -> str:
        return self.gate(name).get("status", PENDING)

    def is_approved(self, name: str) -> bool:
        return self.gate_status(name) == APPROVED

    def set_gate(self, name: str, status: str, by: str | None = None,
                 note: str = "") -> None:
        entry = {"status": status, "by": by or default_reviewer(), "at": now()}
        if note:
            entry["note"] = note
        self.data.setdefault("gates", {})[name] = entry
        self.save()

    def require(self, name: str) -> None:
        """Refuse to proceed past an unapproved gate."""
        if not self.is_approved(name):
            raise GateNotApproved(
                f"gate '{name}' is {self.gate_status(name)}, must be approved first\n"
                f"  {GATES.get(name, '')}"
            )

    # -- per-clause decisions --------------------------------------------

    def clause(self, clause_id: str) -> dict:
        return self.data.setdefault("clauses", {}).get(clause_id, {"status": PENDING})

    def clause_status(self, clause_id: str) -> str:
        return self.clause(clause_id).get("status", PENDING)

    def set_clause(self, clause_id: str, status: str, by: str | None = None,
                   edited: bool = False, note: str = "") -> None:
        entry: dict[str, Any] = {
            "status": status, "by": by or default_reviewer(), "at": now(),
        }
        if edited:
            entry["edited"] = True
        if note:
            entry["note"] = note
        self.data.setdefault("clauses", {})[clause_id] = entry
        self.save()

    def accepted_clauses(self) -> list[str]:
        return sorted(
            cid for cid, entry in self.data.get("clauses", {}).items()
            if entry.get("status") == APPROVED
        )

    # -- per-condition decisions -----------------------------------------

    def condition_status(self, condition_id: str) -> str:
        return self.data.get("conditions", {}).get(condition_id, {}).get("status", PENDING)

    def set_condition(self, condition_id: str, status: str, by: str | None = None,
                      note: str = "") -> None:
        entry: dict[str, Any] = {
            "status": status, "by": by or default_reviewer(), "at": now(),
        }
        if note:
            entry["note"] = note
        self.data.setdefault("conditions", {})[condition_id] = entry
        self.save()

    # -- persistence ------------------------------------------------------

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.data, indent=2, ensure_ascii=False, sort_keys=True)
        # Write-then-replace: an interrupted write cannot corrupt the real file.
        handle, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(payload + "\n")
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


class GateNotApproved(RuntimeError):
    pass


def load_state(slug: str, directory: Path) -> State:
    path = Path(directory) / STATE_FILENAME
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {"scheme": slug, "created_at": now(), "gates": {}, "clauses": {},
                "conditions": {}}
    data.setdefault("scheme", slug)
    return State(slug=slug, path=path, data=data)


def summarize(state: State) -> str:
    lines = [f"scheme: {state.slug}", ""]
    for name, description in GATES.items():
        entry = state.data.get("gates", {}).get(name, {})
        status = entry.get("status", PENDING)
        mark = {"approved": "[x]", "rejected": "[!]"}.get(status, "[ ]")
        who = f"  ({entry['by']}, {entry['at']})" if entry.get("by") else ""
        lines.append(f"  {mark} {name}  {description}{who}")

    clauses = state.data.get("clauses", {})
    if clauses:
        approved = sum(1 for e in clauses.values() if e.get("status") == APPROVED)
        rejected = sum(1 for e in clauses.values() if e.get("status") == REJECTED)
        lines += ["", f"  clauses: {approved} accepted, {rejected} rejected, "
                      f"{len(clauses)} decided"]
    return "\n".join(lines)
