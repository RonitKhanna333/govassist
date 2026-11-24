"""Account-owned general interview, callback requests and grounded dashboard."""
from __future__ import annotations

import json
import logging
import os
from urllib.parse import urlsplit, urlunsplit
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.auth.models import User
from api.agents.llm import LLMProvider
from api.auth.router import current_user, get_sessions
from api.deps import get_llm
from api.onboarding import interview, service
from api.onboarding.models import CallRecord
from api.rate_limit import auth_rate_limiter, enforce
from api.rules.engine import load_clauses, load_rules
from api.rules.next_steps import SECTION_TYPES, checklist_map
from api.rules.values import check_values, specs_for
from api.routers.chat import review_assessment
from api.routers.voice import _callback_urls
from api.voice import bland, script
from parse_scheme import repo_root

router = APIRouter(prefix="/account", tags=["account"])
log = logging.getLogger(__name__)


class InterviewBody(BaseModel):
    answers: dict = Field(default_factory=dict, max_length=64)
    skipped: list[str] = Field(default_factory=list, max_length=64)
    locale: str = Field(default="en", pattern="^(en|hi)$")


class CallbackBody(BaseModel):
    consent: bool
    locale: str = Field(default="en", pattern="^(en|hi)$")
    call_language: Literal["en", "hi", "hi-Latn"] | None = None


def clean_answers(values: dict) -> dict:
    specs = {}
    for slug in interview.schemes():
        specs.update(specs_for(load_rules(slug, repo_root())))
    unknown = set(values) - set(specs)
    if unknown:
        raise HTTPException(422, "Unknown profile question")
    checked = check_values(specs, values)
    if checked.errors:
        raise HTTPException(422, "; ".join(str(e) for e in checked.errors))
    return checked.values


def interview_state(profile: dict, locale: str, skipped: list[str] | None = None) -> dict:
    question = interview.next_field(profile, locale, skipped)
    return {"profile": profile, "question": question.to_dict() if question else None,
            "progress": interview.progress(profile), "verdicts": interview.verdicts(profile)}


@router.get("/interview")
def get_interview(locale: str = "en", user: User = Depends(current_user)) -> dict:
    return interview_state(json.loads(user.profile_json or "{}"), locale)


@router.post("/interview")
def answer_interview(body: InterviewBody, user: User = Depends(current_user),
                     sessions=Depends(get_sessions)) -> dict:
    values = clean_answers(body.answers)
    with sessions() as session:
        stored = session.scalar(select(User).where(User.id == user.id).with_for_update())
        # Merge into freshly loaded state so a web answer preserves call answers.
        stored.profile_json = service.merge_profile(stored.profile_json, values)
        stored.locale = body.locale
        session.commit()
        return interview_state(json.loads(stored.profile_json), body.locale, body.skipped)


