"""Reader and writer for `scheme.md` -- the one hand-authored corpus artifact.

Format (see the corpus spec in the skill's references/clause-spec.md):

    ---
    scheme: pm-kisan
    ...
    conditions:
      - id: landholding
        expr: profile.owns_cultivable_land == true
        clause: landholding-basic
        asks: Do you or your family own cultivable farmland?
    decision: ALL(conditions)
    ---

    ## landholding-basic

    ```yaml
    type: eligibility
    source: guidelines-2024
    page: 3
    tests: [owns_cultivable_land]
    ```

    > All landholding farmers' families, which have cultivable landholding in
    > their names, shall be eligible to receive benefit under the scheme.

    **Plain:** You qualify if you or your family own farmland.

    **Aliases:** my own farm land · we have some acres

Markdown rather than JSON because human review is the quality gate, and a
clause corpus has to be reviewable in a pull-request diff.

Round-tripping is deterministic: parse -> dump -> parse yields identical data,
so `build.py` output can be diffed in CI without spurious churn.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ALIAS_SEPARATOR = " · "

_FRONTMATTER = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
_SECTION = re.compile(r"^##[ \t]+(.+?)[ \t]*$", re.MULTILINE)
_YAML_FENCE = re.compile(r"```ya?ml\r?\n(.*?)```", re.DOTALL)
_BLOCKQUOTE_LINE = re.compile(r"^[ \t]*>[ \t]?(.*)$")
_PLAIN = re.compile(r"^\*\*Plain:?\*\*[ \t]*(.*)$", re.MULTILINE | re.IGNORECASE)
_ALIASES = re.compile(r"^\*\*Aliases:?\*\*[ \t]*(.*)$", re.MULTILINE | re.IGNORECASE)

CLAUSE_TYPES = {
    "eligibility", "exclusion", "benefit", "document", "procedure", "definition",
}


class SchemeParseError(ValueError):
    pass


@dataclass
class Source:
    id: str
    pdf: str = ""
    txt: str = ""
    url: str = ""
    retrieved_at: str = ""
    checksum: str = ""
    extractor: str = ""
    hand_corrected: bool = False

    def to_dict(self) -> dict:
        out = {"id": self.id, "pdf": self.pdf, "txt": self.txt, "url": self.url,
               "retrieved_at": self.retrieved_at, "checksum": self.checksum}
        if self.extractor:
            out["extractor"] = self.extractor
        if self.hand_corrected:
            out["hand_corrected"] = True
        return out


@dataclass
class Condition:
    id: str
    expr: str
    clause: str
    asks: str = ""

    def to_dict(self) -> dict:
        out = {"id": self.id, "expr": self.expr, "clause": self.clause}
        if self.asks:
            out["asks"] = self.asks
        return out


@dataclass
class Clause:
    id: str
    quote: str = ""
    plain: str = ""
    aliases: list[str] = field(default_factory=list)
    type: str = "eligibility"
    source: str = ""
    page: int | None = None
    tests: list[str] = field(default_factory=list)
    uncertain: bool = False
    note: str = ""

    def meta_dict(self) -> dict:
        out: dict[str, Any] = {"type": self.type, "source": self.source,
                               "page": self.page, "tests": self.tests}
        if self.uncertain:
            out["uncertain"] = True
        if self.note:
            out["note"] = self.note
        return out


@dataclass
class Scheme:
    scheme: str
    name_en: str = ""
    tier: int = 1
    version: int = 1
    effective_from: str | None = None
    effective_to: str | None = None
    authority: str = ""
    license: str = ""
    sources: list[Source] = field(default_factory=list)
    conditions: list[Condition] = field(default_factory=list)
    decision: str = "ALL(conditions)"
    clauses: list[Clause] = field(default_factory=list)
    path: Path | None = None

    def clause(self, clause_id: str) -> Clause | None:
        return next((c for c in self.clauses if c.id == clause_id), None)

    def source(self, source_id: str) -> Source | None:
        return next((s for s in self.sources if s.id == source_id), None)

    @property
    def clause_ids(self) -> list[str]:
        return [c.id for c in self.clauses]


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def _clean_quote(lines: list[str]) -> str:
    """Join blockquote lines into the quote text, preserving internal spacing."""
    return "\n".join(lines).strip()


def _parse_clause(clause_id: str, body: str) -> Clause:
    clause = Clause(id=clause_id)

    fence = _YAML_FENCE.search(body)
    if fence:
        try:
            meta = yaml.safe_load(fence.group(1)) or {}
        except yaml.YAMLError as exc:
            raise SchemeParseError(f"clause '{clause_id}': bad yaml block: {exc}") from exc
        if not isinstance(meta, dict):
            raise SchemeParseError(f"clause '{clause_id}': yaml block must be a mapping")
        clause.type = str(meta.get("type", "eligibility"))
        clause.source = str(meta.get("source", ""))
        page = meta.get("page")
        clause.page = int(page) if isinstance(page, (int, str)) and str(page).isdigit() else None
        tests = meta.get("tests") or []
        clause.tests = [str(t) for t in tests] if isinstance(tests, list) else []
        clause.uncertain = bool(meta.get("uncertain", False))
        clause.note = str(meta.get("note", "") or "")

    # The blockquote is the citation, so take it from the text AFTER the yaml
    # fence -- a fence can legitimately contain '>' inside a string.
    after_fence = body[fence.end():] if fence else body
    quote_lines: list[str] = []
    for line in after_fence.splitlines():
        match = _BLOCKQUOTE_LINE.match(line)
        if match:
            quote_lines.append(match.group(1).rstrip())
        elif quote_lines and not line.strip():
            continue  # blank line inside a quote block
        elif quote_lines:
            break
    clause.quote = _clean_quote(quote_lines)

    plain = _PLAIN.search(body)
    if plain:
        clause.plain = plain.group(1).strip()

    aliases = _ALIASES.search(body)
    if aliases:
        raw = aliases.group(1).strip()
        parts = re.split(r"\s*[·|]\s*", raw) if raw else []
        clause.aliases = [p.strip() for p in parts if p.strip()]

    return clause


def parse_scheme_text(text: str, path: Path | None = None) -> Scheme:
    text = text.replace("\r\n", "\n")

    match = _FRONTMATTER.match(text)
    if not match:
        raise SchemeParseError(
            "missing YAML frontmatter -- the file must start with a '---' line"
        )
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise SchemeParseError(f"bad frontmatter yaml: {exc}") from exc
    if not isinstance(meta, dict):
        raise SchemeParseError("frontmatter must be a mapping")
    if not meta.get("scheme"):
        raise SchemeParseError("frontmatter is missing required key 'scheme'")

    scheme = Scheme(
        scheme=str(meta["scheme"]),
        name_en=str(meta.get("name_en", "")),
        tier=int(meta.get("tier", 1)),
        version=int(meta.get("version", 1)),
        effective_from=meta.get("effective_from"),
        effective_to=meta.get("effective_to"),
        authority=str(meta.get("authority", "")),
        license=str(meta.get("license", "")),
        decision=str(meta.get("decision", "ALL(conditions)")),
        path=path,
    )
    if scheme.effective_from is not None:
        scheme.effective_from = str(scheme.effective_from)
    if scheme.effective_to is not None:
        scheme.effective_to = str(scheme.effective_to)

    for raw in meta.get("sources") or []:
        if not isinstance(raw, dict) or not raw.get("id"):
            raise SchemeParseError("every entry in 'sources' needs an 'id'")
        scheme.sources.append(
            Source(
                id=str(raw["id"]),
                pdf=str(raw.get("pdf", "")),
                txt=str(raw.get("txt", "")),
                url=str(raw.get("url", "")),
                retrieved_at=str(raw.get("retrieved_at", "")),
                checksum=str(raw.get("checksum", "")),
                extractor=str(raw.get("extractor", "")),
                hand_corrected=bool(raw.get("hand_corrected", False)),
            )
        )

    for raw in meta.get("conditions") or []:
        if not isinstance(raw, dict) or not raw.get("id"):
            raise SchemeParseError("every entry in 'conditions' needs an 'id'")
        scheme.conditions.append(
            Condition(
                id=str(raw["id"]),
                expr=str(raw.get("expr", "")),
                clause=str(raw.get("clause", "")),
                asks=str(raw.get("asks", "") or ""),
            )
        )

    body = text[match.end():]
    headings = list(_SECTION.finditer(body))
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
        clause_id = heading.group(1).strip()
        scheme.clauses.append(_parse_clause(clause_id, body[heading.end():end]))

    seen: set[str] = set()
    for clause in scheme.clauses:
        if clause.id in seen:
            raise SchemeParseError(f"duplicate clause id '{clause.id}'")
        seen.add(clause.id)

    return scheme


def load_scheme(path: str | Path) -> Scheme:
    path = Path(path)
    if not path.exists():
        raise SchemeParseError(f"no such file: {path}")
    return parse_scheme_text(path.read_text(encoding="utf-8"), path=path)


# --------------------------------------------------------------------------
# Serialization
# --------------------------------------------------------------------------


def _yaml_dump(data: dict) -> str:
    return yaml.dump(data, sort_keys=False, allow_unicode=True,
                     default_flow_style=False, width=100).rstrip()


def dump_scheme(scheme: Scheme) -> str:
    """Render a Scheme back to `scheme.md`. Deterministic and round-trip safe."""
    front: dict[str, Any] = {
        "scheme": scheme.scheme,
        "name_en": scheme.name_en,
        "tier": scheme.tier,
        "version": scheme.version,
        "effective_from": scheme.effective_from,
        "effective_to": scheme.effective_to,
        "authority": scheme.authority,
        "license": scheme.license,
        "sources": [s.to_dict() for s in scheme.sources],
        "conditions": [c.to_dict() for c in scheme.conditions],
        "decision": scheme.decision,
    }

    parts = ["---", _yaml_dump(front), "---", ""]

    for clause in scheme.clauses:
        parts.append(f"## {clause.id}")
        parts.append("")
        parts.append("```yaml")
        parts.append(_yaml_dump(clause.meta_dict()))
        parts.append("```")
        parts.append("")
        for line in (clause.quote or "").splitlines() or [""]:
            parts.append(f"> {line}".rstrip())
        parts.append("")
        if clause.plain:
            parts.append(f"**Plain:** {clause.plain}")
            parts.append("")
        if clause.aliases:
            parts.append("**Aliases:** " + ALIAS_SEPARATOR.join(clause.aliases))
            parts.append("")

    return "\n".join(parts).rstrip() + "\n"


def save_scheme(scheme: Scheme, path: str | Path | None = None) -> Path:
    target = Path(path) if path else scheme.path
    if target is None:
        raise SchemeParseError("no path to save to")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dump_scheme(scheme), encoding="utf-8", newline="\n")
    return target


# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def scheme_dir(slug: str, root: Path | None = None) -> Path:
    return (root or repo_root()) / "data" / "schemes" / slug


def scheme_path(slug: str, root: Path | None = None) -> Path:
    return scheme_dir(slug, root) / "scheme.md"


def draft_path(slug: str, root: Path | None = None) -> Path:
    return scheme_dir(slug, root) / "scheme.draft.md"


def source_text(scheme: Scheme, source_id: str) -> str:
    """Read the extracted .txt a clause cites -- the validation target."""
    source = scheme.source(source_id)
    if source is None:
        raise SchemeParseError(f"unknown source id '{source_id}'")
    if scheme.path is None:
        raise SchemeParseError("scheme has no path; cannot resolve source files")
    txt = scheme.path.parent / source.txt
    if not txt.exists():
        raise SchemeParseError(f"source text not found: {txt}")
    return txt.read_text(encoding="utf-8", errors="replace")
