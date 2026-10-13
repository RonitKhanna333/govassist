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

The deterministic layer only records an answer when the message can mean
exactly one thing. "Do I need to be over 18?" contains a number but is a
question; "I am not 25, I am 17" contains two numbers and a negation; "Is
passing class 8 necessary or not?" contains "not". Each of those used to be
recorded as an answer -- 18, 25 and false -- and the second one returned
ELIGIBLE for a 17-year-old. `read_answer` now says which of four things a
message is, and only VALUE is ever recorded without a person confirming it.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass

from api.agents.llm import LLMError, LLMProvider, Tier
from api.rules.forms import OTHER

# What a message is, relative to the question on screen.
VALUE = "value"          # an unambiguous answer: record it
NONE = "none"            # no deterministic signal: a model may classify it
AMBIGUOUS = "ambiguous"  # conflicting or hedged: ask the person, never guess
QUESTION = "question"    # they asked something: answer it, record nothing


@dataclass(frozen=True)
class Reading:
    status: str
    value: object = None

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

# "I don't know" contains "don't", which is a NO word. Hedges are checked as
# phrases first so uncertainty is never recorded as an answer.
_UNSURE = (
    "not sure", "unsure", "don't know", "dont know", "do not know", "no idea",
    "not certain", "maybe", "perhaps", "i think", "pata nahi", "pata nahin",
    "maloom nahi", "पता नहीं", "पता नही", "मालूम नहीं", "ਪਤਾ ਨਹੀਂ", "ਪਤਾ ਨਹੀ",
    # Word order moves in speech ("मुझे नहीं पता"), and each of these
    # contains a no-word, so without them a "don't know" is recorded as a
    # definite No -- which can deny someone a scheme they qualify for.
    "नहीं पता", "नहीं मालूम", "याद नहीं", "नहीं याद", "nahi pata", "nahi maloom",
    "yaad nahi", "ਨਹੀਂ ਪਤਾ", "ਨਹੀਂ ਮਾਲੂਮ", "can't say", "cant say", "theriyala",
    "தெரியாது", "தெரியல", "theriyadhu", "theriyala",
)

# A question starts with one of these (after a filler like "ok" or "so")...
_QUESTION_STARTS = {
    "do", "does", "did", "is", "are", "can", "could", "should", "would",
    "will", "shall", "must", "may", "what", "why", "how", "when", "where",
    "which", "who", "whom", "whose",
}
_FILLERS = {"ok", "okay", "so", "and", "but", "then", "please", "sir", "madam",
            "um", "uh", "hmm", "well"}
# ...or contains one of these interrogatives anywhere. Romanized Punjabi "ki"
# is left out on purpose: it is also the everyday Hindi "of".
_QUESTION_WORDS = {
    "क्या", "क्यों", "क्यूँ", "कैसे", "कब", "कितना", "कितने", "कितनी",
    "kya", "kyaa", "kyon", "kyun", "kaise", "kitna", "kitne", "kitni",
    "ਕੀ", "ਕਿਉਂ", "ਕਿਵੇਂ", "ਕਦੋਂ", "ਕਿੰਨਾ", "ਕਿੰਨੇ", "ਕਿੰਨੀ",
    "என்ன", "ஏன்", "எப்படி", "எப்போது", "எவ்வளவு", "எத்தனை",
}


def _tokens(text: str) -> list[str]:
    # NFC so the several ways of encoding "हाँ" compare equal.
    normalized = unicodedata.normalize("NFC", text).lower()
    return [t.strip("'") for t in _SEPARATORS.split(normalized) if t.strip("'")]


def is_question(text: str) -> bool:
    """A question of their own, not an answer to ours.

    Deliberately simple and one-directional: it can only stop a value from
    being recorded, never cause one to be.
    """
    if any(mark in text for mark in ("?", "？")):
        return True
    tokens = _tokens(text)
    if set(tokens) & _QUESTION_WORDS:
        return True
    leading = [t for t in tokens if t not in _FILLERS]
    return bool(leading) and leading[0] in _QUESTION_STARTS


def _is_hedged(text: str) -> bool:
    lowered = " ".join(_tokens(text))
    return any(phrase in lowered for phrase in _UNSURE)


def _negated(tokens: list[str]) -> bool:
    return bool(set(tokens) & NO)


def read_yes_no(text: str) -> Reading:
    if is_question(text):
        return Reading(QUESTION)
    if _is_hedged(text):
        return Reading(AMBIGUOUS)
    tokens = set(_tokens(text))
    said_yes = bool(tokens & YES)
    said_no = bool(tokens & NO)
    if said_yes and said_no:
        # "haan, nahi liya" -- guessing which one they meant is exactly the
        # error this app must not make on an eligibility question.
        return Reading(AMBIGUOUS)
    if said_yes or said_no:
        return Reading(VALUE, said_yes)
    return Reading(NONE)


def parse_yes_no(text: str) -> bool | None:
    """True / False, or None when there's no signal -- or conflicting ones,
    a hedge, or a question."""
    reading = read_yes_no(text)
    return reading.value if reading.status == VALUE else None


