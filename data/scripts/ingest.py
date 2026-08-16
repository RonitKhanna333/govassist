"""Gates 0-2: acquire a source document and turn it into the validation target.

    python data/scripts/ingest.py --scheme pm-kisan --url https://.../guidelines.pdf
    python data/scripts/ingest.py --scheme pm-kisan --file downloads/guidelines.pdf

What this produces is the anchor for everything that follows:

    data/schemes/<slug>/source/<id>.pdf        the authority, committed, checksummed
    data/schemes/<slug>/source/<id>.txt        ⭐ the ONLY thing quotes validate against
    data/schemes/<slug>/source/<id>.meta.json  url, retrieved_at, checksum, extractor

Three human gates, each blocking:

  0  Is this URL the canonical official document, or a summary of one?
  1  Is the downloaded file the right scheme and the right version?
  2  Is the extracted text readable where it matters (eligibility, exclusions)?

Gate 1 is the cheapest minute in the whole pipeline. A wrong document caught
here costs sixty seconds; caught during clause review it costs an afternoon.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

import console
from parse_scheme import repo_root, scheme_dir
from state import APPROVED, REJECTED, load_state

USER_AGENT = "GovAssist-corpus-tool/0.1 (student project; contact via repository)"
OFFICIAL_HINTS = (".gov.in", ".nic.in", ".gov", "india.gov.in")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def slug_from_url(url: str) -> str:
    stem = Path(url.split("?")[0]).stem or "guidelines"
    stem = re.sub(r"[^a-zA-Z0-9]+", "-", stem).strip("-").lower()
    return stem or "guidelines"


# --------------------------------------------------------------------------
# Gate 0 -- source selection
# --------------------------------------------------------------------------


def gate_source(url: str, state) -> bool:
    console.heading("GATE 0 — Source selection")
    print()
    print(console.wrap(url))
    print()

    looks_official = any(hint in url.lower() for hint in OFFICIAL_HINTS)
    if looks_official:
        console.ok("host looks like an official government domain")
    else:
        console.warn("host does NOT look like a .gov.in / .nic.in domain")
        console.info("aggregators and news sites paraphrase; their wording is not")
        console.info("citable. Prefer the ministry's own guidelines PDF.")

    print()
    print("  Confirm before downloading:")
    console.bullet("hosted by the ministry or department that runs the scheme")
    console.bullet("it is the guidelines or notification, not a press release,")
    console.bullet("  explainer, coaching-site summary, or news article")
    console.bullet("it is the current version, not a superseded one")

    approved = console.confirm("Is this the canonical official document?", gate="0")
    state.set_gate("0_source", APPROVED if approved else REJECTED, note=url)
    if not approved:
        print()
        console.info("Nothing downloaded. Find the official document and re-run.")
    return approved


# --------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------


def download(url: str, target: Path) -> None:
    import requests

    print()
    print(f"  downloading {url}")
    response = requests.get(url, timeout=60, headers={"User-Agent": USER_AGENT},
                            stream=True)
    response.raise_for_status()
    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with target.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1 << 16):
            handle.write(chunk)
            written += len(chunk)
    print(f"  wrote {written:,} bytes to {target.name}")


# --------------------------------------------------------------------------
# Gate 1 -- document identity
# --------------------------------------------------------------------------


def pdf_overview(path: Path) -> tuple[int, dict, str]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    meta = {k.lstrip("/"): str(v) for k, v in (reader.metadata or {}).items()}
    first_page = ""
    if reader.pages:
        try:
            first_page = reader.pages[0].extract_text() or ""
        except Exception:  # noqa: BLE001 -- damaged PDFs are a normal input here
            first_page = ""
    return len(reader.pages), meta, first_page


def gate_identity(path: Path, checksum: str, state) -> bool:
    console.heading("GATE 1 — Document identity")

    pages, meta, first_page = pdf_overview(path)
    print()
    print(f"  file      {path.name}")
    print(f"  size      {path.stat().st_size:,} bytes")
    print(f"  pages     {pages}")
    print(f"  checksum  {checksum}")
    for field in ("Title", "Author", "Subject", "CreationDate"):
        if meta.get(field):
            print(f"  {field.lower():9} {meta[field][:60]}")

    console.section("First page as extracted")
    if first_page.strip():
        for line in first_page.strip().splitlines()[:18]:
            print(f"  {line[:76]}")
    else:
        print()
        console.warn("no text layer on page 1 -- this is probably a scanned image")
        console.info("extraction will produce nothing useful without OCR")
        console.info("re-run with --ocr (requires pytesseract + Tesseract installed)")

    print()
    print("  Confirm:")
    console.bullet("this is the right scheme")
    console.bullet("this is the right version / year")
    console.bullet("the document looks complete, not a cover page or a fragment")

    approved = console.confirm("Correct scheme and version?", gate="1")
    state.set_gate("1_identity", APPROVED if approved else REJECTED,
                   note=f"{path.name} {checksum}")
    return approved


# --------------------------------------------------------------------------
# Extraction + Gate 2
# --------------------------------------------------------------------------


def extract_text_pages(path: Path) -> list[str]:
    """Extract per page with pdfminer.six -- pure Python, no poppler needed."""
    from pdfminer.high_level import extract_text
    from pdfminer.layout import LAParams
    from pypdf import PdfReader

    page_count = len(PdfReader(str(path)).pages)
    params = LAParams(line_margin=0.5, char_margin=2.0, boxes_flow=0.5)
    pages: list[str] = []
    for index in range(page_count):
        try:
            pages.append(extract_text(str(path), page_numbers=[index], laparams=params))
        except Exception as exc:  # noqa: BLE001
            console.warn(f"page {index + 1} failed to extract: {exc}")
            pages.append("")
    return pages


def ocr_text_pages(path: Path) -> list[str]:
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise SystemExit(
            "OCR needs extra tools that are not installed:\n"
            "    pip install pytesseract pdf2image\n"
            "  plus the Tesseract binary itself, with the language packs you need:\n"
            "    https://github.com/UB-Mannheim/tesseract/wiki  (Windows installer)\n"
            "  Install 'hin', 'tam' and 'pan' language data if the document is not\n"
            "  in English.\n"
            f"  (import failed: {exc})"
        ) from exc

    print("  running OCR -- this is slow, a few seconds per page")
    return [pytesseract.image_to_string(image)
            for image in convert_from_path(str(path))]


def gate_extraction(pages: list[str], txt_path: Path, state) -> bool:
    console.heading("GATE 2 — Extraction quality")

    text = "\n".join(pages)
    total = len(text)
    print()
    print(f"  pages      {len(pages)}")
    print(f"  characters {total:,}")

    console.section("Characters per page")
    empty = []
    for index, page in enumerate(pages, start=1):
        count = len(page.strip())
        if count == 0:
            empty.append(index)
        bar = "#" * min(40, count // 60)
        print(f"  {index:3}  {count:6,}  {bar}")

    if empty:
        print()
        console.warn(f"page(s) with no text at all: {', '.join(map(str, empty))}")
        console.info("scanned inserts, or a table rendered purely as an image")

    txt_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.write_text(text, encoding="utf-8", newline="\n")
    print()
    console.ok(f"wrote {txt_path}")

    print()
    print("  Open that file and read it before answering. Check specifically:")
    console.bullet("the ELIGIBILITY section is readable")
    console.bullet("the EXCLUSIONS section is readable")
    console.bullet("no rule-bearing table has been shredded into unreadable columns")
    print()
    console.info("Mangled text elsewhere is tolerable. Mangled eligibility text is")
    console.info("not -- every quote will be validated against this file, so a")
    console.info("broken .txt makes correct quotes fail.")
    console.info("")
    console.info("If a table is destroyed you may hand-repair THIS .txt and set")
    console.info("hand_corrected: true in the meta. Repairing the .txt is honest and")
    console.info("reviewable; editing quotes later to match a broken .txt is not.")

    approved = console.confirm("Is the extracted text usable?", gate="2")
    state.set_gate("2_extraction", APPROVED if approved else REJECTED,
                   note=f"{len(pages)} pages, {total} chars")
    return approved


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    console.setup()

    parser = argparse.ArgumentParser(
        description="Download a scheme's official document and prepare it for drafting.",
    )
    parser.add_argument("--scheme", required=True, help="scheme slug, e.g. pm-kisan")
    parser.add_argument("--url", help="URL of the official PDF")
    parser.add_argument("--file", help="local PDF, if you downloaded it manually")
    parser.add_argument("--source-id", help="short label (default: from filename)")
    parser.add_argument("--ocr", action="store_true",
                        help="OCR instead of text extraction (scanned documents)")
    parser.add_argument("--force", action="store_true",
                        help="replace an already-approved source")
    parser.add_argument("--root", help="repository root (default: auto)")
    args = parser.parse_args(argv)

    if not args.url and not args.file:
        parser.error("give either --url or --file")

    root = Path(args.root) if args.root else repo_root()
    directory = scheme_dir(args.scheme, root)
    source_dir = directory / "source"
    state = load_state(args.scheme, directory)

    source_id = args.source_id or slug_from_url(args.url or args.file)
    pdf_path = source_dir / f"{source_id}.pdf"
    txt_path = source_dir / f"{source_id}.txt"
    meta_path = source_dir / f"{source_id}.meta.json"

    if pdf_path.exists() and not args.force:
        existing = sha256_file(pdf_path)
        console.heading("Source already present")
        print()
        print(f"  {pdf_path}")
        print(f"  {existing}")
        print()
        console.info("Re-run with --force to replace it. The new checksum will be")
        console.info("shown before anything is overwritten.")
        return 1

    # Gate 0
    if args.url:
        if not gate_source(args.url, state):
            return 1
        try:
            download(args.url, pdf_path)
        except Exception as exc:  # noqa: BLE001
            print()
            console.fail(f"download failed: {exc}")
            console.info("Many government sites block automated requests. Download")
            console.info("the PDF in a browser and re-run with --file <path>.")
            return 1
    else:
        local = Path(args.file)
        if not local.exists():
            console.fail(f"no such file: {local}")
            return 1
        if not gate_source(str(local.resolve()), state):
            return 1
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(local.read_bytes())
        print()
        console.ok(f"copied to {pdf_path}")

    checksum = sha256_file(pdf_path)

    if args.force and pdf_path.exists():
        console.info(f"new checksum: {checksum}")

    # Gate 1
    if not gate_identity(pdf_path, checksum, state):
        print()
        console.info("Rejected. The downloaded file is kept so you can inspect it,")
        console.info("but no text was extracted. Find the right document and re-run.")
        return 1

    # Extraction + Gate 2
    print()
    print("  extracting text ...")
    pages = ocr_text_pages(pdf_path) if args.ocr else extract_text_pages(pdf_path)
    if not gate_extraction(pages, txt_path, state):
        print()
        console.info("Rejected. Fix the extraction (try --ocr, or hand-repair the")
        console.info(".txt) and re-run, or choose a better source document.")
        return 1

    meta = {
        "id": source_id,
        "url": args.url or "",
        "local_file": args.file or "",
        "retrieved_at": date.today().isoformat(),
        "checksum": checksum,
        "extractor": "tesseract-ocr" if args.ocr else "pdfminer.six",
        "pages": len(pages),
        "characters": sum(len(p) for p in pages),
        "hand_corrected": False,
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8",
                         newline="\n")

    console.heading("Ready for drafting")
    print()
    console.ok(f"pdf   {pdf_path}")
    console.ok(f"txt   {txt_path}   <- quotes validate against this")
    console.ok(f"meta  {meta_path}")
    print()
    print("  Paste this into your scheme.md frontmatter:")
    print()
    print("  sources:")
    print(f"    - id: {source_id}")
    print(f"      pdf: source/{pdf_path.name}")
    print(f"      txt: source/{txt_path.name}")
    print(f"      url: {args.url or '<local file>'}")
    print(f"      retrieved_at: '{meta['retrieved_at']}'")
    print(f"      checksum: {checksum}")
    print()
    print("  Next:")
    print(f"    python data/scripts/segment.py --scheme {args.scheme} --emit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
