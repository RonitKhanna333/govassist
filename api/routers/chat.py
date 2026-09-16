"""POST /chat -- the English-only text path from docs/phase2-design.md's
sequence diagram, minus the language layer (ASR/NMT/TTS, still design-only)
and minus the graph-based retrieval patterns other than the eligibility one
(required_documents / benefits / exclusions / reverse_by_attributes are
proven in api/graph/traverse.py but this endpoint doesn't route to them yet
-- see the module docstring on why eligibility_evidence itself isn't needed
for this specific flow).

The rule engine decides, never the LLM. Route this one for real: an empty
profile against pmfme, then answer every question it asks, and the verdict
should always be traceable to a real clause in api/rules/engine.py's own
citation resolution -- the composer and verifier only ever see what that
resolution already produced.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

import api._corpus_bridge  # noqa: F401 -- must run before importing parse_scheme
from api.agents import nlu, orchestrate
from api.agents.llm import LLMProvider
from api.agents.router import route
from api.deps import get_llm
from api.rules.engine import decide, known_attributes, load_rules
from parse_scheme import repo_root  # noqa: E402

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/chat")
def chat(body: dict, llm: LLMProvider = Depends(get_llm)) -> dict:
    scheme = body.get("scheme")
    profile = dict(body.get("profile") or {})
    message = body.get("message") or ""

    if not scheme:
        raise HTTPException(422, "scheme is required")

    routed = route(message or scheme)
    if not routed.supported:
        return {
            "domain": routed.domain.value, "supported": False,
            "verdict": None, "answer": routed.message,
            "next_question": None, "citations": [], "profile": profile,
        }

    try:
        rules = load_rules(scheme, repo_root())
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc

    if message:
        extracted = nlu.extract_attributes(llm, message, known_attributes(rules))
        profile = {**profile, **extracted}

    result = decide(scheme, profile)

    if result.verdict.value == "INSUFFICIENT_INFO":
        return {
            "domain": "scheme", "supported": True,
            "verdict": result.verdict.value, "answer": None,
            "next_question": result.next_question,
            "citations": [], "profile": profile,
        }

    answer = orchestrate.compose_verified_answer(llm, result.verdict.value, result.citations)
    return {
        "domain": "scheme", "supported": True,
        "verdict": result.verdict.value, "answer": answer,
        "next_question": None,
        "citations": [c.__dict__ for c in result.citations],
        "profile": profile,
    }
