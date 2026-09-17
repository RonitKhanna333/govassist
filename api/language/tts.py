"""Server-side speech for Hindi (and English), via Microsoft Edge's neural voices.

Why not Groq: Groq's only speech models are English and Arabic. Why not the
browser: most Windows machines and many phones ship no Hindi voice at all,
so "Listen" was a disabled button for exactly the people it was for.

`edge-tts` talks to the same free endpoint Edge's Read Aloud uses. It needs
no key, but it is unofficial and can change or be rate limited without
notice -- the browser voice remains the fallback in the frontend.
"""

from __future__ import annotations

import os

from api.language.providers.base import LanguageError

VOICES = {
    "hi": os.environ.get("TTS_VOICE_HI", "hi-IN-SwaraNeural"),
    "en": os.environ.get("TTS_VOICE_EN", "en-IN-NeerjaNeural"),
}

# A spoken reply is a few sentences; anything longer is not something a
# person wants read out, and costs the endpoint's goodwill.
MAX_CHARS = 1500


async def synthesize(text: str, locale: str) -> bytes:
    voice = VOICES.get(locale)
    if not voice:
        raise LanguageError(f"no server voice for {locale}")
    text = text.strip()[:MAX_CHARS]
    if not text:
        raise LanguageError("nothing to say")
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
