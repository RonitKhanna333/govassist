"""POST /voice/call and POST /voice/webhook -- the same conversation, by phone.

    /voice/call      -> places a call that asks the scheme's questions
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

from api.agents.phrases import phrase
from api.deps import get_language
from api.language.providers.base import LanguageError
from api.language.registry import get as get_locale
from api.language.service import LanguageService
from api.routers.chat import SCHEME_SLUG
from api.rules.engine import Citation, decide, load_rules
from api.rules.forms import OTHER, derive_fields
from api.rules.spoken import parse_number, parse_yes_no
from api.voice import bland, script
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


@router.get("/script")
def call_script(scheme: str = "pmfme", locale: str = "hi") -> dict:
    """The script and answer schema, for review before any call is placed."""
    _check_scheme(scheme)
    try:
        return {
            "scheme": scheme,
            "locale": get_locale(locale).code,
            "task": script.build_task(scheme, locale),
            "answer_schema": script.answer_schema(scheme, locale),
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

    webhook = os.environ.get("VOICE_WEBHOOK_URL")
    secret = os.environ.get("VOICE_WEBHOOK_SECRET")
    if webhook and secret:
        webhook = f"{webhook}?token={secret}"

    try:
        call_id = bland.start_call(
            phone=phone,
            task=script.build_task(scheme, locale),
            schema=script.answer_schema(scheme, locale),
            webhook=webhook,
            locale=locale,
            metadata={"scheme": scheme, "locale": locale},
        )
    except bland.VoiceError as exc:
        raise HTTPException(503, str(exc)) from exc

    return {"call_id": call_id, "scheme": scheme, "locale": locale,
            "result_delivery": "sms" if webhook else "none"}


@router.post("/webhook")
async def webhook(request: Request,
                  language: LanguageService = Depends(get_language)) -> dict:
    """The provider posts the finished call. We parse, decide, and text back."""
    expected = os.environ.get("VOICE_WEBHOOK_SECRET")
    if not expected:
        raise HTTPException(503, "VOICE_WEBHOOK_SECRET is not set")
    presented = request.query_params.get("token") or request.headers.get("x-webhook-token", "")
    if not hmac.compare_digest(presented, expected):
        raise HTTPException(401, "bad webhook token")

    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(422, "expected a JSON object")

    metadata = body.get("metadata") or {}
    scheme = str(metadata.get("scheme") or body.get("scheme") or "pmfme")
    locale = get_locale(metadata.get("locale") or "hi").code
    _check_scheme(scheme)

    heard = body.get("analysis") or body.get("answers") or {}
    if not isinstance(heard, dict):
        heard = {}

    profile, unparsed = read_answers(scheme, heard)
    result = decide(scheme, profile)
    verdict = result.verdict.value if hasattr(result.verdict, "value") else str(result.verdict)

    message = result_message(scheme, locale, verdict, result.citations,
                             result.failed_citations, language)

    phone = str(body.get("to") or body.get("phone_number") or "")
    delivery = send_sms(phone, message) if phone else "no_number"

    # The transcript is the only record of what was actually said, and the
    # profile above is an interpretation of it. Keep both together in the
    # log so a wrong verdict can be traced to a mishearing.
    log.info("voice call %s: scheme=%s verdict=%s unparsed=%s",
             body.get("call_id"), scheme, verdict, unparsed)

    return {
        "scheme": scheme, "locale": locale, "verdict": verdict,
        "profile": profile, "unparsed": unparsed,
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
