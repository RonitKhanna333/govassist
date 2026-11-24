"""Unreviewed document hints must still be the source's own words."""
import json
import re

from parse_scheme import repo_root


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def test_dashboard_hints_carry_the_official_source_link():
    from api.onboarding.router import _document_hints
    hints = _document_hints("pmuy")
    assert hints and all(h["source_url"].startswith("https://www.pmuy.gov.in/") for h in hints)
    assert _document_hints("apy") == []


def test_every_document_hint_is_quoted_from_its_source():
    root = repo_root()
    hints = json.loads((root / "data" / "document_hints.json").read_text(encoding="utf-8"))
    for scheme, rows in hints.items():
        if scheme.startswith("_"):
            continue
        for row in rows:
            source = root / "data" / "schemes" / scheme / "source" / f"{row['source']}.txt"
            assert _collapse(row["quote"]) in _collapse(source.read_text(encoding="utf-8")), \
                (scheme, row["quote"])
