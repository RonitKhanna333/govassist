"""Bland AI: starts the call and runs the audio.

Why a platform rather than our own websocket: a phone conversation needs
streaming speech, barge-in, silence handling and an actual phone number,
and none of that is the interesting part of this project.

Checked against Bland's API reference (docs.bland.ai, October 2026), because
an earlier version guessed at it and three guesses were wrong:

* `language` takes "hi" or "en-IN" -- not "hin";
* there is no `analysis_schema` on POST /v1/calls, so answers are extracted
  from the transcript afterwards (api/voice/extract.py), not requested;
* `tools` takes IDs ("TL-...") of tools created once via POST /v1/tools,
  not inline tool definitions -- an inline object is simply not a tool.

This module never decides anything.
"""

from __future__ import annotations

import os
import re

import requests

BASE_URL = os.environ.get("BLAND_BASE_URL", "https://api.bland.ai/v1")

LANGUAGE = {"hi": "hi", "en": "en-IN"}

# Optional: a Bland voice id. Unset means Bland's default voice, which the
# `language` setting makes speak Hindi; /voice/check lists Hindi-tagged
# voices to pick from.
VOICE = os.environ.get("BLAND_VOICE") or None

# Credit is scarce (a free account has about $2). A call that runs long is
# almost always a stuck one, and the questions take two or three minutes.
MAX_MINUTES = int(os.environ.get("BLAND_MAX_MINUTES", "4"))

# E.164. A call is money and a stranger's phone ringing, so the format is
# checked here rather than discovered by the provider.
E164 = re.compile(r"^\+[1-9]\d{7,14}$")

TOOL_PREFIX = "GovAssist scheme info"

# Tool ids already resolved by this process, keyed by tool name. A cold
# start re-resolves by listing, so tools are not duplicated per instance.
_tool_ids: dict[str, str] = {}


class VoiceError(Exception):
    """Calling could not be attempted, or the provider refused."""


def configured() -> bool:
    return bool(os.environ.get("BLAND_API_KEY"))


def _key() -> str:
    key = os.environ.get("BLAND_API_KEY")
    if not key:
        raise VoiceError("BLAND_API_KEY is not set")
    return key


def _request(method: str, path: str, *, json: dict | None = None,
             timeout: float = 30.0) -> dict:
    try:
        response = requests.request(
            method, f"{BASE_URL}{path}",
            # Bland takes the raw key, not "Bearer <key>".
            headers={"Authorization": _key(), "Content-Type": "application/json"},
            json=json, timeout=timeout,
        )
    except requests.RequestException as exc:
        raise VoiceError(f"could not reach Bland: {exc}") from exc
    try:
        body = response.json()
    except ValueError:
        raise VoiceError(f"Bland returned {response.status_code}") from None
    if response.status_code >= 400 or body.get("status") == "error":
        message = body.get("message") or body.get("errors") or response.status_code
        raise VoiceError(f"Bland refused: {message}")
    return body


def allowed_numbers() -> set[str]:
    """Numbers this deployment may call.

    Default-deny, and deliberately not overridable by a request field: an
    automated call to a stranger in India needs consent and DLT
    registration, and an open /voice/call endpoint on a public URL is a
    robocaller waiting for someone to find it.
    """
    raw = os.environ.get("VOICE_ALLOWED_NUMBERS", "")
    return {n.strip().replace(" ", "") for n in raw.split(",") if n.strip()}


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


# -- the mid-call question tool ---------------------------------------------


def tool_name(scheme: str, locale: str) -> str:
    return f"{TOOL_PREFIX} {scheme} {locale}"


