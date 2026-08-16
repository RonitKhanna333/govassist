"""Shared console helpers for the corpus CLIs.

The corpus contains Devanagari, Gurmukhi and Tamil text. Windows consoles
default to a legacy code page, so printing an alias list raises
UnicodeEncodeError and the tool looks broken for reasons that have nothing to
do with the corpus. `setup()` fixes stdout/stderr before anything prints.

The prompt helpers exist so every human gate looks and behaves the same way:
default to "no", require an explicit yes, and never treat a bare Enter as
approval. A gate that is easy to approve by accident is not a gate.
"""

from __future__ import annotations

import sys

RULE = "─" * 76


def setup() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def heading(text: str) -> None:
    print()
    print(RULE)
    print(text)
    print(RULE)


def section(text: str) -> None:
    print()
    print(text)
    print("-" * min(len(text), 76))


def bullet(text: str, mark: str = "  •") -> None:
    print(f"{mark} {text}")


def wrap(text: str, width: int = 76, indent: str = "  ") -> str:
    out, line = [], indent
    for word in str(text).split():
        if len(line) + len(word) + 1 > width and line.strip():
            out.append(line)
            line = indent
        line += ("" if line == indent else " ") + word
    if line.strip():
        out.append(line)
    return "\n".join(out)


def confirm(question: str, gate: str | None = None) -> bool:
    """Ask a blocking yes/no question. Anything but an explicit yes is no."""
    if gate:
        print()
        print(f"  GATE {gate}")
    print()
    try:
        answer = input(f"  {question} [y/N] ").strip().lower()
    except EOFError:
        print("\n  no input available -- treating as 'no'")
        return False
    except KeyboardInterrupt:
        print("\n  interrupted -- treating as 'no'")
        return False
    return answer in {"y", "yes"}


def ask(question: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"  {question}{suffix} ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return answer or default


def key(question: str, choices: str) -> str:
    """Read a single-letter choice. Loops until the answer is valid."""
    while True:
        try:
            answer = input(f"  {question} ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return "q"
        if answer[:1] in choices:
            return answer[:1]
        print(f"  please choose one of: {', '.join(choices)}")


def ok(text: str) -> None:
    print(f"  [ok]   {text}")


def warn(text: str) -> None:
    print(f"  [warn] {text}")


def fail(text: str) -> None:
    print(f"  [FAIL] {text}")


def info(text: str) -> None:
    print(f"         {text}")
