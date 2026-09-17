"""Server-side speech for Hindi (and English).

Why not Groq: Groq's only speech models are English and Arabic. Why not the
browser: most Windows machines and many phones ship no Hindi voice at all,
so "Listen" was a disabled button for exactly the people it was for.

Two engines, both keyless and both unofficial -- either can change or be
rate limited without notice, so the browser voice remains the fallback in
the frontend:

* edge: the endpoint Edge's Read Aloud uses. Better voice. It returns no
  audio when called from Vercel (datacenter IPs, apparently), while working
  fine from a home connection.
* google: Google Translate's speech endpoint. Works from Vercel. About 200
  characters per request, so text is split and the MP3s concatenated
  (MP3 frames concatenate cleanly).

On Vercel google goes first; TTS_ENGINES overrides the order.
"""

from __future__ import annotations

import os
import re

import requests

from api.language.providers.base import LanguageError

VOICES = {
    "hi": os.environ.get("TTS_VOICE_HI", "hi-IN-SwaraNeural"),
    "en": os.environ.get("TTS_VOICE_EN", "en-IN-NeerjaNeural"),
}

# A spoken reply is a few sentences; anything longer is not something a
# person wants read out, and costs the endpoint's goodwill.
MAX_CHARS = 1500


GOOGLE_URL = "https://translate.google.com/translate_tts"
GOOGLE_CHUNK = 180


def _engines() -> list[str]:
    configured = os.environ.get("TTS_ENGINES")
    if configured:
        return [e.strip() for e in configured.split(",") if e.strip()]
    return ["google", "edge"] if os.environ.get("VERCEL") else ["edge", "google"]


async def synthesize(text: str, locale: str) -> bytes:
    if locale not in VOICES:
        raise LanguageError(f"no server voice for {locale}")
    text = text.strip()[:MAX_CHARS]
    if not text:
        raise LanguageError("nothing to say")
    errors = []
    for engine in _engines():
        try:
            if engine == "edge":
                return await _edge(text, locale)
            if engine == "google":
                from starlette.concurrency import run_in_threadpool
                return await run_in_threadpool(_google, text, locale)
        except LanguageError as exc:
            errors.append(f"{engine}: {exc}")
    raise LanguageError("; ".join(errors) or "no speech engine configured")


def split_for_google(text: str, limit: int = GOOGLE_CHUNK) -> list[str]:
    """Sentence-sized pieces under `limit`, never splitting inside a word."""
    pieces: list[str] = []
    for sentence in re.split(r"(?<=[.!?।])\s+", text):
        current = ""
        for word in sentence.split():
            while len(word) > limit:  # a pathological unbroken run
                if current:
                    pieces.append(current)
                    current = ""
                pieces.append(word[:limit])
                word = word[limit:]
            candidate = f"{current} {word}".strip()
            if len(candidate) > limit:
                pieces.append(current)
                current = word
            else:
                current = candidate
        if current:
            pieces.append(current)
    return [p for p in pieces if p]


def _google(text: str, locale: str) -> bytes:
    audio = bytearray()
    for piece in split_for_google(text):
        try:
            response = requests.get(
                GOOGLE_URL,
                params={"ie": "UTF-8", "tl": locale, "client": "tw-ob", "q": piece},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise LanguageError(f"request failed: {exc}") from exc
        if not response.headers.get("content-type", "").startswith("audio/"):
            raise LanguageError("did not return audio")
        audio.extend(response.content)
    if not audio:
        raise LanguageError("returned no audio")
    return bytes(audio)


async def _edge(text: str, locale: str) -> bytes:
    voice = VOICES[locale]
    try:
        import edge_tts
    except ImportError as exc:  # pragma: no cover - dependency missing
        raise LanguageError("edge-tts is not installed") from exc

    audio = bytearray()
    try:
        async for chunk in edge_tts.Communicate(text, voice).stream():
            if chunk["type"] == "audio":
                audio.extend(chunk["data"])
    except Exception as exc:  # network, endpoint changes, throttling
        raise LanguageError(f"speech synthesis failed: {exc}") from exc
    if not audio:
        raise LanguageError("speech synthesis returned no audio")
    return bytes(audio)