def tool_definition(url: str, scheme: str, locale: str) -> dict:
    """POST /v1/tools body: answers a question from the scheme's clauses.

    Without it the agent would answer from the model's own memory -- an
    invented subsidy amount in a government helpline voice. One tool per
    scheme and language, with both written into the body literally, so the
    tool does not depend on variable substitution behaving as expected.
    """
    return {
        "name": tool_name(scheme, locale),
        "description": (
            "Use this whenever the caller asks anything about the scheme -- "
            "money, who can apply, documents, how to apply. Never answer "
            "such questions from your own knowledge. Say the returned answer "
            "to the caller naturally, without adding anything."
        ),
        "speech": "एक सेकंड जी, देख रहा हूँ।" if locale == "hi" else "One second, let me check.",
        "url": url,
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "body": {"question": "{{input.question}}", "scheme": scheme, "locale": locale},
        "input_schema": {
            "example": {"question": "मुझे कितने पैसे मिलेंगे?" if locale == "hi"
                        else "How much money will I get?"},
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
        "response": {"answer": "$.answer"},
        # /voice/ask takes about 9 s with translation; the default is 10 s.
        "timeout": 20000,
    }


def list_tools() -> list[dict]:
    body = _request("GET", "/tools")
    tools = body.get("tools") or body.get("data") or []
    return tools if isinstance(tools, list) else []


def ensure_tool(url: str, scheme: str, locale: str) -> str:
    """The tool id for this scheme and language, creating it once if needed.

    A tool whose URL no longer matches (the secret or host changed) is
    created again rather than reused, so a call never points at a dead URL.
    """
    name = tool_name(scheme, locale)
    if name in _tool_ids:
        return _tool_ids[name]
    for tool in list_tools():
        tool_body = tool.get("tool") or tool
        if tool_body.get("name") == name and tool_body.get("url") == url:
            tool_id = tool.get("tool_id") or tool.get("id") or tool_body.get("tool_id")
            if tool_id:
                _tool_ids[name] = str(tool_id)
                return _tool_ids[name]
    created = _request("POST", "/tools", json=tool_definition(url, scheme, locale))
    tool_id = created.get("tool_id") or (created.get("data") or {}).get("tool_id")
    if not tool_id:
        raise VoiceError("Bland did not return a tool id")
    _tool_ids[name] = str(tool_id)
    return _tool_ids[name]


# -- calls ------------------------------------------------------------------


def call_payload(phone: str, task: str, webhook: str | None, locale: str,
                 metadata: dict, tool_ids: list[str]) -> dict:
    payload: dict = {
        "phone_number": check_number(phone),
        "task": task,
        "language": LANGUAGE.get(locale, "hi"),
        "max_duration": MAX_MINUTES,
        "record": False,
        # People answer a call with "हैलो?" -- talking over them first
        # sounds like a robocall.
        "wait_for_greeting": True,
        "metadata": metadata,
    }
    if VOICE:
        payload["voice"] = VOICE
    if webhook:
        payload["webhook"] = webhook
    if tool_ids:
        payload["tools"] = tool_ids
    return payload


def start_call(phone: str, task: str, webhook: str | None, locale: str = "hi",
               metadata: dict | None = None, ask_url: str | None = None,
               scheme: str = "pmfme") -> str:
    """Place the call. Returns the provider's call id."""
    _key()
    check_number(phone)  # before any request that could create a tool
    tool_ids = [ensure_tool(ask_url, scheme, locale)] if ask_url else []
    body = _request("POST", "/calls", json=call_payload(
        phone, task, webhook, locale, metadata or {}, tool_ids))
    call_id = body.get("call_id")
    if not call_id:
        raise VoiceError(f"Bland did not start the call: {body.get('message')}")
    return str(call_id)


# -- free checks, no call placed ---------------------------------------------


def account() -> dict:
    """GET /v1/me: account status and credit balance. Places no call."""
    body = _request("GET", "/me")
    billing = body.get("billing") or {}
    return {"status": body.get("status"),
            "balance": billing.get("current_balance"),
            "total_calls": body.get("total_calls")}


def hindi_voices() -> list[dict]:
    """Voices whose tags or description mention Hindi or India."""
    body = _request("GET", "/voices")
    out = []
    for voice in body.get("voices") or []:
        text = " ".join([str(voice.get("name", "")), str(voice.get("description", "")),
                         " ".join(map(str, voice.get("tags") or []))]).lower()
        if "hindi" in text or "india" in text:
            out.append({"id": voice.get("id") or voice.get("voice_id"),
                        "name": voice.get("name"), "tags": voice.get("tags")})
    return out


def get_call(call_id: str) -> dict:
    """GET /v1/calls/{id}: status, transcript and cost of one call."""
    if not re.fullmatch(r"[A-Za-z0-9-]{8,64}", call_id):
        raise VoiceError("bad call id")
    return _request("GET", f"/calls/{call_id}")
