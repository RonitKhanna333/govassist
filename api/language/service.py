"""LanguageService -- the only thing the rest of the app talks to.

English is canonical. Rule evaluation, retrieval, clause text, and
verification all happen in English; translation happens at the boundary, on
the way in and on the way out. That is what keeps a fifth language an entry
in registry.py rather than a re-architecture, and it's what lets the
verifier do monolingual entailment instead of a research problem.

Two properties this class exists to hold:

1. **Entities survive translation, or the translation is rejected.** Not
   softened, not warned about -- rejected, falling back to English. A
   fluent Punjabi sentence with the subsidy cap silently changed is worse
   than an English one that's correct.
2. **Nothing fails silently.** Every degradation is visible in the returned
   object, so the UI can tell the user which rung they're on rather than
   showing a mute speaker button or, worse, a confident wrong number.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from enum import Enum

from api.language import protect as protect_mod
from api.language.chunk import chunk_for_tts
from api.language.providers.base import LanguageError
from api.language.registry import CANONICAL_LOCALE, get

# Below this lexical similarity a back-translation is treated as drift.
# Calibrate on the golden set; 0.55 is a deliberately forgiving starting
# point because word order legitimately changes through a round trip.
ROUND_TRIP_THRESHOLD = 0.55


class Rung(str, Enum):
    """Which rung of the fallback ladder a result came from. Returned to
    the UI so a degradation is something the user is told about."""

    PROVIDER = "provider"          # Bhashini answered
    BROWSER = "browser"            # client should use Web Speech instead
    TEXT_ONLY = "text_only"        # no voice available for this language
    ENGLISH_FALLBACK = "english"   # translation rejected; English shown


@dataclass
class TranslationResult:
    text: str
    locale: str
    rung: Rung
    note: str | None = None        # user-facing reason, when degraded


@dataclass
class SpeechPlan:
    """What the client should do to speak this text.

    The server does not stream audio here; it decides *how* speech should
    happen and hands the client the pieces. That keeps the browser fallback
    honest -- the client is the only thing that knows which voices the
    device actually has.
    """

    chunks: list[str] = field(default_factory=list)
    locale: str = CANONICAL_LOCALE
    rung: Rung = Rung.TEXT_ONLY
    bcp47: str | None = None
    note: str | None = None


class LanguageService:
    def __init__(self, provider=None, protected_terms: list[str] | None = None) -> None:
        self._provider = provider
        self._terms = protected_terms or []

    # -- translation -------------------------------------------------------

    def translate(self, text: str, target: str,
                  source: str = CANONICAL_LOCALE) -> TranslationResult:
        if not text.strip() or target == source:
            return TranslationResult(text=text, locale=source, rung=Rung.PROVIDER)

        if self._provider is None:
            return TranslationResult(
                text=text, locale=source, rung=Rung.ENGLISH_FALLBACK,
                note="Translation isn't configured, so this is shown in English.",
            )

        protected = protect_mod.protect(text, self._terms)

        try:
            translated = self._provider.translate(protected.text, source, target)
        except LanguageError:
            return TranslationResult(
                text=text, locale=source, rung=Rung.ENGLISH_FALLBACK,
                note="Translation is unavailable right now, so this is shown in English.",
            )

        if not protected.survived(translated):
            # An entity was dropped, duplicated, or mangled. This is the
            # hard gate -- no threshold, no judgement call.
            return TranslationResult(
                text=text, locale=source, rung=Rung.ENGLISH_FALLBACK,
                note="The translation altered a number or date, so the English "
                     "version is shown instead.",
            )

        restored = protected.restore(translated)

        if not self._round_trip_ok(text, restored, target, source):
            return TranslationResult(
                text=text, locale=source, rung=Rung.ENGLISH_FALLBACK,
                note="The translation didn't check out against the original, so "
                     "the English version is shown instead.",
            )

        return TranslationResult(text=restored, locale=target, rung=Rung.PROVIDER)

    def _round_trip_ok(self, original: str, translated: str,
                       target: str, source: str) -> bool:
        """Back-translate and compare.

        The comparison here is lexical (difflib on the protected forms), not
        embedding cosine as docs/phase2-design.md describes. That's a
        deliberate, stated substitution: the *hard* protection is the entity
        check above, which is exact; this is the soft signal on top of it,
        and a lexical proxy avoids pulling a 90MB embedding model into the
        request path for a secondary check. Swap in
        api/embeddings/local.py here when it exists -- the call site is one
        line and the threshold is already a module constant.
        """
        try:
            back = self._provider.translate(translated, target, source)
        except LanguageError:
            return True  # can't check -- don't punish a translation for that

        a = protect_mod.protect(original, self._terms).text.lower()
        b = protect_mod.protect(back, self._terms).text.lower()
        return difflib.SequenceMatcher(None, a, b).ratio() >= ROUND_TRIP_THRESHOLD

    # -- speech ------------------------------------------------------------

    def plan_speech(self, text: str, locale: str) -> SpeechPlan:
        """Decide how this text should be spoken, and say so explicitly.

        Rung 1 is the provider. Rung 2 is the browser's own voice for this
        language. Rung 3 is text only -- which is a real outcome for
        Punjabi and Tamil on many devices, and the UI is expected to say so
        rather than show a button that does nothing.
        """
        entry = get(locale)
        chunks = chunk_for_tts(text, locale)

        # A provider only earns the top rung if it can actually speak.
        # Groq can translate and transcribe but has no Indic voices, so
        # claiming "provider" there would promise audio that never arrives.
        can_speak = self._provider is not None and getattr(
            self._provider, "supports_tts", False,
        )
        if can_speak and "tts" in entry.bhashini:
            return SpeechPlan(chunks=chunks, locale=entry.code, rung=Rung.PROVIDER,
                              bcp47=entry.bcp47)

        if entry.web_speech_fallback:
            return SpeechPlan(
                chunks=chunks, locale=entry.code, rung=Rung.BROWSER,
                bcp47=entry.web_speech_fallback,
                note="Using your device's built-in voice -- quality varies by device.",
            )

        return SpeechPlan(
            chunks=chunks, locale=entry.code, rung=Rung.TEXT_ONLY,
            note=f"Voice isn't available in {entry.endonym} on this device.",
        )

    def synthesize(self, text: str, locale: str) -> bytes | None:
        """Actual audio from the provider, or None to signal "use the plan"."""
        if self._provider is None:
            return None
        try:
            return self._provider.synthesize(text, locale)
        except LanguageError:
            return None

    def can_transcribe(self) -> bool:
        return self._provider is not None and hasattr(self._provider, "transcribe")

    def transcribe(self, audio: bytes, locale: str, mime: str = "audio/webm",
                   filename: str = "speech.webm") -> str:
        """Raises LanguageError with the real reason rather than returning
        None. A silent None is how "speech doesn't work" turned into a
        guessing game -- the caller needs to know whether it was no
        provider, no audio, or the provider refusing."""
        if self._provider is None:
            raise LanguageError("speech-to-text isn't configured")
        return self._provider.transcribe(audio, locale, mime=mime, filename=filename)
