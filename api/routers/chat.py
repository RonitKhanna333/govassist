"""POST /chat -- the full path from docs/phase2-design.md's sequence diagram.

    message (any of 4 languages)
      -> translate to English            (api/language)
      -> route domain                    (api/agents/router.py)
      -> extract stated attributes       (api/agents/nlu.py, FAST tier)
      -> decide                          (api/rules/engine.py -- NOT the LLM)
      -> compose + verify                (api/agents/orchestrate.py, REASONING)
      -> translate back, entities intact (api/language)
      -> speech plan for the client      (api/language/service.py)

Two things this endpoint will not do, by design:

* The LLM never decides eligibility. `decide()` runs before the composer is
  ever called, and the composer only ever sees the citations that decision
  already resolved.
* A citation is never translated. The explanation is localized; the quoted
  clause stays in the language the government published it in, because a
  translated quote is no longer a quote.

Not wired yet: the four non-eligibility graph retrieval patterns
(required_documents / benefits / exclusions / reverse_by_attributes), which
are proven in api/graph/traverse.py but need intent classification to route
to. That's the next slice, not this one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

import api._corpus_bridge  # noqa: F401 -- must run before importing parse_scheme
from api.agents import nlu, orchestrate
from api.agents.llm import LLMProvider
from api.agents.router import route
from api.deps import get_language, get_llm
from api.language.registry import CANONICAL_LOCALE, LOCALES, get as get_locale, negotiate
from api.language.service import LanguageService
from api.rules.engine import decide, known_attributes, load_rules
from parse_scheme import repo_root  # noqa: E402

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/locales")
def locales() -> dict:
    """The locale registry, for the client's language switcher. Endonyms
    only -- see api/language/registry.py."""
    return {
        "default": CANONICAL_LOCALE,
        "locales": [
            {"code": loc.code, "bcp47": loc.bcp47, "endonym": loc.endonym,
             "name_en": loc.name_en, "script": loc.script, "font": loc.font,
             "direction": loc.direction}
            for loc in LOCALES.values()
        ],
    }


@router.get("/detect-locale")
def detect_locale(request: Request) -> dict:
    """What the browser asked for, resolved against what we support."""
    return {"locale": negotiate(request.headers.get("accept-language"))}


def _localize(language: LanguageService, text: str | None, target: str):
    """Translate one field out of English, reporting any degradation."""
    if not text:
        return text, None
    result = language.translate(text, target=target)
    return result.text, (result.note if result.locale != target else None)


@router.post("/chat")
def chat(body: dict,
         llm: LLMProvider = Depends(get_llm),
         language: LanguageService = Depends(get_language)) -> dict:
    scheme = body.get("scheme")
    profile = dict(body.get("profile") or {})
    message = body.get("message") or ""

    # Three independent axes, per the original design: the UI's language is
    # the client's business; these two are the server's.
    content_locale = get_locale(body.get("locale")).code
    message_locale = get_locale(body.get("message_locale") or content_locale).code

    if not scheme:
        raise HTTPException(422, "scheme is required")

    # In: anything -> English. Everything downstream is monolingual.
    english_message = message
    if message and message_locale != CANONICAL_LOCALE:
        inbound = language.translate(message, target=CANONICAL_LOCALE,
                                     source=message_locale)
        english_message = inbound.text

    routed = route(english_message or scheme)
    if not routed.supported:
        text, note = _localize(language, routed.message, content_locale)
        return {
            "domain": routed.domain.value, "supported": False,
            "verdict": None, "answer": text, "next_question": None,
            "citations": [], "profile": profile,
            "locale": content_locale, "language_note": note,
            "speech": None,
        }

    try:
        rules = load_rules(scheme, repo_root())
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc

    if english_message:
        extracted = nlu.extract_attributes(llm, english_message, known_attributes(rules))
        profile = {**profile, **extracted}

    result = decide(scheme, profile)

    if result.verdict.value == "INSUFFICIENT_INFO":
        question, note = _localize(language, result.next_question, content_locale)
        plan = language.plan_speech(question or "", content_locale)
        return {
            "domain": "scheme", "supported": True,
            "verdict": result.verdict.value, "answer": None,
            "next_question": question,
            "missing_attributes": result.missing_attributes,
            "citations": [], "profile": profile,
            "locale": content_locale, "language_note": note,
            "speech": {"chunks": plan.chunks, "rung": plan.rung.value,
                       "bcp47": plan.bcp47, "note": plan.note},
        }

    english_answer = orchestrate.compose_verified_answer(
        llm, result.verdict.value, result.citations,
    )
    answer, note = _localize(language, english_answer, content_locale)
    plan = language.plan_speech(answer or "", content_locale)

    return {
        "domain": "scheme", "supported": True,
        "verdict": result.verdict.value, "answer": answer,
        "next_question": None,
        "missing_attributes": [],
        # Citations stay verbatim in their source language, always.
        "citations": [c.__dict__ for c in result.citations],
        "profile": profile,
        "locale": content_locale, "language_note": note,
        "speech": {"chunks": plan.chunks, "rung": plan.rung.value,
                   "bcp47": plan.bcp47, "note": plan.note},
    }
