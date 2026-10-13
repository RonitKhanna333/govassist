"""The general interview: which questions, in what order, and when to stop.

Derived entirely from the committed rule packs:

* `order()` -- attributes several schemes share come first, most-shared
  first; then each scheme's own attributes, in the order its rules list
  them (which puts a scheme's opening question first).
* `next_field()` -- the first attribute in that order that is unanswered
  and still matters, i.e. used by a scheme the engine hasn't decided yet.
  "No, I don't sell on the street" decides PM SVANidhi, so its other
  question is never asked.
* `skip_rules()` -- the same idea, written out for a phone script that
  can't call the engine between questions: "if they say NO to question 9,
  skip 10-11", computed by asking the engine which answer decides the
  scheme.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from api.rules.engine import decide, load_rules
from api.rules.forms import OTHER, Field, derive_fields
from parse_scheme import repo_root

HIDDEN = {"demo-scheme"}


def schemes() -> list[str]:
    root = repo_root() / "data" / "schemes"
    return sorted(
        d.name for d in root.iterdir()
        if d.name not in HIDDEN and (d / "build").is_dir()
    )


@dataclass
class Attribute:
    name: str
    schemes: list[str] = field(default_factory=list)
    position: tuple[int, int] = (0, 0)   # (scheme index, condition index)


@lru_cache(maxsize=1)
def _catalogue() -> tuple[dict[str, Attribute], dict[str, list[str]]]:
    """attribute -> where it is used; scheme -> its attributes in rule order."""
    attrs: dict[str, Attribute] = {}
    per_scheme: dict[str, list[str]] = {}
    for s_index, scheme in enumerate(schemes()):
        rules = load_rules(scheme, repo_root())
        ordered: list[str] = []
        for c_index, condition in enumerate(rules["conditions"]):
            for f in derive_fields(condition["expr"]):
                if f.attribute in ordered:
                    continue
                ordered.append(f.attribute)
                entry = attrs.setdefault(
                    f.attribute, Attribute(f.attribute, position=(s_index, c_index)))
                if scheme not in entry.schemes:
                    entry.schemes.append(scheme)
        per_scheme[scheme] = ordered
    return attrs, per_scheme


def _settles_on(scheme: str, attribute: str) -> str | None:
    """'yes' or 'no' if that answer alone makes `scheme` NOT_ELIGIBLE."""
    f = field_for(attribute)
    if f is None or f.kind == "number":
        return None
    for value, word in ((False, "no"), (True, "yes")):
        stored = value
        if f.kind == "choice":
            stored = f.satisfied_by if value else OTHER
        if decide(scheme, {attribute: stored}).verdict.value == "NOT_ELIGIBLE":
            return word
    return None


@lru_cache(maxsize=None)
def gate(scheme: str) -> str | None:
    """The question that opens a scheme's block: one only this scheme asks,
    whose answer alone can settle it -- a plain yes/no preferred over a
    multiple-choice one, because "Do you make food to sell?" opens a topic
    better than "Are you applying on your own?"."""
    attrs, per_scheme = _catalogue()
    own = [a for a in per_scheme[scheme] if attrs[a].schemes == [scheme]]
    settling = [a for a in own if _settles_on(scheme, a)]
    booleans = [a for a in settling if (field_for(a) or Field(a, "")).kind == "boolean"]
    return (booleans or settling or [None])[0]


@lru_cache(maxsize=1)
def order() -> list[str]:
    attrs, per_scheme = _catalogue()
    shared = sorted(
        (a for a in attrs.values() if len(a.schemes) > 1),
        key=lambda a: (-len(a.schemes), a.position),
    )
    out = [a.name for a in shared]
    for scheme in schemes():
        block = [n for n in per_scheme[scheme] if n not in out]
        opener = gate(scheme)
        if opener in block:
            block.remove(opener)
            block.insert(0, opener)
        out.extend(block)
    return out


def field_for(attribute: str, locale: str = "en") -> Field | None:
    """The question for an attribute, from the first scheme that uses it."""
    attrs, _ = _catalogue()
    entry = attrs.get(attribute)
    if entry is None:
        return None
    rules = load_rules(entry.schemes[0], repo_root())
    for condition in rules["conditions"]:
        for f in derive_fields(condition["expr"], locale):
            if f.attribute == attribute:
                return f
    return None


def verdicts(profile: dict) -> dict[str, str]:
    return {s: decide(s, profile).verdict.value for s in schemes()}


def next_field(profile: dict, locale: str = "en") -> Field | None:
    """The next question worth asking, or None when nothing is left."""
    open_schemes = {s for s, v in verdicts(profile).items() if v == "INSUFFICIENT_INFO"}
    attrs, _ = _catalogue()
    for name in order():
        if profile.get(name) is not None:
            continue
        if set(attrs[name].schemes) & open_schemes:
            return field_for(name, locale)
    return None


def progress(profile: dict) -> dict:
    """How far along the interview is, for a progress bar."""
    answered = sum(1 for name in order() if profile.get(name) is not None)
    remaining = 0
    probe = dict(profile)
    # Count what would still be asked if every remaining answer kept every
    # scheme open -- an upper bound, which is what a progress bar needs.
    while (f := next_field(probe)) is not None and remaining < 100:
        remaining += 1
        probe[f.attribute] = _keeps_open(f)
    return {"answered": answered, "remaining": remaining}


def _keeps_open(f: Field) -> object:
    if f.kind == "number":
        return f.bound if f.bound is not None else 1
    if f.kind == "choice":
        return f.satisfied_by
    return f.satisfied_by if f.satisfied_by is not None else True


def skip_rules(locale: str = "en") -> dict[str, dict]:
    """For a static script: which yes/no answers make later questions
    pointless. A later question can be skipped once every scheme that asks
    it is settled by this answer -- "no bank account" settles both insurance
    schemes, so their auto-debit question goes. Computed by asking the
    engine, never written by hand."""
    attrs, _ = _catalogue()
    sequence = order()
    rules: dict[str, dict] = {}
    for i, attribute in enumerate(sequence):
        f = field_for(attribute)
        if f is None or f.kind == "number":
            continue
        for value, word in ((False, "no"), (True, "yes")):
            stored = value
            if f.kind == "choice":
                stored = f.satisfied_by if value else OTHER
            settled = {s for s in attrs[attribute].schemes
                       if decide(s, {attribute: stored}).verdict.value == "NOT_ELIGIBLE"}
            if not settled:
                continue
            later = [a for a in sequence[i + 1:] if set(attrs[a].schemes) <= settled]
            if later:
                rules[attribute] = {"answer": word, "skip": later,
                                    "schemes": sorted(settled)}
            break
    return rules


def number_limits(scheme: str, attribute: str = "age") -> tuple[float | None, float | None]:
    """The (lowest, highest) value of a number the scheme's rules accept,
    read from every comparison in its conditions -- e.g. (18, 40) for
    `profile.age >= 18 and profile.age <= 40`."""
    import ast

    low = high = None
    for condition in load_rules(scheme, repo_root())["conditions"]:
        for node in ast.walk(ast.parse(condition["expr"], mode="eval")):
            if not (isinstance(node, ast.Compare) and len(node.ops) == 1):
                continue
            left, op, right = node.left, node.ops[0], node.comparators[0]
            if not (isinstance(left, ast.Attribute) and left.attr == attribute
                    and isinstance(right, ast.Constant)
                    and isinstance(right.value, (int, float))
                    and not isinstance(right.value, bool)):
                continue
            if isinstance(op, (ast.GtE, ast.Gt)):
                low = right.value if low is None else max(low, right.value)
            elif isinstance(op, (ast.LtE, ast.Lt)):
                high = right.value if high is None else min(high, right.value)
    return low, high
