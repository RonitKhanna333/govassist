# PMFME rule-boundary audit

Audited against the current authored conditions in
`data/schemes/pmfme/scheme.md`. The rule engine uses the restricted grammar;
the table records the semantic direction a human must confirm against the
quoted clause.

| Condition | Expression | Interpretation |
|---|---|---|
| `applicant_is_individual_unit` | `applicant_type == "individual"` | Exact categorical match; no threshold. |
| `existing_micro_food_unit` | `is_existing_micro_food_processing_unit == true` | Inclusive boolean requirement: the unit must be existing/operating. |
| `unit_identified_or_verified` | `identified_in_slup_or_verified == true` | Inclusive boolean requirement: one of the stated verification paths must be true. |
| `unincorporated_and_under_ten_workers` | `is_unincorporated == true and worker_count < 10` | Boolean requirement plus an exclusive upper bound: 9 passes; 10 fails. |
| `applicant_has_ownership_right` | `has_enterprise_ownership_right == true` | Inclusive boolean requirement. |
| `applicant_age_and_education` | `age > 18 and passed_class_8 == true` | Exclusive lower age bound: 18 fails and 19 passes; education is a required boolean. |
| `one_person_per_family_only` | `family_member_already_received_assistance == false` | Negated exclusion: an already-assisted family makes the condition false. |
| `willing_to_formalize_and_contribute` | `will_formalize == true and own_contribution_percent >= 10 and will_take_bank_loan == true` | Boolean requirements plus an inclusive lower bound: exactly 10% passes. |

The wording search covered `above`, `at least`, `less than`, `minimum`,
`maximum`, and exclusion clauses. No other PMFME condition currently uses a
numeric boundary. The PMFME source says the applicant should be “above 18
years of age”, so the authored expression is deliberately `> 18`, not `>= 18`.

The automated regression cases in
`tests/api/test_pmfme_boundaries.py` cover ages 17, 18, 19, missing age, the
age citation, the worker-count boundary, the 10% boundary, and the negated
family exclusion. A human still has to perform Gate 5; tests cannot certify
that the expression matches the source sentence.
