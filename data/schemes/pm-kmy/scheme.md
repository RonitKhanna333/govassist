---
scheme: pm-kmy
name_en: Pradhan Mantri Kisan Maan-Dhan Yojana (farmer pension)
tier: 1
version: 1
effective_from: '2019-08-09'
effective_to: null
authority: Department of Agriculture, Cooperation & Farmers Welfare
license: GoI public document
sources:
- id: operational-guidelines
  pdf: source/operational-guidelines.pdf
  txt: source/operational-guidelines.txt
  url: https://pmkisan.gov.in/Documents/PMKMYOperationalGuidelines.pdf
  retrieved_at: '2026-09-17'
  checksum: sha256:a60ec28b4d4344a60447efe61abbca5c45b8a291633518b353beb91aee8546ef
  extractor: pdfminer.six
conditions:
- id: small_or_marginal_farmer
  expr: profile.owns_cultivable_land == true and profile.land_hectares <= 2
  clause: pmkmy-smf-definition
  asks: Do you own cultivable land up to 2 hectare as per land records?
- id: age_18_to_40
  expr: profile.age >= 18 and profile.age <= 40
  clause: pmkmy-eligibility
  asks: Are you of the age of 18 years and above and upto the age of 40 years?
- id: not_in_other_social_security
  expr: profile.in_other_pension_or_social_security_scheme == false
  clause: pmkmy-exclusion-other-schemes
  asks: Are you covered under NPS, ESIC, EPFO, PM-SYM or PM-LVM?
- id: not_institutional_land
  expr: profile.is_institutional_landholder == false
  clause: pmkmy-exclusion-higher-status
  asks: Are you an institutional land holder?
- id: not_constitutional_or_elected
  expr: profile.holds_or_held_public_office == false
  clause: pmkmy-exclusion-higher-status
  asks: Are you a former or present holder of a constitutional post, Minister, MP, MLA, Mayor or District
    Panchayat Chairperson?
- id: not_government_employee
  expr: profile.is_government_employee == false
  clause: pmkmy-exclusion-higher-status
  asks: Are you a serving or retired officer or employee of Central/State Government, PSE or Local Body
    (other than MTS/Class IV/Group D)?
- id: not_income_tax_payer
  expr: profile.paid_income_tax_last_year == false
  clause: pmkmy-exclusion-higher-status
  asks: Did you pay Income Tax in the last assessment year?
- id: not_practising_professional
  expr: profile.is_practising_professional == false
  clause: pmkmy-exclusion-higher-status
  asks: Are you a registered practising Doctor, Engineer, Lawyer, Chartered Accountant or Architect?
decision: ALL(conditions)
---

## pmkmy-pension

```yaml
type: benefit
source: operational-guidelines
page: 1
tests: []
```

> The Pradhan Mantri Kisan Maan-Dhan Yojana (PM-KMY) provides
> for  an  assured  monthly  pension  of  Rs.  3000/-  to  all  land  holding  Small  and  Marginal
> Farmers (SMFs), whether male or female, on their attaining the age of 60 years.

**Plain:** Small and marginal farmers who own land get a pension of Rs. 3000 a month after turning 60, whether they are men or women.

**Aliases:** how much pension · 3000 per month · farmer pension · after 60

## pmkmy-smf-definition

```yaml
type: definition
source: operational-guidelines
page: 2
tests:
- owns_cultivable_land
- land_hectares
```

> “Small and Marginal Farmer” or “SMF” means a farmer who owns cultivable
>
> land upto 2 hectare as per land records of the concerned State/UT”.

**Plain:** A small or marginal farmer is one who owns farmland of up to 2 hectares, as shown in the state's land records.

**Aliases:** small farmer · 2 hectare · land limit · marginal farmer

## pmkmy-eligibility

```yaml
type: eligibility
source: operational-guidelines
page: 3
tests:
- age
```

