"""Prompt files, versioned, never inline strings -- see docs/phase2-design.md.

`load(name, version)` reads api/agents/prompts/{name}.v{version}.txt. Bumping
a prompt means adding a new file (composer.v2.txt), not editing the old one
in place -- the version number in the filename is what makes a prompt change
reviewable as a diff and revertable independently of code.
"""

from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).resolve().parent


def load(name: str, version: int = 1) -> str:
    path = _DIR / f"{name}.v{version}.txt"
    if not path.exists():
        raise FileNotFoundError(f"no prompt file at {path}")
    return path.read_text(encoding="utf-8")
