---
scheme: pm-kisan
name_en: Pradhan Mantri Kisan Samman Nidhi (PM-KISAN)
tier: 1
version: 1
effective_from: null
effective_to: null
authority: Department of Agriculture, Cooperation & Farmers’ Welfare (DAC&FW)
license: GoI public document
sources:
- id: operational-guidelines
  pdf: source/operational-guidelines.pdf
  txt: source/operational-guidelines.txt
  url: https://pmkisan.gov.in/Documents/RevisedPM-KISANOperationalGuidelines(English).pdf
  retrieved_at: '2026-11-25'
  checksum: sha256:ae82cac83f61a5fa5049387a7c13e00c6d55cef0e9163deb5497dc86c86d697f
conditions:
- id: landholding_farmer_family
  expr: profile.owns_cultivable_land == true
  clause: pmkisan-farmer-family
  asks: Does your family own cultivable land as per the land records?
- id: not_institutional_land
  expr: profile.is_institutional_landholder == false
  clause: pmkisan-exclusion-institutional
  asks: Is the land held by an institution rather than a person?
- id: not_constitutional_post
  expr: profile.holds_or_held_public_office == false
  clause: pmkisan-exclusion-constitutional
  asks: Does anyone in your family hold, or did they ever hold, a constitutional post, or serve as a Minister, MP, MLA, Mayor or District Panchayat Chairperson?
- id: not_elected_office
  expr: profile.holds_or_held_public_office == false
  clause: pmkisan-exclusion-ministers
  asks: Does anyone in your family hold, or did they ever hold, a constitutional post, or serve as a Minister, MP, MLA, Mayor or District Panchayat Chairperson?
- id: not_government_employee
  expr: profile.is_government_employee == false
  clause: pmkisan-exclusion-government-employees
  asks: Is anyone in your family a serving or retired Central/State Government, PSE or Local Body employee (other than Multi Tasking Staff / Class IV / Group D)?
- id: not_income_tax_payer
  expr: profile.paid_income_tax_last_year == false
  clause: pmkisan-exclusion-income-tax
  asks: Did anyone in your family pay Income Tax in the last assessment year?
- id: not_practising_professional
  expr: profile.is_practising_professional == false
  clause: pmkisan-exclusion-professionals
  asks: Is anyone in your family a registered, practising Doctor, Engineer, Lawyer, Chartered Accountant or Architect?
decision: ALL(conditions)
---

## pmkisan-scheme

```yaml
type: eligibility
source: operational-guidelines
page: 2
tests: [owns_cultivable_land]
```

> With a view to provide income support to all landholding farmers’ families in the country,
> having  cultivable  land,  the  Central  Government  has  implemented  a  Central  Sector
> Scheme, namely, “Pradhan Mantri Kisan Samman Nidhi (PM-KISAN)”.

**Plain:** PM-KISAN gives income support to farmer families across the country that own cultivable land.

**Aliases:** kisan samman nidhi · farmer income support · पीएम किसान · किसान सम्मान निधि · who gets pm kisan

## pmkisan-farmer-family

```yaml
type: definition
source: operational-guidelines
page: 2
tests: [owns_cultivable_land]
```

> A landholder farmer’s family is defined as “a family comprising of husband, wife
> and  minor  children  who  owns  cultivable  land  as  per  land  records  of  the  concerned
> State/UT”.

**Plain:** A farmer family means a husband, wife and their minor children who own cultivable land in the state's land records.

**Aliases:** farmer family meaning · land in our name · हमारे नाम ज़मीन है · khet hamare naam · land records

## pmkisan-benefit

```yaml
type: benefit
source: operational-guidelines
page: 10
tests: []
```

> 10.1  The  financial  benefit  of  Rs.6000/-  per  year  is  to  be  released  to  the  eligible
> farmers in three installments of Rs.2000/- each every 4-month / trimester, i.e. April-July,
> August-November and December-March.

**Plain:** Eligible farmers get Rs. 6000 a year, paid as three instalments of Rs. 2000, one every four months.

**Aliases:** how much money · 6000 per year · 2000 kist · कितना पैसा मिलेगा · installment dates

