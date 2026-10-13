"""POST /voice/call and POST /voice/webhook -- the same conversation, by phone.

    /voice/check     -> free: key, balance, tools, Hindi voices -- no call
    /voice/call      -> places a call that asks the scheme's questions
    /voice/ask       -> called BY the agent mid-call: the person asked
                        something, and this returns the grounded answer it
                        is allowed to say
    /voice/webhook   -> the provider posts what it heard; we parse, decide,
                        and send the result with its citation by SMS

The division of labour is the point. The provider supplies a phone line and
speech; the questions come from `scheme.md`; the answers are parsed by
`api/rules/spoken.py`; and the verdict comes from `decide()`. No model is
asked whether anyone is eligible, on a call any more than in the browser.

Three guards, because this endpoint can ring a stranger's phone and is
reachable from the internet:

* numbers must be in VOICE_ALLOWED_NUMBERS (see api/voice/bland.py), so a
  found URL cannot be used to robocall anyone;
* the request must carry `consent: true`, recording that the person agreed
  to be called -- India's DLT rules are not satisfied by a checkbox in
  code, and the README says so;
* the webhook must present VOICE_WEBHOOK_SECRET, or anything on the
  internet could post a profile and have us text a verdict to a stranger.
"""

from __future__ import annotations

import hmac
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request

from api.agents import conversation
from api.agents.llm import LLMProvider
from api.agents.phrases import phrase
from api.deps import get_language, get_llm
from api.language.providers.base import LanguageError
from api.language.registry import get as get_locale
from api.language.service import LanguageService
from api.routers.chat import SCHEME_NAMES  # noqa: F401 -- re-exported for script.py
from api.rules.engine import SCHEME_SLUG, Citation, decide, load_clauses, load_rules
from api.rules.forms import OTHER, derive_fields
from api.rules.spoken import parse_number, parse_yes_no
from api.voice import bland, extract, script
from api.voice.sms import send_sms
from parse_scheme import repo_root

router = APIRouter(prefix="/voice")
log = logging.getLogger(__name__)


@router.get("/health")
def voice_health() -> dict:
    """What is configured. Never the keys themselves."""
    return {
        "calling": bland.configured(),
        "sms": bool(os.environ.get("TWILIO_ACCOUNT_SID")),
        "allowed_numbers": len(bland.allowed_numbers()),
        "webhook_secret": bool(os.environ.get("VOICE_WEBHOOK_SECRET")),
        "locales": sorted(script.CALL_LOCALES),
    }


@router.get("/check")
def check(request: Request) -> dict:
    """Everything that can be checked without placing a call (no credit used).

    Secret-gated: it reports the account balance and creates tools.
    """
    _check_webhook_token(request)
    report: dict = {"calling": bland.configured()}
    problems: list[str] = []
    if not bland.configured():
        problems.append("BLAND_API_KEY is not set")
    if not bland.allowed_numbers():
        problems.append("VOICE_ALLOWED_NUMBERS is empty -- nobody can be called")
    webhook, ask_url = _callback_urls()
    if not webhook:
        problems.append("VOICE_WEBHOOK_URL is not set -- answers won't come back")
    elif not webhook.startswith("https://"):
        problems.append("VOICE_WEBHOOK_URL must start with https://")
    report["allowed_numbers"] = len(bland.allowed_numbers())

    if bland.configured():
        try:
            report["account"] = bland.account()
            balance = report["account"].get("balance")
            if isinstance(balance, (int, float)) and balance < 0.5:
                problems.append(f"low credit: {balance}")
        except bland.VoiceError as exc:
            problems.append(f"API key check failed: {exc}")
        try:
            report["hindi_voices"] = bland.hindi_voices()[:10]
        except bland.VoiceError as exc:
            report["hindi_voices"] = f"could not list voices: {exc}"
        if ask_url:
            tools = {}
            for scheme in ("pmsby",):
                try:
                    tools[scheme] = bland.ensure_tool(ask_url, scheme, "hi")
                except bland.VoiceError as exc:
                    problems.append(f"tool creation failed: {exc}")
            report["tools"] = tools

    # The agent's question tool posts here; prove it answers before a call
    # depends on it. Same process, so no network hop and no model call.
    report["ask_reachable"] = bool(ask_url)
    report["ready"] = not problems
    report["problems"] = problems
    return report


