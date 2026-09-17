---
scheme: pmjjby
name_en: Pradhan Mantri Jeevan Jyoti Bima Yojana (life insurance)
tier: 1
version: 1
effective_from: '2022-06-01'
effective_to: null
authority: Department of Financial Services, Ministry of Finance
license: GoI public document
sources:
- id: rules
  pdf: source/rules.pdf
  txt: source/rules.txt
  url: https://jansuraksha.gov.in/Files/PMJJBY/English/Rules.pdf
  retrieved_at: '2026-09-17'
  checksum: sha256:a184cbee3339abe0483e8d10a56f71f5d9e6eda6415660844940349e3d216745
  extractor: pdfminer.six
conditions:
- id: has_bank_account
  expr: profile.has_bank_or_post_office_account == true
  clause: pmjjby-scope
  asks: Are you an individual account holder of a participating bank or Post office?
- id: age_18_to_50
  expr: profile.age >= 18 and profile.age <= 50
  clause: pmjjby-eligibility
  asks: Are you aged between 18 years (completed) and 50 years?
- id: consents_to_auto_debit
  expr: profile.consents_to_auto_debit == true
  clause: pmjjby-eligibility
  asks: Do you consent to join and enable auto-debit of the premium?
decision: ALL(conditions)
---

## pmjjby-details

```yaml
type: definition
source: rules
page: 1
tests: []
```

> PMJJBY  is  an  insurance  scheme  offering  life
> insurance cover for death due to any reason. It is a one-year cover, renewable from
> year  to  year.

**Plain:** PMJJBY is life insurance. It pays if the person dies for any reason. The cover lasts one year and can be renewed every year.

**Aliases:** life insurance · what is pmjjby · jeevan jyoti

## pmjjby-scope

```yaml
type: eligibility
source: rules
page: 1
tests:
- has_bank_or_post_office_account
- age
```

> Scope of coverage: All individual account holders of participating banks/
> Post  office  in  the  age  group  of  18  to  50  years  are  entitled  to  join.  In  case  of
> multiple  bank  /  Post  office  accounts  held  by  an  individual  in  one  or  different
> banks/  Post  office,  the  person  is  eligible  to  join  the  scheme  through  one  bank/
> Post office account only. Aadhaar is the primary KYC for the bank / Post office
> account.

**Plain:** Anyone aged 18 to 50 with an account in a participating bank or Post office can join. A person with several accounts can join through only one account. Aadhaar is the main identity proof for the account.

**Aliases:** who can join · bank account needed · post office account

## pmjjby-benefit

```yaml
type: benefit
source: rules
page: 2
tests: []
```

> Benefits: Rs.2 lakh is payable on member’s death due to any cause.

**Plain:** Rs. 2 lakh is paid when the member dies, for any reason.

**Aliases:** how much money · 2 lakh · death benefit · claim amount

## pmjjby-premium

```yaml
type: benefit
source: rules
page: 2
tests: []
```

> Premium:  Rs.436/-  per  annum  per  member.  The  premium  will  be
> deducted  from  the  account  holder’s  bank  /  Post  office  account  through  ‘auto
> debit’ facility in one instalment, as per the option given, at the time of enrolment
> under the scheme.

**Plain:** The premium is Rs. 436 a year per member, taken from the bank or Post office account by auto-debit in one instalment.

**Aliases:** 436 rupees · premium cost · yearly fee

## pmjjby-lien-period

```yaml
type: exclusion
source: rules
page: 1
tests: []
```

> For  subscribers  enrolling  for  the  first  time  on  or  after  1st  June  2021,  insurance
> cover shall not be available for death (other than due to accident) occurring during
> the first 30 days from the date of enrolment into the scheme (lien period) and in
> case  of death (other  than due to accident) during lien period, no claim would be
> admissible.

**Plain:** For people joining for the first time, death from a cause other than an accident in the first 30 days after joining is not covered.

**Aliases:** first 30 days · waiting period · lien period

## pmjjby-eligibility

```yaml
type: eligibility
source: rules
page: 2
tests:
- age
- consents_to_auto_debit
```

> Individual  bank/  Post  office  account  holders  of  the  participating  banks/  Post
> office aged between 18 years (completed) and 50 years (age nearer birthday) who
> give  their  consent  to join  /  enable  auto-debit,  as per  the above  modality,  will  be
> enrolled into the scheme.

**Plain:** Account holders aged from 18 (completed) to 50 who agree to join and allow auto-debit of the premium are enrolled.

**Aliases:** eligibility · age limit · consent

## pmjjby-termination-age

```yaml
type: exclusion
source: rules
page: 2
tests: []
```

> 1)  On attaining age 55 years (age near birth day) subject to annual renewal up
> to that date (entry, however, will not be possible beyond the age of 50 years).

**Plain:** The cover ends at age 55. A person cannot join after age 50.

**Aliases:** cover stops · age 55 · upper age
