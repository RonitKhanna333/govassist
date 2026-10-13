"""The call script and the answer schema, generated from the scheme's rules.

Hand-writing a prompt per scheme would mean the call drifts from the rule
pack the moment either changes -- and the drift is silent, because a prompt
has no validator. Here both the questions and the fields the platform must
return come from `scheme.md` via the same `derive_fields()` the web UI uses,
so adding a scheme adds a working call script with no new prose.
"""

from __future__ import annotations

from api.language.registry import get as get_locale
from api.rules.engine import load_rules
from api.rules.forms import derive_fields
from parse_scheme import repo_root

# Hindi first: it is the only language the voice pipeline has been tested in
# (see VOICE_INPUT_LOCALES in api/routers/chat.py).
CALL_LOCALES = {"hi", "en"}

_INSTRUCTIONS = {
    "hi": """आप भारत सरकार की योजना के लिए जानकारी लेने वाले सहायक हैं। \
आप गाँव-देहात के लोगों से हिंदी में बात कर रहे हैं, जिनमें से कई कम पढ़े-लिखे हैं।

ऐसे बोलें:
- बहुत आसान हिंदी, छोटे वाक्य। धीरे और साफ़ बोलें।
- एक बार में एक ही सवाल पूछें। जवाब का इंतज़ार करें।
- हर संख्या (उम्र, ज़मीन) दोहराकर पक्का करें: "आपकी उम्र {{n}} साल — सही है?"
- अगर जवाब समझ न आए तो दोबारा पूछें, अंदाज़ा न लगाएँ।
- कोई जवाब न देना चाहें तो आगे बढ़ें।

बहुत ज़रूरी:
- आप यह नहीं बताएँगे कि व्यक्ति योजना के लिए पात्र है या नहीं। यह जाँच बाद में \
नियमों से होती है। पूछा जाए तो कहें: "नतीजा आपको मैसेज पर मिलेगा।"
- कोई रकम, तारीख़, दस्तावेज़ या शर्त अपनी तरफ़ से न बताएँ।
- पैसे, बैंक का पासवर्ड, OTP, आधार या कोई निजी नंबर कभी न माँगें।

शुरू में कहें: "नमस्ते! मैं {scheme} के बारे में कुछ आसान सवाल पूछना चाहता हूँ। \
इसमें दो मिनट लगेंगे। क्या मैं पूछ सकता हूँ?"
अंत में कहें: "धन्यवाद! नतीजा आपको मैसेज पर भेज दिया जाएगा।\"""",
    "en": """You collect information for an Indian government scheme from \
people in rural India, many with little schooling.

How to speak:
- Very simple words, short sentences. Speak slowly and clearly.
- Ask ONE question at a time and wait for the answer.
- Repeat every number back to confirm it: "Your age is {{n}}, is that right?"
- If an answer is unclear, ask again. Never guess.
- If they don't want to answer something, move on.

Critical:
- You do NOT tell the person whether they qualify. That is checked
  afterwards against the rules. If asked, say the result will be sent by
  message.
- Never state an amount, date, document or condition of your own.
- Never ask for money, a bank password, an OTP, Aadhaar or any ID number.

Open with: "Hello! I'd like to ask a few simple questions about {scheme}.
It takes two minutes. May I?"
Close with: "Thank you! Your result will be sent to you by message.\"""",
}


def _questions(scheme: str, locale: str) -> list[dict]:
    """One entry per attribute the rules test, in the order they're asked."""
    rules = load_rules(scheme, repo_root())
    seen: set[str] = set()
    out: list[dict] = []
    for condition in rules["conditions"]:
        for field in derive_fields(condition["expr"], locale):
            if field.attribute in seen:
                continue
            seen.add(field.attribute)
            out.append({
                "attribute": field.attribute,
                "kind": field.kind,
                "ask": field.ask,
                "help": field.help,
                "unit": field.unit,
            })
    return out


def scheme_name(scheme: str, locale: str) -> str:
    from api.routers.chat import SCHEME_NAMES  # local: avoids a cycle
    names = SCHEME_NAMES.get(scheme, {})
    rules = load_rules(scheme, repo_root())
    return names.get(locale) or names.get("en") or rules.get("name_en", scheme)


def build_task(scheme: str, locale: str = "hi") -> str:
    """The instructions the voice platform runs the conversation from."""
    code = get_locale(locale).code
    if code not in CALL_LOCALES:
        raise ValueError(f"calls aren't available in {code} yet")

    lines = []
    for index, question in enumerate(_questions(scheme, code), start=1):
        line = f"{index}. {question['ask']}"
        if question["kind"] == "number" and question["unit"]:
            line += f"  [{question['unit']}]"
        if question["help"]:
            line += f"\n   ({question['help']})"
        lines.append(line)

    return (
        _INSTRUCTIONS[code].format(scheme=scheme_name(scheme, code))
        + "\n\n"
        + ("पूछने के सवाल, इसी क्रम में:\n" if code == "hi"
           else "Ask these questions, in this order:\n")
        + "\n".join(lines)
    )


def answer_schema(scheme: str, locale: str = "hi") -> dict:
    """What the platform must return after the call, as a JSON schema.

    Asking for structured values beats mining the transcript with regular
    expressions: a verdict here turns on exact numbers, and "I think he said
    forty" is not something a pattern can report. Every value still goes
    through our own parser before it is recorded -- see routers/voice.py.
    """
    code = get_locale(locale).code
    properties: dict[str, dict] = {}
    for question in _questions(scheme, code):
        if question["kind"] == "number":
            spec = {"type": ["number", "null"],
                    "description": f"{question['ask']} ({question['unit'] or 'number'})"}
        else:
            # Spoken, not boolean: "haan ji", "nahi liya", "mujhe nahi pata".
            spec = {"type": ["string", "null"],
                    "description": f"{question['ask']} -- the person's answer, "
                                   f"in their own words"}
        properties[question["attribute"]] = spec
    return {"type": "object", "properties": properties}


def attribute_kinds(scheme: str) -> dict[str, str]:
    """attribute -> "number" | "boolean" | "choice", for parsing replies."""
    return {q["attribute"]: q["kind"] for q in _questions(scheme, "en")}
