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


def normalize_url(url: str) -> str:
    """Make a hosted Postgres URL work with the driver we actually ship.

    Neon, Supabase and Heroku all hand out `postgres://` or `postgresql://`
    URLs. SQLAlchemy maps both to psycopg2, which isn't in requirements.txt
    (psycopg 3 is), so without this rewrite a correct connection string
    fails at import with a confusing "No module named psycopg2".
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def get_engine(url: str | None = None):
    url = normalize_url(url or os.environ.get("DATABASE_URL") or default_sqlite_url())

    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}

        # In-memory SQLite gives every *connection* its own empty database.
        # With a normal pool, a request handled on FastAPI's threadpool gets a
        # different connection from the one the tables were created on, and
        # the query fails with "no such table" against a database that was
        # definitely set up. StaticPool keeps exactly one shared connection,
        # which is what makes :memory: usable for tests at all.
        if ":memory:" in url or "mode=memory" in url:
            from sqlalchemy.pool import StaticPool
            return create_engine(url, connect_args=connect_args, poolclass=StaticPool)

        return create_engine(url, connect_args=connect_args)

    # Serverless: every cold start opens a new connection and the process may
    # be frozen between requests, so a long-lived pool is a liability. Recycle
    # aggressively and always check liveness before handing a connection out.
    return create_engine(
        url, pool_pre_ping=True, pool_recycle=280, pool_size=1, max_overflow=2,
    )


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
