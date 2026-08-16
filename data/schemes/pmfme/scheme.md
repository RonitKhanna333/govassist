---
scheme: pmfme
name_en: PM Formalisation of Micro Food Processing Enterprises Scheme
tier: 1
version: 1
effective_from: null
effective_to: null
authority: Ministry of Food Processing Industries
license: GoI public document
sources:
- id: scheme-guidelines
  pdf: source/scheme-guidelines.pdf
  txt: source/scheme-guidelines.txt
  url: https://pmfme.mofpi.gov.in/newsletters/docs/SchemeGuidelines.pdf
  retrieved_at: '2026-08-05'
  checksum: sha256:632c359d08289866abb104c642b0efb1bf9e007baf06b651a13fd0de47f90ce8
  extractor: pdfminer.six
conditions:
- id: applicant_is_individual_unit
  expr: profile.applicant_type == "individual"
  clause: individual-capital-subsidy
  asks: Are you applying as an individual micro food processing unit?
- id: existing_micro_food_unit
  expr: profile.is_existing_micro_food_processing_unit == true
  clause: individual-existing-unit
  asks: Is your food processing unit already operating?
- id: unit_identified_or_verified
  expr: profile.identified_in_slup_or_verified == true
  clause: individual-identified-or-verified
  asks: Has your unit been identified in the SLUP for an ODOP product or verified by the Resource Person?
- id: unincorporated_and_under_ten_workers
  expr: profile.is_unincorporated == true and profile.worker_count < 10
  clause: individual-unincorporated-under-ten-workers
  asks: Is the enterprise unincorporated, and does it employ fewer than 10 workers?
- id: applicant_has_ownership_right
  expr: profile.has_enterprise_ownership_right == true
  clause: individual-ownership-right
  asks: Do you have ownership rights over the enterprise?
- id: applicant_age_and_education
  expr: profile.age >= 18 and profile.passed_class_8 == true
  clause: individual-age-and-education
  asks: Are you at least 18 years old and at least VIII standard pass?
- id: one_person_per_family_only
  expr: profile.family_member_already_received_assistance == false
  clause: individual-one-person-per-family
  asks: Has anyone else in your family already received this financial assistance?
- id: willing_to_formalize_and_contribute
  expr: profile.will_formalize == true and profile.own_contribution_percent >= 10 and profile.will_take_bank_loan
    == true
  clause: individual-formalize-contribute-and-borrow
  asks: Are you willing to formalize the unit, contribute at least 10% of the project cost, and take a
    bank loan?
decision: ALL(conditions)
---

## scheme-purpose

```yaml
type: definition
source: scheme-guidelines
page: 4
tests: []
```

> 1.2.1  The scheme aims to:
>
> i)  Enhance  the  competitiveness  of  existing  individual  micro-enterprises  in  the
> industry  and  promote
>
> food  processing
>
> the
>
> unorganized  segment  of
> formalization of the sector; and

**Plain:** One purpose of the scheme is to improve existing individual micro food processing enterprises and help formalize them.

**Aliases:** purpose of scheme · what is pmfme for · why was this scheme made · scheme objective

## individual-capital-subsidy

```yaml
type: benefit
source: scheme-guidelines
page: 7
tests:
- applicant_type
- own_contribution_percent
```

> Individual  micro  food  processing  units  would  be  provided  credit-linked  capital
> subsidy @35% of the eligible project cost with a maximum ceiling of Rs.10.0 lakh
> per  unit.  Beneficiary  contribution  should  be minimum  of  10%  of  the  project  cost
> with balance being loan from Bank.

**Plain:** An individual micro food processing unit can get a 35% credit-linked capital subsidy, capped at Rs.10 lakh. The beneficiary must put in at least 10% of the project cost and finance the rest through a bank loan.

**Aliases:** 35 percent subsidy · 10 lakh max subsidy · capital subsidy for unit · bank loan with subsidy

## individual-existing-unit

```yaml
type: eligibility
source: scheme-guidelines
page: 7
tests:
- is_existing_micro_food_processing_unit
```

> i)  Existing micro food processing units in operations;

**Plain:** The individual-unit support is for micro food processing units that are already operating.

**Aliases:** existing running unit · already in operation · currently running food unit · old unit not new

## individual-identified-or-verified

```yaml
type: eligibility
source: scheme-guidelines
page: 7
tests:
- identified_in_slup_or_verified
```

> ii)  Existing  units  should  be  those  identified  in  the  SLUP  for  ODOP
> products or by the Resource Person on physical verification. In case
> of units using electrical power, electricity bill would support it being in
> operations. For others units, existing operations, inventory, machines
> and sales would form the basis;

**Plain:** The unit should be identified in the SLUP for an ODOP product or verified in the field by the Resource Person. Operational proof can come from the electricity bill or from evidence such as inventory, machines, and sales.

