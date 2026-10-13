"""Pooled Postgres (Supabase transaction pooler, pgbouncer) can't keep
server-side prepared statements between transactions."""

from unittest.mock import patch

from api.db import get_engine

SUPABASE = ("postgresql://postgres.ref:pw@aws-0-ap-south-1.pooler.supabase.com"
            ":6543/postgres")


def test_postgres_engines_never_auto_prepare_statements():
    with patch("api.db.create_engine") as create:
        get_engine(SUPABASE)
    url = create.call_args.args[0]
    assert url.startswith("postgresql+psycopg://")
    assert create.call_args.kwargs["connect_args"] == {"prepare_threshold": None}


def test_sqlite_is_unaffected():
    engine = get_engine("sqlite:///:memory:")
    assert engine.dialect.name == "sqlite"
