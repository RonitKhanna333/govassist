"""Tests for the restricted expression language.

Two things are being defended here:
  1. Rule packs are data and must never execute anything.
  2. Missing information must never silently become a denial.
"""

import pytest

from grammar import (
    UNKNOWN,
    ExpressionError,
    Verdict,
    evaluate,
    evaluate_conditions,
    parse_decision,
    referenced_attributes,
    validate_expr,
)


class TestAcceptedExpressions:
    @pytest.mark.parametrize(
        "expr",
        [
            "profile.owns_cultivable_land == true",
            "profile.age >= 60",
            "profile.annual_income < 200000",
            "profile.age >= 60 and profile.annual_income < 200000",
            "profile.age >= 60 or profile.is_disabled == true",
            "not profile.is_government_employee",
            'profile.category in ["sc", "st", "obc"]',
            'profile.state not in ["goa"]',
            "profile.land_area_hectares <= 2.0",
            "(profile.age >= 60 and profile.category == 'sc') or profile.age >= 80",
            "60 <= profile.age",
            "profile.paid_income_tax_last_year == false",
            "profile.household_size != 1",
        ],
    )
    def test_valid(self, expr):
        assert validate_expr(expr) == []


class TestRejectedExpressions:
    """Every one of these must be refused. This is the security boundary."""

    @pytest.mark.parametrize(
        "expr,reason",
        [
            ("__import__('os').system('rm -rf /')", "function calls"),
            ("open('/etc/passwd').read()", "function calls"),
            ("profile.age.__class__", "attribute chains"),
            ("len(profile.category) > 2", "function calls"),
            ("profile.age + 5 > 60", "arithmetic"),
            ("profile.income * 2 < 100", "arithmetic"),
            ("lambda x: x", "lambdas"),
            ("[x for x in profile.items]", "comprehensions"),
            ("profile.data[0] == 1", "subscripts"),
            ("age >= 60", "bare names"),
            ("os.getcwd() == '/'", "unknown names"),
            ("profile.age if True else 0", "conditionals"),
            ("profile.age", "bare value, not boolean"),
            ("true", "bare value, not boolean"),
            ("", "empty"),
            ("profile.age >=", "syntax error"),
            ("profile.age >= 60 and", "syntax error"),
        ],
    )
    def test_rejected(self, expr, reason):
        assert validate_expr(expr), f"should have rejected ({reason}): {expr!r}"

    def test_parse_raises_rather_than_returning_garbage(self):
        with pytest.raises(ExpressionError):
            evaluate("__import__('os')", {})

    def test_no_side_effect_is_possible(self, tmp_path):
        # If eval() were reachable, this would create a file.
        canary = tmp_path / "canary.txt"
        expr = f"open({str(canary)!r}, 'w') == 1"
        with pytest.raises(ExpressionError):
            evaluate(expr, {})
        assert not canary.exists()


class TestReferencedAttributes:
    def test_collects_all_attributes(self):
        expr = "profile.age >= 60 and profile.annual_income < 200000"
        assert referenced_attributes(expr) == ["age", "annual_income"]

    def test_deduplicates(self):
        expr = "profile.age >= 60 and profile.age < 80"
        assert referenced_attributes(expr) == ["age"]


class TestEvaluation:
    def test_true(self):
        value, missing = evaluate("profile.age >= 60", {"age": 65})
        assert value is True and missing == []

    def test_false(self):
        value, _ = evaluate("profile.age >= 60", {"age": 40})
        assert value is False

    def test_yaml_booleans(self):
        value, _ = evaluate(
            "profile.owns_cultivable_land == true", {"owns_cultivable_land": True}
        )
        assert value is True

    def test_membership(self):
        value, _ = evaluate('profile.category in ["sc", "st"]', {"category": "st"})
        assert value is True

    def test_boundary_inclusive(self):
        # "up to 2 hectares" is inclusive -- the classic Gate 5 error.
        assert evaluate("profile.land <= 2", {"land": 2})[0] is True
        assert evaluate("profile.land < 2", {"land": 2})[0] is False

    def test_chained_comparison(self):
        assert evaluate("60 <= profile.age", {"age": 60})[0] is True


