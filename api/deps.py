"""FastAPI dependencies -- the seams tests replace to avoid real network calls.

`get_llm` and `get_language` are functions, not module-level singletons,
specifically so `app.dependency_overrides[...] = lambda: Fake(...)` works
cleanly in tests without touching GROQ_API_KEY / ULCA credentials or making
a real request.
"""

from __future__ import annotations

import os

from api.agents.llm import GroqLLM, LLMProvider
from api.language.service import LanguageService

# Names that must never be machine-translated. Curated, never guessed --
# see api/language/protect.py.
PROTECTED_TERMS = [
    "PM Formalisation of Micro Food Processing Enterprises",
    "PMFME", "PM-KISAN", "PM-JAY", "NSAP", "ODOP", "SLUP",
    "Ayushman Bharat", "Aadhaar", "GST", "ITR",
]


def get_llm() -> LLMProvider:
    return GroqLLM()


def get_language() -> LanguageService:
    """Bhashini when credentials exist, otherwise a provider-less service
    that degrades to English + browser speech rather than failing. The
    fallback is the normal path for anyone who hasn't registered for a
    free ULCA key yet."""
    if os.environ.get("ULCA_USER_ID") and os.environ.get("ULCA_API_KEY"):
        from api.language.providers.bhashini import BhashiniProvider
        return LanguageService(provider=BhashiniProvider(),
                               protected_terms=PROTECTED_TERMS)
    return LanguageService(provider=None, protected_terms=PROTECTED_TERMS)
