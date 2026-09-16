"""Turn a rule expression into the input control that can answer it.

The bug this exists to kill: the server asks "Are you applying as an
individual micro food processing unit?", the user taps Yes, and that "Yes"
gets sent to an LLM to guess which attribute it referred to. With no API
key the guess returns nothing, the profile never advances, and the same
question repeats forever. Even *with* a key, spending a model call to
learn that Yes means `applicant_type == "individual"` is absurd -- the
expression already says so, exactly, in a grammar we wrote.

So this reads the condition's own AST and reports what would satisfy it:

    profile.is_unincorporated == true        -> boolean, satisfied by True
    profile.applicant_type == "individual"   -> choice, satisfied by "individual"
    profile.age >= 18                        -> number, >= 18
    profile.category in ["sc", "st"]         -> choice of two

A compound condition yields one field per attribute, which is also better
UX than a single Yes/No that cannot express "age 25 and passed class 8".

This only ever reports what the committed expression says. It never
invents a bound, an option, or a default.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field as dataclass_field
from functools import lru_cache
from pathlib import Path

import api._corpus_bridge  # noqa: F401 -- must run before importing grammar
from grammar import PROFILE, parse  # noqa: E402

_NUMERIC_OPS = {
    ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=",
}


@lru_cache(maxsize=1)
def attribute_registry() -> dict:
    """Plain-language questions, one per attribute -- data/attributes.json.

    The `asks` text in scheme.md follows the government's own wording, which
    is the right thing for a reviewer checking a rule against its source and
    the wrong thing to put in front of an applicant. A question there reads
    "Has your unit been identified in the SLUP for an ODOP product or
    verified by the Resource Person?"; the registry asks whether an officer
    visited and added the business to the district list.
    """
    path = Path(__file__).resolve().parents[2] / "data" / "attributes.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


@dataclass
class Field:
    attribute: str
    kind: str                       # "boolean" | "number" | "choice"
    satisfied_by: object = None     # value that makes this comparison true
    options: list = dataclass_field(default_factory=list)
    comparator: str | None = None   # for number, so the UI can hint the bound
    bound: object = None
    # Plain-language wording. `ask` is what a person is shown; `help`
    # explains any term they'd have no reason to know.
    ask: str | None = None
    help: str | None = None
    unit: str | None = None
    warn_if_yes: bool = False

    def to_dict(self) -> dict:
        return {
            "attribute": self.attribute, "kind": self.kind,
            "satisfied_by": self.satisfied_by, "options": self.options,
            "comparator": self.comparator, "bound": self.bound,
            "ask": self.ask, "help": self.help, "unit": self.unit,
            "warn_if_yes": self.warn_if_yes,
        }


YES_NO = {
    "en": ("Yes", "No"),
    "hi": ("हाँ", "नहीं"),
    "pa": ("ਹਾਂ", "ਨਹੀਂ"),
    "ta": ("ஆம்", "இல்லை"),
}


def localized_entry(attribute: str, locale: str = "en") -> dict:
    """The registry entry for `attribute`, with the `locale` wording laid over
    the English. A missing translation falls back to English per field, never
    to the raw attribute name -- a question in the wrong language is a bug,
    but `worker_count` on a Tamil screen is a worse one."""
    entry = dict(attribute_registry().get(attribute, {}))
    translated = (entry.pop("i18n", None) or {}).get(locale) or {}
    for key, value in translated.items():
        if value:
            entry[key] = value
    return entry


def _attribute_name(node: ast.AST) -> str | None:
    if (isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == PROFILE):
        return node.attr
    return None


def _literal(node: ast.AST):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_literal(el) for el in node.elts]
    return None


def derive_fields(expr: str, locale: str = "en") -> list[Field]:
    """One Field per `profile.<attr>` comparison in `expr`, in source order."""
    tree = parse(expr)  # reuses the same restricted parser the engine trusts
    fields: list[Field] = []
    seen: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare) or len(node.ops) != 1:
            continue

        attribute = _attribute_name(node.left)
        if attribute is None or attribute in seen:
            continue

        operator = node.ops[0]
        value = _literal(node.comparators[0])

        if isinstance(operator, (ast.In, ast.NotIn)) and isinstance(value, list):
            found = Field(attribute, "choice", options=value,
                          satisfied_by=value[0] if value else None)
        elif isinstance(operator, (ast.Eq, ast.NotEq)):
            satisfying = value if isinstance(operator, ast.Eq) else (
                not value if isinstance(value, bool) else None
            )
            if isinstance(value, bool):
                found = Field(attribute, "boolean", satisfied_by=satisfying)
            elif isinstance(value, str):
                found = Field(attribute, "choice", options=[value],
                              satisfied_by=satisfying)
            elif isinstance(value, (int, float)):
                found = Field(attribute, "number", satisfied_by=satisfying,
                              comparator="==", bound=value)
            else:
                continue
        elif type(operator) in _NUMERIC_OPS:
            found = Field(attribute, "number",
                          comparator=_NUMERIC_OPS[type(operator)], bound=value)
        else:
            continue

        entry = localized_entry(attribute, locale)
        found.ask = entry.get("ask")
        found.help = entry.get("help")
        found.unit = entry.get("unit")
        found.warn_if_yes = bool(entry.get("warn_if_yes"))

        seen.add(attribute)
        fields.append(found)

    return fields


def unresolved_fields(expr: str, profile: dict, locale: str = "en") -> list[Field]:
    """Only the fields this profile hasn't answered yet."""
    return [
        f for f in derive_fields(expr, locale)
        if profile.get(f.attribute) is None
    ]


