"""Gate 3: split the extracted text into chunks worth drafting from.

    python data/scripts/segment.py --scheme pm-kisan            # review boundaries
    python data/scripts/segment.py --scheme pm-kisan --emit     # write paste-ready chunks
    python data/scripts/segment.py --scheme pm-kisan --merge 4,5

Segmentation is deterministic -- headings and numbered paragraphs, no model
involved. Two reasons this is its own step with its own gate:

  * A rule split across two chunks gets drafted from half its text, and the
    resulting quote is wrong in a way that still validates, because both halves
    genuinely appear in the source. Automated checks cannot catch it. A human
    glancing at the boundaries can, in about a minute.

  * Fixing a boundary here is free. Fixing it after drafting means redoing the
    work (and, on the API path, spending the quota twice).

`--emit` writes one file per chunk under `chunks/`, each ready to paste into a
chat alongside the clause spec.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import console
from parse_scheme import repo_root, scheme_dir
from state import APPROVED, REJECTED, load_state

TARGET_CHARS = 4500      # comfortable to paste and to reason about in one go
MAX_CHARS = 9000         # above this, split even without a heading

# Ordered by confidence: a numbered section heading is a stronger boundary than
# a bare capitalised line.
_NUMBERED = re.compile(r"^\s*(\d+(?:\.\d+)*)[.)]?\s+\S")
_CAPS_HEADING = re.compile(r"^\s*([A-Z][A-Z \t&,'()./-]{3,60})\s*$")
_ROMAN = re.compile(r"^\s*\(?([ivxlIVXL]+)\)[.)]?\s+\S")


@dataclass
class Segment:
    index: int
    title: str
    text: str

    @property
    def chars(self) -> int:
        return len(self.text)

    @property
    def first_line(self) -> str:
        for line in self.text.splitlines():
            if line.strip():
                return line.strip()
        return ""


def _boundary_score(line: str) -> int:
    if _CAPS_HEADING.match(line):
        return 3
    match = _NUMBERED.match(line)
    if match:
        # "2." is a stronger boundary than "2.1.3"
        return 3 - min(2, match.group(1).count("."))
    if _ROMAN.match(line):
        return 1
    return 0


def segment_text(text: str, target: int = TARGET_CHARS,
                 maximum: int = MAX_CHARS) -> list[Segment]:
    lines = text.replace("\r\n", "\n").split("\n")

    chunks: list[list[str]] = []
    current: list[str] = []
    size = 0

    for line in lines:
        score = _boundary_score(line)
        # Start a new chunk at a strong boundary once we have enough material,
        # or at any boundary once the chunk is oversized.
        start_new = current and (
            (score >= 2 and size >= target)
            or (score >= 1 and size >= maximum)
            or size >= maximum * 1.5
        )
        if start_new:
            chunks.append(current)
            current, size = [], 0
        current.append(line)
        size += len(line) + 1

    if current:
        chunks.append(current)

    segments: list[Segment] = []
    for index, chunk in enumerate(chunks, start=1):
        body = "\n".join(chunk).strip("\n")
        if not body.strip():
            continue
        title = next((ln.strip() for ln in chunk if ln.strip()), f"segment {index}")
        segments.append(Segment(index=len(segments) + 1, title=title[:70], text=body))
    return segments


def apply_merge(segments: list[Segment], spec: str) -> list[Segment]:
    wanted = {int(part) for part in spec.split(",") if part.strip().isdigit()}
    if not wanted:
        return segments
    merged: list[Segment] = []
    buffer: Segment | None = None
    for segment in segments:
        if buffer is None:
            buffer = Segment(segment.index, segment.title, segment.text)
        elif segment.index in wanted:
            buffer = Segment(buffer.index, buffer.title,
                             buffer.text + "\n\n" + segment.text)
            continue
        else:
            merged.append(buffer)
            buffer = Segment(segment.index, segment.title, segment.text)
    if buffer is not None:
        merged.append(buffer)
    for position, segment in enumerate(merged, start=1):
        segment.index = position
    return merged


def apply_split(segments: list[Segment], spec: str) -> list[Segment]:
    try:
        target_index, offset = (int(part) for part in spec.split(":", 1))
    except ValueError:
        raise SystemExit("--split expects N:OFFSET, e.g. --split 7:1200") from None

    out: list[Segment] = []
    for segment in segments:
        if segment.index != target_index:
            out.append(segment)
            continue
        head, tail = segment.text[:offset].strip(), segment.text[offset:].strip()
        if not head or not tail:
            raise SystemExit(f"offset {offset} does not split segment {target_index}")
        out.append(Segment(segment.index, segment.title, head))
        out.append(Segment(segment.index, tail.splitlines()[0][:70], tail))
    for position, segment in enumerate(out, start=1):
        segment.index = position
    return out


def find_source_text(directory: Path, source_id: str | None) -> Path:
    source_dir = directory / "source"
    if not source_dir.exists():
        raise SystemExit(
            f"no source directory at {source_dir}\n"
            "  run ingest.py first"
        )
    candidates = sorted(source_dir.glob("*.txt"))
    if not candidates:
        raise SystemExit(f"no extracted .txt in {source_dir} -- run ingest.py first")
    if source_id:
        match = source_dir / f"{source_id}.txt"
        if not match.exists():
            raise SystemExit(f"no such source text: {match}")
        return match
    if len(candidates) > 1:
        names = ", ".join(p.stem for p in candidates)
        raise SystemExit(f"several sources present ({names}); pass --source-id")
    return candidates[0]


def show(segments: list[Segment], total: int) -> None:
    console.heading("GATE 3 — Segmentation")
    print()
    print(f"  {len(segments)} segments from {total:,} characters")
    print()
    for segment in segments:
        flag = "  <- large" if segment.chars > MAX_CHARS else ""
        print(f"  {segment.index:3}  {segment.chars:6,}  {segment.first_line[:56]}{flag}")

    print()
    print("  Check for the one thing automation cannot catch later:")
    console.bullet("does any single eligibility rule START in one segment and")
    console.bullet("  FINISH in the next?")
    print()
    console.info("A rule split across a boundary gets drafted from half its text.")
    console.info("The resulting quote still validates -- both halves really are in")
    console.info("the source -- so no later check will flag it.")
    print()
    console.info("Fix with:  --merge 4,5      fold segments 4 and 5 into 3")
    console.info("           --split 7:1200   break segment 7 at character 1200")


def emit(segments: list[Segment], directory: Path, slug: str) -> Path:
    chunk_dir = directory / "chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    for stale in chunk_dir.glob("*.txt"):
        stale.unlink()
    for segment in segments:
        path = chunk_dir / f"{segment.index:02d}.txt"
        path.write_text(segment.text + "\n", encoding="utf-8", newline="\n")
    return chunk_dir


def main(argv: list[str] | None = None) -> int:
    console.setup()

    parser = argparse.ArgumentParser(
        description="Split extracted source text into reviewable, paste-ready chunks.",
    )
    parser.add_argument("--scheme", required=True)
    parser.add_argument("--source-id")
    parser.add_argument("--emit", action="store_true",
                        help="write chunks/NN.txt for pasting into a chat")
    parser.add_argument("--merge", help="fold segments together, e.g. 4,5")
    parser.add_argument("--split", help="break a segment, e.g. 7:1200")
    parser.add_argument("--target", type=int, default=TARGET_CHARS)
    parser.add_argument("--root")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else repo_root()
    directory = scheme_dir(args.scheme, root)
    state = load_state(args.scheme, directory)

    if not state.is_approved("2_extraction"):
        console.fail("gate 2 (extraction quality) is not approved")
        console.info("run ingest.py and approve the extracted text first")
        return 1

    txt_path = find_source_text(directory, args.source_id)
    text = txt_path.read_text(encoding="utf-8", errors="replace")

    segments = segment_text(text, target=args.target)
    if args.merge:
        segments = apply_merge(segments, args.merge)
    if args.split:
        segments = apply_split(segments, args.split)

    show(segments, len(text))

    if not console.confirm("Are these boundaries sane?", gate="3"):
        state.set_gate("3_segments", REJECTED)
        print()
        console.info("Adjust with --merge / --split and re-run.")
        return 1

    state.set_gate("3_segments", APPROVED, note=f"{len(segments)} segments")

    if args.emit:
        chunk_dir = emit(segments, directory, args.scheme)
        console.heading("Chunks written")
        print()
        console.ok(f"{len(segments)} files in {chunk_dir}")
        print()
        print("  Next, for each chunk:")
        print("    1. open a fresh chat")
        print("    2. paste .claude/skills/govassist-corpus/references/clause-spec.md")
        print(f"    3. paste one file from {chunk_dir.name}/")
        print(f"    4. append the output to data/schemes/{args.scheme}/scheme.draft.md")
        print()
        print("  Then validate everything it wrote:")
        print(f"    python data/scripts/import_draft.py --scheme {args.scheme}")
    else:
        print()
        console.info("Re-run with --emit to write the paste-ready chunk files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
