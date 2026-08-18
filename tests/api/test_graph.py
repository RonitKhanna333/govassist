"""api/graph/{sync,traverse}.py -- storage scoping and the five retrieval
patterns from docs/phase2-design.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.db import Base, get_session_factory
from api.graph import traverse as T
from api.graph.sync import sync_scheme
from sqlalchemy import create_engine


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    from api.graph import models  # noqa: F401 -- ensure tables are registered
    Base.metadata.create_all(engine)
    return get_session_factory(engine)


def _write_graph(root: Path, scheme: str, version: int, nodes: list[dict],
                  edges: list[dict]) -> None:
    build_dir = root / "data" / "schemes" / scheme / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / f"graph.v{version}.json").write_text(
        json.dumps({"scheme": scheme, "version": version, "nodes": nodes, "edges": edges}),
        encoding="utf-8",
    )


def _minimal_scheme_graph(scheme: str, clause_id: str) -> tuple[list[dict], list[dict]]:
    """A tiny but complete graph exercising every predicate the five patterns need."""
    scheme_node = f"scheme:{scheme}"
    condition_node = "condition:only_condition"
    clause_node = f"clause:{clause_id}"
    source_node = "source:doc"
    attr_node = "attribute:age"
    doc_clause_node = f"clause:{clause_id}-doc"
    benefit_clause_node = f"clause:{clause_id}-benefit"
    excl_clause_node = f"clause:{clause_id}-excl"
    excl_condition_node = "condition:exclusion_condition"

    nodes = [
        {"id": scheme_node, "type": "Scheme", "name": scheme},
        {"id": condition_node, "type": "Condition", "expr": "profile.age >= 18"},
        {"id": clause_node, "type": "Clause", "clause_type": "eligibility"},
        {"id": source_node, "type": "SourceDocument", "url": "https://example.gov/doc.pdf"},
        {"id": attr_node, "type": "Attribute", "name": "age"},
        {"id": doc_clause_node, "type": "Clause", "clause_type": "document"},
        {"id": benefit_clause_node, "type": "Clause", "clause_type": "benefit"},
        {"id": excl_clause_node, "type": "Clause", "clause_type": "exclusion"},
        {"id": excl_condition_node, "type": "Condition", "expr": "profile.x == false"},
    ]
    edges = [
        {"from": scheme_node, "predicate": "REQUIRES", "to": condition_node},
        {"from": condition_node, "predicate": "GROUNDED_IN", "to": clause_node},
        {"from": condition_node, "predicate": "TESTS", "to": attr_node},
        {"from": clause_node, "predicate": "FROM", "to": source_node},
        {"from": clause_node, "predicate": "BEARS_ON", "to": attr_node},
        {"from": scheme_node, "predicate": "HAS_CLAUSE", "to": clause_node},
        {"from": scheme_node, "predicate": "REQUIRES_DOCUMENT", "to": doc_clause_node},
        {"from": scheme_node, "predicate": "PROVIDES", "to": benefit_clause_node},
        {"from": scheme_node, "predicate": "EXCLUDES", "to": excl_clause_node},
        {"from": excl_condition_node, "predicate": "GROUNDED_IN", "to": excl_clause_node},
    ]
    return nodes, edges


def test_sync_loads_nodes_and_edges(tmp_path, session_factory):
    nodes, edges = _minimal_scheme_graph("alpha", "the-clause")
    _write_graph(tmp_path, "alpha", 1, nodes, edges)

    n, e = sync_scheme("alpha", tmp_path, session_factory)
    assert n == len(nodes)
    assert e == len(edges)


def test_cross_scheme_clause_id_collision_does_not_merge(tmp_path, session_factory):
    """The exact bug graph/models.py's docstring exists to prevent: two
    schemes independently choosing the same clause slug must stay distinct."""
    nodes_a, edges_a = _minimal_scheme_graph("alpha", "shared-slug")
    nodes_b, edges_b = _minimal_scheme_graph("beta", "shared-slug")
    _write_graph(tmp_path, "alpha", 1, nodes_a, edges_a)
    _write_graph(tmp_path, "beta", 1, nodes_b, edges_b)

    sync_scheme("alpha", tmp_path, session_factory)
    sync_scheme("beta", tmp_path, session_factory)

    with session_factory() as s:
        ev_a = T.eligibility_evidence(s, "alpha", 1)
        ev_b = T.eligibility_evidence(s, "beta", 1)

    # Same raw clause id ("clause:shared-slug") in both -- but each traversal
    # is scoped to its own scheme and must not see the other's clause.
    assert ev_a.nodes["clause:shared-slug"]["scheme"] == "alpha"
    assert ev_b.nodes["clause:shared-slug"]["scheme"] == "beta"


def test_reverse_by_attributes_merges_across_schemes_on_purpose(tmp_path, session_factory):
    """The one intentional cross-scheme merge: Attribute nodes, by name."""
    nodes_a, edges_a = _minimal_scheme_graph("alpha", "clause-a")
    nodes_b, edges_b = _minimal_scheme_graph("beta", "clause-b")
    _write_graph(tmp_path, "alpha", 1, nodes_a, edges_a)
    _write_graph(tmp_path, "beta", 1, nodes_b, edges_b)
    sync_scheme("alpha", tmp_path, session_factory)
    sync_scheme("beta", tmp_path, session_factory)

    with session_factory() as s:
        versions = T.latest_versions(s, ["alpha", "beta"])
        ev = T.reverse_by_attributes(s, ["age"], versions)

    schemes_reached = {n["scheme"] for n in ev.nodes.values() if n["type"] == "Scheme"}
    assert schemes_reached == {"alpha", "beta"}


def test_eligibility_evidence_pattern(tmp_path, session_factory):
    nodes, edges = _minimal_scheme_graph("alpha", "the-clause")
    _write_graph(tmp_path, "alpha", 1, nodes, edges)
    sync_scheme("alpha", tmp_path, session_factory)

    with session_factory() as s:
        ev = T.eligibility_evidence(s, "alpha", 1)

    assert ev.clause_ids == ["clause:the-clause"]
    assert "attribute:age" in ev.nodes  # TESTS hop included, for phrasing the question
    assert "source:doc" in ev.nodes      # FROM hop included, for citation


def test_required_documents_pattern(tmp_path, session_factory):
    nodes, edges = _minimal_scheme_graph("alpha", "x")
    _write_graph(tmp_path, "alpha", 1, nodes, edges)
    sync_scheme("alpha", tmp_path, session_factory)

    with session_factory() as s:
        ev = T.required_documents(s, "alpha", 1)

    assert ev.clause_ids == ["clause:x-doc"]


def test_benefits_pattern(tmp_path, session_factory):
    nodes, edges = _minimal_scheme_graph("alpha", "x")
    _write_graph(tmp_path, "alpha", 1, nodes, edges)
    sync_scheme("alpha", tmp_path, session_factory)

    with session_factory() as s:
        ev = T.benefits(s, "alpha", 1)

    assert ev.clause_ids == ["clause:x-benefit"]


def test_exclusions_pattern_pairs_clause_with_its_condition(tmp_path, session_factory):
    nodes, edges = _minimal_scheme_graph("alpha", "x")
    _write_graph(tmp_path, "alpha", 1, nodes, edges)
    sync_scheme("alpha", tmp_path, session_factory)

    with session_factory() as s:
        ev = T.exclusions(s, "alpha", 1)

    assert ev.clause_ids == ["clause:x-excl"]
    assert "condition:exclusion_condition" in ev.nodes


def test_resync_replaces_rather_than_duplicates(tmp_path, session_factory):
    nodes, edges = _minimal_scheme_graph("alpha", "x")
    _write_graph(tmp_path, "alpha", 1, nodes, edges)
    n1, e1 = sync_scheme("alpha", tmp_path, session_factory)
    n2, e2 = sync_scheme("alpha", tmp_path, session_factory)  # same version, re-run
    assert n1 == n2
    assert e1 == e2


def test_missing_graph_json_raises_a_clear_error(tmp_path, session_factory):
    with pytest.raises(FileNotFoundError, match="run 'python data/scripts/build.py"):
        sync_scheme("nonexistent-scheme", tmp_path, session_factory)


# -- Integration: against the real, committed pmfme corpus --------------


@pytest.fixture
def real_pmfme_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    from api.graph import models  # noqa: F401
    Base.metadata.create_all(engine)
    session_factory = get_session_factory(engine)
    from parse_scheme import repo_root
    sync_scheme("pmfme", repo_root(), session_factory)
    return session_factory


def test_real_pmfme_eligibility_evidence_matches_the_eight_conditions(real_pmfme_session):
    with real_pmfme_session() as s:
        ev = T.eligibility_evidence(s, "pmfme", 1)
    assert len(ev.clause_ids) == 8  # one per condition -- see docs/phase2-design.md


def test_real_pmfme_required_documents_finds_loan_documents(real_pmfme_session):
    with real_pmfme_session() as s:
        ev = T.required_documents(s, "pmfme", 1)
    assert ev.clause_ids == ["clause:loan-documents-required"]


def test_real_pmfme_exclusions_finds_one_person_per_family(real_pmfme_session):
    with real_pmfme_session() as s:
        ev = T.exclusions(s, "pmfme", 1)
    assert ev.clause_ids == ["clause:individual-one-person-per-family"]