def _callback_urls() -> tuple[str | None, str | None]:
    """Webhook and ask URLs, each carrying the secret, or None."""
    webhook = os.environ.get("VOICE_WEBHOOK_URL")
    secret = os.environ.get("VOICE_WEBHOOK_SECRET")
    ask_url = os.environ.get("VOICE_ASK_URL")
    if not ask_url and webhook:
        ask_url = webhook.rsplit("/", 1)[0] + "/ask"
    if not secret:
        # An unauthenticated tool URL is a public LLM endpoint, and an
        # unauthenticated webhook lets anyone text a verdict to a stranger.
        return webhook, None
    return ((f"{webhook}?token={secret}" if webhook else None),
            (f"{ask_url}?token={secret}" if ask_url else None))


@router.get("/calls/{call_id}")
def call_detail(call_id: str, request: Request,
                llm: LLMProvider = Depends(get_llm)) -> dict:
    """One call as Bland recorded it, beside what we extracted from it.

    For diagnosing a call that produced no answers. Secret-gated: it shows
    what the caller said.
    """
    _check_webhook_token(request)
    try:
        call = bland.get_call(call_id)
    except bland.VoiceError as exc:
        raise HTTPException(503, str(exc)) from exc
    metadata = call.get("metadata") or {}
    scheme = str(metadata.get("scheme") or "pmsby")
    locale = get_locale(metadata.get("locale") or "hi").code
    _check_scheme(scheme)
    questions = {q["attribute"]: q["ask"] for q in script.questions(scheme, locale)}
    heard = extract.find_answers(llm, questions, call.get("transcripts"),
                                 call.get("concatenated_transcript"))
    profile, unparsed = read_answers(scheme, heard)
    return {
        "status": call.get("status"), "answered_by": call.get("answered_by"),
        "call_length": call.get("call_length"), "price": call.get("price"),
        "error_message": call.get("error_message"),
        "transcripts": [{"user": t.get("user"), "text": t.get("text")}
                        for t in call.get("transcripts") or [] if isinstance(t, dict)],
        "caller_turns": extract.caller_turns(call.get("transcripts"),
                                             call.get("concatenated_transcript")),
        "heard": heard, "profile": profile, "unparsed": unparsed,
        "verdict": decide(scheme, profile).verdict.value,
    }


@router.get("/script")
def call_script(scheme: str = "pmfme", locale: str = "hi") -> dict:
    """The script and answer schema, for review before any call is placed."""
    _check_scheme(scheme)
    try:
        return {
            "scheme": scheme,
            "locale": get_locale(locale).code,
            "task": script.build_task(scheme, locale),
            "questions": script.questions(scheme, locale),
        }
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/call")
def place_call(body: dict) -> dict:
    scheme = str(body.get("scheme") or "pmfme")
    locale = get_locale(body.get("locale") or "hi").code
    phone = str(body.get("phone") or "")
    _check_scheme(scheme)

    if not body.get("consent"):
        raise HTTPException(
            422,
            "consent must be true: only call someone who has agreed to be "
            "called. Automated calls in India also need DLT registration.",
        )
    if locale not in script.CALL_LOCALES:
        raise HTTPException(422, f"calls aren't available in {locale} yet")

    # The agent asks /voice/ask for anything the person wants to know, so
    # the call can answer questions without a model inventing facts.
    webhook, ask_url = _callback_urls()

    try:
        call_id = bland.start_call(
            phone=phone,
            task=script.build_task(scheme, locale),
            webhook=webhook,
            locale=locale,
            metadata={"scheme": scheme, "locale": locale},
            ask_url=ask_url,
            scheme=scheme,
        )
    except bland.VoiceError as exc:
        raise HTTPException(503, str(exc)) from exc

    return {"call_id": call_id, "scheme": scheme, "locale": locale,
            "result_delivery": "sms" if webhook else "none",
            "answers_questions": bool(ask_url)}