> All Small and Marginal Farmers (SMFs) in all States and Union Territories of the country,
> who are of the age of 18 years and above and upto the age of 40 years, and who do not
> fall within the purview of the exclusion criteria as mentioned in the guidelines, are eligible
> to avail the benefits of this Scheme by joining it.

**Plain:** Small and marginal farmers aged 18 to 40, anywhere in India, can join unless they fall under the exclusions.

**Aliases:** who can join · age limit · 18 to 40

## pmkmy-exclusion-other-schemes

```yaml
type: exclusion
source: operational-guidelines
page: 3
tests:
- in_other_pension_or_social_security_scheme
```

> SMFs covered under any other statuary social security schemes such as National
> Pension  Scheme  (NPS),  Employees’  State  Insurance  Corporation  scheme,
> Employees’ Fund Organization Scheme etc.
> Farmers who have opted for Pradhan Mantri Shram Yogi Maan Dhan Yojana (PM-
> SYM) administered by the Ministry of Labour & Employment
> Farmers  who  have  opted  for  Pradhan  Mantri  Laghu  Vyapari  Maan-dhan  Yojana
> (PM-LVM) administered by the Ministry of Labour & Employment

**Plain:** Farmers already in NPS, ESIC or EPFO, or who have joined the PM-SYM or PM-LVM pension schemes, cannot join.

**Aliases:** nps · esic · epfo · other pension · pm-sym

## pmkmy-exclusion-higher-status

```yaml
type: exclusion
source: operational-guidelines
page: 3
tests:
- is_institutional_landholder
- holds_or_held_public_office
- is_government_employee
- paid_income_tax_last_year
- is_practising_professional
```

> Further, the following categories of beneficiaries of higher economic status shall
> not be eligible for benefits under the scheme:
>
> (a) All Institutional Land holders; and
> (b) Former and present holders of constitutional posts
> (c)  Former and present Ministers/ State Ministers and former/present  Members
> of Lok Sabha/ Rajya Sabha/ State Legislative Assemblies/ State Legislative
> Councils,former and present Mayors of Municipal Corporations, former and
> present Chairpersons of District Panchayats.
> (d)  All serving or retired officers and employees of Central/ State Government
> Ministries/  Offices/Departments and their field units, Central or State PSEs and
> Attached offices/ Autonomous Institutions under Government as well as regular
> employees of the Local Bodies (Excluding Multi Tasking Staff / Class IV/Group D
> employees)
> (e)  All Persons who paid Income Tax in last assessment year.
> (f) Professionals like Doctors, Engineers, Lawyers, Chartered Accountants, and
> Architects registered with Professional bodies and carrying out profession by
> undertaking practice.

**Plain:** These people cannot join: institutions that hold land; current or former holders of constitutional posts, ministers, MPs, MLAs, mayors and district panchayat chairpersons; serving or retired government and PSU employees (except Group D and similar staff); people who paid income tax last year; and practising doctors, engineers, lawyers, CAs and architects.

**Aliases:** government employee · income tax · doctor lawyer · mp mla · who cannot join

## pmkmy-contribution

```yaml
type: procedure
source: operational-guidelines
page: 5
tests: []
```

> The amount of the monthly contribution shall range between Rs.55 to Rs.200 per
> month depending upon the age of entry of the farmers into the Scheme, as per
> the following contribution chart:

**Plain:** The farmer pays between Rs. 55 and Rs. 200 a month, depending on their age when they join.

**Aliases:** how much to pay · monthly contribution · 55 to 200

## pmkmy-government-match

```yaml
type: benefit
source: operational-guidelines
page: 4
tests: []
```

> The Central Government through the Department  of Agriculture Cooperation and
> Farmers  Welfare  shall  also  contribute  an  equal  amount  as  contributed  by  the
> eligible subscriber, to the pension Fund.

**Plain:** The central government puts in the same amount as the farmer pays.

**Aliases:** government contribution · matching amount
