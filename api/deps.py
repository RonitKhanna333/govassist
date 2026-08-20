"""FastAPI dependencies -- the seam tests replace to avoid real network calls.

`get_llm` is a function, not a module-level singleton, specifically so
`app.dependency_overrides[get_llm] = lambda: FakeLLM(...)` works cleanly in
tests (see tests/api/test_chat_endpoint.py) without touching GROQ_API_KEY or
making a real request.
"""

from __future__ import annotations

from api.agents.llm import GroqLLM, LLMProvider


def get_llm() -> LLMProvider:
    return GroqLLM()