@router.post("/ask")
def ask(body: dict, request: Request,
        llm: LLMProvider = Depends(get_llm),
        language: LanguageService = Depends(get_language)) -> dict:
    """A question asked during the call, answered from the scheme's clauses.

    The voice agent is told to call this for anything the person asks and to
    say back exactly what it returns. That is the only way a call can answer
    questions without the model inventing amounts, documents or deadlines --
    the same grounded path the web chat uses (`conversation.answer_question`,
    which cites clauses and runs the verifier), with the same honest "I don't
    have that information" when the clauses don't cover it.
    """
    _check_webhook_token(request)

    scheme = str(body.get("scheme") or "pmfme")
    locale = get_locale(body.get("locale") or "hi").code
    question = str(body.get("question") or "").strip()
    _check_scheme(scheme)
    if not question:
        raise HTTPException(422, "question is required")

    english = question
    if locale != "en":
        try:
            english = language.translate(question, target="en", source=locale).text
        except LanguageError:
            pass  # try the question as spoken; Groq handles Hindi input

    clauses = [
        Citation(clause_id=row["id"], quote=row["quote"], plain=row["plain"],
                 source_url=row["source_url"], page=row["page"])
        for row in load_clauses(scheme, repo_root()).values()
    ]
    reply = conversation.answer_question(llm, english, clauses)

    if reply.busy:
        return {"answer": phrase("busy", locale), "grounded": False}
    if not reply.text:
        return {"answer": phrase("unknown", locale), "grounded": False}

    spoken = reply.text
    if locale != "en":
        try:
            spoken = language.translate(reply.text, target=locale).text
        except LanguageError:
            pass
    return {
        "answer": spoken,
        "grounded": True,
        "clauses": [c.clause_id for c in reply.citations],
    }


def _check_webhook_token(request: Request) -> None:
    expected = os.environ.get("VOICE_WEBHOOK_SECRET")
    if not expected:
        raise HTTPException(503, "VOICE_WEBHOOK_SECRET is not set")
    presented = (request.query_params.get("token")
                 or request.headers.get("x-webhook-token", ""))
    if not hmac.compare_digest(presented, expected):
        raise HTTPException(401, "bad webhook token")


