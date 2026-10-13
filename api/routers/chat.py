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

import hmac
import json
import os
import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, StrictBool, StrictStr
from starlette.concurrency import run_in_threadpool

import api._corpus_bridge  # noqa: F401 -- must run before importing parse_scheme
from api.agents import composer, conversation, nlu, orchestrate
from api.agents.llm import LLMProvider
from api.agents.phrases import phrase
from api.agents.router import route
from api.body_limit import AUDIO_BODY_LIMIT
from api.deps import get_language, get_llm
from api.language import tts
from api.language.providers.base import LanguageError
from api.language.registry import CANONICAL_LOCALE, LOCALES, get as get_locale, negotiate
from api.language.service import LanguageService
from api.rate_limit import (
    chat_rate_limiter,
    client_key,
    enforce,
    probe_rate_limiter,
    speak_rate_limiter,
    too_many,
    transcribe_rate_limiter,
)
from api.rules.engine import Citation, decide, known_attributes, load_clauses, load_rules
from api.rules import next_steps
from api.rules.forms import OTHER, answer_yes_no, summarize_profile, unresolved_fields
from api.rules.spoken import AMBIGUOUS, NONE, QUESTION, VALUE, Reading, read_answer
from api.rules.values import check_value, check_values, specs_for
from parse_scheme import repo_root  # noqa: E402
from review_binding import Assessment, assess  # noqa: E402

router = APIRouter()

# Speech input is enabled for these only, for now. Whisper handles Punjabi and
# Tamil too, but Hindi is what has been decided to ship and test first, and a
# mic that half-works in a language nobody has checked is worse than an honest
# "voice input isn't available in this language yet".
VOICE_INPUT_LOCALES = {"en", "hi"}
MAX_AUDIO_BYTES = AUDIO_BODY_LIMIT  # under Vercel's 4.5 MB request ceiling
# A transcript of the 30-second recording cap is a few hundred characters.
MAX_MESSAGE_CHARS = 1000
MAX_SPEAK_CHARS = 2000
MAX_PROFILE_KEYS = 64

_AUDIO_EXT = {
    "audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a",
    "audio/mpeg": "mp3", "audio/wav": "wav", "audio/x-wav": "wav",
}


def _probe_allowed(request: Request) -> bool:
    """`?probe=llm` spends provider quota, so it is for operators only:
    the caller must present GOVASSIST_DIAGNOSTIC_TOKEN. With no token
    configured the probe is simply off."""
    expected = os.environ.get("GOVASSIST_DIAGNOSTIC_TOKEN", "")
    given = request.headers.get("x-diagnostic-token", "")
    return len(expected) >= 16 and hmac.compare_digest(given, expected)


