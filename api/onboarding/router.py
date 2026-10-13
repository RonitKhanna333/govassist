"""Account-owned general interview, callback requests and grounded dashboard."""
from __future__ import annotations

import json
import logging
import os
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.auth.models import User
from api.auth.router import current_user, get_sessions
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
             sessions=Depends(get_sessions)) -> dict:
    if body.consent is not True:
        raise HTTPException(422, "Please agree to receive the callback first.")
    if not user.phone:
        raise HTTPException(422, "A phone account is needed for a callback.")
    webhook, ask_url = _callback_urls()
    if not webhook or not ask_url or urlsplit(webhook).scheme != "https":
        raise HTTPException(503, "Callbacks need an HTTPS webhook and VOICE_WEBHOOK_SECRET.")
    parts = urlsplit(webhook)
    eligibility_url = urlunsplit(parts._replace(path=parts.path.rsplit("/", 1)[0] + "/eligibility"))
    questions = {a: f.ask or a for a, f in service.fields(body.locale).items()}
    try:
        max_minutes = int(os.environ.get("BLAND_INTERVIEW_MAX_MINUTES", "10"))
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
        record = CallRecord(user_id=user.id, locale=body.locale)
        session.add(record)
        session.commit()
        record_id = record.id
    try:
        call_id = bland.start_call(
            phone=user.phone, task=script.build_interview_task(body.locale, user.display_name or ""),
            webhook=webhook, locale=body.locale, scheme="all", ask_url=ask_url,
            metadata={"kind": "interview", "record_id": record_id, "locale": body.locale},
            extra_tools=[bland.eligibility_tool_definition(eligibility_url, body.locale, questions)],
            max_minutes=max_minutes,
        )
    except bland.VoiceError as exc:
        log.warning("Callback failed: locale=%s operation=%s provider_status=%s",
                    body.locale, exc.operation, exc.status_code)
        with sessions() as session:
            record = session.get(CallRecord, record_id)
            service.complete_record(record, "failed", [], {}, {})
            session.commit()
        if exc.status_code in (401, 403):
            raise HTTPException(503, {"code": "CALLBACK_PROVIDER_ACCESS_DENIED",
                                      "message": str(exc),
                                      "provider_status": exc.status_code,
                                      "provider_operation": exc.operation,
                                      "locale": body.locale}) from exc
        raise HTTPException(503, str(exc)) from exc
    with sessions() as session:
        record = session.get(CallRecord, record_id)
        record.call_id = call_id
        session.commit()
    return {"id": record_id, "call_id": call_id, "status": record.status}


@router.get("/dashboard")
def dashboard(locale: str = "en", user: User = Depends(current_user),
              sessions=Depends(get_sessions)) -> dict:
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