class TestThreeValuedLogic:
    """Missing information must never masquerade as a denial."""

    def test_missing_attribute_is_unknown_not_false(self):
        value, missing = evaluate("profile.age >= 60", {})
        assert value is UNKNOWN
        assert missing == ["age"]

    def test_explicit_none_is_also_unknown(self):
        value, missing = evaluate("profile.age >= 60", {"age": None})
        assert value is UNKNOWN
        assert missing == ["age"]

    def test_unknown_and_false_is_false(self):
        # We do not need the missing answer: one leg already fails.
        value, _ = evaluate(
            "profile.age >= 60 and profile.income < 100", {"income": 500}
        )
        assert value is False

    def test_unknown_and_true_is_unknown(self):
        value, missing = evaluate(
            "profile.age >= 60 and profile.income < 100", {"income": 50}
        )
        assert value is UNKNOWN
        assert missing == ["age"]

    def test_unknown_or_true_is_true(self):
        value, _ = evaluate(
            "profile.age >= 60 or profile.is_disabled == true", {"is_disabled": True}
        )
        assert value is True

    def test_unknown_or_false_is_unknown(self):
        value, _ = evaluate(
            "profile.age >= 60 or profile.is_disabled == true", {"is_disabled": False}
        )
        assert value is UNKNOWN

    def test_not_unknown_is_unknown(self):
        assert evaluate("not profile.is_government_employee", {})[0] is UNKNOWN

    def test_type_mismatch_is_unknown_not_false(self):
        # Profile holds a string where a number belongs: we do not know, and
        # must not deny.
        value, _ = evaluate("profile.age >= 60", {"age": "sixty"})
        assert value is UNKNOWN

    def test_unknown_raises_if_used_as_a_bool(self):
        value, _ = evaluate("profile.age >= 60", {})
        with pytest.raises(TypeError):
            bool(value)


PM_KISAN = [
    {"id": "landholding", "expr": "profile.owns_cultivable_land == true",
     "clause": "landholding-basic", "asks": "Do you own cultivable farmland?"},
    {"id": "not_taxpayer", "expr": "profile.paid_income_tax_last_year == false",
     "clause": "exclusion-income-tax", "asks": "Did you pay income tax last year?"},
]


class TestDecisions:
    def test_all_satisfied_is_eligible(self):
        decision = evaluate_conditions(
            PM_KISAN,
            {"owns_cultivable_land": True, "paid_income_tax_last_year": False},
        )
        assert decision.verdict is Verdict.ELIGIBLE

    def test_one_failure_is_not_eligible(self):
        decision = evaluate_conditions(
            PM_KISAN,
            {"owns_cultivable_land": True, "paid_income_tax_last_year": True},
        )
        assert decision.verdict is Verdict.NOT_ELIGIBLE
        assert [r.id for r in decision.failed_conditions] == ["not_taxpayer"]

    def test_missing_attribute_is_insufficient_info(self):
        decision = evaluate_conditions(PM_KISAN, {"owns_cultivable_land": True})
        assert decision.verdict is Verdict.INSUFFICIENT_INFO
        assert decision.missing_attributes == ["paid_income_tax_last_year"]

    def test_insufficient_info_surfaces_the_question_to_ask(self):
        decision = evaluate_conditions(PM_KISAN, {"owns_cultivable_land": True})
        assert decision.next_questions == ["Did you pay income tax last year?"]

    def test_definite_failure_beats_missing_info(self):
        # We know they pay income tax, so we can answer without asking about land.
        decision = evaluate_conditions(PM_KISAN, {"paid_income_tax_last_year": True})
        assert decision.verdict is Verdict.NOT_ELIGIBLE

    def test_empty_profile_is_insufficient_info(self):
        assert evaluate_conditions(PM_KISAN, {}).verdict is Verdict.INSUFFICIENT_INFO

    def test_any_mode(self):
        decision = evaluate_conditions(
            PM_KISAN,
            {"owns_cultivable_land": True, "paid_income_tax_last_year": True},
            decision="ANY(conditions)",
        )
        assert decision.verdict is Verdict.ELIGIBLE

    def test_failed_condition_carries_its_clause(self):
        decision = evaluate_conditions(
            PM_KISAN,
            {"owns_cultivable_land": True, "paid_income_tax_last_year": True},
        )
        assert decision.failed_conditions[0].clause == "exclusion-income-tax"


class TestDecisionParsing:
    @pytest.mark.parametrize("text", ["ALL(conditions)", "ANY( conditions )", "all(conditions)"])
    def test_valid(self, text):
        assert parse_decision(text) in {"ALL", "ANY"}

    @pytest.mark.parametrize("text", ["MOST(conditions)", "ALL(clauses)", "", "ALL"])
    def test_invalid(self, text):
        with pytest.raises(ExpressionError):
            parse_decision(text)
