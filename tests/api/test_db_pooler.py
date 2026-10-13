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


# -- a failed connection says why, without leaking the URL ------------------

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from api.db import describe_connection_error
from api.main import app


def _op(message):
    return OperationalError("SELECT 1", {}, Exception(message))


@pytest.mark.parametrize("message,expected", [
    ('connection failed: FATAL:  password authentication failed for user "postgres"', "password"),
    ("FATAL:  Tenant or user not found", "postgres.<project-ref>"),
    ("could not translate host name \"db.x.supabase.co\" to address", "host name"),
    ("connection is bad: Network is unreachable", "pooler URL"),
])
def test_connection_errors_name_the_cause(message, expected):
    assert expected in describe_connection_error(_op(message))


def test_the_raw_driver_text_is_never_repeated():
    secret = "postgresql://postgres.ref:hunter2@host:6543/postgres"
    text = describe_connection_error(_op(f"weird failure for {secret}"))
    assert "hunter2" not in text and "host:6543" not in text


def test_a_broken_database_is_a_503_with_a_reason_not_a_bare_500(monkeypatch):
    def broken():
        raise _op("FATAL:  password authentication failed")
    monkeypatch.setattr("api.auth.router.init_db", broken)
    response = TestClient(app).get("/auth/me", headers={"Authorization": "Bearer x"})
    assert response.status_code == 503
    assert "password was rejected" in response.json()["detail"]


def test_an_unparseable_url_says_so(monkeypatch):
    """A password with '@' or '#' breaks the URL before any connection is
    attempted -- the error the live deployment hit."""
    from sqlalchemy.exc import ArgumentError

    def broken():
        raise ArgumentError("Could not parse SQLAlchemy URL from string")
    monkeypatch.setattr("api.auth.router.init_db", broken)
    response = TestClient(app).get("/auth/me", headers={"Authorization": "Bearer x"})
    assert response.status_code == 503
    assert "couldn't be read as a connection string" in response.json()["detail"]


def test_a_bad_port_in_the_url_says_so(monkeypatch):
    def broken():
        raise ValueError("invalid literal for int() with base 10: 'pa#ss'")
    monkeypatch.setattr("api.auth.router.init_db", broken)
    response = TestClient(app).get("/auth/me", headers={"Authorization": "Bearer x"})
    assert response.status_code == 503
    assert "pa#ss" not in response.text
