"""Load build/graph.v{n}.json into storage. Never derives, only upserts.

    python -m api.graph.sync --scheme pmfme
    python -m api.graph.sync --all
    python -m api.graph.sync --all --database-url postgresql://...

Idempotent per (scheme, version): re-running replaces that version's rows
wholesale rather than diffing, because build/graph.v{n}.json is itself
deterministic output (build.py guarantees byte-identical regeneration) -- if
the file didn't change, replacing it is a no-op; if it did, a diff-based
upsert would just be more code to reach the same result.

This is the one place that reads build/graph.v{n}.json. Nothing downstream
(traverse.py, the rule engine, any future agent) reads scheme.md or
graph.json directly -- they read this table.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import api._corpus_bridge  # noqa: F401 -- must run before importing parse_scheme
from api.db import get_engine, get_session_factory, init_db
from api.graph.models import GraphEdge, GraphNode
from parse_scheme import repo_root  # noqa: E402


def _latest_graph_path(scheme_dir: Path) -> Path | None:
    candidates = sorted(scheme_dir.glob("build/graph.v*.json"))
    return candidates[-1] if candidates else None


def load_graph_json(scheme: str, root: Path) -> dict:
    scheme_dir = root / "data" / "schemes" / scheme
    path = _latest_graph_path(scheme_dir)
    if path is None:
        raise FileNotFoundError(
            f"no build/graph.v*.json for '{scheme}' -- run "
            f"'python data/scripts/build.py --scheme {scheme}' first"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def sync_scheme(scheme: str, root: Path, session_factory) -> tuple[int, int]:
    graph = load_graph_json(scheme, root)
    version = graph["version"]

    with session_factory() as session:
        # Replace this (scheme, version) wholesale -- see module docstring.
        session.query(GraphEdge).filter_by(scheme=scheme, version=version).delete()
        session.query(GraphNode).filter_by(scheme=scheme, version=version).delete()

        for node in graph["nodes"]:
            props = {k: v for k, v in node.items() if k not in ("id", "type", "name")}
            session.add(GraphNode(
                scheme=scheme, version=version,
                id=node["id"], type=node["type"],
                name=node.get("name"), props=props,
            ))

        for edge in graph["edges"]:
            session.add(GraphEdge(
                scheme=scheme, version=version,
                from_id=edge["from"], predicate=edge["predicate"], to_id=edge["to"],
            ))

        session.commit()

    return len(graph["nodes"]), len(graph["edges"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Load committed build/graph.v{n}.json files into storage.",
    )
    parser.add_argument("--scheme", help="sync one scheme")
    parser.add_argument("--all", action="store_true", help="sync every scheme")
    parser.add_argument("--database-url", help="override DATABASE_URL for this run")
    parser.add_argument("--root")
    args = parser.parse_args(argv)

    if not args.scheme and not args.all:
        parser.error("give --scheme or --all")

    root = Path(args.root) if args.root else repo_root()
    engine = get_engine(args.database_url)
    init_db(engine)
    session_factory = get_session_factory(engine)

    if args.all:
        schemes = sorted(
            p.parent.name for p in (root / "data" / "schemes").glob("*/build")
        )
        if not schemes:
            print("no schemes with a build/ directory found")
            return 0
    else:
        schemes = [args.scheme]

    failed = 0
    for scheme in schemes:
        try:
            n_nodes, n_edges = sync_scheme(scheme, root, session_factory)
        except FileNotFoundError as exc:
            print(f"[FAIL] {scheme}: {exc}")
            failed += 1
            continue
        print(f"[ok]   {scheme}: {n_nodes} nodes, {n_edges} edges")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
