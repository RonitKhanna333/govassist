"""One engine, two dialects, same schema.

`DATABASE_URL` unset -> a local SQLite file (govassist.db at the repo root),
zero setup, matches "GraphRAG handled locally" for dev and CI. Set it to a
Neon/Postgres URL for the real deployment. Nothing in graph/ or rules/ should
branch on which dialect is active -- if it needs to, that's a bug here, not
there.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def default_sqlite_url(root: Path | None = None) -> str:
    if root is None:
        root = Path(__file__).resolve().parent.parent
    return f"sqlite:///{(root / 'govassist.db').as_posix()}"


def get_engine(url: str | None = None):
    url = url or os.environ.get("DATABASE_URL") or default_sqlite_url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


def get_session_factory(engine=None) -> sessionmaker[Session]:
    engine = engine or get_engine()
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine=None) -> None:
    """Create tables that don't exist yet. Never drops or migrates -- a real
    migration tool (alembic) takes over the moment this needs a schema
    change against data someone cares about keeping."""
    from api.graph.models import GraphEdge, GraphNode  # noqa: F401 -- registers tables

    engine = engine or get_engine()
    Base.metadata.create_all(engine)
