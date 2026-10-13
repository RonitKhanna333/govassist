"""Bland AI: starts the call and runs the audio.

Why a platform rather than our own websocket: a phone conversation needs
streaming speech, barge-in, silence handling and an actual phone number,
and none of that is the interesting part of this project. Bland's free tier
covers a student demo; Vapi and Retell expose the same shape of API, so
`start_call` is the only place that would change.

This module never decides anything. It sends the script from
`api/voice/script.py`, asks for answers in a fixed schema, and hands the
result to `api/routers/voice.py`.
"""

from __future__ import annotations

import os
import re

import requests

BASE_URL = os.environ.get("BLAND_BASE_URL", "https://api.bland.ai/v1")

# Bland's own Hindi voice. Overridable because voice names change often.
DEFAULT_VOICE = os.environ.get("BLAND_VOICE_HI", "maya")

# E.164. A call is money and a stranger's phone ringing, so the format is
# checked here rather than discovered by the provider.
E164 = re.compile(r"^\+[1-9]\d{7,14}$")


class VoiceError(Exception):
    """Calling could not be attempted, or the provider refused."""


def configured() -> bool:
    return bool(os.environ.get("BLAND_API_KEY"))


def allowed_numbers() -> set[str]:
    """Numbers this deployment may call.

    Default-deny, and deliberately not overridable by a request field: an
    automated call to a stranger in India needs consent and DLT
    registration, and an open /voice/call endpoint on a public URL is a
    robocaller waiting for someone to find it. For the demo this holds the
    team's own phones.
    """
    raw = os.environ.get("VOICE_ALLOWED_NUMBERS", "")
    return {n.strip() for n in raw.split(",") if n.strip()}


def check_number(phone: str) -> str:
    phone = phone.strip().replace(" ", "")
    if not E164.fullmatch(phone):
        raise VoiceError("phone number must be in +91… form")
    allowed = allowed_numbers()
    if not allowed:
        raise VoiceError(
            "VOICE_ALLOWED_NUMBERS is empty, so no number may be called. "
            "Add the numbers that have agreed to be called."
        )
    if phone not in allowed:
        raise VoiceError("that number is not in VOICE_ALLOWED_NUMBERS")
    return phone


def scheme_info_tool(url: str, scheme: str, locale: str) -> dict:
    """The mid-call tool that answers questions about the scheme.

    Without it the agent would answer from the model's own memory, which is
    exactly the failure this project exists to prevent -- an invented
    subsidy amount delivered in a government helpline voice. The tool posts
    the question to /voice/ask, which answers from clauses and verifies, and
    the script tells the agent to speak the result verbatim.

    Provider tool schemas differ in detail (Bland, Vapi and Retell each
    spell this slightly differently); the endpoint itself is
    provider-agnostic, so only this dict changes.
    """
    return {
        "name": "scheme_info",
        "description": (
            "Answer a question the person asked about this government "
            "scheme. Always use this instead of your own knowledge. Speak "
            "the returned 'answer' exactly as given."
        ),
        "url": url,
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "body": {
            "question": "{{input.question}}",
            "scheme": scheme,
            "locale": locale,
        },
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "What the person asked, in their own words",
                },
            },
            "required": ["question"],
        },
        "response": {"answer": "$.answer"},
        "timeout": 20000,
    }


def start_call(phone: str, task: str, schema: dict, webhook: str | None,
               locale: str = "hi", metadata: dict | None = None,
               ask_url: str | None = None, scheme: str = "pmfme",
               timeout: float = 30.0) -> str:
    """Place the call. Returns the provider's call id."""
    key = os.environ.get("BLAND_API_KEY")
    if not key:
        raise VoiceError("BLAND_API_KEY is not set")

    payload: dict = {
        "phone_number": check_number(phone),
        "task": task,
        "voice": DEFAULT_VOICE,
        "language": "hin" if locale == "hi" else "eng",
        # The person must be able to end it by saying so, and a stuck call
        # should not run up the bill.
        "max_duration": 8,
        "record": False,
        # Answers come back in our own shape; see script.answer_schema.
        "analysis_schema": schema,
        "metadata": metadata or {},
    }
    if webhook:
        payload["webhook"] = webhook
    if ask_url:
        payload["tools"] = [scheme_info_tool(ask_url, scheme, locale)]

    try:
        response = requests.post(
            f"{BASE_URL}/calls",
            headers={"Authorization": key, "Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise VoiceError(f"could not reach the calling provider: {exc}") from exc

    try:
        body = response.json()
    except ValueError:
        raise VoiceError(f"provider returned {response.status_code}") from None

    call_id = body.get("call_id")
    if response.status_code >= 400 or not call_id:
        message = body.get("message") or body.get("errors") or response.status_code
        raise VoiceError(f"provider refused the call: {message}")
    return str(call_id)