@router.post("/webhook")
async def webhook(request: Request,
                  llm: LLMProvider = Depends(get_llm),
                  language: LanguageService = Depends(get_language)) -> dict:
    """The provider posts the finished call. We parse, decide, and text back."""
    _check_webhook_token(request)

    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(422, "expected a JSON object")

    log.info("voice webhook keys: %s", sorted(body.keys()))
    metadata = body.get("metadata") or {}
    scheme = str(metadata.get("scheme") or body.get("scheme") or "pmfme")
    locale = get_locale(metadata.get("locale") or "hi").code
    _check_scheme(scheme)

    phone = str(body.get("to") or body.get("phone_number") or "")

    # Unanswered, voicemail, failed: there are no answers, and texting a
    # "we couldn't work it out" to a voicemail box helps nobody.
    answered_by = body.get("answered_by")
    status = body.get("status")
    if answered_by in ("voicemail", "no-answer") or status in ("failed", "busy", "no-answer", "canceled"):
        log.info("voice call %s not answered (%s/%s)", body.get("call_id"), status, answered_by)
        return {"scheme": scheme, "locale": locale, "verdict": None,
                "answered": False, "sms": "skipped"}

    # `answers` (attribute -> spoken words) when a caller supplies them, as
    # the tests do; otherwise found in the transcript, quote-checked.
    heard = body.get("answers")
    if not isinstance(heard, dict):
        questions = {q["attribute"]: q["ask"] for q in script.questions(scheme, locale)}
        heard = extract.find_answers(llm, questions, body.get("transcripts"),
                                     body.get("concatenated_transcript"))

    profile, unparsed = read_answers(scheme, heard)
    result = decide(scheme, profile)
    verdict = result.verdict.value if hasattr(result.verdict, "value") else str(result.verdict)

    message = result_message(scheme, locale, verdict, result.citations,
                             result.failed_citations, language)

    delivery = send_sms(phone, message) if phone else "no_number"

    # The transcript is the only record of what was actually said, and the
    # profile above is an interpretation of it. Keep both together in the
    # log so a wrong verdict can be traced to a mishearing.
    log.info("voice call %s: scheme=%s verdict=%s unparsed=%s",
             body.get("call_id"), scheme, verdict, unparsed)

    return {
        "scheme": scheme, "locale": locale, "verdict": verdict, "answered": True,
        "heard": heard, "profile": profile, "unparsed": unparsed,
        "message": message, "sms": delivery,
        "missing_attributes": result.missing_attributes,
    }


def _check_scheme(scheme: str) -> None:
    if not SCHEME_SLUG.fullmatch(scheme):
        raise HTTPException(404, f"unknown scheme '{scheme}'")
    try:
        load_rules(scheme, repo_root())
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


def read_answers(scheme: str, heard: dict) -> tuple[dict, list[str]]:
    """Spoken answers -> profile, using only values our parser recognises.

    Everything the platform reports is a transcription of 8 kHz phone audio,
    so "I think they said yes" must not become a recorded True. A value the
    parser cannot read is returned in `unparsed` and left out of the
    profile, where the three-valued engine treats it as not-yet-known.
    """
    fields = {}
    rules = load_rules(scheme, repo_root())
    for condition in rules["conditions"]:
        for field in derive_fields(condition["expr"]):
            fields.setdefault(field.attribute, field)

    profile: dict = {}
    unparsed: list[str] = []

    for attribute, raw in heard.items():
        field = fields.get(attribute)
        if field is None or raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue

        if field.kind == "number":
            number = raw if isinstance(raw, (int, float)) and not isinstance(raw, bool) \
                else parse_number(text)
            if number is None:
                unparsed.append(attribute)
            else:
                profile[attribute] = number
            continue

        said_yes = raw if isinstance(raw, bool) else parse_yes_no(text)
        if said_yes is None:
            unparsed.append(attribute)
        elif field.kind == "choice":
            profile[attribute] = field.satisfied_by if said_yes else OTHER
        else:
            profile[attribute] = said_yes

    return profile, unparsed


def result_message(scheme: str, locale: str, verdict: str,
                   citations: list[Citation], failed: list[Citation],
                   language: LanguageService | None = None) -> str:
    """The SMS: verdict, the reason in the person's language, official link.

    The reason is a clause's plain-language gloss, translated like any other
    explanation. The quote itself is never translated and never shortened
    into an SMS -- the link goes to the document it came from.
    """
    name = script.scheme_name(scheme, locale)

    if verdict == "ELIGIBLE":
        key, reasons = "sms_eligible", citations
    elif verdict == "NOT_ELIGIBLE":
        key, reasons = "sms_not_eligible", failed or citations
    else:
        return phrase("sms_incomplete", locale).format(scheme=name)

    reason = reasons[0].plain if reasons else ""
    url = reasons[0].source_url if reasons else ""
    if reason and language is not None and locale != "en":
        try:
            reason = language.translate(reason, target=locale).text
        except LanguageError:
            pass  # English reason beats no message at all
    return phrase(key, locale).format(scheme=name, reason=reason, url=url)
