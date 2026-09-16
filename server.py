"""Vercel serverless entry point for the API.

Vercel's Python runtime serves an ASGI app exported as `app`. This file
exists at the repo root rather than inside api/ on purpose: Vercel's
zero-config treats every `api/*.py` file as its own serverless function,
which would turn `api/deps.py`, `api/main.py` and friends into a dozen
broken endpoints. Routing everything through one explicit build (see
vercel.json) keeps the FastAPI router in charge of paths.

Worth knowing before relying on this in production: serverless is a real
trade for this workload. Every cold start re-imports the corpus JSON and
re-opens a database connection, so use a pooled Postgres URL (Neon's
`-pooler` host), not a direct one. And when local embeddings land, the
~90MB model will not fit comfortably in a Vercel function -- that's the
point to move the API to a container host instead.
"""

from api.main import app  # noqa: F401  -- Vercel looks for this name
