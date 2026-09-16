"""Turn a spoken (or typed) answer into a value for the question on screen.

Someone taps the mic and says "haan ji", "ਨਹੀਂ ਲਿਆ", "இல்லை" or "पच्चीस साल".
The question being answered is already known -- the server just asked it --
so this does not need to work out *what* the person is talking about, only
*what they said about it*. That is a much smaller problem, and most of it is
deterministic:

* yes / no words in English, Hindi, Punjabi and Tamil, in native script and
  romanized, because Whisper returns either depending on how the clip sounds;
* numbers, including Devanagari, Gurmukhi and Tamil digits.

Only when that fails does it ask a model, and even then the model is only
asked to classify -- never to decide eligibility. An answer it can't place
comes back as None, and the UI asks the person to tap instead of guessing.

Polarity follows the same rule as the buttons: "yes" means the attribute is
true. "Has anyone in your family already taken money?" -- "haan" -> true ->
disqualified. The questions are phrased so that holds; see
data/attributes.json.
"""

from __future__ import annotations

import re
import unicodedata

from api.agents.llm import LLMError, LLMProvider, Tier
from api.rules.forms import OTHER

YES = {
    # English
    "yes", "yeah", "yep", "yup", "ya", "sure", "correct", "right", "ok",
    "okay", "absolutely", "definitely", "indeed",
    # Hindi
    "हाँ", "हां", "हा", "जी", "हाँजी", "हांजी", "बिल्कुल", "बिलकुल", "सही",
    "haan", "han", "haa", "ha", "ji", "haanji", "hanji", "bilkul", "sahi",
    # Punjabi
    "ਹਾਂ", "ਹਾਂਜੀ", "ਜੀ", "ਬਿਲਕੁਲ", "ਸਹੀ", "ਹਾਂਜੀ", "haanji",
    # Tamil
    "ஆம்", "ஆமா", "ஆமாம்", "ஆமாங்க", "ஆம்ங்க", "சரி", "சரிங்க",
    "aam", "aama", "aamaa", "aamam", "sari",
}

NO = {
    # English
    "no", "nope", "nah", "not", "never", "don't", "dont", "haven't",
    "havent", "didn't", "didnt", "isn't", "isnt", "none",
    # Hindi
    "नहीं", "नही", "ना", "न", "मत", "nahi", "nahin", "nai", "na",
    # Punjabi
    "ਨਹੀਂ", "ਨਹੀ", "ਨਾ", "ਨਾਂ", "nhi",
    # Tamil
    "இல்லை", "இல்ல", "இல்லீங்க", "இல்லைங்க", "வேண்டாம்",
    "illai", "illa", "illeenga",
}

# Native-script digits -> ASCII, so "२५", "੨੫" and "௨௫" all read as 25.
_DIGITS = {}
for _start in (0x0966, 0x0A66, 0x0BE6):          # Devanagari, Gurmukhi, Tamil
    for _i in range(10):
        _DIGITS[chr(_start + _i)] = str(_i)
_DIGIT_TABLE = str.maketrans(_DIGITS)

_EN_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_EN_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}

# Split on separators, NOT on "non-word characters". Python's \w excludes
# combining marks, so matching words with it shreds every Indic answer:
# "हाँ" -> ["ह"], "ஆம்" -> ["ஆம"], "இல்லை" -> ["இல", "ல"]. None of those
# would ever match the yes/no lists, and every spoken answer in Hindi,
# Punjabi or Tamil would silently fall through to "unclear".
_SEPARATORS = re.compile(r"[\s,.!?;:।॥\"()\[\]{}\-–—]+")


def _tokens(text: str) -> list[str]:
    # NFC so the several ways of encoding "हाँ" compare equal.
    normalized = unicodedata.normalize("NFC", text).lower()
    return [t.strip("'") for t in _SEPARATORS.split(normalized) if t.strip("'")]


def parse_yes_no(text: str) -> bool | None:
    """True / False, or None when there's no signal -- or conflicting ones.

    "haan, nahi liya" contains both, and guessing which one the person meant
    is exactly the kind of error this app must not make on an eligibility
    question. Ambiguity goes back to the person.
    """
    tokens = set(_tokens(text))
    said_yes = bool(tokens & YES)
    said_no = bool(tokens & NO)
    if said_yes and not said_no:
        return True
    if said_no and not said_yes:
        return False
    return None


def _english_number_words(tokens: list[str]) -> int | None:
    total, found = 0, False
    for token in tokens:
        if token in _EN_TENS:
            total += _EN_TENS[token]
            found = True
        elif token in _EN_UNITS:
            total += _EN_UNITS[token]
            found = True
        elif token == "hundred" and found:
            total *= 100
    return total if found else None


def parse_number(text: str) -> float | None:
    ascii_text = unicodedata.normalize("NFC", text).translate(_DIGIT_TABLE)
    match = re.search(r"\d+(?:\.\d+)?", ascii_text.replace(",", ""))
    if match:
        value = float(match.group(0))
        return int(value) if value.is_integer() else value
    return _english_number_words(_tokens(ascii_text))


_CLASSIFY = """A person was asked a yes/no question and answered in their own \
words, possibly in Hindi, Punjabi, Tamil or English.

Question: {question}
Their answer: {answer}

Did they answer YES or NO to exactly that question? If the answer is unclear, \
off-topic, or could mean either, say UNCLEAR. Do not guess.
Reply with one word only: YES, NO, or UNCLEAR."""

_NUMBER = """A person was asked: {question}
They answered, possibly in Hindi, Punjabi, Tamil or English: {answer}

What single number did they give? Number words count ("pachchees" is 25).
Reply with the number in digits only. If they gave no number, reply NONE."""


def interpret(text: str, field: dict, llm: LLMProvider | None = None) -> object | None:
    """The value to record for `field`, or None if the answer can't be placed.

    `field` is a dict as produced by Field.to_dict().
    """
    text = (text or "").strip()
    if not text:
        return None

    kind = field.get("kind")
    question = field.get("ask") or field.get("attribute", "")

    if kind == "number":
        value = parse_number(text)
        if value is None and llm is not None:
            try:
                raw = llm.complete(
                    "You extract numbers. Reply with digits only, or NONE.",
                    _NUMBER.format(question=question, answer=text), Tier.FAST,
                ).strip()
                value = parse_number(raw) if raw.upper() != "NONE" else None
            except LLMError:
                value = None
        return value

    yes = parse_yes_no(text)
    if yes is None and llm is not None:
        try:
            raw = llm.complete(
                "You classify answers. Reply YES, NO, or UNCLEAR.",
                _CLASSIFY.format(question=question, answer=text), Tier.FAST,
            ).strip().upper()
            yes = {"YES": True, "NO": False}.get(raw.split()[0] if raw else "")
        except LLMError:
            yes = None
    if yes is None:
        return None

    if kind == "choice":
        options = field.get("options") or []
        if len(options) == 1:
            return field.get("satisfied_by") if yes else OTHER
        return None  # a multi-option choice can't be answered by yes/no

    return yes
