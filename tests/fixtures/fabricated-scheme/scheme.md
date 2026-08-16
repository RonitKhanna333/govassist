---
scheme: fabricated-scheme
name_en: Fabricated Scheme (negative fixture)
tier: 1
version: 1
effective_from: '2024-04-01'
effective_to: null
authority: Department of Demonstration Affairs
license: Fixture -- deliberately invalid
sources:
- id: guidelines-demo
  pdf: ../demo-scheme/source/guidelines-demo.pdf
  txt: ../demo-scheme/source/guidelines-demo.txt
  url: https://example.invalid/guidelines-demo.pdf
  retrieved_at: '2026-08-06'
  checksum: sha256:0000000000000000000000000000000000000000000000000000000000000000
conditions:
- id: senior_bonus
  expr: profile.age >= 60
  clause: fabricated-senior-bonus
  asks: How old are you?
- id: dangling
  expr: profile.owns_cultivable_land == true
  clause: no-such-clause
  asks: Do you own farmland?
decision: ALL(conditions)
---

## fabricated-senior-bonus

```yaml
type: eligibility
source: guidelines-demo
page: 1
tests:
- age
```

> Farmers over the age of sixty years shall receive a double benefit of
> Rs. 12000 per year under the enhanced provisions of this scheme.

**Plain:** Farmers over sixty get twice the benefit.

**Aliases:** senior farmer extra money

## altered-benefit-amount

```yaml
type: benefit
source: guidelines-demo
page: 1
tests: []
```

> The benefit of Rs. 8000 per year shall be transferred in three equal
> instalments of Rs. 2000 each, directly to the bank account of the
> beneficiary.

**Plain:** The scheme pays Rs. 8000 a year.

**Aliases:** how much money will i get

## paraphrased-eligibility

```yaml
type: eligibility
source: guidelines-demo
page: 1
tests:
- owns_cultivable_land
```

> Farmers who own land they are able to farm are eligible for benefits
> under this scheme.

**Plain:** Landowning farmers qualify.

**Aliases:** we own farm land