# A number, with the sign kept: "-25" is a negative number, not 25. Thousands
# separators ("1,000") are allowed only in their exact three-digit form, so
# "25,17" stays two numbers instead of becoming 2517.
_NUMBER = re.compile(r"(?<![\d.])([-−]\s*)?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?![\d])")


def _number_word_groups(tokens: list[str]) -> list[int]:
    """Each run of consecutive English number words, as one number.

    "twenty five" is one number; "one son and twenty workers" is two, and
    must not be summed into 21.
    """
    groups: list[int] = []
    total, found = 0, False
    for token in tokens + [""]:
        if token in _EN_TENS:
            total += _EN_TENS[token]
            found = True
        elif token in _EN_UNITS:
            total += _EN_UNITS[token]
            found = True
        elif token == "hundred" and found:
            total *= 100
        elif found:
            groups.append(total)
            total, found = 0, False
    return groups


def _numbers(text: str) -> list[float]:
    ascii_text = unicodedata.normalize("NFC", text).translate(_DIGIT_TABLE)
    found: list[float] = []
    for sign, digits, fraction in _NUMBER.findall(ascii_text):
        value = float(digits.replace(",", "") + (fraction or ""))
        found.append(-value if sign else value)
    remainder = _NUMBER.sub(" ", ascii_text)
    if re.search(r"\bminus\b", remainder.lower()):
        groups = _number_word_groups(_tokens(remainder))
        return found + [-g for g in groups]
    return found + [float(g) for g in _number_word_groups(_tokens(remainder))]


def _as_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def read_number(text: str) -> Reading:
    if is_question(text):
        return Reading(QUESTION)
    if _is_hedged(text):
        return Reading(AMBIGUOUS)
    numbers = _numbers(text)
    # "I am not 25, I am 17", "nahi, 17", "25... no, 26": a correction or a
    # negation around a number is for the person to settle, not for us.
    if _negated(_tokens(text)):
        return Reading(AMBIGUOUS)
    if len(numbers) > 1:
        return Reading(AMBIGUOUS)
    if len(numbers) == 1:
        return Reading(VALUE, _as_number(numbers[0]))
    return Reading(NONE)


def parse_number(text: str) -> float | None:
    """The single number in an unambiguous answer, sign included; else None."""
    reading = read_number(text)
    return reading.value if reading.status == VALUE else None


def read_answer(text: str, field: dict) -> Reading:
    """What `text` says about `field`, using no model at all."""
    text = (text or "").strip()
    if not text:
        return Reading(NONE)
    kind = field.get("kind")
    if kind == "number":
        return read_number(text)
    reading = read_yes_no(text)
    if reading.status != VALUE:
        return reading
    if kind == "choice":
        options = field.get("options") or []
        if len(options) != 1:
            # A multi-option choice can't be answered by yes/no.
            return Reading(AMBIGUOUS)
        return Reading(VALUE, field.get("satisfied_by") if reading.value else OTHER)
    return reading


_CLASSIFY = """A person was asked a yes/no question and answered in their own \
words, possibly in Hindi, Punjabi, Tamil or English.

Question: {question}
Their answer: {answer}

Did they answer YES or NO to exactly that question? If the answer is unclear, \
off-topic, or could mean either, say UNCLEAR. Do not guess.
Reply with one word only: YES, NO, or UNCLEAR."""

_NUMBER_PROMPT = """A person was asked: {question}
They answered, possibly in Hindi, Punjabi, Tamil or English: {answer}

What single number did they give? Number words count ("pachchees" is 25).
Reply with the number in digits only. If they gave no number, reply NONE."""


def interpret(text: str, field: dict, llm: LLMProvider | None = None) -> object | None:
    """The value to record for `field`, or None if the answer can't be placed.

    `field` is a dict as produced by Field.to_dict(). A model is consulted
    only when the deterministic reading found no signal at all -- never to
    resolve a question, a hedge, or a contradiction.
    """
    reading = read_answer(text, field)
    if reading.status == VALUE:
        return reading.value
    if reading.status != NONE or llm is None:
        return None

    text = text.strip()
    kind = field.get("kind")
    question = field.get("ask") or field.get("attribute", "")

    if kind == "number":
        try:
            raw = llm.complete(
                "You extract numbers. Reply with digits only, or NONE.",
                _NUMBER_PROMPT.format(question=question, answer=text), Tier.FAST,
            ).strip()
        except LLMError:
            return None
        value = parse_number(raw) if raw.upper() != "NONE" else None
        return value if value is None or math.isfinite(value) else None

    try:
        raw = llm.complete(
            "You classify answers. Reply YES, NO, or UNCLEAR.",
            _CLASSIFY.format(question=question, answer=text), Tier.FAST,
        ).strip().upper()
    except LLMError:
        return None
    yes = {"YES": True, "NO": False}.get(raw.split()[0] if raw else "")
    if yes is None:
        return None

    if kind == "choice":
        options = field.get("options") or []
        if len(options) == 1:
            return field.get("satisfied_by") if yes else OTHER
        return None  # a multi-option choice can't be answered by yes/no

    return yes
