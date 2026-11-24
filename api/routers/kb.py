"""The knowledge base: every committed clause of every scheme, and one
grounded chat over all of them (the same path the phone call uses)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.agents.llm import LLMProvider
from api.deps import get_language, get_llm
from api.language.registry import get as get_locale
from api.language.service import LanguageService
from api.onboarding import interview
from api.rate_limit import chat_rate_limiter, enforce
from api.routers.chat import review_assessment
from api.routers.voice import answer_from_clauses
from api.rules.engine import load_clauses, load_rules
from api.voice import script
from parse_scheme import repo_root

router = APIRouter(prefix="/kb", tags=["kb"])


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    locale: str = "en"


@router.get("")
def knowledge(locale: str = "en") -> dict:
    root = repo_root()
    schemes = []
    for slug in interview.schemes():
        rules = load_rules(slug, root)
        clauses = [{k: row.get(k) for k in ("id", "type", "plain", "quote", "page", "source_url")}
                   for row in load_clauses(slug, root).values()]
        schemes.append({"id": slug, "name": script.scheme_name(slug, locale),
                        "authority": rules.get("authority"),
                        "reviewed": review_assessment(slug).reviewed, "clauses": clauses})
    return {"schemes": schemes}


@router.post("/ask", dependencies=[Depends(enforce(chat_rate_limiter))])
def ask(body: AskBody, llm: LLMProvider = Depends(get_llm),
        language: LanguageService = Depends(get_language)) -> dict:
    question = body.question.strip()
    if not question:
        raise HTTPException(422, "question is required")
    return answer_from_clauses(question, get_locale(body.locale).code, "all", llm, language)
