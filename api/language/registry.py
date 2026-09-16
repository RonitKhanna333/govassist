"""The locale registry -- one source of truth every layer reads.

Four languages ship: English, Hindi, Punjabi, Tamil. That set is a
deliberate choice, not a limit of the architecture -- English is canonical
internally (see api/language/service.py), so a fifth language is an entry
here plus a message catalog, not a re-architecture.

`web/lib/locale/registry.ts` mirrors this file. A test asserts the two lists
match, because a locale that exists on one side and not the other is a
runtime English leak in an otherwise Punjabi UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Locale:
    code: str
    bcp47: str
    script: str
    name_en: str
    endonym: str          # shown in the switcher -- never the English name
    font: str
    direction: str = "ltr"
    # Devanagari and Gurmukhi end sentences with a danda. Splitting on "." alone
    # leaves a whole Hindi answer as one unsplittable blob for TTS.
    sentence_terminators: tuple[str, ...] = (".", "?", "!")
    # Browser SpeechSynthesis tag to try when Bhashini is unavailable. Indic
    # coverage here is thin and device-dependent -- see service.py's ladder.
    web_speech_fallback: str | None = None
    bhashini: frozenset[str] = field(default_factory=frozenset)


LOCALES: dict[str, Locale] = {
    "en": Locale(
        code="en", bcp47="en-IN", script="Latn", name_en="English",
        endonym="English", font="Noto Sans",
        web_speech_fallback="en-IN",
        bhashini=frozenset({"asr", "tts", "nmt"}),
    ),
    "hi": Locale(
        code="hi", bcp47="hi-IN", script="Deva", name_en="Hindi",
        endonym="हिन्दी", font="Noto Sans Devanagari",
        sentence_terminators=("।", ".", "?", "!"),
        web_speech_fallback="hi-IN",
        bhashini=frozenset({"asr", "tts", "nmt"}),
    ),
    "pa": Locale(
        code="pa", bcp47="pa-IN", script="Guru", name_en="Punjabi",
        endonym="ਪੰਜਾਬੀ", font="Noto Sans Gurmukhi",
        sentence_terminators=("।", ".", "?", "!"),
        web_speech_fallback="pa-IN",
        bhashini=frozenset({"asr", "tts", "nmt"}),
    ),
    "ta": Locale(
        code="ta", bcp47="ta-IN", script="Taml", name_en="Tamil",
        endonym="தமிழ்", font="Noto Sans Tamil",
        web_speech_fallback="ta-IN",
        bhashini=frozenset({"asr", "tts", "nmt"}),
    ),
}

DEFAULT_LOCALE = "en"
CANONICAL_LOCALE = "en"  # what the rule engine, graph, and clauses all speak


def get(code: str | None) -> Locale:
    """Resolve a locale code, collapsing region subtags. Never raises --
    an unknown tag falls back to English rather than 404ing someone out of
    the product for typing pa-PK."""
    if not code:
        return LOCALES[DEFAULT_LOCALE]
    primary = code.replace("_", "-").split("-")[0].lower()
    return LOCALES.get(primary, LOCALES[DEFAULT_LOCALE])


def is_supported(code: str | None) -> bool:
    if not code:
        return False
    return code.replace("_", "-").split("-")[0].lower() in LOCALES


def negotiate(accept_language: str | None) -> str:
    """Pick a locale from an Accept-Language header, by q-value order.

    Standard BCP-47 lookup, deliberately forgiving: the first supported
    primary subtag wins, anything unrecognised is skipped rather than
    treated as an error.
    """
    if not accept_language:
        return DEFAULT_LOCALE

    entries: list[tuple[float, str]] = []
    for part in accept_language.split(","):
        piece = part.strip()
        if not piece:
            continue
        tag, _, params = piece.partition(";")
        quality = 1.0
        if params.strip().startswith("q="):
            try:
                quality = float(params.strip()[2:])
            except ValueError:
                quality = 1.0
        entries.append((quality, tag.strip()))

    for _, tag in sorted(entries, key=lambda e: e[0], reverse=True):
        if is_supported(tag):
            return get(tag).code
    return DEFAULT_LOCALE


def codes() -> list[str]:
    return list(LOCALES.keys())
