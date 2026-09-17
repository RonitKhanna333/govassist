---
scheme: pmsby
name_en: Pradhan Mantri Suraksha Bima Yojana (accident insurance)
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
  url: https://jansuraksha.gov.in/Files/PMSBY/English/Rules.pdf
  retrieved_at: '2026-09-17'
  checksum: sha256:195a99298e85821bd84174c4973ad8f8be2ecf24cfb97f865799c702cae7feb5
  extractor: pdfminer.six
conditions:
- id: has_bank_account
  expr: profile.has_bank_or_post_office_account == true
  clause: pmsby-scope
  asks: Are you an individual account holder of a participating bank or Post office?
- id: age_18_to_70
  expr: profile.age >= 18 and profile.age <= 70
  clause: pmsby-eligibility
  asks: Are you aged between 18 years (completed) and 70 years?
- id: consents_to_auto_debit
  expr: profile.consents_to_auto_debit == true
  clause: pmsby-eligibility
  asks: Do you consent to join and enable auto-debit of the premium?
decision: ALL(conditions)
---

## pmsby-details

```yaml
type: definition
source: rules
page: 1
tests: []
```

> PMSBY  is  an  Accident  Insurance  Scheme  offering  accidental  death  and  disability
> cover for death or disability on account of an accident. It would be a one-year cover,
> renewable from year to year.

**Plain:** PMSBY is accident insurance. It pays if a person dies or is disabled in an accident. The cover lasts one year and can be renewed every year.

**Aliases:** accident insurance · what is pmsby · suraksha bima

## pmsby-scope

```yaml
type: eligibility
source: rules
page: 1
tests:
- has_bank_or_post_office_account
- age
```

> Scope  of  coverage:  All  individual  bank/  Post  office  account  holders  in  the  age
> group of 18 to 70 years in participating banks/ Post office will be entitled to join. In
> case of multiple bank/ Post office accounts held by an individual in one or different
> banks/ Post office, the person would be eligible to join the scheme through one bank
> /  Post  office  account  only.  Aadhar  would  be  the  primary  KYC  for  the  bank/  Post
> office account.

**Plain:** Anyone aged 18 to 70 who has a bank or Post office account in a participating bank or Post office can join. A person with several accounts can join through only one account. Aadhaar is the main identity proof for the account.

**Aliases:** who can join · bank account needed · post office account · multiple accounts

## pmsby-benefits

```yaml
type: benefit
source: rules
page: 1
tests: []
```

> Benefits: As per the following table:
>
> Table of Benefits
>
> a  Death
> b  Total and irrecoverable loss of both eyes or loss of use of
> both hands or feet or loss of sight of one eye and loss of
> use of hand or foot
>
> Sum Insured
> Rs. 2 Lakh
>
> Rs. 2 Lakh
>
> c  Total and irrecoverable loss of sight of one eye or loss of
>
> Rs. 1 Lakh
>
> use of one hand or foot

**Plain:** The insurance pays Rs. 2 lakh on death, or on total loss of both eyes, both hands or feet, or one eye and one hand or foot. It pays Rs. 1 lakh on total loss of sight of one eye, or loss of use of one hand or foot.

**Aliases:** how much money · 2 lakh · 1 lakh · claim amount · disability payment

## pmsby-premium

```yaml
type: benefit
source: rules
page: 2
tests: []
```

> Premium: Rs. 20/- per annum per member. The premium will be deducted from the
> account  holder’s  bank/  Post  office  account  through  ‘auto  debit’  facility  in  one
> instalment

**Plain:** The premium is Rs. 20 a year per member. It is taken from the bank or Post office account by auto-debit in one instalment.

**Aliases:** 20 rupees · premium cost · yearly fee · auto debit

## pmsby-eligibility

```yaml
type: eligibility
source: rules
page: 2
tests:
- age
- consents_to_auto_debit
```

> Eligibility Conditions: Individual bank/ Post office account holders of participating
> banks/  Post  office  aged  between  18  years  (completed)  and  70  years  (age  nearer
> birthday)  who  give  their  consent  to  join  /  enable  auto-debit,  as  per  the  above
> modality, will be enrolled into the scheme.

**Plain:** Account holders aged from 18 (completed) to 70 who agree to join and allow auto-debit of the premium are enrolled.

**Aliases:** eligibility · age limit · consent · auto debit permission

## pmsby-termination

```yaml
type: exclusion
source: rules
page: 2
tests: []
```

> Termination of cover: The accident cover for the member shall terminate on any of
> the following events and no benefit will be payable there under:
>
> 1) On attaining age 70 years (age nearest birthday).
>
> 2) Closure of account with the Bank/ Post office or insufficiency of balance to keep
> the insurance in force.

**Plain:** The cover ends at age 70, or if the bank or Post office account is closed or does not have enough money to pay the premium.

**Aliases:** cover stops · when does insurance end · account closed · low balance