def answer_yes_no(expr: str, profile: dict, affirmative: bool) -> dict:
    """Map a plain Yes/No onto the attributes this condition tests.

    Only safe when every unresolved field is boolean or a single-option
    choice -- "yes" cannot mean a number. Returns {} when it isn't safe,
    and the caller then asks for the specific values instead of guessing.
    """
    fields = unresolved_fields(expr, profile)
    if not fields or any(f.kind == "number" for f in fields):
        return {}

    answers: dict = {}
    for f in fields:
        if f.kind == "boolean":
            # Yes means the attribute is true -- NOT "whatever satisfies the
            # condition". Those differ whenever a question is phrased against
            # a negative rule, and conflating them silently inverts the
            # answer. Concretely: "Has anyone in your family already received
            # this?" tests `already_received == false`. Mapping Yes to the
            # satisfying value would record "yes they did" as false and call
            # an ineligible person eligible.
            #
            # This works because `asks` is authored to describe the
            # attribute, not the condition -- which is a property of the
            # corpus review gates, so a future scheme that breaks it is a
            # clause-review problem, not a bug to patch here.
            answers[f.attribute] = affirmative
        elif f.kind == "choice" and affirmative and f.satisfied_by is not None:
            # Choice questions do name their value ("are you an *individual*
            # unit?"), so here Yes genuinely means the satisfying option.
            answers[f.attribute] = f.satisfied_by
        elif f.kind == "choice" and not affirmative:
            # "No" says what they are not, which the expression can't turn
            # into a value. A sentinel records the refusal so the condition
            # resolves false instead of staying unknown and re-asking.
            answers[f.attribute] = "__other__"
    return answers


# Sentinel recorded when someone says "no" to a single-option choice -- it
# says what they are NOT, which the expression can't turn into a value.
OTHER = "__other__"


def summarize_profile(profile: dict, locale: str = "en") -> list[dict]:
    """The answers so far, in words a person would recognise.

    Raw state is `{"applicant_type": "__other__", "worker_count": 9}`.
    Showing that verbatim leaks an internal sentinel and a variable name
    into the interface -- which, for an app whose whole premise is replacing
    bureaucratic vocabulary, is the same failure in a different font.
    """
    yes, no = YES_NO.get(locale, YES_NO["en"])
    rows: list[dict] = []

    for attribute, value in profile.items():
        entry = localized_entry(attribute, locale)
        label = entry.get("label") or attribute.replace("_", " ").capitalize()

        if value is True:
            shown = yes
        elif value is False:
            shown = no
        elif value == OTHER:
            # Never show the sentinel. What they told us is a negative.
            shown = no
        elif entry.get("affirmative_is") is not None and value == entry["affirmative_is"]:
            # A single-option choice ("applying on your own?") was answered
            # yes. Its stored value is the rule's option name -- `individual`
            # -- which is an internal identifier, not something they said.
            shown = yes
        elif entry.get("unit"):
            shown = f"{value} {entry['unit']}"
        else:
            shown = str(value)

        rows.append({"attribute": attribute, "label": label, "value": shown})

    return rows
