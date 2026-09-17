"""POST /chat and POST /transcribe -- one conversational turn, in any of four
languages, with the rule engine deciding and the model only explaining.

    message (typed or spoken, any of 4 languages)
      -> translate to English                (api/language)
      -> an answer to the question on screen? (api/rules/spoken.py, then one
                                               FAST call if that can't tell)
      -> or a question of their own?          (api/agents/conversation.py --
                                               answered from clauses, verified)
      -> decide                               (api/rules/engine.py -- NOT the LLM)
      -> explain a verdict                    (api/agents/orchestrate.py)
      -> say it back in their language        (static bank + api/language)

Three things this endpoint will not do, by design:

* The LLM never decides eligibility. `decide()` works only from recorded
  answers, and a model is only ever asked to classify a message or to
  explain from clauses it is handed.
* A citation is never translated. The explanation is localized; the quoted
  clause stays in the language the government published it in.
* A question never gets silently ignored. Before the conversational layer,
  "what documents do I need?" extracted nothing and the same prompt came
  back, and after a verdict every message re-sent the same explanation.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

import api._corpus_bridge  # noqa: F401 -- must run before importing parse_scheme
from api.agents import composer, conversation, nlu, orchestrate
from api.agents.llm import LLMProvider
from api.agents.phrases import phrase
from api.agents.router import route
from api.deps import get_language, get_llm
from api.language.providers.base import LanguageError
from api.language.registry import CANONICAL_LOCALE, LOCALES, get as get_locale, negotiate
from api.language.service import LanguageService
from api.rate_limit import chat_rate_limiter
from api.rules.engine import Citation, decide, known_attributes, load_clauses, load_rules
from api.rules.forms import OTHER, answer_yes_no, summarize_profile, unresolved_fields
from api.rules.spoken import interpret
from parse_scheme import repo_root  # noqa: E402

router = APIRouter()

# Speech input is enabled for these only, for now. Whisper handles Punjabi and
# Tamil too, but Hindi is what has been decided to ship and test first, and a
# mic that half-works in a language nobody has checked is worse than an honest
# "voice input isn't available in this language yet".
VOICE_INPUT_LOCALES = {"en", "hi"}
MAX_AUDIO_BYTES = 4 * 1024 * 1024  # under Vercel's 4.5 MB request ceiling

_AUDIO_EXT = {
    "audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a",
    "audio/mpeg": "mp3", "audio/wav": "wav", "audio/x-wav": "wav",
}


@router.get("/health")
def health(probe: str | None = None) -> dict:
    """Liveness, plus which capabilities are actually configured.

    This exists because of a real failure that took far too long to
    diagnose: the composer catches every LLMError and returns the same
    honest fallback sentence, so "no API key", "wrong API key", "model
    retired" and "rate limited" all look identical from outside.

    Reporting configuration is safe and free. `?probe=llm` goes further and
    actually calls Groq once, returning the provider's real error text --
    never the key itself, only whether it works and what it said.
    """
    report = {
        "status": "ok",
        "configured": {
            # Presence only. Never the value, never a prefix of it.
            "groq": bool(os.environ.get("GROQ_API_KEY")),
            "bhashini": bool(os.environ.get("ULCA_USER_ID")
                             and os.environ.get("ULCA_API_KEY")),
            "database": bool(os.environ.get("DATABASE_URL")),
            "auth": bool(os.environ.get("JWT_SECRET")),
        },
        # What still works regardless -- the whole point of the design.
        "works_without_keys": ["verdict", "citations", "questions"],
        "voice_input": sorted(VOICE_INPUT_LOCALES),
    }

    if probe == "llm":
        from api.agents.llm import GroqLLM, LLMError, Tier
        try:
            reply = GroqLLM().complete("Reply with the single word: ok.", "ping", Tier.FAST)
            report["llm_probe"] = {"ok": True, "reply": reply.strip()[:80]}
        except LLMError as exc:
            report["llm_probe"] = {"ok": False, "error": str(exc)[:500]}

    return report


@router.get("/locales")
def locales() -> dict:
    """The locale registry, for the client's language switcher. Endonyms
    only -- see api/language/registry.py."""
    return {
        "default": CANONICAL_LOCALE,
        "locales": [
            {"code": loc.code, "bcp47": loc.bcp47, "endonym": loc.endonym,
             "name_en": loc.name_en, "script": loc.script, "font": loc.font,
             "direction": loc.direction,
             "voice_input": loc.code in VOICE_INPUT_LOCALES}
            for loc in LOCALES.values()
        ],
    }


@router.get("/detect-locale")
def detect_locale(request: Request) -> dict:
    """What the browser asked for, resolved against what we support."""
    return {"locale": negotiate(request.headers.get("accept-language"))}


@router.post("/transcribe")
async def transcribe(request: Request, locale: str = "hi",
                     language: LanguageService = Depends(get_language)) -> dict:
    """Speech to text, server side.

    The browser's own recognizer was the previous approach and it cannot be
    relied on: Brave exposes the API but blocks the Google servers behind
    it, so it fails silently, and Firefox doesn't have it at all. Recording
    is plain microphone capture, which every current browser supports, and
    Whisper does the rest.
    """
    code = get_locale(locale).code
    if code not in VOICE_INPUT_LOCALES:
        raise HTTPException(422, f"Voice input isn't available in {code} yet.")

    audio = await request.body()
    if not audio:
        raise HTTPException(422, "No audio received.")
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "That recording is too long. Please keep it short.")

    mime = (request.headers.get("content-type") or "audio/webm").split(";")[0].strip()
    ext = _AUDIO_EXT.get(mime, "webm")
    try:
        text = await run_in_threadpool(
            language.transcribe, audio, code, mime, f"speech.{ext}",
        )
    except LanguageError as exc:
        raise HTTPException(503, f"Couldn't transcribe: {exc}") from exc
    return {"text": text, "locale": code}


def _localize(language: LanguageService, text: str | None, target: str):
    """Translate one field out of English, reporting any degradation."""
    if not text:
        return text, None
    result = language.translate(text, target=target)
    return result.text, (result.note if result.locale != target else None)


def _record(profile: dict, field: dict, value: object) -> dict:
    """Store an interpreted value against the field that was on screen."""
    if field.get("kind") == "choice" and isinstance(value, bool):
        value = field.get("satisfied_by") if value else OTHER
    return {**profile, field["attribute"]: value}


def _speech(language: LanguageService, messages: list[str], locale: str) -> dict:
    plan = language.plan_speech(" ".join(m for m in messages if m), locale)
    return {"chunks": plan.chunks, "rung": plan.rung.value,
            "bcp47": plan.bcp47, "note": plan.note}


def _all_clauses(scheme: str) -> list[Citation]:
    return [
        Citation(clause_id=row["id"], quote=row["quote"], plain=row["plain"],
                 source_url=row["source_url"], page=row["page"])
        for row in load_clauses(scheme, repo_root()).values()
    ]


@router.post("/chat")
def chat(body: dict,
         request: Request,
         llm: LLMProvider = Depends(get_llm),
         language: LanguageService = Depends(get_language)) -> dict:
    """One conversational turn. `bot_messages` is what the helper says this
    turn, in order -- a reply to their question and the next question arrive
    as two natural messages instead of one repeated prompt."""
    client_key = request.client.host if request.client else "unknown"
    limit = chat_rate_limiter.check(client_key)
    if not limit.allowed:
        raise HTTPException(
            429,
            "This demo is receiving a lot of requests. Please wait and try again.",
            headers={"Retry-After": str(limit.retry_after or 1)},
        )

    scheme = body.get("scheme")
    profile = dict(body.get("profile") or {})
    message = (body.get("message") or "").strip()
    starting = bool(body.get("start"))

    content_locale = get_locale(body.get("locale")).code
    message_locale = get_locale(body.get("message_locale") or content_locale).code

    if not scheme:
        raise HTTPException(422, "scheme is required")

    try:
        rules = load_rules(scheme, repo_root())
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    allowed = set(known_attributes(rules))

    # Buttons and number inputs: exact values, no interpretation needed.
    answers = body.get("answers")
    if isinstance(answers, dict) and answers:
        profile = {**profile, **{k: v for k, v in answers.items() if k in allowed}}

    yes_no = body.get("answer")
    if yes_no in ("yes", "no"):
        current = decide(scheme, profile)
        if current.pending:
            profile = {**profile,
                       **answer_yes_no(current.pending.expr, profile, yes_no == "yes")}

    bot_messages: list[str] = []
    language_notes: list[str] = []
    reply_citations: list[Citation] = []
    acknowledged = False
    asked_question = False

    if starting:
        bot_messages.append(phrase("greeting", content_locale))

    if message:
        english = message
        if message_locale != CANONICAL_LOCALE:
            english = language.translate(message, target=CANONICAL_LOCALE,
                                         source=message_locale).text

        routed = route(english)
        if not routed.supported:
            text, note = _localize(language, routed.message, content_locale)
            return {
                "domain": routed.domain.value, "supported": False,
                "verdict": None, "answer": text, "next_question": None,
                "bot_messages": [text], "reply": text, "acknowledged": False,
                "citations": [], "reply_citations": [], "profile": profile,
                "profile_summary": summarize_profile(profile, content_locale),
                "pending": None, "locale": content_locale,
                "language_note": note, "speech": None,
            }

        before = decide(scheme, profile)
        pending_fields = (
            unresolved_fields(before.pending.expr, profile)
            if before.pending else []
        )
        field = pending_fields[0].to_dict() if pending_fields else None

        # 1. Deterministic: "haan", "ਨਹੀਂ", "25", "२५" need no model at all.
        value = interpret(message, field) if field else None
        if value is None and field and english != message:
            value = interpret(english, field)

        if value is not None:
            profile = _record(profile, field, value)
            acknowledged = True
        else:
            # 2. One classification call: answer, question, or chat?
            intent = conversation.classify(
                llm, field.get("ask") if field else None,
                field.get("kind") if field else None, english,
            )
            if intent.value is not None and field:
                profile = _record(profile, field, intent.value)
                acknowledged = True

            if intent.kind == "question":
                asked_question = True
                reply = conversation.answer_question(llm, english, _all_clauses(scheme))
                reply_citations = reply.citations
                if reply.text:
                    text, note = _localize(language, reply.text, content_locale)
                    if note:
                        language_notes.append(note)
                elif reply.busy:
                    text = phrase("busy", content_locale)
                else:
                    text = phrase("unknown", content_locale)
                bot_messages.append(text)
            elif intent.kind == "chat":
                bot_messages.append(phrase("chat", content_locale))
            elif not acknowledged:
                # It looked like an answer but no value could be placed. Try
                # the free-text extraction for anything else they stated, and
                # say so if it still went nowhere -- never re-ask silently.
                extracted = nlu.extract_attributes(llm, english, sorted(allowed))
                if extracted:
                    profile = {**profile, **extracted}
                    acknowledged = True
                else:
                    bot_messages.append(phrase("not_understood", content_locale))

    result = decide(scheme, profile)
    summary = summarize_profile(profile, content_locale)

    if result.verdict.value == "INSUFFICIENT_INFO":
        fields = (
            unresolved_fields(result.pending.expr, profile, content_locale)
            if result.pending else []
        )
        question = fields[0].ask if fields and fields[0].ask else result.next_question
        spoken_question = question
        if acknowledged and not asked_question:
            spoken_question = f"{phrase('ack', content_locale)} {question}"
        bot_messages.append(spoken_question)

        pending = None
        if result.pending:
            pending = result.pending.to_dict()
            pending["fields"] = [f.to_dict() for f in fields]

        return {
            "domain": "scheme", "supported": True,
            "verdict": result.verdict.value, "answer": None,
            "next_question": question,
            "bot_messages": bot_messages,
            "reply": bot_messages[0] if asked_question else None,
            "acknowledged": acknowledged,
            "missing_attributes": result.missing_attributes,
            "pending": pending,
            "citations": [],
            "reply_citations": [c.__dict__ for c in reply_citations],
            "profile": profile, "profile_summary": summary,
            "locale": content_locale,
            "language_note": language_notes[0] if language_notes else None,
            "speech": _speech(language, bot_messages, content_locale),
        }

    # A verdict. If this turn was a question about an already-decided case,
    # answer the question and stop -- re-sending the same explanation on every
    # follow-up is what made this read as fixed text.
    answer = None
    if not asked_question:
        # A denial is explained by the rules it FAILED; see engine.py.
        evidence = (
            result.failed_citations
            if result.verdict.value == "NOT_ELIGIBLE" and result.failed_citations
            else result.citations
        )
        english_answer = orchestrate.compose_verified_answer(
            llm, result.verdict.value, evidence,
        )
        if english_answer == composer.FALLBACK_BUSY:
            answer, note = phrase("busy", content_locale), None
        else:
            answer, note = _localize(language, english_answer, content_locale)
        if note:
            language_notes.append(note)
        bot_messages.append(answer)

    return {
        "domain": "scheme", "supported": True,
        "verdict": result.verdict.value, "answer": answer,
        "next_question": None,
        "bot_messages": bot_messages,
        "reply": bot_messages[0] if asked_question else None,
        "acknowledged": acknowledged,
        "missing_attributes": [],
        "pending": None,
        # Citations stay verbatim in their source language, always.
        "citations": [c.__dict__ for c in result.citations],
        "reply_citations": [c.__dict__ for c in reply_citations],
        "profile": profile, "profile_summary": summary,
        "locale": content_locale,
        "language_note": language_notes[0] if language_notes else None,
        "speech": _speech(language, bot_messages, content_locale),
    }
