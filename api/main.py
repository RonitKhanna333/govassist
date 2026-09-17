"""FastAPI entrypoint.

    uvicorn api.main:app --reload

Requires GROQ_API_KEY for /chat to compose an answer (see api/agents/llm.py);
/health, /locales and the rule-engine verdict itself do not.

CORS: the frontend is a separate origin (its own Vercel project in
production, localhost:3000 in development), so without this every browser
call fails with an opaque "Failed to fetch" and the UI looks broken for a
reason that never reaches the console usefully. Origins are explicitly
allowlisted, with known frontend deployments plus exact `CORS_ORIGINS`
overrides. A wildcard is unsafe because this API will carry an Authorization
header once auth is on and `*` cannot be combined with credentials.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.auth.router import router as auth_router
from api.routers.chat import router as chat_router

DEFAULT_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# These are the public frontend origins known to this repository. Preview
# deployments are opt-in through CORS_ORIGINS below; a wildcard would let any
# Vercel project call the credential-bearing API.
KNOWN_PRODUCTION_ORIGINS = [
    "https://govassist-web-ronit-khannas-projects.vercel.app",
    "https://govassist-web-git-main-ronit-khannas-projects.vercel.app",
]

# Vercel branch/commit previews for this one frontend project. Keep the
# project slug and account suffix anchored; never allow every *.vercel.app
# origin while credentials are enabled.
VERCEL_PREVIEW_ORIGIN_REGEX = (
    r"^https://govassist-web-git-[a-z0-9-]+-ronit-khannas-projects\.vercel\.app$"
)


def allowed_origins() -> list[str]:
    configured = os.environ.get("CORS_ORIGINS", "")
    configured_origins = [o.strip().rstrip("/") for o in configured.split(",") if o.strip()]
    return list(dict.fromkeys(DEFAULT_ORIGINS + KNOWN_PRODUCTION_ORIGINS + configured_origins))


app = FastAPI(title="GovAssist API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_origin_regex=VERCEL_PREVIEW_ORIGIN_REGEX,
    # This regex is scoped to the GovAssist web project. Never use a broad
    # *.vercel.app regex here: credentials are enabled.
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(chat_router)
app.include_router(auth_router)