@router.get("/health")
def health(request: Request, probe: str | None = None) -> dict:
    """Liveness, plus which capabilities are actually configured.

    This exists because of a real failure that took far too long to
    diagnose: the composer catches every LLMError and returns the same
    honest fallback sentence, so "no API key", "wrong API key", "model
    retired" and "rate limited" all look identical from outside.

    Reporting configuration is safe and free, and stays open and unlimited.
    `?probe=llm` goes further and actually calls Groq once, returning the
    provider's real error text -- never the key itself. Because that costs
    quota, it needs the X-Diagnostic-Token header and is rate limited.
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
        if not _probe_allowed(request):
            raise HTTPException(403, "The provider probe is for operators. "
                                     "Send X-Diagnostic-Token.")
        decision = probe_rate_limiter.check(client_key(request))
        if not decision.allowed:
            raise too_many(decision.retry_after)
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


# The fixture scheme exists for tests, not for applicants.
_HIDDEN_SCHEMES = {"demo-scheme"}
_SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")

# Names people actually use, per language. The official English name stays
# in `name_en`.
_SCHEME_NAMES = {
    "pmfme": {"en": "Food processing business support (PMFME)",
              "hi": "खाद्य प्रसंस्करण उद्यम सहायता (PMFME)",
              "pa": "ਖ਼ੁਰਾਕ ਪ੍ਰੋਸੈਸਿੰਗ ਕਾਰੋਬਾਰ ਸਹਾਇਤਾ (PMFME)",
              "ta": "உணவு பதப்படுத்தும் தொழில் உதவி (PMFME)"},
    "pmsby": {"en": "Accident insurance for Rs. 20 a year (PMSBY)",
              "hi": "₹20 सालाना दुर्घटना बीमा (PMSBY)",
              "pa": "₹20 ਸਾਲਾਨਾ ਹਾਦਸਾ ਬੀਮਾ (PMSBY)",
              "ta": "ஆண்டுக்கு ₹20 விபத்துக் காப்பீடு (PMSBY)"},
    "pmjjby": {"en": "Life insurance of Rs. 2 lakh (PMJJBY)",
               "hi": "₹2 लाख जीवन बीमा (PMJJBY)",
               "pa": "₹2 ਲੱਖ ਜੀਵਨ ਬੀਮਾ (PMJJBY)",
               "ta": "₹2 லட்சம் ஆயுள் காப்பீடு (PMJJBY)"},
    "apy": {"en": "Pension after 60 (Atal Pension Yojana)",
            "hi": "60 साल के बाद पेंशन (अटल पेंशन योजना)",
            "pa": "60 ਸਾਲ ਤੋਂ ਬਾਅਦ ਪੈਨਸ਼ਨ (ਅਟਲ ਪੈਨਸ਼ਨ ਯੋਜਨਾ)",
            "ta": "60 வயதுக்குப் பிறகு ஓய்வூதியம் (அடல் பென்ஷன் யோஜனா)"},
    "pm-kmy": {"en": "Farmer pension of Rs. 3000 a month (PM-KMY)",
               "hi": "किसान पेंशन ₹3000 महीना (PM किसान मानधन)",
               "pa": "ਕਿਸਾਨ ਪੈਨਸ਼ਨ ₹3000 ਮਹੀਨਾ (PM ਕਿਸਾਨ ਮਾਨਧਨ)",
               "ta": "விவசாயி ஓய்வூதியம் மாதம் ₹3000 (PM-KMY)"},
}


def review_assessment(slug: str) -> Assessment:
    """Whether a person's Gate 4 and Gate 5 approvals cover exactly the rules
    and clauses being served. Never inferred or assumed: a status string of
    "approved" is not enough -- see data/scripts/review_binding.py. Anything
    unreadable is pending, never reviewed."""
    path = repo_root() / "data" / "schemes" / slug / ".state.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        rules = load_rules(slug, repo_root())
        rows = load_clauses(slug, repo_root()).values()
    except (OSError, ValueError):
        return Assessment(reviewed=False, reasons=["no readable review record"])
    clauses = [{"id": r["id"], "type": r.get("type"), "source": r.get("source_id"),
                "quote": r.get("quote"), "plain": r.get("plain"),
                "tests": r.get("tests") or []} for r in rows]
    conditions = [{"id": c["id"], "expr": c["expr"], "clause": c.get("clause")}
                  for c in rules.get("conditions", [])]
    return assess(state if isinstance(state, dict) else {}, clauses, conditions,
                  rules.get("decision", ""))


def _reviewed(slug: str) -> bool:
    return review_assessment(slug).reviewed


@router.get("/schemes")
def schemes(locale: str | None = None) -> dict:
    """Every scheme with built rules. `reviewed` is false until a person has
    approved the clause and rule-logic gates for the content served now --
    the UI says so, both when choosing a scheme and next to its result."""
    code = get_locale(locale).code
    root = repo_root() / "data" / "schemes"
    out = []
    for directory in sorted(root.iterdir()):
        slug = directory.name
        if slug in _HIDDEN_SCHEMES or not (directory / "build").is_dir():
            continue
        try:
            rules = load_rules(slug, repo_root())
        except FileNotFoundError:
            continue
        names = _SCHEME_NAMES.get(slug, {})
        out.append({
            "id": slug,
            "name": names.get(code) or names.get("en") or rules.get("name_en", slug),
            "name_en": rules.get("name_en", slug),
            "authority": rules.get("authority"),
            "reviewed": _reviewed(slug),
        })
    # Reviewed schemes first, then PMFME (the demonstrated flow).
    out.sort(key=lambda s: (not s["reviewed"], s["id"] != "pmfme", s["id"]))
    return {"schemes": out}


@router.post("/transcribe", dependencies=[Depends(enforce(transcribe_rate_limiter))])
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


class SpeakRequest(BaseModel):
    text: str = Field(default="", max_length=MAX_SPEAK_CHARS)
    locale: str | None = Field(default=None, max_length=16)


@router.post("/speak", dependencies=[Depends(enforce(speak_rate_limiter))])
async def speak(body: SpeakRequest) -> Response:
    """Text to speech for Hindi and English, returned as MP3."""
    code = get_locale(body.locale or "hi").code
    text = body.text
    if code not in tts.VOICES:
        raise HTTPException(422, f"Server speech isn't available in {code} yet.")
    if not text.strip():
        raise HTTPException(422, "Nothing to say.")
    try:
        audio = await tts.synthesize(text, code)
    except LanguageError as exc:
        raise HTTPException(503, f"Couldn't make speech: {exc}") from exc
    return Response(audio, media_type="audio/mpeg",
                    headers={"Cache-Control": "private, max-age=3600"})


def _localize(language: LanguageService, text: str | None, target: str):
    """Translate one field out of English, reporting any degradation."""
    if not text:
        return text, None
    result = language.translate(text, target=target)
    return result.text, (result.note if result.locale != target else None)


def _checked(specs: dict, field: dict, value: object) -> object | None:
    """`value` for the field on screen, normalized -- or None if it is not a
    well-formed answer (api/rules/values.py, the one validation path)."""
    if field.get("kind") == "choice" and isinstance(value, bool):
        value = field.get("satisfied_by") if value else OTHER
    spec = specs.get(field["attribute"])
    if spec is None:
        return None
    normalized, reason = check_value(spec, value)
    return None if reason else normalized


def _invalid(errors) -> HTTPException:
    """An actionable 422: which attribute, and what a valid value looks like."""
    return HTTPException(422, "Invalid answer -- " + "; ".join(str(e) for e in errors))



class ChatRequest(BaseModel):
    """The /chat body. Wrong types are a 422 here, not a 500 later."""
    scheme: StrictStr = Field(max_length=64)
    profile: dict[str, Any] | None = Field(default=None, max_length=MAX_PROFILE_KEYS)
    message: StrictStr | None = Field(default=None, max_length=MAX_MESSAGE_CHARS)
    start: StrictBool = False
    answer: Literal["yes", "no"] | None = None
    answers: dict[str, Any] | None = Field(default=None, max_length=MAX_PROFILE_KEYS)
    locale: StrictStr | None = Field(default=None, max_length=16)
    message_locale: StrictStr | None = Field(default=None, max_length=16)


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


@router.post("/chat", dependencies=[Depends(enforce(chat_rate_limiter))])
def chat(body: ChatRequest,
         llm: LLMProvider = Depends(get_llm),
         language: LanguageService = Depends(get_language)) -> dict:
    """One conversational turn. `bot_messages` is what the helper says this
    turn, in order -- a reply to their question and the next question arrive
    as two natural messages instead of one repeated prompt."""
    scheme = body.scheme
    message = (body.message or "").strip()
    starting = body.start

    content_locale = get_locale(body.locale).code
    message_locale = get_locale(body.message_locale or content_locale).code

    if not scheme:
        raise HTTPException(422, "scheme is required")
    if not _SLUG.fullmatch(scheme):
        raise HTTPException(404, f"unknown scheme '{scheme}'")

    try:
        rules = load_rules(scheme, repo_root())
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    allowed = set(known_attributes(rules))
    specs = specs_for(rules)

    # The profile the client carries, and button/number answers: exact
    # values, but still checked -- a malformed value must never reach a
    # verdict. Both go through the same validation as every other source.
    checked = check_values(specs, body.profile or {})
    if checked.errors:
        raise _invalid(checked.errors)
    profile = checked.values

    if body.answers:
        checked = check_values(specs, body.answers)
        if checked.errors:
            raise _invalid(checked.errors)
        profile = {**profile, **checked.values}

    yes_no = body.answer
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

        before = decide(scheme, profile)
        # Only a question that is actually on screen can be answered. After a
        # verdict the engine still reports its next unknown condition, but
        # nobody was asked it -- a "haan" typed then must not be recorded as
        # "yes, my family already took this help".
        pending_fields = (
            unresolved_fields(before.pending.expr, profile)
            if before.pending and before.verdict.value == "INSUFFICIENT_INFO" else []
        )
        field = pending_fields[0].to_dict() if pending_fields else None

        # 1. Deterministic: "haan", "ਨਹੀਂ", "25", "२५" need no model at all.
        #    Only a message that can mean one thing is recorded; a question,
        #    a hedge or a contradiction is never turned into a value.
        reading = read_answer(message, field) if field else Reading(NONE)
        if reading.status == NONE and field and english != message:
            reading = read_answer(english, field)

        value = _checked(specs, field, reading.value) if reading.status == VALUE else None
        if reading.status == VALUE and value is None:
            # Well-understood but not a possible answer ("-25 years").
            reading = Reading(AMBIGUOUS)

        # Only now is the message routed. An answer to the question on screen
        # is never a request for tax-filing help, whatever words it uses.
        routed = route(english, scheme) if reading.status != VALUE else None
        if routed is not None and not routed.supported:
            text, note = _localize(language, routed.message, content_locale)
            return {
                "domain": routed.domain.value, "supported": False,
                "verdict": None, "answer": text, "next_question": None,
                "bot_messages": [text], "reply": text, "acknowledged": False,
                "citations": [], "reply_citations": [], "profile": profile,
                "profile_summary": summarize_profile(profile, content_locale),
                "pending": None, "next_steps": None, "locale": content_locale,
                "language_note": note, "speech": None,
            }

        if value is not None:
            profile = {**profile, field["attribute"]: value}
            acknowledged = True
        elif reading.status == AMBIGUOUS:
            # Two numbers, "not 25", "I don't know": the person settles it.
            bot_messages.append(phrase("clarify", content_locale))
        else:
            # 2. One classification call: answer, question, or chat?
            intent = conversation.classify(
                llm, field.get("ask") if field else None,
                field.get("kind") if field else None, english,
            )
            if reading.status == QUESTION:
                intent = conversation.Intent("question")
            # A model's value is used only for an answer of the right type
            # and domain -- the same check a typed answer gets.
            if intent.kind == "answer" and intent.value is not None and field:
                value = _checked(specs, field, intent.value)
                if value is not None:
                    profile = {**profile, field["attribute"]: value}
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
                # Extraction only fills what is still unanswered: a model's
                # reading of free text never overwrites an answer the person
                # gave, and every value passes the same domain checks.
                extracted = check_values(
                    specs, nlu.extract_attributes(llm, english, sorted(allowed)),
                ).values
                extracted = {k: v for k, v in extracted.items() if k not in profile}
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
            "next_steps": None,
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

    # "What should I do next?" -- committed clauses only, no model call.
    # The gloss is localized like any explanation; the quote is not.
    checklist = next_steps.build(scheme, result, repo_root(), _reviewed(scheme))
    if checklist and content_locale != CANONICAL_LOCALE:
        steps = [item for section in checklist["sections"] for item in section["items"]]
        for item in steps + [c for c in checklist["confirm"] if "plain" in c]:
            item["plain"], note = _localize(language, item["plain"], content_locale)
            if note and note not in language_notes:
                language_notes.append(note)

    return {
        "domain": "scheme", "supported": True,
        "verdict": result.verdict.value, "answer": answer,
        "next_question": None,
        "bot_messages": bot_messages,
        "reply": bot_messages[0] if asked_question else None,
        "acknowledged": acknowledged,
        "missing_attributes": [],
        "pending": None,
        "next_steps": checklist,
        # Citations stay verbatim in their source language, always.
        "citations": [c.__dict__ for c in result.citations],
        "reply_citations": [c.__dict__ for c in reply_citations],
        "profile": profile, "profile_summary": summary,
        "locale": content_locale,
        "language_note": language_notes[0] if language_notes else None,
        "speech": _speech(language, bot_messages, content_locale),
    }
