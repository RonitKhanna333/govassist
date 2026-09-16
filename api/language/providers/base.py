"""Provider protocols. Nothing above this layer knows Bhashini exists.

Same pattern as api/agents/llm.py's LLMProvider, for the same reason: the
translation/voice provider is the part most likely to rate-limit, change
shape, or be unavailable on demo day, so everything that depends on it
depends on an interface instead.
"""

from __future__ import annotations

from typing import Protocol


class TranslationProvider(Protocol):
    def translate(self, text: str, source: str, target: str) -> str:
        """Translate between two locale codes. Raises LanguageError."""
        ...


class TTSProvider(Protocol):
    def synthesize(self, text: str, locale: str) -> bytes:
        """Return audio bytes (wav/mp3). Raises LanguageError."""
        ...


class ASRProvider(Protocol):
    def transcribe(self, audio: bytes, locale: str) -> str:
        """Return the transcript. Raises LanguageError."""
        ...


class LanguageError(RuntimeError):
    """Any provider failure -- missing credentials, network, bad response.

    One type for all of them, deliberately: every caller's correct response
    is the same, which is to drop a rung on the fallback ladder in
    api/language/service.py, not to branch on the cause.
    """
