---
scheme: demo-scheme
name_en: Demo Welfare Scheme
tier: 1
version: 1
effective_from: '2024-04-01'
effective_to: null
authority: Department of Demonstration Affairs
license: Fixture -- not a real scheme
sources:
- id: guidelines-demo
  pdf: source/guidelines-demo.pdf
  txt: source/guidelines-demo.txt
  url: https://example.invalid/guidelines-demo.pdf
  retrieved_at: '2026-08-06'
  checksum: sha256:0000000000000000000000000000000000000000000000000000000000000000
conditions:
- id: landholding
  expr: profile.owns_cultivable_land == true
  clause: landholding-basic
  asks: Do you or your family own cultivable farmland?
- id: adult
  expr: profile.age >= 18
  clause: age-minimum
  asks: How old are you?
- id: not_income_tax_payer
  expr: profile.paid_income_tax_last_year == false
  clause: exclusion-income-tax
  asks: Did you or anyone in your family pay income tax last year?
- id: not_government_employee
  expr: profile.is_government_employee == false
  clause: exclusion-government-employee
  asks: Are you a serving or retired government employee?
decision: ALL(conditions)
---

## landholding-basic

```yaml
type: eligibility
source: guidelines-demo
page: 1
tests:
- owns_cultivable_land
```

> All landholding farmers' families, which have cultivable landholding
> in their names, shall be eligible to receive benefit under the scheme.

**Plain:** You qualify if you or your family own farmland that can be cultivated.

**Aliases:** we own farm land · i have some acres · my family farms our own land · ਸਾਡੀ ਆਪਣੀ ਜ਼ਮੀਨ ਹੈ · मेरे पास खेती की ज़मीन है

## age-minimum

```yaml
type: eligibility
source: guidelines-demo
page: 1
tests:
- age
```

> The applicant shall have attained the age of eighteen years as on the
> first day of the financial year in which the application is made.

**Plain:** You must be at least eighteen years old at the start of the financial year you apply in.

**Aliases:** i am 17 · am i old enough · minimum age to apply

## benefit-amount

```yaml
type: benefit
source: guidelines-demo
page: 1
tests: []
```

> The benefit of Rs. 6000 per year shall be transferred in three equal
> instalments of Rs. 2000 each, directly to the bank account of the
> beneficiary.

**Plain:** The scheme pays Rs. 6000 a year, sent to your bank account in three instalments of Rs. 2000.

**Aliases:** how much money will i get · kitna paisa milega · payment amount

## exclusion-income-tax

```yaml
type: exclusion
source: guidelines-demo
page: 1
tests:
- paid_income_tax_last_year
```

> All Institutional Land holders and farmer families in which one or
> more of its members paid Income Tax in last assessment year are excluded
> from the benefit under the scheme.

**Plain:** You are not eligible if you, or anyone in your family, paid income tax last year. Land held by institutions is also excluded.

**Aliases:** i pay income tax · we filed ITR last year · मैंने टैक्स भरा था · ਅਸੀਂ ਟੈਕਸ ਭਰਿਆ ਸੀ

## exclusion-government-employee

```yaml
type: exclusion
source: guidelines-demo
page: 1
tests:
- is_government_employee
```

> Serving or retired officers and employees of Central or State
> Government Ministries, Offices and Departments are excluded from the
> benefit under the scheme.

**Plain:** You are not eligible if you work, or used to work, for a central or state government department.

**Aliases:** i work for the government · sarkari naukri · retired from government service

## documents-required

```yaml
type: document
source: guidelines-demo
page: 1
tests: []
```

> The applicant shall furnish proof of landholding, a valid identity
> document, and bank account details at the time of registration.

**Plain:** You need proof that you own land, an identity document, and your bank account details.

**Aliases:** what papers do i need · documents to apply · kya kagaz chahiye
