"""Groq as the language provider when Bhashini isn't configured.

Bhashini is still the better fit for Indic voice -- it is built for exactly
that -- and api/deps.py prefers it whenever ULCA credentials exist. But it
needs a separate registration, and until someone does that, every
translation fell back to English and every Hindi user got an English app
with a note saying so. The Groq key is already configured, and Groq serves
both halves of what's missing:

* Transcription: Whisper, which covers Hindi, Punjabi and Tamil. This also
  replaces the browser's own speech recognition, which silently does
  nothing in Brave (it depends on Google servers Brave blocks) and does not
  exist at all in Firefox.
* Translation: the fast model, told to leave entity sentinels alone.
  The safety net is unchanged -- api/language/service.py still rejects any
  translation that drops or alters a protected number, date or name, and
  still round-trips it. Which model does the translating does not change
  what gets through.

What Groq does NOT provide is Indic speech synthesis, so `supports_tts` is
False and the speech ladder correctly drops to the browser's own voices.
"""

from __future__ import annotations

import os

import requests

from api.agents.llm import GroqLLM, LLMError, Tier
from api.language.providers.base import LanguageError
from api.language.registry import get as get_locale

TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

# large-v3 over turbo: turbo is faster, but accuracy on lower-resource
# languages is what matters here, and Punjabi and Tamil are exactly where
# the smaller model gives ground. Overridable, like the chat models.
DEFAULT_WHISPER = "whisper-large-v3"

# Whisper takes ISO 639-1 codes, which our locale codes already are.
_WHISPER_LANG = {"en": "en", "hi": "hi", "pa": "pa", "ta": "ta"}

_TRANSLATE_SYSTEM = """You translate short messages for a government-scheme \
eligibility assistant used by people in rural India.

Rules, all of them hard requirements:
- Translate from {source} to {target}. Output ONLY the translation -- no \
notes, no quotation marks, no transliteration, no explanation.
- Tokens that look like ⟦E0⟧, ⟦E1⟧ stand for amounts, dates \
and official names. Copy every one of them into your output EXACTLY as \
written, same number of them, unchanged. Never translate, drop, merge or \
renumber them.
- Use simple, everyday words a farmer or small shopkeeper would use. Avoid \
formal or bureaucratic vocabulary.
- Keep the meaning exactly. Do not add or remove any condition, number or \
claim. A "not" must stay a "not"."""


class GroqLanguageProvider:
    """Implements TranslationProvider and ASRProvider. Not TTS."""

    supports_tts = False

    def __init__(self, timeout: float = 60.0) -> None:
        self._timeout = timeout
        self._llm = GroqLLM(timeout=timeout)

    def _key(self) -> str:
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            raise LanguageError("GROQ_API_KEY is not set")
        return key

    # -- translation ---------------------------------------------------------

    def translate(self, text: str, source: str, target: str) -> str:
        if source == target or not text.strip():
            return text
        system = _TRANSLATE_SYSTEM.format(
            source=get_locale(source).name_en, target=get_locale(target).name_en,
        )
        try:
            # FAST, not REASONING: short-message translation is well within
            # the small model, it keeps sentinels intact in testing, and a
            # Hindi question turn otherwise spends three reasoning-tier calls
            # on translation alone -- enough to hit the free-tier rate limit.
            out = self._llm.complete(system, text, Tier.FAST)
        except LLMError as exc:
            raise LanguageError(f"Groq translation failed: {exc}") from exc
        return out.strip().strip('"').strip()

    # -- speech to text ------------------------------------------------------

    def transcribe(self, audio: bytes, locale: str,
                   mime: str = "audio/webm", filename: str = "speech.webm") -> str:
        if not audio:
            raise LanguageError("no audio received")
        model = os.environ.get("GROQ_WHISPER_MODEL") or DEFAULT_WHISPER
        data = {"model": model, "response_format": "json", "temperature": "0"}
        language = _WHISPER_LANG.get(locale)
        if language:
            # Telling Whisper the language matters a lot for short clips: a
            # two-word Punjabi answer is otherwise easily heard as Hindi.
            data["language"] = language
        try:
            response = requests.post(
                TRANSCRIBE_URL,
                headers={"Authorization": f"Bearer {self._key()}"},
                files={"file": (filename, audio, mime)},
                data=data,
                timeout=self._timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise LanguageError(f"Groq transcription failed: {exc}") from exc

        try:
            return str(response.json()["text"]).strip()
        except (KeyError, ValueError) as exc:
            raise LanguageError(f"unexpected transcription response: {response.text[:200]}") from exc

    def synthesize(self, text: str, locale: str) -> bytes:
        raise LanguageError("Groq has no Indic speech synthesis; use the browser voice")
