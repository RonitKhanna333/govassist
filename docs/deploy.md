# Deployment

Two Vercel projects can be deployed from one repository:

| Project | Root | What it is | URL |
|---|---|---|---|
| `govassist-api` | repo root | FastAPI on Vercel's Python runtime | https://govassist-api-ronit-khannas-projects.vercel.app |
| `govassist-web` | `web/` | Next.js 16 frontend | https://govassist-web-git-main-ronit-khannas-projects.vercel.app |

The repository does not deploy or push as part of local development. Treat
these URLs as public examples and verify the current deployment separately.

## What runs without any credentials

This matters more than it sounds: **the eligibility verdict and its
citations need no API key at all.** The rule engine is deterministic and
the corpus is committed JSON, so a deployment with zero secrets still
answers correctly — it just can't phrase the explanation or speak it.

```bash
curl -X POST $API/chat -H 'Content-Type: application/json' \
  -d '{"scheme":"pmfme","profile":{}}'
# -> INSUFFICIENT_INFO + a real question, no key needed
```

Each key adds one capability, and its absence is visible rather than silent:

| Missing | What still works | What degrades |
|---|---|---|
| `GROQ_API_KEY` | verdict, citations, questions | `answer` becomes the honest "no grounded facts to explain with" fallback |
| `ULCA_*` | all four UI languages, verdicts | answers stay English with a stated reason; speech drops to browser voices |
| `DATABASE_URL` | public chat and eligibility flow | optional account/graph persistence is unavailable; serverless auth/database routes must not be claimed as enabled |

## Setting secrets

Neither key is in the repo and neither should be. Add them per project in
**Vercel → Project → Settings → Environment Variables**:

- `govassist-api`: `GROQ_API_KEY`, optionally `ULCA_USER_ID` /
  `ULCA_API_KEY` / `BHASHINI_INFERENCE_KEY`, optionally `DATABASE_URL`, and
  optionally `CORS_ORIGINS` for exact preview origins. `GOVASSIST_RATE_LIMIT`
  defaults to 60 requests per client IP per 60 seconds on each warm function
  instance.
- `govassist-web`: nothing required — `NEXT_PUBLIC_API_BASE` is committed
  in `web/vercel.json` so the frontend is self-configuring.

Redeploy after adding them; Vercel does not re-run a build on an env change
by itself.

## CORS and demo abuse protection

The API allows localhost plus the two known public GovAssist frontend origins.
Additional preview origins must be supplied as a comma-separated list of exact
origins in `CORS_ORIGINS`. There is no wildcard `*.vercel.app` rule because
credentials are enabled.

`POST /chat` has a modest in-memory fixed-window safeguard: 60 requests per
client IP per 60 seconds per warm function instance, returning HTTP 429 with a
`Retry-After` header. The frontend shows a specific busy message and never
turns a rate-limit response into a verdict. This is not a distributed quota;
configure a Vercel/deployment-level limit before a larger public launch.

## Postgres

Use a **pooled** connection string. Neon's pooled host ends in `-pooler`:

```
postgresql://user:pass@ep-xxx-pooler.region.aws.neon.tech/govassist?sslmode=require
```

A direct (non-pooled) URL will exhaust Postgres connection slots under
serverless cold starts, which presents as intermittent 500s that are
painful to diagnose. `api/db.py` rewrites `postgres://` and `postgresql://`
to the psycopg 3 driver automatically and uses a deliberately tiny pool
with pre-ping, because a long-lived pool is a liability in a function that
may be frozen between requests.

Then load the graph into it:

```bash
DATABASE_URL=... python -m api.graph.sync --all
```

## Known limits of this topology

Worth stating plainly rather than discovering later:

- **Cold starts.** Every idle-then-hit request re-imports the corpus. Fine
  for a demo, noticeable for a user.
- **Local embeddings will not fit.** When `api/embeddings/local.py` lands,
  the ~90MB sentence-transformers model exceeds what belongs in a Vercel
  function. That's the point to move the API to a container host (Hugging
  Face Spaces' free CPU tier gives 16GB RAM and was the original plan).
- **Hobby plan forbids commercial use.** Fine for a course project;
  relevant if this ever becomes a real service.

## Local development

```bash
pip install -e ".[dev,serve]"
uvicorn api.main:app --reload            # :8000

cd web && npm install && npm run dev     # :3000
```

Open **http://localhost:3000**, not `127.0.0.1:3000` — Next 16 blocks
cross-origin dev resources, and on the wrong host HMR fails, hydration
never completes, and every button silently does nothing.
(`allowedDevOrigins` in `web/next.config.mjs` covers both, but the
canonical host is the safer habit.)
