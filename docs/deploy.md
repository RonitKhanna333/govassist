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
  defaults to 180 requests per client IP per 60 seconds on each warm function
  instance; the per-route limits below have their own variables.
  `GOVASSIST_DIAGNOSTIC_TOKEN` (16+ characters) enables the operator-only
  provider probe.
- `govassist-web`: configure `NEXT_PUBLIC_API_BASE` separately for each Vercel
  environment. Production should point to the production API. A PR Preview
  should point to the matching API Preview deployment. The value is not
  committed in `web/vercel.json`, and no ephemeral PR hostname belongs in
  source control.

Redeploy after adding them; Vercel does not re-run a build on an env change
by itself.

## CORS and demo abuse protection

The API allows localhost, the two known public GovAssist frontend origins, and
the narrowly scoped `govassist-web-git-<branch-or-hash>-ronit-khannas-projects`
Vercel preview pattern. Additional preview origins can be supplied as a
comma-separated list of exact origins in `CORS_ORIGINS`. There is no wildcard
`*.vercel.app` rule because credentials are enabled.

Every route that costs something has an in-memory fixed-window guard that
answers HTTP 429 with `Retry-After` **before** any provider call or password
hash runs:

| Route | Default per client IP per 60 s | Variable | Why |
|---|---|---|---|
| `POST /chat` | 180 | `GOVASSIST_RATE_LIMIT` | may call Groq; classroom NAT headroom |
| `POST /transcribe` | 20 | `GOVASSIST_TRANSCRIBE_RATE_LIMIT` | Whisper/Bhashini quota |
| `POST /speak` | 30 | `GOVASSIST_SPEAK_RATE_LIMIT` | TTS provider calls |
| `POST /auth/register`, `POST /auth/login` | 10 (shared) | `GOVASSIST_AUTH_RATE_LIMIT` | scrypt costs ~64 MB per hash |
| `GET /health?probe=llm` | 5, and only with `X-Diagnostic-Token` | `GOVASSIST_PROBE_RATE_LIMIT` | spends Groq quota |

Plain `GET /health` stays open, unlimited and free: it reports configuration
presence only. Without `GOVASSIST_DIAGNOSTIC_TOKEN` the probe returns 403 and
never contacts Groq.

Request bodies are capped before a route reads them: 64 KB for JSON routes and
4 MB for `/transcribe` audio (HTTP 413). Field limits sit on top: a chat
message is at most 1,000 characters, `/speak` text 2,000, and a profile at
most 64 attributes.

**What this does not do.** The counters live in one process's memory, so each
warm serverless instance counts separately, a cold start resets them, and
parallel instances multiply the effective limit. They are keyed on the
connecting address; forwarded headers are deliberately not trusted (any client
can set them), so users behind one NAT share a bucket and, on a host whose
proxy hides the client address, every caller may share one. This is
accidental-loop and casual-abuse protection, **not** a distributed quota.
Before a larger public launch, configure a deployment-wide limit in front of
the API -- for example Vercel Firewall rate-limiting rules (WAF) on
`/chat`, `/transcribe`, `/speak` and `/auth/*`, or the equivalent at a
reverse proxy/CDN -- and keep provider-side spending caps on the Groq and
Bhashini accounts. None of that is configured by this repository.

The frontend shows a specific busy message and never turns a rate-limit
response into a verdict.

## Dependency audits

CI fails on any high or critical advisory in the Python runtime set
(`pip-audit --strict -r requirements.txt`) and in production npm packages
(`npm audit --omit=dev --audit-level=high`).

Documented exception, dev tooling only: `npm audit` without `--omit=dev`
reports GHSA-vfj7-8cjw-p6xm (`braces`, stack exhaustion on deeply nested glob
patterns) through `eslint-config-next -> @next/eslint-plugin-next ->
fast-glob -> micromatch -> braces`. Every `braces` version is in the affected
range, so there is no patched release to move to; npm's only offer is a
forced downgrade to `eslint-config-next@14`, which does not support Next 16.
The package runs only when a developer or CI lints repository-authored files
with repository-authored glob patterns, and it is never bundled or deployed.
Re-check when a fixed `braces` (or a `fast-glob` without it) is published.

The October 2026 remediation moved `next` 16.3.5 -> 16.3.8 (GHSA-vcvr-r3jv-pc5j
and six further Next advisories), `sharp` 0.35.4 -> 0.35.5 (GHSA-wq5f-xc86-pv6w)
and `source-map-js` 1.2.1 -> 1.2.2 (GHSA-68fv-2mgg-jv7q). For the critical
`next/og` advisory: the vulnerable code shipped in the installed package, but
no route in this app imports `next/og` or renders `ImageResponse`, so no
exploitable path was demonstrated -- the upgrade removes the package-level
exposure rather than a known live one.

## Preview-to-API wiring

`web/lib/api.ts` reads `NEXT_PUBLIC_API_BASE`; if it is absent, local
development safely uses `http://127.0.0.1:8000`. Set the variable in the
`govassist-web` Vercel project's Preview environment to the API Preview URL
created for the same PR. Keep the production value in the Production
environment only. The presentation and evidence routes display the resolved
backend target and warn when a Vercel Preview is accidentally using the
production API or the local default.

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
