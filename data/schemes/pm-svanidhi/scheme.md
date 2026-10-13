---
scheme: pm-svanidhi
name_en: PM Street Vendor's AtmaNirbhar Nidhi (PM SVANidhi)
tier: 1
version: 1
effective_from: null
effective_to: null
authority: Ministry of Housing and Urban Affairs
license: GoI public document
sources:
- id: scheme-guidelines
  pdf: source/scheme-guidelines.pdf
  txt: source/scheme-guidelines.txt
  url: https://www.mohua.gov.in/static/uploads/2026/01/bde957bc3a87fb001c05ddd09484edda.pdf
  retrieved_at: '2026-10-13'
  checksum: sha256:c3e73b7107ee281e8c875478604722d0fdb8234ed0f4ebd8644a79d7722c43be
  extractor: pdfminer.six
conditions:
- id: is_street_vendor
  expr: profile.is_street_vendor == true
  clause: svanidhi-street-vendor-definition
  asks: Is the applicant a 'Street Vendor' as defined in the Street Vendors Act, 2014?
- id: vends_in_covered_area
  expr: profile.vends_in_town_or_peri_urban == true
  clause: svanidhi-target-beneficiaries
  asks: Is the vendor vending in a city-region (statutory town, census town or peri-urban area)?
decision: ALL(conditions)
---

## svanidhi-target-beneficiaries

```yaml
type: eligibility
source: scheme-guidelines
page: 3
tests:
- vends_in_town_or_peri_urban
```

> The target beneficiaries of the scheme are street vendors vending in various city-regions. The
> State/  UTs  may  adopt  suitable  methodology  for  identifying  eligible  vendors  to  ensure
> comprehensive coverage.

**Plain:** The scheme is for street vendors who sell in towns and cities, including census towns and areas around cities. Each State decides how it identifies eligible vendors.

**Aliases:** who can apply · street vendor · thela · rehri · city vendor

## svanidhi-coverage

```yaml
type: definition
source: scheme-guidelines
page: 3
tests: []
```

> The scheme extends to all the States/UTs which have notified rules and schemes under Street
> Vendors (Protection of Livelihood and Regulation of Street Vending) Act,2014. Further, the
> scheme is extended to City-Region i.e., census towns, peri urban areas, etc in graded manner
> for providing scheme benefits seamlessly, so as to establish cities as “growth hubs”.

**Plain:** The scheme covers States and UTs that have made rules under the Street Vendors Act, 2014. It is also being extended step by step to census towns and areas around cities.

**Aliases:** which states · census town · peri urban

## svanidhi-street-vendor-definition

```yaml
type: definition
source: scheme-guidelines
page: 11
tests:
- is_street_vendor
```

> A ‘Street Vendor’ means a person engaged in vending of articles, good, wares, food items or merchandise of everyday use
> or offering services to the general public in a street lane, side walk, footpath, pavement, park or any other public place or
> private area from a temporary built-up structure or by moving from place to place and includes hawkers, peddler, squatter, and
> all other synonyms terms which may be local or region specific

**Plain:** A street vendor is someone who sells everyday goods, food or services to the public on a street, footpath, park or other public place, from a temporary stall or by moving around. Hawkers and pheriwalas count.

**Aliases:** what is a street vendor · hawker · pheriwala · moving cart

## svanidhi-seasonal-or-mobile

```yaml
type: eligibility
source: scheme-guidelines
page: 11
tests: []
```

> ii.  The vendor may be engaged in either seasonal or year-round vending activities.
>
> iii.  The vendor may operate as a mobile or stationary vendor.

**Plain:** Selling only in some seasons is fine, and so is moving from place to place instead of having a fixed spot.

**Aliases:** seasonal · mobile vendor · no fixed place

## svanidhi-certificate-or-recommendation

```yaml
type: procedure
source: scheme-guidelines
page: 3
tests: []
```

> a)  In  statutory  towns,  the  Certificate  of  Vending  (CoV)/Identity  Card/Letter  of
>
> Recommendation (LoR) to the street vendors will be issued by TVC/ ULBs.
>
> b)  For  census  towns  and  peri  urban  areas,  the  Letter  of  Recommendation  (LoR)  to  the
> street vendors will be issued by Block Development Offices after due verification as
> per Annexure A.
>
> c)  The  verification  and  issuance  of  LoR  shall  be  completed  within  15  days  of  the
>
> submission of application.

**Plain:** In towns, the town vending committee or the urban local body gives the vendor a Certificate of Vending, ID card or Letter of Recommendation. In census towns and areas around cities, the Block Development Office gives a Letter of Recommendation after checking. This should be done within 15 days of applying.

**Aliases:** certificate of vending · letter of recommendation · LoR · BDO · how to apply

## svanidhi-loan-tranches

```yaml
type: benefit
source: scheme-guidelines
page: 4
tests: []
```

> SVs will be eligible for collateral free working capital term loan in three tranches:
>
> 1.  1st tranche loan of up to ₹15,000 to be repaid in 12 months,
> 2.  2nd tranche loan of up to ₹25,000 to be repaid in 18 months and
> 3.  3rd tranche loan of up to ₹50,000 to be repaid in 36 months

**Plain:** Vendors can get loans without any security, in three steps: up to ₹15,000 (repay in 12 months), then up to ₹25,000 (18 months), then up to ₹50,000 (36 months).

**Aliases:** how much loan · 15000 · 25000 · 50000 · no guarantee loan

## svanidhi-next-tranche

```yaml
type: benefit
source: scheme-guidelines
page: 4
tests: []
```

> Upon timely or early repayment of a tranche, vendors will be eligible for the next tranche of
> working capital term loans, with the enhanced limit. For repayment before the scheduled date,
> no prepayment penalty will be charged from the vendor.

**Plain:** Repaying on time or early makes the vendor eligible for the next, bigger loan. There is no penalty for repaying early.

**Aliases:** next loan · repay early · prepayment penalty

## svanidhi-interest-subsidy

```yaml
type: benefit
source: scheme-guidelines
page: 4
tests: []
```

> The vendors, availing loan under the scheme, are eligible to get an interest subsidy at 7% per
> annum. The interest  subsidy  amount will be credited into the borrower’s account  quarterly.

**Plain:** Vendors who take the loan get a 7% a year interest subsidy, paid into their account every three months.

**Aliases:** interest subsidy · 7 percent · interest back

## svanidhi-credit-card

```yaml
type: benefit
source: scheme-guidelines
page: 5
tests: []
```

> A UPI linked RuPay Credit Card will be available as an additional facility for PM SVANidhi
> beneficiaries  who  have  successfully  repaid  their  2nd  tranche  loan  and  are  eligible  for  3rd
> tranche loan under the PM SVANidhi Scheme.
> This card will be a domestic card and initially the credit limit will be ₹10,000 which will be
> gradually increased to ₹30,000, the card will be valid for a period of 5 years.

**Plain:** Vendors who have repaid their second loan and qualify for the third can also get a UPI-linked RuPay credit card, starting at a ₹10,000 limit and rising to ₹30,000, valid for 5 years.

**Aliases:** credit card · rupay · upi card
