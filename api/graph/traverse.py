"""The five retrieval patterns from docs/phase2-design.md, against real storage.

Each pattern is a short, fixed chain of typed edges -- 2-3 hops, known in
advance -- not an open-ended walk. That's deliberate: a fully generic
recursive traverser would technically cover these same patterns, but it
would also make each one harder to read for a graph this size, and it would
let a future caller construct a traversal outside the five patterns this
system is willing to answer. Composing named steps keeps "hop-capped, typed
whitelist" true by construction instead of by convention. If the graph ever
grows enough that hand-enumerated patterns stop scaling, that's the point to
introduce a real `WITH RECURSIVE` walker -- not before.

`_step` does one hop of one predicate, in one direction, scoped to
(scheme, version). Every public function below is that, composed a few times.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.graph.models import GraphEdge, GraphNode


@dataclass
class Evidence:
    """What a retrieval pattern found: enough to cite, never more than asked for."""

    query_class: str
    nodes: dict[str, dict] = field(default_factory=dict)   # id -> {scheme, type, name, props}
    edges: list[dict] = field(default_factory=list)         # [{scheme, from, predicate, to}]

    @property
    def clause_ids(self) -> list[str]:
        return sorted(
            n["id"] for n in self.nodes.values()
            if n["type"] == "Clause"
        )

    def clauses(self) -> list[dict]:
        return [self.nodes[cid] for cid in self.clause_ids]


def _step(session: Session, scheme: str, version: int, from_ids: set[str],
          predicate: str, direction: str = "fwd") -> list[GraphEdge]:
    """One hop of one predicate, one direction, scoped to (scheme, version).

    direction="fwd"  : follow edges whose `from` is in from_ids
    direction="rev"  : follow edges whose `to`   is in from_ids (walk backward)
    """
    if not from_ids:
        return []
    column = GraphEdge.from_id if direction == "fwd" else GraphEdge.to_id
    stmt = (
        select(GraphEdge)
        .where(GraphEdge.scheme == scheme, GraphEdge.version == version)
        .where(GraphEdge.predicate == predicate)
        .where(column.in_(from_ids))
    )
    return list(session.scalars(stmt))


def _fetch_nodes(session: Session, scheme: str, version: int,
                  ids: set[str]) -> dict[str, dict]:
    if not ids:
        return {}
    stmt = (
        select(GraphNode)
        .where(GraphNode.scheme == scheme, GraphNode.version == version)
        .where(GraphNode.id.in_(ids))
    )
    return {
        n.id: {"scheme": n.scheme, "id": n.id, "type": n.type,
               "name": n.name, "props": n.props}
        for n in session.scalars(stmt)
    }


def _collect(evidence: Evidence, session: Session, scheme: str, version: int,
             edges: list[GraphEdge]) -> set[str]:
    """Record edges into `evidence`, fetch the nodes they touch, return the
    far-side ids so the caller can take the next hop."""
    far_ids: set[str] = set()
    for e in edges:
        evidence.edges.append({"scheme": scheme, "from": e.from_id,
                               "predicate": e.predicate, "to": e.to_id})
        far_ids.add(e.from_id)
        far_ids.add(e.to_id)
    evidence.nodes.update(_fetch_nodes(session, scheme, version, far_ids))
    return far_ids


def eligibility_evidence(session: Session, scheme: str, version: int) -> Evidence:
    """"Am I eligible for X" -- every Condition this scheme REQUIRES, the
    Clause each is GROUNDED_IN, and the SourceDocument that Clause is FROM.

    This is what the composer and the verifier are allowed to cite from when
    explaining a rule-engine verdict. It intentionally does not include every
    clause the scheme has (benefits, documents, procedure notes) -- those are
    separate patterns below, asked for only when the question calls for them.
    """
    scheme_id = f"scheme:{scheme}"
    evidence = Evidence(query_class="eligibility_evidence")
    evidence.nodes.update(_fetch_nodes(session, scheme, version, {scheme_id}))

    conditions = _collect(evidence, session, scheme, version,
                          _step(session, scheme, version, {scheme_id}, "REQUIRES"))
    clauses = _collect(evidence, session, scheme, version,
                       _step(session, scheme, version, conditions, "GROUNDED_IN"))
    _collect(evidence, session, scheme, version,
            _step(session, scheme, version, clauses, "FROM"))
    # what each condition actually tests -- needed to phrase the next question
    _collect(evidence, session, scheme, version,
            _step(session, scheme, version, conditions, "TESTS"))
    return evidence


def required_documents(session: Session, scheme: str, version: int) -> Evidence:
    """"What do I need to bring" -- Scheme --REQUIRES_DOCUMENT--> Clause."""
    scheme_id = f"scheme:{scheme}"
    evidence = Evidence(query_class="required_documents")
    _collect(evidence, session, scheme, version,
            _step(session, scheme, version, {scheme_id}, "REQUIRES_DOCUMENT"))
    return evidence


def benefits(session: Session, scheme: str, version: int) -> Evidence:
    """"What do I get" -- Scheme --PROVIDES--> Clause."""
    scheme_id = f"scheme:{scheme}"
    evidence = Evidence(query_class="benefits")
    _collect(evidence, session, scheme, version,
            _step(session, scheme, version, {scheme_id}, "PROVIDES"))
    return evidence


def exclusions(session: Session, scheme: str, version: int) -> Evidence:
    """"Why was I excluded" -- Scheme --EXCLUDES--> Clause, paired with
    whichever Condition is GROUNDED_IN that clause (walked backward), since
    that's the condition the rule engine actually evaluated."""
    scheme_id = f"scheme:{scheme}"
    evidence = Evidence(query_class="exclusions")
    clauses = _collect(evidence, session, scheme, version,
                       _step(session, scheme, version, {scheme_id}, "EXCLUDES"))
    _collect(evidence, session, scheme, version,
            _step(session, scheme, version, clauses, "GROUNDED_IN", direction="rev"))
    return evidence


