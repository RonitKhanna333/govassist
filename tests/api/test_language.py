"""api/language/ -- registry, entity protection, chunking, and the service's
fallback ladder. No network, no Bhashini credentials needed.
"""

from __future__ import annotations

from api.language import protect as protect_mod
from api.language.chunk import chunk_for_tts, split_sentences
from api.language.providers.base import LanguageError
from api.language.registry import LOCALES, get, negotiate
from api.language.service import LanguageService, Rung


# -- registry ---------------------------------------------------------------


def test_four_locales_ship():
    assert set(LOCALES) == {"en", "hi", "pa", "ta"}


def test_every_locale_has_an_endonym_not_an_english_name():
    # The switcher shows these. Someone who needs the Punjabi UI cannot
    # necessarily read the word "Punjabi".
    assert LOCALES["pa"].endonym == "ਪੰਜਾਬੀ"
    assert LOCALES["ta"].endonym == "தமிழ்"
    assert LOCALES["hi"].endonym == "हिन्दी"


def test_devanagari_and_gurmukhi_carry_the_danda():
    assert "।" in LOCALES["hi"].sentence_terminators
    assert "।" in LOCALES["pa"].sentence_terminators


def test_region_subtags_collapse():
    assert get("pa-PK").code == "pa"
    assert get("ta_LK").code == "ta"


def test_unknown_locale_falls_back_to_english_rather_than_failing():
    assert get("xx-YY").code == "en"
    assert get(None).code == "en"


def test_negotiate_respects_q_values():
    assert negotiate("ta;q=0.9, en;q=0.8") == "ta"
    assert negotiate("fr-FR, hi;q=0.7") == "hi"
    assert negotiate("de-DE") == "en"
    assert negotiate(None) == "en"


# -- entity protection ------------------------------------------------------


SAMPLE = ("You get Rs.10.0 lakh at 35% if you apply before 31st March 2026. "
          "See https://pmfme.mofpi.gov.in")


def test_protect_captures_money_percent_date_and_url():
    p = protect_mod.protect(SAMPLE)
    joined = " ".join(p.entities)
    assert "Rs.10.0 lakh" in joined
    assert "35%" in joined
    assert "https://pmfme.mofpi.gov.in" in joined


def test_restore_is_byte_exact():
    p = protect_mod.protect(SAMPLE)
    assert p.restore(p.text) == SAMPLE


def test_sentinels_are_immune_to_re_protection():
    """The bug this guards: a bare-digit sentinel sits at a word boundary,
    so the number pattern matches the index and protects it recursively."""
    p = protect_mod.protect("pay 500 and 600")
    reprotected = protect_mod.protect(p.text)
    assert reprotected.entities == []  # nothing left to find inside sentinels


def test_dropped_entity_is_detected():
    p = protect_mod.protect(SAMPLE)
    mangled = p.text.replace("⟦E1⟧", "")
    assert not p.survived(mangled)


def test_reordered_entities_still_survive():
    # Word order legitimately changes in translation; entity presence is
    # what matters, not position.
    p = protect_mod.protect("A 50 and B 60")
    reordered = p.text.replace("A ", "B ", 1)
    assert p.survived(reordered)


def test_curated_terms_are_protected_longest_first():
    p = protect_mod.protect("PM Formalisation of Micro Food Processing helps",
                            ["PM", "PM Formalisation of Micro Food Processing"])
    assert "PM Formalisation of Micro Food Processing" in p.entities


# -- chunking ---------------------------------------------------------------


def test_hindi_splits_on_danda_not_full_stop():
    text = "यह पहला वाक्य है। यह दूसरा वाक्य है।"
    assert len(split_sentences(text, "hi")) == 2


def test_english_splits_on_full_stop():
    assert len(split_sentences("One thing. Two things. Three.", "en")) == 3


def test_chunks_stay_within_the_limit_where_possible():
    text = " ".join(f"Sentence number {i} here." for i in range(40))
    chunks = chunk_for_tts(text, "en", max_chars=120)
    assert all(len(c) <= 120 for c in chunks)
    assert chunks


def test_no_text_is_lost_in_chunking():
    text = "First one. Second one. Third one."
    joined = " ".join(chunk_for_tts(text, "en", max_chars=15))
    for word in ("First", "Second", "Third"):
        assert word in joined


def test_an_unsplittable_sentence_comes_back_whole_not_truncated():
    long_word_run = "supercalifragilistic " * 20
    chunks = chunk_for_tts(long_word_run.strip(), "en", max_chars=50)
    assert "".join(chunks).replace(" ", "") == long_word_run.strip().replace(" ", "")


# -- service: the fallback ladder ------------------------------------------


class FakeProvider:
    def __init__(self, translations=None, fail=False):
        self._translations = translations or {}
        self._fail = fail
        self.calls = []

    def translate(self, text, source, target):
        self.calls.append((text, source, target))
        if self._fail:
            raise LanguageError("simulated failure")
        return self._translations.get((source, target), text)

    def synthesize(self, text, locale):
        if self._fail:
            raise LanguageError("simulated failure")
        return b"audio"

    def transcribe(self, audio, locale):
        if self._fail:
            raise LanguageError("simulated failure")
        return "transcript"


def test_no_provider_means_english_fallback_with_a_stated_reason():
    service = LanguageService(provider=None)
    result = service.translate("Hello", target="hi")
    assert result.rung is Rung.ENGLISH_FALLBACK
    assert result.locale == "en"
    assert result.note


def test_same_language_is_a_no_op():
    service = LanguageService(provider=FakeProvider())
    result = service.translate("Hello", target="en", source="en")
    assert result.text == "Hello"
    assert result.rung is Rung.PROVIDER


def test_provider_failure_degrades_to_english_not_an_exception():
    service = LanguageService(provider=FakeProvider(fail=True))
    result = service.translate("Hello there", target="hi")
    assert result.rung is Rung.ENGLISH_FALLBACK
    assert result.text == "Hello there"


def test_translation_that_drops_an_entity_is_rejected():
    """The hard gate: fluent output with a mangled number is worse than
    correct English."""
    class DropsEntities:
        def translate(self, text, source, target):
            return "पूरी तरह से अलग वाक्य"  # sentinels gone entirely
    service = LanguageService(provider=DropsEntities())
    result = service.translate("You get Rs.10.0 lakh", target="hi")
    assert result.rung is Rung.ENGLISH_FALLBACK
    assert "Rs.10.0 lakh" in result.text
    assert "number" in (result.note or "").lower()


def test_faithful_translation_passes_and_keeps_entities():
    class Faithful:
        def translate(self, text, source, target):
            return text  # keeps sentinels in place
    service = LanguageService(provider=Faithful())
    result = service.translate("You get Rs.10.0 lakh", target="hi")
    assert result.rung is Rung.PROVIDER
    assert result.locale == "hi"
    assert "Rs.10.0 lakh" in result.text  # restored byte-exact


def test_speech_plan_uses_provider_when_available():
    service = LanguageService(provider=FakeProvider())
    plan = service.plan_speech("Hello there.", "hi")
    assert plan.rung is Rung.PROVIDER
    assert plan.chunks


def test_speech_plan_falls_back_to_browser_without_a_provider():
    service = LanguageService(provider=None)
    plan = service.plan_speech("Hello there.", "pa")
    assert plan.rung is Rung.BROWSER
    assert plan.bcp47 == "pa-IN"
    assert plan.note  # the user is told which rung they're on


def test_synthesize_returns_none_rather_than_raising_on_failure():
    service = LanguageService(provider=FakeProvider(fail=True))
    assert service.synthesize("hi there", "hi") is None
