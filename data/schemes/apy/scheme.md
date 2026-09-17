---
scheme: apy
name_en: Atal Pension Yojana
tier: 1
version: 1
effective_from: '2015-06-01'
effective_to: null
authority: Department of Financial Services, Ministry of Finance
license: GoI public document
sources:
- id: scheme-details
  pdf: source/scheme-details.pdf
  txt: source/scheme-details.txt
  url: https://jansuraksha.gov.in/Files/APY/ENGLISH/APY.pdf
  retrieved_at: '2026-09-17'
  checksum: sha256:3b7291f47c9e17dc3378745e0fb45100b3119deb699d9cf5cfc353b6390ef939
  extractor: pdfminer.six
conditions:
- id: citizen_with_savings_account
  expr: profile.is_indian_citizen == true and profile.has_savings_bank_account == true
  clause: apy-eligibility
  asks: Are you a citizen of India who has a savings bank account?
- id: age_18_to_40
  expr: profile.age >= 18 and profile.age <= 40
  clause: apy-eligibility
  asks: Is your age between 18 and 40 years?
- id: never_income_tax_payer
  expr: profile.ever_paid_income_tax == false
  clause: apy-income-tax-exclusion
  asks: Are you, or have you ever been, an income-tax payer?
decision: ALL(conditions)
---

## apy-pension-amount

```yaml
type: benefit
source: scheme-details
page: 1
tests: []
```

> (i) Central Government guaranteed minimum pension amount:
>
>      Each  subscriber  under  APY  shall  receive  a  Central  Government  guaranteed  minimum  pension  of  Rs.  1000  per
>
> month or Rs. 2000 per month or Rs. 3000 per month or Rs. 4000 per month or Rs. 5000 per month, after the age of
>
> 60 years until death;

**Plain:** Each member gets a government-guaranteed pension of Rs. 1000, 2000, 3000, 4000 or 5000 a month after turning 60, for the rest of their life.

**Aliases:** how much pension · monthly pension · 1000 to 5000 · after 60

## apy-spouse-pension

```yaml
type: benefit
source: scheme-details
page: 1
tests: []
```

> (ii) Central Government guaranteed minimum pension amount to the spouse:
>
>   After the subscriber’s demise, the spouse of the subscriber shall be entitled to receive the same pension amount
>
> as that of the subscriber until the death of the spouse;

**Plain:** After the member dies, their husband or wife gets the same pension for the rest of their life.

**Aliases:** wife pension · husband pension · spouse

## apy-nominee

```yaml
type: benefit
source: scheme-details
page: 1
tests: []
```

> (iii) Return of the pension wealth to the nominee of the subscriber:
>
>       After the demise of both,  the subscriber and the spouse, the nominee of the subscriber shall be entitled to receive
>
> the pension wealth, as accumulated till the age of  60 years  of the subscriber.

**Plain:** After both the member and their husband or wife die, the nominee gets the money saved up to when the member turned 60.

**Aliases:** nominee · family gets money · after death

## apy-eligibility

```yaml
type: eligibility
source: scheme-details
page: 2
tests:
- is_indian_citizen
- has_savings_bank_account
- age
```

> APY is open to all citizens of India who have a savings bank account. The minimum age of joining APY is 18 years and
>
> maximum age is 40 years.

**Plain:** Any Indian citizen with a savings bank account can join. You must be at least 18 and at most 40 years old to join.

**Aliases:** who can join · age limit · savings account · 18 to 40

## apy-income-tax-exclusion

```yaml
type: exclusion
source: scheme-details
page: 2
tests:
- ever_paid_income_tax
```

> From 1st October,  2022, any citizen who is or has been an income-tax payer, is not eligible to join APY.

**Plain:** Since 1 October 2022, anyone who pays income tax, or has ever paid it, cannot join.

**Aliases:** income tax · taxpayer · not allowed

## apy-contribution

```yaml
type: procedure
source: scheme-details
page: 2
tests: []
```

> The subscriber’s contributions to APY shall be made through the facility of ‘auto-debit’ of the prescribed contribution amount
>
> from the savings bank account of the subscriber in monthly, quarterly or half-yearly frequency. The subscribers are required
>
> to contribute the prescribed contribution amount from the age of joining APY till the age of 60 years.

**Plain:** Money is taken automatically from the member's savings account every month, quarter or half-year. Payments continue from joining until age 60.

**Aliases:** how to pay · monthly payment · auto debit · till 60