**Aliases:** verified by resource person · slup listed unit · odop unit verified · proof that unit is running

## individual-unincorporated-under-ten-workers

```yaml
type: eligibility
source: scheme-guidelines
page: 7
tests:
- is_unincorporated
- worker_count
```

> iii)  The  enterprise  should  be  unincorporated  and  should  employ  less
>
> than 10 workers;

**Plain:** The enterprise must be unincorporated and have fewer than 10 workers.

**Aliases:** less than 10 workers · small unincorporated unit · no company structure · tiny unit staff count

## individual-ownership-right

```yaml
type: eligibility
source: scheme-guidelines
page: 7
tests:
- has_enterprise_ownership_right
```

> v)  The applicant should have ownership right of the enterprise;

**Plain:** The applicant must hold ownership rights over the enterprise.

**Aliases:** i own the unit · ownership rights of enterprise · unit belongs to me · enterprise ownership

## individual-age-and-education

```yaml
type: eligibility
source: scheme-guidelines
page: 7
tests:
- age
- passed_class_8
```

> vii) The applicant should be above 18 years of age and should possess
>
> at least VIII standard pass educational qualification;

**Plain:** The applicant must be older than 18 and have passed at least class VIII.

**Aliases:** above 18 years · eighth pass required · minimum education viii pass · age and qualification

## individual-one-person-per-family

```yaml
type: exclusion
source: scheme-guidelines
page: 7
tests:
- family_member_already_received_assistance
```

> viii)  Only  one  person  from  one  family  would  be  eligible  for  obtaining
> financial assistance. The “family” for this purpose would include self,
> spouse and children;

**Plain:** Only one person in a family can get assistance. For this rule, family includes the applicant, spouse, and children.

**Aliases:** one person per family · spouse already got benefit · family member already applied · same family second application

## individual-formalize-contribute-and-borrow

```yaml
type: eligibility
source: scheme-guidelines
page: 7
tests:
- will_formalize
- own_contribution_percent
- will_take_bank_loan
```

> ix)  Willingness to formalize and contribute10% of project cost and obtain
>
> Bank loan;

**Plain:** The applicant must be willing to formalize the unit, contribute 10% of the project cost, and take a bank loan.

**Aliases:** ready to formalize · can put 10 percent · willing to take bank loan · own contribution for project

## fpo-grant-support

```yaml
type: benefit
source: scheme-guidelines
page: 8
tests: []
```

> i)  Grant @35% with credit linkage;
>
> ii)  Training support;

**Plain:** FPOs and producer cooperatives can receive a 35% credit-linked grant along with training support.

**Aliases:** fpo support · producer cooperative grant · 35 percent grant for fpo · training for cooperative

## fpo-turnover-minimum

```yaml
type: eligibility
source: scheme-guidelines
page: 8
tests:
- turnover_rs
```

> ii)  It should have minimum turnover of Rs.1 crore;

**Plain:** An FPO or cooperative must have at least Rs.1 crore in turnover.

**Aliases:** 1 crore turnover · minimum turnover for fpo · cooperative turnover requirement · sales threshold

## fpo-experience-minimum

```yaml
type: eligibility
source: scheme-guidelines
page: 8
tests:
- years_experience
```

> iv)  The members should have sufficient knowledge and experience in dealing with
>
> the product for a minimum period of 3 years.

**Plain:** The members should have at least 3 years of knowledge and experience with the product.

**Aliases:** 3 years experience · members know the product · minimum experience for fpo · product handling experience

## shg-seed-capital

```yaml
type: benefit
source: scheme-guidelines
page: 9
tests: []
```

> i)  Seed capital @ Rs40,000/- per member of SHG for working capital and purchase
>
> of small tools would be provided under the scheme;

**Plain:** SHGs can get seed capital of Rs.40,000 per member for working capital and small tools.

**Aliases:** 40000 per shg member · seed capital for shg · money for small tools · working capital support

## shg-processing-members-only

```yaml
type: eligibility
source: scheme-guidelines
page: 9
tests:
- is_currently_processing_food
```

> i)  Only SHG members that are presently engaged in food processing would be
>
> eligible;

**Plain:** Only SHG members who are already engaged in food processing can receive this seed-capital support.

**Aliases:** only active food processing members · shg member already processing · currently engaged in processing · seed capital eligibility

## shg-individual-member-grant

```yaml
type: benefit
source: scheme-guidelines
page: 9
tests: []
```

> 5.3.3  Support to individual SHG member as a single unit of food processing industry
>
> with credit linked grant @35% with maximum amount being Rs 10 lakh.

**Plain:** An individual SHG member applying as a single food processing unit can get a 35% credit-linked grant, up to Rs.10 lakh.

**Aliases:** shg member single unit grant · 10 lakh for shg member · 35 percent credit linked grant · individual shg unit

