---
scheme: nsap
name_en: National Social Assistance Programme -- Indira Gandhi National Old Age Pension (IGNOAPS)
tier: 1
version: 1
effective_from: null
effective_to: null
authority: Ministry of Rural Development
license: GoI public document
sources:
- id: programme-guidelines
  pdf: source/programme-guidelines.pdf
  txt: source/programme-guidelines.txt
  url: http://www.esomsa.hp.gov.in/sites/default/files/NSAP.pdf
  retrieved_at: '2026-10-13'
  checksum: sha256:0c40f855361da341498b85d098bbc27d343ffd2be3cee7ab55572f660a14e7b4
  extractor: pdfminer.six
conditions:
- id: below_poverty_line
  expr: profile.household_is_bpl == true
  clause: nsap-bpl-category
  asks: Does the person belong to the Below Poverty Line (BPL) category?
- id: age_60_or_more
  expr: profile.age >= 60
  clause: ignoaps-age-and-amount
  asks: Is the person 60 years of age or above?
decision: ALL(conditions)
---

## nsap-bpl-category

```yaml
type: eligibility
source: programme-guidelines
page: 12
tests:
- household_is_bpl
```

> The assistance under the sub-schemes of NSAP are applicable for persons belonging
>
> to  Below  Poverty  Line  (BPL)  category.  The  other  eligibility  criteria  and  the  scale  of
>
> assistance under the sub-schemes of NSAP are as follows:

**Plain:** These pensions are for people from poor (Below Poverty Line) households.

**Aliases:** bpl · garib · poor family · who can get

## ignoaps-age-and-amount

```yaml
type: eligibility
source: programme-guidelines
page: 12
tests:
- age
uncertain: true
note: Source is a 2014-era copy of the NSAP guidelines hosted on a Himachal Pradesh site. The amounts
  may have been revised since, and states often add their own top-up. Confirm current amounts at the block
  or panchayat.
```

> Indira  Gandhi  National  Old  Age  Pension  Scheme  (IGNOAPS):  The
>
> eligible  age  for  IGNOAPS  is  60  years.  The  pension  is  Rs.200  p.m.  for
>
> persons  between  60  years  and  79  years.  For  persons  who  are  80  years  and
>
> above the pension is Rs.500/- per month.

**Plain:** The old-age pension is for people aged 60 or more. This document says the central pension is Rs. 200 a month from 60 to 79 years, and Rs. 500 a month from 80 years.

**Aliases:** old age pension · budhapa pension · 60 years · how much pension

## nsap-not-left-out-of-bpl-list

```yaml
type: eligibility
source: programme-guidelines
page: 16
tests: []
```

> However  if  an  eligible
>
> person’s name does not figure in the BPL list, he/she should not be left out. Following the
>
> directions  of  the  Hon’ble  Supreme  Court  of  India  in  W.P  no.  196  of  2001,  the  deserving
>
> person's eligibility should be established and included in the select list.

**Plain:** Even if a person's name is not on the BPL list, they should not be left out. Their eligibility should be checked and they should be added.

**Aliases:** not on bpl list · name missing · left out

## nsap-gram-panchayat-identifies

```yaml
type: procedure
source: programme-guidelines
page: 16
tests: []
```

> For the identification of new beneficiaries, Gram Panchayats / Municipalities should
>
> be  given  the  central  role.  Elected  heads  and  representatives  should  be  sensitized  on  the
>
> criteria and processes of NSAP.  Based on the available BPL list, the beneficiaries should
>
> be  proactively  identified  by  reaching  out  to  their  households.

**Plain:** The Gram Panchayat or Municipality plays the central role in finding new beneficiaries, using the BPL list, and should reach out to households.

**Aliases:** panchayat · where to apply · sarpanch

## nsap-application-form

```yaml
type: procedure
source: programme-guidelines
page: 16
tests: []
```

> Applications  are  needed  for  enrollment  of  a  new  beneficiary.  A  specimen  form  is
>
> given  as  Annexe  III.  The  States  may  prepare  a  simple  format  in  the  local  language  and
>
> make the application forms available widely, free of cost.

**Plain:** An application is needed to join. States should make simple application forms in the local language available free of cost.

**Aliases:** application form · free form · how to apply

## nsap-help-with-documents

```yaml
type: procedure
source: programme-guidelines
page: 10
tests: []
```

> This  would  include  providing  support  to  the  eligible  people  in  obtaining  their
>
> documents to establish their eligibility. States may device methods for certification by local
>
> governments, if documents are not available with the eligible persons.

**Plain:** Eligible people should be helped to get the documents they need. If they don't have documents, the local government can certify them.

**Aliases:** documents · no papers · certificate
