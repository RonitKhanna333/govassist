---
scheme: pmuy
name_en: Pradhan Mantri Ujjwala Yojana (free LPG connection)
tier: 1
version: 1
effective_from: null
effective_to: null
authority: Ministry of Petroleum and Natural Gas
license: GoI public document
sources:
- id: kyc-form
  pdf: source/kyc-form.pdf
  txt: source/kyc-form.txt
  url: https://www.pmuy.gov.in/documents/Ujjwala-KYC_englishnew.pdf
  retrieved_at: '2026-10-13'
  checksum: sha256:e2ecac3614bacb5febbf6fe3ef190c41b4bbe0835c33dec61b7a8de95cd780ad
  extractor: pdfminer.six
conditions:
- id: adult_woman
  expr: profile.is_woman == true and profile.age >= 18
  clause: pmuy-adult-woman
  asks: Is the applicant an adult woman (18 years and above)?
- id: indian_citizen
  expr: profile.is_indian_citizen == true
  clause: pmuy-citizen
  asks: Is the applicant an Indian citizen residing in India?
- id: no_lpg_in_household
  expr: profile.household_has_lpg_or_png == false
  clause: pmuy-no-existing-connection
  asks: Does the applicant or any household member possess an LPG or Piped Natural Gas connection?
- id: gives_deprivation_declaration
  expr: profile.will_give_deprivation_declaration == true
  clause: pmuy-deprivation-declaration
  asks: Will the applicant fill in the Deprivation Declaration and consent to its verification?
decision: ALL(conditions)
---

## pmuy-adult-woman

```yaml
type: eligibility
source: kyc-form
page: 1
tests:
- is_woman
- age
uncertain: true
note: From the PMUY KYC application form (Version 8.0), not the scheme guidelines.
```

> Only Adult women (18 Yrs & above) is
> eligible to apply for PMUY Connection

**Plain:** Only women aged 18 or more can apply for the Ujjwala connection.

**Aliases:** who can apply · woman · mahila · 18 years

## pmuy-citizen

```yaml
type: eligibility
source: kyc-form
page: 2
tests:
- is_indian_citizen
uncertain: true
note: From the PMUY KYC application form (Version 8.0), not the scheme guidelines.
```

> That I am an Indian  citizen and residing in India.

**Plain:** The applicant declares she is an Indian citizen living in India.

**Aliases:** citizen · indian

## pmuy-no-existing-connection

```yaml
type: exclusion
source: kyc-form
page: 2
tests:
- household_has_lpg_or_png
uncertain: true
note: From the PMUY KYC application form (Version 8.0), not the scheme guidelines.
```

> That neither I, nor any other member of the household (household means a family consisting of all members reﬂecting in the family composition document living
> together in a dwelling unit having common kitchen),possess/possessed any LPG connection from PSU Oil Companies or Piped Natural Gas Connection for domestic use
> in our dwelling unit.  (‘Households’ having Piped Natural Gas connection are not entitled for subsidized LPG).

**Plain:** No one in the household -- the family living together and sharing one kitchen -- may already have, or have had, an LPG connection from a government oil company or a piped gas connection.

**Aliases:** already have gas · existing connection · piped gas · cylinder at home

## pmuy-deprivation-declaration

```yaml
type: procedure
source: kyc-form
page: 2
tests:
- will_give_deprivation_declaration
uncertain: true
note: The form requires this declaration but does not list its criteria; this form alone cannot say what
  counts as deprived.
```

> That I have understood and ﬁlled in the Deprivation Declaration form and give my consent for veriﬁcation (including physical veriﬁcation) of the particulars mentioned
> therein.

**Plain:** The applicant fills in a Deprivation Declaration form (about the household being poor) and agrees that the details can be checked, including at home.

**Aliases:** deprivation declaration · poverty form · garibi praman

## pmuy-free-connection

```yaml
type: benefit
source: kyc-form
page: 1
tests: []
uncertain: true
note: From the PMUY KYC application form (Version 8.0), not the scheme guidelines.
```

> Under PMUY, beneﬁciaries receive a deposit-free LPG connection that covers the security deposit of cylinder, pressure regulator, suraksha hose, Domestic Gas Consumer Card (DGCC)
> booklet, and installation charges. In addition, the ﬁrst reﬁll and stove are also provided free of cost. Beneﬁciaries are not required to make any payment for these beneﬁts.

**Plain:** Beneficiaries get an LPG connection with no deposit: the cylinder deposit, regulator, hose, gas card booklet and installation are covered. The first refill and the stove are also free. Nothing has to be paid for these.

**Aliases:** what do I get · free cylinder · free stove · free refill · no deposit

## pmuy-cylinder-choice

```yaml
type: benefit
source: kyc-form
page: 1
tests: []
uncertain: true
note: From the PMUY KYC application form (Version 8.0), not the scheme guidelines.
```

> Beneﬁciaries have the ﬂexibility to choose from a 14.2 kg single bottle connection, a 5 kg single bottle connection, or a 5 kg double bottle connection.

**Plain:** You can choose a 14.2 kg single cylinder, a 5 kg single cylinder, or two 5 kg cylinders.

**Aliases:** cylinder size · 5 kg · 14.2 kg
