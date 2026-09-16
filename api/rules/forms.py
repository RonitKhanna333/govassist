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
from dataclasses import dataclass, field as dataclass_field

import api._corpus_bridge  # noqa: F401 -- must run before importing grammar
from grammar import PROFILE, parse  # noqa: E402

_NUMERIC_OPS = {
    ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=",
}


@dataclass
class Field:
    attribute: str
    kind: str                       # "boolean" | "number" | "choice"
    satisfied_by: object = None     # value that makes this comparison true
    options: list = dataclass_field(default_factory=list)
    comparator: str | None = None   # for number, so the UI can hint the bound
    bound: object = None

    def to_dict(self) -> dict:
        return {
            "attribute": self.attribute, "kind": self.kind,
            "satisfied_by": self.satisfied_by, "options": self.options,
            "comparator": self.comparator, "bound": self.bound,
        }


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


def derive_fields(expr: str) -> list[Field]:
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

        seen.add(attribute)
        fields.append(found)

    return fields


def unresolved_fields(expr: str, profile: dict) -> list[Field]:
    """Only the fields this profile hasn't answered yet."""
    return [
        f for f in derive_fields(expr)
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
