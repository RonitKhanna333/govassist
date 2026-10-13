# Proposed clauses for the "What should I do next?" gaps

**Status: proposals only. None of these is in any `scheme.md`, and none is
shown to anyone.** They exist so a human can close the checklist's "where
and how to apply" gaps through the gated workflow in AGENTS.md. An agent
drafted them; only a person can accept them (Gate 4).

Every quote below was copied from the committed `source/*.txt`, not from a
PDF viewer, and passes `normalize.validate_quote` as **EXACT**. Page numbers
were counted from the text's page breaks; check them in review. The **Plain**
glosses and aliases are drafts and need the same scrutiny as any gloss: they
must add no number, place or condition that the quote doesn't state.

## How to adopt them

1. Copy the scheme's `scheme.md` to `data/schemes/<slug>/scheme.draft.md`
   (drafts are gitignored) and append the clause block below.
2. `python data/scripts/import_draft.py --scheme <slug> --repair`
3. `python data/scripts/review.py --scheme <slug> --only all` -- a named
   human reads every clause, including the new one, and answers Gate 4.
4. `python data/scripts/validate.py --scheme <slug>` then
   `python data/scripts/build.py --scheme <slug>`.
5. Add the accepted clause id to that scheme's `"apply"` list in
   `data/next_steps.json`. `tests/api/test_next_steps.py` checks that the id
   exists and is a `procedure`. The checklist picks it up with no code change.

## Gaps that remain even with these

- **APY**: the committed 4-page source says nothing about where or how to
  join. Closing that gap needs a new official source (Gate 0 onward), not a
  clause from this document.
- **Documents** for APY, PM-KMY, PMJJBY and PMSBY: only PM-KMY's source names
  any (Aadhaar card, bank passbook -- in the first proposal below, which
  could also be listed under `"documents"` if a reviewer types a second,
  document-typed clause for it).

---

## pm-kmy -- `pmkmy-enrol-at-csc`

```yaml
type: procedure
source: operational-guidelines
page: 6
tests: []
```

> (xvi)   The  Eligible  SMFs  desirous  of  joining  the  scheme  shall  visit  nearest  Common
> Service Centre (CSC) along with his Aadhaar card and bank passbook or account details.

**Plain:** To join, eligible small and marginal farmers should visit their nearest Common Service Centre (CSC) with their Aadhaar card and bank passbook or account details.

**Aliases:** where to join · how to apply for farmer pension · CSC enrolment · what to bring

## pm-kmy -- `pmkmy-csc-online-registration`

```yaml
type: procedure
source: operational-guidelines
page: 6
tests: []
```

> (xvii) The Village Level Entrepreneur (VLE) present at the CSC shall complete the on-line
> registration process after taking details of Aadhaar number, name, date of birth, spouse
> and nominee particulars, mobile number (optional), address and a few other details.

**Plain:** At the CSC, the Village Level Entrepreneur completes the online registration using your Aadhaar number, name, date of birth, spouse and nominee details, address, an optional mobile number and a few other details.

**Aliases:** registration at CSC · details needed to register · VLE registration

## pmsby -- `pmsby-enrolment-form`

```yaml
type: procedure
source: rules
page: 3
tests: []
```

> Enrolment  form  /  Auto-debit  authorization  in  the  prescribed  proforma  shall  be
> obtained  and  retained  by  the  participating  bank/  Post  office.

**Plain:** The participating bank or Post office takes and keeps the enrolment form and auto-debit authorization, in the prescribed format.

**Aliases:** how to enrol · enrolment form · where to apply for accident insurance

## pmjjby -- `pmjjby-enrolment-form`

```yaml
type: procedure
source: rules
page: 3
tests: []
```

> Enrolment  form /  Auto-debit  authorization /  Consent  cum Declaration  form in
> the prescribed proforma shall be obtained and retained by the participating bank/
> Post  office.

**Plain:** The participating bank or Post office takes and keeps the enrolment form, auto-debit authorization and consent-cum-declaration form, in the prescribed format.

**Aliases:** how to enrol · enrolment form · where to apply for life insurance

## pmfme -- `proposals-to-bank-with-kyc`

```yaml
type: procedure
source: scheme-guidelines
page: 30
tests: []
```

> 13.7  The proposals should be forwarded to the bank branches along with basic KYC of
> the applicant.

**Plain:** Applications are forwarded to bank branches together with the applicant's basic KYC.

**Aliases:** where does my application go · bank branch · KYC

Reviewer note: section 13 describes what the State Nodal Agency does with
applications, so this tells an applicant where an application ends up, not
where to submit it. Accept it as an `"after"` step rather than `"apply"` if
that reading is right; PMFME's guidelines in this corpus do not name an
applicant-facing portal.