def reverse_by_attributes(session: Session, attribute_names: list[str],
                          scheme_versions: dict[str, int]) -> Evidence:
    """"I have these documents/facts, what applies to me" -- across every
    scheme, on purpose. This is the one pattern that spans scheme scope,
    because it merges on Attribute *name*, not on any node id -- see
    graph/models.py for why raw id merging would be unsafe here.

    `scheme_versions` is which version of each scheme to search -- normally
    "the latest committed version per scheme", decided by the caller so this
    function stays a pure query, not a policy about which version is current.
    """
    evidence = Evidence(query_class="reverse_by_attributes")
    for scheme, version in scheme_versions.items():
        attr_ids = {
            n.id for n in session.scalars(
                select(GraphNode)
                .where(GraphNode.scheme == scheme, GraphNode.version == version,
                       GraphNode.type == "Attribute", GraphNode.name.in_(attribute_names))
            )
        }
        if not attr_ids:
            continue
        evidence.nodes.update(_fetch_nodes(session, scheme, version, attr_ids))
        clauses = _collect(evidence, session, scheme, version,
                           _step(session, scheme, version, attr_ids, "BEARS_ON", direction="rev"))
        _collect(evidence, session, scheme, version,
                _step(session, scheme, version, clauses, "HAS_CLAUSE", direction="rev"))
    return evidence


def latest_versions(session: Session, schemes: list[str] | None = None) -> dict[str, int]:
    """The highest synced version per scheme -- what reverse_by_attributes
    should search unless a caller has a specific reason to look at history."""
    stmt = select(GraphNode.scheme, GraphNode.version).where(GraphNode.type == "Scheme")
    if schemes:
        stmt = stmt.where(GraphNode.scheme.in_(schemes))
    result: dict[str, int] = {}
    for scheme, version in session.execute(stmt):
        result[scheme] = max(version, result.get(scheme, version))
    return result
