"""Compile scheme.md into the machine-readable projections.

    python data/scripts/build.py --scheme pm-kisan
    python data/scripts/build.py --all --check      # CI: fail if output is stale

`scheme.md` is the only hand-authored artifact. Three things are generated from
it, and none of them is ever edited by hand:

    build/rules.json     conditions + decision, for the deterministic rule engine
    build/graph.json     nodes and edges, for multi-hop retrieval
    build/clauses.jsonl  one row per clause, ready to embed

Generating the graph from the rule pack rather than authoring it separately is
deliberate. Two hand-maintained descriptions of the same rules will drift, and
the drift is silent -- the rule engine says one thing, retrieval says another,
and nothing flags it. Here there is one source and three views of it.

Output is byte-for-byte deterministic: sorted keys, stable ordering, LF endings,
and no timestamps. `--check` regenerates and compares, so CI turns any drift
between scheme.md and build/ into a reviewable diff.

Embedding text is `plain` plus aliases, never the blockquote: retrieval should
match how a citizen describes their situation, while citations quote what the
government actually wrote.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import console
from grammar import referenced_attributes, validate_expr
from parse_scheme import Scheme, SchemeParseError, load_scheme, repo_root, scheme_dir


def _json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def build_rules(scheme: Scheme) -> dict:
    return {
        "scheme": scheme.scheme,
        "name_en": scheme.name_en,
        "tier": scheme.tier,
        "version": scheme.version,
        "effective_from": scheme.effective_from,
        "effective_to": scheme.effective_to,
        "authority": scheme.authority,
        "decision": scheme.decision,
        "conditions": [
            {
                "id": condition.id,
                "expr": condition.expr,
                "clause": condition.clause,
                "asks": condition.asks,
                "reads": referenced_attributes(condition.expr)
                if not validate_expr(condition.expr) else [],
            }
            for condition in scheme.conditions
        ],
        "sources": [source.to_dict() for source in scheme.sources],
    }


def build_graph(scheme: Scheme) -> dict:
    """Nodes and edges, derived entirely from scheme.md.

    Every Clause node carries its source and span metadata, and every Condition
    node reaches a Clause via GROUNDED_IN. A node with no path to a committed
    source is a bug -- validate.py treats the absence of that path as an error.
    """
    nodes: list[dict] = []
    edges: list[dict] = []

    def node(node_id: str, node_type: str, **props) -> None:
        nodes.append({"id": node_id, "type": node_type, **props})

    def edge(source: str, predicate: str, target: str, **props) -> None:
        edges.append({"from": source, "predicate": predicate, "to": target, **props})

    scheme_id = f"scheme:{scheme.scheme}"
    node(scheme_id, "Scheme", name=scheme.name_en, tier=scheme.tier,
         version=scheme.version, authority=scheme.authority,
         effective_from=scheme.effective_from, effective_to=scheme.effective_to)

    for source in scheme.sources:
        source_id = f"source:{source.id}"
        node(source_id, "SourceDocument", url=source.url,
             checksum=source.checksum, retrieved_at=source.retrieved_at)

    for clause in scheme.clauses:
        clause_id = f"clause:{clause.id}"
        node(clause_id, "Clause", clause_type=clause.type, page=clause.page,
             tier=scheme.tier, version=scheme.version, uncertain=clause.uncertain)
        edge(scheme_id, "HAS_CLAUSE", clause_id)
        if clause.source:
            edge(clause_id, "FROM", f"source:{clause.source}")

        # Exclusions and required documents are first-class edges: "who is
        # disqualified" and "what do I need" are the questions users actually ask.
        if clause.type == "exclusion":
            edge(scheme_id, "EXCLUDES", clause_id)
        elif clause.type == "document":
            edge(scheme_id, "REQUIRES_DOCUMENT", clause_id)
        elif clause.type == "benefit":
            edge(scheme_id, "PROVIDES", clause_id)

        for attribute in clause.tests:
            attribute_id = f"attribute:{attribute}"
            if not any(n["id"] == attribute_id for n in nodes):
                node(attribute_id, "Attribute", name=attribute)
            edge(clause_id, "BEARS_ON", attribute_id)

    for condition in scheme.conditions:
        condition_id = f"condition:{condition.id}"
        node(condition_id, "Condition", expr=condition.expr, asks=condition.asks)
        edge(scheme_id, "REQUIRES", condition_id)
        if condition.clause:
            edge(condition_id, "GROUNDED_IN", f"clause:{condition.clause}")
        if not validate_expr(condition.expr):
            for attribute in referenced_attributes(condition.expr):
                attribute_id = f"attribute:{attribute}"
                if not any(n["id"] == attribute_id for n in nodes):
                    node(attribute_id, "Attribute", name=attribute)
                edge(condition_id, "TESTS", attribute_id)

    nodes.sort(key=lambda n: (n["type"], n["id"]))
    edges.sort(key=lambda e: (e["from"], e["predicate"], e["to"]))
    return {"scheme": scheme.scheme, "version": scheme.version,
            "nodes": nodes, "edges": edges}


def build_clauses(scheme: Scheme) -> list[dict]:
    rows: list[dict] = []
    for clause in scheme.clauses:
        source = scheme.source(clause.source)
        rows.append({
            "id": clause.id,
            "scheme": scheme.scheme,
            "tier": scheme.tier,
            "version": scheme.version,
            "type": clause.type,
            "quote": clause.quote,          # cited verbatim, never embedded alone
            "plain": clause.plain,
            "aliases": clause.aliases,
            # Embed how a citizen would say it; cite what the government wrote.
            "embedding_text": " ".join(
                [clause.plain, *clause.aliases]
            ).strip() or clause.quote,
            "tests": clause.tests,
            "source_id": clause.source,
            "source_url": source.url if source else "",
            "page": clause.page,
            "uncertain": clause.uncertain,
        })
    return rows


def outputs(scheme: Scheme) -> dict[str, str]:
    rules = build_rules(scheme)
    graph = build_graph(scheme)
    clauses = build_clauses(scheme)
    return {
        f"rules.v{scheme.version}.json": _json(rules),
        f"graph.v{scheme.version}.json": _json(graph),
        "clauses.jsonl": "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in clauses
        ),
    }


def write(scheme: Scheme, directory: Path, check_only: bool) -> tuple[bool, list[str]]:
    build_dir = directory / "build"
    generated = outputs(scheme)
    stale: list[str] = []

    if check_only:
        for name, content in generated.items():
            path = build_dir / name
            if not path.exists():
                stale.append(f"{name} (missing)")
            elif path.read_text(encoding="utf-8") != content:
                stale.append(name)
        return not stale, stale

    build_dir.mkdir(parents=True, exist_ok=True)
    for name, content in generated.items():
        (build_dir / name).write_text(content, encoding="utf-8", newline="\n")
    return True, list(generated)


def main(argv: list[str] | None = None) -> int:
    console.setup()

    parser = argparse.ArgumentParser(
        description="Compile scheme.md into rules, graph, and clause rows.",
    )
    parser.add_argument("--scheme")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--check", action="store_true",
                        help="fail if build/ is out of date (for CI)")
    parser.add_argument("--root")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else repo_root()

    if args.all:
        paths = sorted((root / "data" / "schemes").glob("*/scheme.md"))
        if not paths:
            console.warn("no schemes found under data/schemes/")
            return 0
    elif args.scheme:
        paths = [scheme_dir(args.scheme, root) / "scheme.md"]
    else:
        parser.error("give --scheme or --all")

    failed = 0
    for path in paths:
        if not path.exists():
            console.fail(f"no such file: {path}")
            failed += 1
            continue
        try:
            scheme = load_scheme(path)
        except SchemeParseError as exc:
            console.fail(f"{path.parent.name}: {exc}")
            failed += 1
            continue

        ok, names = write(scheme, path.parent, args.check)
        console.heading(f"build — {scheme.scheme} v{scheme.version}")
        print()
        if args.check:
            if ok:
                console.ok("build/ is up to date")
            else:
                console.fail("build/ is stale: " + ", ".join(names))
                console.info("run without --check to regenerate, and commit the result")
                failed += 1
        else:
            for name in names:
                console.ok(f"wrote build/{name}")
            print()
            print(f"  clauses: {len(scheme.clauses)}   "
                  f"conditions: {len(scheme.conditions)}")

    print()
    if failed:
        return 1
    console.ok(f"{len(paths)} scheme(s) built" if not args.check else "all up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
