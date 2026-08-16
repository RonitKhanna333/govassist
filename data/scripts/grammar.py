"""The restricted expression language for eligibility conditions.

Rule conditions are authored as short boolean expressions over `profile.*`:

    profile.owns_cultivable_land == true
    profile.age >= 60 and profile.annual_income < 200000
    profile.category in ["sc", "st", "obc"]

Two design decisions worth stating plainly, because both are load-bearing:

1. `eval()` is never used. Expressions are parsed with `ast.parse` and every
   node is checked against a whitelist. Function calls, arithmetic, attribute
   chains, subscripts, comprehensions and lambdas are all rejected. A rule pack
   is data, and data must not be able to execute anything.

2. Missing information is not falsehood. If a profile lacks an attribute the
   expression needs, the result is UNKNOWN -- never False. Evaluation uses
   three-valued (Kleene) logic, so `A and B` is False when either side is
   definitely False even if the other is unknown, but UNKNOWN when the answer
   genuinely depends on what we have not asked yet.

   That distinction is the whole reason INSUFFICIENT_INFO exists as an outcome.
   Collapsing it into NOT_ELIGIBLE would mean confidently telling someone they
   do not qualify because we forgot to ask a question -- the single worst
   failure this system could have.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

PROFILE = "profile"

_ALLOWED_NODES = (
    ast.Expression,
    ast.BoolOp, ast.And, ast.Or,
    ast.UnaryOp, ast.Not,
    ast.Compare,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
    ast.Attribute, ast.Name, ast.Load,
    ast.Constant, ast.List, ast.Tuple,
)

# YAML-style lowercase booleans are what rule authors naturally write.
_YAML_BOOL = re.compile(r"\b(true|false|null)\b")
_YAML_TO_PY = {"true": "True", "false": "False", "null": "None"}


class Unknown:
    """Sentinel for 'we have not been told this yet'. Distinct from False."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNKNOWN"

    def __bool__(self):
        raise TypeError(
            "UNKNOWN has no truth value -- handle it explicitly. Treating it as "
            "False is how a missing answer turns into a wrongful denial."
        )


UNKNOWN = Unknown()


class Verdict(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    INSUFFICIENT_INFO = "INSUFFICIENT_INFO"


class ExpressionError(ValueError):
    """Raised when an expression violates the restricted grammar."""


@dataclass
class ConditionResult:
    id: str
    value: Any                       # True, False, or UNKNOWN
    missing: list[str] = field(default_factory=list)
    clause: str | None = None
    asks: str | None = None

    @property
    def satisfied(self) -> bool:
        return self.value is True

    @property
    def failed(self) -> bool:
        return self.value is False


@dataclass
class Decision:
    verdict: Verdict
    results: list[ConditionResult]

    @property
    def failed_conditions(self) -> list[ConditionResult]:
        return [r for r in self.results if r.failed]

    @property
    def missing_attributes(self) -> list[str]:
        seen: list[str] = []
        for r in self.results:
            for attr in r.missing:
                if attr not in seen:
                    seen.append(attr)
        return seen

    @property
    def next_questions(self) -> list[str]:
        """The `asks` prompts for conditions we could not resolve."""
        return [r.asks for r in self.results if r.value is UNKNOWN and r.asks]


# --------------------------------------------------------------------------
# Parsing and validation
# --------------------------------------------------------------------------


def _preprocess(expr: str) -> str:
    return _YAML_BOOL.sub(lambda m: _YAML_TO_PY[m.group(1)], expr)


def parse(expr: str) -> ast.Expression:
    """Parse and validate an expression. Raises ExpressionError if illegal."""
    if not expr or not expr.strip():
        raise ExpressionError("expression is empty")

    try:
        tree = ast.parse(_preprocess(expr), mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"syntax error: {exc.msg}") from exc

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ExpressionError(
                f"{type(node).__name__} is not allowed in rule expressions. "
                "Permitted: profile.<attr>, comparisons, and/or/not, "
                "'in [...]', and literals."
            )
        if isinstance(node, ast.Attribute):
            if not (isinstance(node.value, ast.Name) and node.value.id == PROFILE):
                raise ExpressionError(
                    f"only '{PROFILE}.<attr>' attribute access is allowed, "
                    f"got '{ast.unparse(node)}'"
                )
        if isinstance(node, ast.Name) and node.id != PROFILE:
            raise ExpressionError(
                f"unknown name '{node.id}' -- rule expressions may only "
                f"reference '{PROFILE}.<attr>' and literals"
            )

    if not _is_boolean_shaped(tree.body):
        raise ExpressionError(
            "expression must evaluate to a boolean -- use a comparison "
            "(e.g. 'profile.age >= 60'), not a bare value"
        )
    return tree


def _is_boolean_shaped(node: ast.AST) -> bool:
    if isinstance(node, (ast.Compare, ast.BoolOp)):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return True
    return False


def validate_expr(expr: str) -> list[str]:
    """Return a list of problems with `expr`; empty means valid."""
    try:
        parse(expr)
    except ExpressionError as exc:
        return [str(exc)]
    return []


def referenced_attributes(expr: str) -> list[str]:
    """Every `profile.<attr>` the expression depends on, in source order."""
    tree = parse(expr)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr not in found:
            found.append(node.attr)
    return sorted(found)


# --------------------------------------------------------------------------
# Three-valued evaluation
# --------------------------------------------------------------------------


def _and(a: Any, b: Any) -> Any:
    if a is False or b is False:
        return False           # one definite falsehood settles it
    if a is UNKNOWN or b is UNKNOWN:
        return UNKNOWN
    return True


def _or(a: Any, b: Any) -> Any:
    if a is True or b is True:
        return True            # one definite truth settles it
    if a is UNKNOWN or b is UNKNOWN:
        return UNKNOWN
    return False


def _not(a: Any) -> Any:
    return UNKNOWN if a is UNKNOWN else (not a)


_COMPARATORS = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}


