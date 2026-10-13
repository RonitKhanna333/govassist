"""One validation path for every attribute value, wherever it came from.

Values reach a profile from five places: the profile the client sends back,
button/number answers, the deterministic spoken-answer parser, the intent
classifier, and the free-text NLU extractor. Before this module each of them
trusted its input, and the rule engine was left to make sense of whatever
arrived -- `worker_count: -5` passed `< 10` and came back ELIGIBLE, and
`passed_class_8: "true"` compared unequal to `true` and came back
NOT_ELIGIBLE. Both are verdicts about a value nobody actually gave.

The specification of a well-formed value is assembled from two committed
sources and nothing else:

* the scheme's own conditions (api/rules/forms.py reads their AST): whether
  an attribute is a boolean, a number, or one of a fixed set of options;
* `value` in data/attributes.json: the INPUT DOMAIN of a numeric attribute
  (a whole number, not negative, a percentage within 0-100).

The domain is deliberately not a threshold. "Ages are whole numbers of zero
or more" says what an answer to "how old are you?" can be; "above 18" says
who qualifies, and that stays in the reviewed condition where it belongs.
A value that is well-formed but fails a threshold is a legitimate input and
must still produce its legitimate NOT_ELIGIBLE.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from api.rules.forms import OTHER, attribute_registry, derive_fields


@dataclass(frozen=True)
class AttributeSpec:
    attribute: str
    kind: str                         # "boolean" | "number" | "choice"
    options: tuple = ()               # for "choice"
    integer: bool = False             # for "number"
    minimum: float | None = None
    maximum: float | None = None

    def to_dict(self) -> dict:
        return {"integer": self.integer, "minimum": self.minimum,
                "maximum": self.maximum}


@dataclass
class InvalidValue:
    attribute: str
    reason: str

    def __str__(self) -> str:
        return f"{self.attribute}: {self.reason}"


@dataclass
class Checked:
    """Values that passed, and the reasons the rest did not."""
    values: dict = field(default_factory=dict)
    errors: list[InvalidValue] = field(default_factory=list)


def numeric_domain(attribute: str) -> dict:
    return dict(attribute_registry().get(attribute, {}).get("value") or {})


def specs_for(rules: dict) -> dict[str, AttributeSpec]:
    """Every attribute the scheme's conditions read, with its value shape."""
    kinds: dict[str, str] = {}
    options: dict[str, list] = {}
    for condition in rules.get("conditions", []):
        for found in derive_fields(condition["expr"]):
            kinds.setdefault(found.attribute, found.kind)
            if found.kind == "choice":
                bucket = options.setdefault(found.attribute, [])
                bucket.extend(o for o in found.options if o not in bucket)

    specs: dict[str, AttributeSpec] = {}
    for attribute, kind in kinds.items():
        domain = numeric_domain(attribute) if kind == "number" else {}
        specs[attribute] = AttributeSpec(
            attribute=attribute,
            kind=kind,
            options=tuple(options.get(attribute, ())),
            integer=bool(domain.get("integer")),
            minimum=domain.get("min"),
            maximum=domain.get("max"),
        )
    return specs


def _describe_number(spec: AttributeSpec) -> str:
    noun = "a whole number" if spec.integer else "a number"
    if spec.minimum is not None and spec.maximum is not None:
        return f"{noun} from {_plain(spec.minimum)} to {_plain(spec.maximum)}"
    if spec.minimum is not None:
        return f"{noun} of {_plain(spec.minimum)} or more"
    return noun


def _plain(number: float) -> str:
    return str(int(number)) if float(number).is_integer() else str(number)


def check_value(spec: AttributeSpec, value: object) -> tuple[object, str | None]:
    """(normalized value, None) when well-formed, else (None, reason).

    Strict about type on purpose. JSON gives real booleans and numbers, so a
    string "true" or a number standing in for a boolean is a client bug, and
    silently coercing it is how a wrong answer gets recorded as a right one.
    """
    if spec.kind == "boolean":
        if isinstance(value, bool):
            return value, None
        return None, "must be true or false"

    if spec.kind == "number":
        # bool is a subclass of int in Python; True is not an age.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None, f"must be {_describe_number(spec)}"
        if not math.isfinite(value):
            return None, f"must be {_describe_number(spec)}"
        if spec.integer:
            if not float(value).is_integer():
                return None, f"must be {_describe_number(spec)}"
            value = int(value)
        if spec.minimum is not None and value < spec.minimum:
            return None, f"must be {_describe_number(spec)}"
        if spec.maximum is not None and value > spec.maximum:
            return None, f"must be {_describe_number(spec)}"
        return value, None

    if spec.kind == "choice":
        if isinstance(value, str) and (value in spec.options or value == OTHER):
            return value, None
        listed = ", ".join(repr(o) for o in spec.options)
        return None, f"must be one of {listed}"

    return None, "is not an attribute this scheme reads"


def check_values(specs: dict[str, AttributeSpec], values: dict) -> Checked:
    """Validate a mapping of attribute -> value.

    `None` means "not answered" -- the engine's UNKNOWN -- so it is dropped,
    not rejected. An attribute the scheme doesn't read is dropped too: it can
    never affect a verdict, and echoing it back would only carry it forward.
    """
    checked = Checked()
    for attribute, value in values.items():
        spec = specs.get(attribute)
        if spec is None or value is None:
            continue
        normalized, reason = check_value(spec, value)
        if reason:
            checked.errors.append(InvalidValue(attribute, reason))
        else:
            checked.values[attribute] = normalized
    return checked
