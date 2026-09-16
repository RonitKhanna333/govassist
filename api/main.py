"""FastAPI entrypoint.

    uvicorn api.main:app --reload

Requires GROQ_API_KEY for /chat to compose an answer (see api/agents/llm.py);
/health, /locales and the rule-engine verdict itself do not.

CORS: the frontend is a separate origin (its own Vercel project in
production, localhost:3000 in development), so without this every browser
call fails with an opaque "Failed to fetch" and the UI looks broken for a
reason that never reaches the console usefully. Origins are read from
CORS_ORIGINS rather than wildcarded, because this API will carry an
Authorization header once auth is on and `*` cannot be combined with
credentials.
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


def allowed_origins() -> list[str]:
    configured = os.environ.get("CORS_ORIGINS", "")
    origins = [o.strip() for o in configured.split(",") if o.strip()]
    return origins or DEFAULT_ORIGINS


app = FastAPI(title="GovAssist API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    # Vercel preview deployments get a generated subdomain per branch, so the
    # exact origin isn't knowable ahead of time -- this matches those without
    # opening the API to every origin on the internet.
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(chat_router)
app.include_router(auth_router)
