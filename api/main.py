"""FastAPI entrypoint.

    uvicorn api.main:app --reload

Requires GROQ_API_KEY in the environment for /chat to actually answer (see
api/agents/llm.py) -- /health does not.
"""

from __future__ import annotations

from fastapi import FastAPI

from api.routers.chat import router as chat_router

app = FastAPI(title="GovAssist API", version="0.1.0")
app.include_router(chat_router)