## shg-own-funds-and-margin-money

```yaml
type: eligibility
source: scheme-guidelines
page: 9
tests:
- own_contribution_percent
- working_capital_margin_percent
```

> i)  The  SHGs  should  have  sufficient  own  funds for  meeting  10%  of  the  project
> cost  and  20%  margin  money  for  working  capital or  sanction  of  the  same  as
> grant from the State Government;

**Plain:** For the credit-linked SHG capital-investment route, the SHG should have enough funds for 10% of the project cost and 20% margin money for working capital, unless the State Government has sanctioned that as a grant.

**Aliases:** 10 percent own funds · 20 percent working capital margin · shg margin money · own contribution for shg

## shg-odop-experience

```yaml
type: eligibility
source: scheme-guidelines
page: 9
tests:
- years_experience
```

> ii)  The SHG members should have for a minimum period of 3 years’ experience
>
> in processing of the ODOP product.

**Plain:** SHG members should have at least 3 years of experience processing the ODOP product.

**Aliases:** 3 years odop experience · shg product experience · odop processing background · experience in odop product

## common-infrastructure-grant

```yaml
type: benefit
source: scheme-guidelines
page: 10
tests: []
```

> chain, etc. Credit linked grant would be available @ 35%. Maximum limit of grant
> in such cases would be as prescribed.

**Plain:** Common-infrastructure proposals can receive a 35% credit-linked grant, subject to the prescribed maximum.

**Aliases:** common infrastructure grant · 35 percent for infrastructure · shared facility grant · cluster infrastructure support

## common-infrastructure-hiring-basis

```yaml
type: procedure
source: scheme-guidelines
page: 10
tests: []
```

> Common  infrastructure  created  under the  scheme  should  also  be  available  for  other  units
> and public to utilize on hiring basis for substantial part of the capacity.

**Plain:** Shared infrastructure created under the scheme should be available for other units and the public to use on a hire basis for much of its capacity.

**Aliases:** shared facility on hire · public can use infrastructure · common facility available to others · hiring basis

## branding-support-limit

```yaml
type: benefit
source: scheme-guidelines
page: 11
tests: []
```

> Support  for
> branding and marketing would be limited to 50% of the total expenditure. Maximum
> limit of grant in such cases would be as prescribed. No support would be provided
> for opening retail outlets under the scheme.

**Plain:** Branding and marketing support can cover up to 50% of total expenditure. The scheme does not support opening retail outlets.

**Aliases:** 50 percent branding support · marketing grant limit · no retail outlet support · packaging and branding assistance

## branding-turnover-minimum

```yaml
type: eligibility
source: scheme-guidelines
page: 12
tests:
- turnover_rs
```

> ii)  Minimum turnover of product to be eligible for assistance should be Rs 5
>
> crore;

**Plain:** Branding and marketing assistance requires the product to have a minimum turnover of Rs.5 crore.

**Aliases:** 5 crore turnover · branding assistance turnover · product turnover threshold · marketing support eligibility

## branding-applicant-types

```yaml
type: eligibility
source: scheme-guidelines
page: 12
tests:
- applicant_type
```

> iv)  Applicant should be an FPO/SHG/cooperative/ regional - State levels SPV to
>
> bring large number of producers together;

**Plain:** The applicant for branding support should be an FPO, SHG, cooperative, or a regional or state-level SPV that can bring together many producers.

**Aliases:** who can apply for branding · spv for branding support · group applicant only · producer collective branding

## loan-documents-required

```yaml
type: document
source: scheme-guidelines
page: 29
tests: []
```

> to the banks along with all the requisite documents required for loan applications
> such  as  lease/ownership  documents  of  land  for  setting  up  the  unit/machinery,
> registration and necessary Government clearances, etc.

**Plain:** Loan applications should include the required documents, such as land lease or ownership documents for setting up the unit or machinery, registration papers, and required government clearances.

**Aliases:** what documents for loan · land papers for unit · registration and clearances · papers needed for bank

## grant-adjustment-after-three-years

```yaml
type: procedure
source: scheme-guidelines
page: 29
tests: []
```

> If after a period of three years from the disbursement of last tranche of the loan,
> the  beneficiary  account  is  still  standard,  and  the  unit  is  operational,  this  grant
> amount would be adjusted in the bank account of the beneficiary. If the account
> becomes NPA prior to three years from the date of disbursement of the loan, the
> grant  amount  would  be  adjusted  by  the  Bank  towards  repayment  by  the
> beneficiary.

**Plain:** If the loan account stays standard for three years and the unit is operational, the grant is adjusted in the beneficiary’s bank account. If the account becomes NPA before three years, the bank adjusts the grant toward repayment.

**Aliases:** grant adjusted after 3 years · npa before three years · subsidy adjustment in bank account · mirror account adjustment