@router.post("/callback", dependencies=[Depends(enforce(auth_rate_limiter))])
def callback(body: CallbackBody, user: User = Depends(current_user),
             sessions=Depends(get_sessions), llm: LLMProvider = Depends(get_llm)) -> dict:
    if body.consent is not True:
        raise HTTPException(422, "Please agree to receive the callback first.")
    if not user.phone:
        raise HTTPException(422, "A phone account is needed for a callback.")
    # A call that already ended must not block the next one as "in progress".
    sync_calls(user.id, sessions, llm)
    call_language = body.call_language or body.locale
    profile_locale = "en" if call_language == "hi-Latn" else call_language
    webhook, ask_url = _callback_urls()
    if not webhook or not ask_url or urlsplit(webhook).scheme != "https":
        raise HTTPException(503, "Callbacks need an HTTPS webhook and VOICE_WEBHOOK_SECRET.")
    parts = urlsplit(webhook)
    eligibility_url = urlunsplit(parts._replace(path=parts.path.rsplit("/", 1)[0] + "/eligibility"))
    questions = {a: f.ask or a for a, f in service.fields(profile_locale).items()}
    if call_language == "hi-Latn":
        from api.voice.hinglish import QUESTIONS
        questions = {a: QUESTIONS.get(a, ask) for a, ask in questions.items()}
    try:
        max_minutes = int(os.environ.get("BLAND_INTERVIEW_MAX_MINUTES", "3"))
        if not 1 <= max_minutes <= 30:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(503, "BLAND_INTERVIEW_MAX_MINUTES must be between 1 and 30.") from exc
    # Persist intent before the external request: a fast webhook can use record_id.
    with sessions() as session:
        session.scalar(select(User).where(User.id == user.id).with_for_update())
        pending = session.scalar(select(CallRecord).where(
            CallRecord.user_id == user.id, CallRecord.status == "requested"))
        if pending:
            raise HTTPException(409, "You already have a callback in progress. Refresh your call history.")
        record = CallRecord(user_id=user.id, locale=call_language)
        session.add(record)
        session.commit()
        record_id = record.id
    try:
        call_id = bland.start_call(
            phone=user.phone, task=_task_for(call_language, user.display_name or ""),
            webhook=webhook if SEND_WEBHOOK else None, locale=call_language, scheme="all", ask_url=ask_url,
            metadata={"kind": "interview", "record_id": record_id, "locale": profile_locale,
                      "call_language": call_language},
            extra_tools=[bland.eligibility_tool_definition(eligibility_url, call_language, questions)],
            max_minutes=max_minutes,
        )
    except bland.VoiceError as exc:
        log.warning("Callback failed: locale=%s operation=%s provider_status=%s",
                    call_language, exc.operation, exc.status_code)
        with sessions() as session:
            record = session.get(CallRecord, record_id)
            service.complete_record(record, "failed", [], {}, {})
            session.commit()
        if exc.status_code in (401, 403):
            raise HTTPException(503, {"code": "CALLBACK_PROVIDER_ACCESS_DENIED",
                                      "message": str(exc),
                                      "provider_status": exc.status_code,
                                      "provider_operation": exc.operation,
                                      "locale": call_language}) from exc
        raise HTTPException(503, str(exc)) from exc
    with sessions() as session:
        record = session.get(CallRecord, record_id)
        record.call_id = call_id
        session.commit()
    return {"id": record_id, "call_id": call_id, "status": record.status}


@router.get("/dashboard")
def dashboard(locale: str = "en", user: User = Depends(current_user),
              sessions=Depends(get_sessions), llm: LLMProvider = Depends(get_llm)) -> dict:
    if sync_calls(user.id, sessions, llm):
        with sessions() as session:
            user = session.get(User, user.id)
    profile = json.loads(user.profile_json or "{}")
    schemes = []
    for slug, result in service.evaluate(profile).items():
        clauses = load_clauses(slug, repo_root())
        document_ids = checklist_map().get(slug, {}).get("documents", [])
        documents = [{"clause_id": cid, **clauses[cid]} for cid in document_ids
                     if cid in clauses and clauses[cid].get("type") in SECTION_TYPES["documents"]]
        schemes.append({**result.to_dict(), "name": script.scheme_name(slug, locale),
                        "reviewed": review_assessment(slug).reviewed,
                        "missing_questions": [f.to_dict() for a in (result.missing_attributes if result.verdict.value == "INSUFFICIENT_INFO" else [])
                                              if (f := interview.field_for(a, locale))],
                        "documents": documents, "documents_available": bool(documents)})
    with sessions() as session:
        records = session.scalars(select(CallRecord).where(CallRecord.user_id == user.id)
                                  .order_by(CallRecord.created_at.desc(), CallRecord.id.desc()))
        calls = [{"id": r.id, "status": r.status, "locale": r.locale,
                  "created_at": r.created_at, "completed_at": r.completed_at,
                  "transcript": json.loads(r.transcript_json or "[]"),
                  "heard": json.loads(r.heard_json or "{}"),
                  "answers": json.loads(r.answers_json or "{}")} for r in records]
    return {"name": user.display_name, "phone": user.phone, "profile": profile,
            "profile_questions": [f.to_dict() for f in service.fields(locale).values()],
            "schemes": schemes, "calls": calls}


