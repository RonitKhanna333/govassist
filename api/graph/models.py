"""Storage for build/graph.v{n}.json -- scoped, not merged, except on purpose.

`build_graph()` in data/scripts/build.py gives every node an id like
`clause:individual-existing-unit`. That id is unique *within one scheme's
file* because a human reviewed it there -- nothing makes it unique *across
schemes*. Two unrelated schemes independently choosing the same clause slug
is plausible, especially now that the clause spec pushes toward short,
descriptive, kebab-case ids. If storage keyed on raw id alone, that collision
would silently merge two different clauses from two different schemes into
one row.

So every node and edge here is scoped by (scheme, version, id) -- nothing
merges across schemes by accident. The one merge this system wants on
purpose -- Attribute nodes sharing meaning across schemes, so "I have these
documents, what applies to me" can traverse every scheme at once -- is done
explicitly in graph/traverse.py by matching on `name`, not by relying on
storage-level id collision. Explicit merge, not an accidental one.
"""

from __future__ import annotations

from sqlalchemy import ForeignKeyConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from api.db import Base


class GraphNode(Base):
    __tablename__ = "graph_nodes"

    scheme: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    id: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. "clause:xyz"
    type: Mapped[str] = mapped_column(String, index=True)      # Scheme|Clause|Condition|...
    name: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    props: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_graph_nodes_type_name", "type", "name"),
    )


class GraphEdge(Base):
    __tablename__ = "graph_edges"

    row_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scheme: Mapped[str] = mapped_column(String, index=True)
    version: Mapped[int] = mapped_column(Integer)
    from_id: Mapped[str] = mapped_column(String, index=True)
    predicate: Mapped[str] = mapped_column(String, index=True)
    to_id: Mapped[str] = mapped_column(String, index=True)

    __table_args__ = (
        UniqueConstraint("scheme", "version", "from_id", "predicate", "to_id",
                         name="uq_graph_edge"),
        ForeignKeyConstraint(
            ["scheme", "version", "from_id"],
            ["graph_nodes.scheme", "graph_nodes.version", "graph_nodes.id"],
        ),
    )