## pmkisan-exclusion-institutional

```yaml
type: exclusion
source: operational-guidelines
page: 2
tests: [is_institutional_landholder]
```

> All Institutional Land holders; and

**Plain:** Land held by institutions does not qualify.

**Aliases:** trust land · company land · institution owns land · संस्था की ज़मीन

## pmkisan-exclusion-constitutional

```yaml
type: exclusion
source: operational-guidelines
page: 2
tests: [holds_or_held_public_office]
```

> i)  Former and present holders of constitutional posts

**Plain:** A family is excluded if any member holds, or once held, a constitutional post.

**Aliases:** constitutional post · governor · judge · संवैधानिक पद

## pmkisan-exclusion-ministers

```yaml
type: exclusion
source: operational-guidelines
page: 2
tests: [holds_or_held_public_office]
```

> ii)  Former and present Ministers / State Ministers and former / present  Members of
> Lok  Sabha  /  Rajya  Sabha  /  State  Legislative  Assemblies  /  State  Legislative
> Councils,  former  and  present  Mayors  of  Municipal  Corporations,  former  and
> present Chairpersons of District Panchayats.

**Plain:** A family is excluded if any member is or was a minister, MP, MLA or MLC, mayor of a municipal corporation, or chairperson of a district panchayat.

**Aliases:** mp mla in family · minister · mayor · zila panchayat adhyaksh · विधायक सांसद

## pmkisan-exclusion-government-employees

```yaml
type: exclusion
source: operational-guidelines
page: 2
tests: [is_government_employee]
```

> iii)  All  serving  or  retired  officers  and  employees  of  Central  /  State  Government
> Ministries / Offices / Departments and their field units, Central or State PSEs and
> Attached offices / Autonomous Institutions under Government as well as regular

**Plain:** A family is excluded if any member is a serving or retired officer or employee of the Central or State Government, a PSE or a government autonomous institution.

**Aliases:** sarkari naukri · government job · retired employee · सरकारी कर्मचारी · psu employee

## pmkisan-exclusion-group-d-exception

```yaml
type: definition
source: operational-guidelines
page: 3
tests: [is_government_employee]
```

> employees of the Local Bodies (Excluding Multi Tasking Staff / Class IV / Group
> D employees)

**Plain:** Regular employees of local bodies are also excluded, but Multi Tasking Staff and Class IV / Group D employees are not.

**Aliases:** group d · class 4 · peon · चपरासी · mts staff

## pmkisan-exclusion-income-tax

```yaml
type: exclusion
source: operational-guidelines
page: 3
tests: [paid_income_tax_last_year]
```

> v)  All Persons who paid Income Tax in last assessment year.

**Plain:** A family is excluded if any member paid income tax in the last assessment year.

**Aliases:** income tax · itr bhara · टैक्स भरा · we pay tax

## pmkisan-exclusion-professionals

```yaml
type: exclusion
source: operational-guidelines
page: 3
tests: [is_practising_professional]
```

> vi)  Professionals  like  Doctors,  Engineers,  Lawyers,  Chartered  Accountants,  and
> Architects  registered  with  Professional  bodies  and  carrying  out  profession  by
> undertaking practices.

**Plain:** A family is excluded if any member is a registered, practising doctor, engineer, lawyer, chartered accountant or architect.

**Aliases:** doctor in family · lawyer · ca · engineer · डॉक्टर वकील

## pmkisan-documents

```yaml
type: document
source: operational-guidelines
page: 8
tests: []
```

> State,  District,  Sub-District/Block,  Village,  Farmer  Name,  Type  of  Identity  –
> Aadhaar Number and in case Aadhaar not available, Aadhaar enrollment number
> with  any  other  ID  proof  like  Voter  ID  etc,  Gender,  Category,  IFSC  Code,  Bank
> Account Number.

**Plain:** Registration needs your location, name, Aadhaar number (or Aadhaar enrolment number with another ID such as a Voter ID), gender, category, and bank IFSC code and account number.

**Aliases:** documents needed · aadhaar · bank passbook · kaagaz · ज़रूरी काग़ज़