def _eval(node: ast.AST, profile: dict, missing: list[str]) -> Any:
    if isinstance(node, ast.Expression):
        return _eval(node.body, profile, missing)

    if isinstance(node, ast.BoolOp):
        combine = _and if isinstance(node.op, ast.And) else _or
        result = _eval(node.values[0], profile, missing)
        for value in node.values[1:]:
            result = combine(result, _eval(value, profile, missing))
        return result

    if isinstance(node, ast.UnaryOp):
        return _not(_eval(node.operand, profile, missing))

    if isinstance(node, ast.Compare):
        left = _eval(node.left, profile, missing)
        result: Any = True
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval(comparator, profile, missing)
            if left is UNKNOWN or right is UNKNOWN:
                result = _and(result, UNKNOWN)
            else:
                try:
                    outcome = _COMPARATORS[type(op)](left, right)
                except TypeError:
                    # e.g. comparing a string to a number: the profile holds a
                    # value of the wrong shape. Unknown, not False.
                    outcome = UNKNOWN
                result = _and(result, outcome)
            left = right
        return result

    if isinstance(node, ast.Attribute):
        if node.attr not in profile or profile[node.attr] is None:
            if node.attr not in missing:
                missing.append(node.attr)
            return UNKNOWN
        return profile[node.attr]

    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, (ast.List, ast.Tuple)):
        return [_eval(el, profile, missing) for el in node.elts]

    raise ExpressionError(f"cannot evaluate {type(node).__name__}")


def evaluate(expr: str, profile: dict) -> tuple[Any, list[str]]:
    """Evaluate one expression. Returns (True | False | UNKNOWN, missing attrs)."""
    tree = parse(expr)
    missing: list[str] = []
    return _eval(tree, profile, missing), missing


# --------------------------------------------------------------------------
# Decisions over a whole rule pack
# --------------------------------------------------------------------------

_DECISION_RE = re.compile(r"^\s*(ALL|ANY)\s*\(\s*conditions\s*\)\s*$", re.IGNORECASE)


def parse_decision(decision: str) -> str:
    match = _DECISION_RE.match(decision or "")
    if not match:
        raise ExpressionError(
            f"decision must be 'ALL(conditions)' or 'ANY(conditions)', got {decision!r}"
        )
    return match.group(1).upper()


def evaluate_conditions(conditions: list[dict], profile: dict,
                        decision: str = "ALL(conditions)") -> Decision:
    """Evaluate a rule pack against a profile.

    `conditions` is a list of dicts with keys: id, expr, and optionally clause
    and asks -- exactly the shape authored in scheme.md frontmatter.
    """
    mode = parse_decision(decision)

    results: list[ConditionResult] = []
    for cond in conditions:
        value, missing = evaluate(cond["expr"], profile)
        results.append(
            ConditionResult(
                id=cond["id"],
                value=value,
                missing=missing,
                clause=cond.get("clause"),
                asks=cond.get("asks"),
            )
        )

    values = [r.value for r in results]
    if mode == "ALL":
        combined: Any = True
        for value in values:
            combined = _and(combined, value)
    else:
        combined = False
        for value in values:
            combined = _or(combined, value)

    if combined is True:
        verdict = Verdict.ELIGIBLE
    elif combined is False:
        verdict = Verdict.NOT_ELIGIBLE
    else:
        verdict = Verdict.INSUFFICIENT_INFO

    return Decision(verdict=verdict, results=results)