_HINDI_CALL_RULES = """You are a warm, patient helpline assistant from GovAssist, calling someone in rural India who asked for this call. Speak ONLY simple, natural spoken Hindi (not Hinglish). Sound like a kind person, not a machine: short sentences, "ji", varied acknowledgements ("achha ji", "theek hai", "samajh gaya").

Opening: greet {name}, say you are calling from GovAssist because they asked for a call, it takes about a minute, and ask if now is a good time. If not, thank them and end.

Rules:
- Ask the questions below one at a time, in order, exactly in their meaning. Wait for each answer. Follow the age and skip notes.
- Never guess. If you can't hear or understand, say politely the line was unclear and ask again; after the third try, skip that question. Silence is never a reason to end the call.
- Confirm every number back ("to aapki umar 35 saal hai, sahi?").
- "Pata nahi" / "maybe" is not yes or no: say "koi baat nahi ji" and move on.
- Never ask for money, OTP, PIN, passwords, Aadhaar or account numbers. If they start saying such a number, stop them kindly and do not repeat it.
- If asked, say honestly you are an automated assistant.
- If they ask about a scheme, use the "GovAssist scheme info all" tool and say its answer; never answer from your own knowledge.
- At the end, call the "GovAssist eligibility" tool with what they said to each question, in their own words, and read its result in Hindi without adding or changing anything. You never decide eligibility yourself. Then say the details are on their GovAssist dashboard, thank them and end the call.

"""


def _task_for(call_language: str, name: str) -> str:
    """The call script.

    Hindi: English instructions plus the questions in Devanagari, so the
    agent says them in proper Hindi. The all-Hindi script (~4,000
    Devanagari characters, ~12 KB) is blocked by Bland's firewall from our
    host on size alone -- every section passes by itself, the whole does
    not (measured with /voice/firewall-probe?sections=1). English rules are
    one byte per character, which keeps the request well under that.
    """
    if call_language == "hi":
        full = script.build_interview_task("hi", name)
        marker = "सवाल, इसी क्रम में।"
        questions = full[full.index(marker):] if marker in full else full
        return _HINDI_CALL_RULES.format(name=name or "them") + questions
    return script.build_interview_task(call_language, name)


# Bland's Cloudflare blocks POST /v1/calls from our host whenever a long
# script and ANY webhook URL are in the same body (measured with
# /voice/firewall-probe: every script passes alone, every webhook shape is
# blocked with one). So calls go out without a webhook and finished calls
# are fetched instead -- a GET the firewall allows. BLAND_SEND_WEBHOOK=1
# restores the webhook if that ever changes.
SEND_WEBHOOK = os.environ.get("BLAND_SEND_WEBHOOK") == "1"
_FINISHED = {"completed", "failed", "busy", "no-answer", "canceled"}


def sync_calls(user_id: int, sessions, llm: LLMProvider) -> int:
    """Fetch and process this person's calls that have ended since they
    were placed. Returns how many were processed. Never raises: a provider
    hiccup must not take the dashboard down with it."""
    from api.routers.voice import _interview_webhook

    with sessions() as session:
        pending = [(r.id, r.call_id) for r in session.scalars(
            select(CallRecord).where(CallRecord.user_id == user_id,
                                     CallRecord.status == "requested",
                                     CallRecord.call_id.is_not(None)))]
    done = 0
    for record_id, call_id in pending:
        try:
            call = bland.get_call(call_id)
        except bland.VoiceError as exc:
            log.warning("sync: could not fetch call %s: %s", call_id, exc)
            continue
        status = str(call.get("status") or "")
        if not (call.get("completed") is True or status in _FINISHED):
            continue  # still ringing or talking
        metadata = {**(call.get("metadata") or {}), "kind": "interview",
                    "record_id": record_id}
        try:
            _interview_webhook({**call, "call_id": call_id}, metadata, llm)
            done += 1
        except Exception as exc:  # noqa: BLE001 -- keep the dashboard up
            log.warning("sync: could not process call %s: %s", call_id, type(exc).__name__)
    return done
