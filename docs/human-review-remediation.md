# Human-review remediation

This correction intentionally leaves `data/schemes/pmfme/.state.json`
unchanged. It must not be rewritten to make a machine or an agent look like a
human reviewer.

## What the current record says

The state file attributes Gate 4 (`4_clauses`) to **Codex**. It also attributes
these clause approvals to **Codex**:

`branding-applicant-types`, `branding-support-limit`,
`branding-turnover-minimum`, `common-infrastructure-grant`,
`common-infrastructure-hiring-basis`, `fpo-experience-minimum`,
`fpo-grant-support`, `fpo-turnover-minimum`,
`grant-adjustment-after-three-years`, `individual-age-and-education`,
`individual-capital-subsidy`, `individual-existing-unit`,
`individual-formalize-contribute-and-borrow`,
`individual-identified-or-verified`, `individual-one-person-per-family`,
`individual-ownership-right`, `individual-unincorporated-under-ten-workers`,
`loan-documents-required`, `scheme-purpose`, `shg-individual-member-grant`,
`shg-odop-experience`, `shg-own-funds-and-margin-money`,
`shg-processing-members-only`, and `shg-seed-capital`.

Gate 5 and all eight condition decisions are currently attributed to `thorb`,
but the age expression has now changed from `profile.age >= 18` to
`profile.age > 18`. The previous Gate 5 decision therefore does not certify
the corrected expression and must be repeated. Gates 0–3 are recorded as
`thorb`; the team should retain those claims only if that named person can
confirm the original source, identity, extraction and segmentation checks.

## How the code now treats these records

`data/scripts/review_binding.py` decides whether a recorded approval counts.
It counts only when it is approved, attributed to a name that is not an
agent/automation label (`Codex`, `Claude ... needs human confirmation`, a
bot, a placeholder), and carries a `content_sha256` binding that equals the
fingerprint of the content committed now (clause quote, gloss, type, source
and tests; condition expression, cited clause and its quote; the decision).
The existing records are preserved exactly as they are; they are simply
classified:

| Record | Classification | Effect |
|---|---|---|
| Gate 4 and 24 clauses by `Codex` | unattributed | pending human review |
| Gate 5, all 8 conditions, and 4 clauses by `thorb` | unbound (no binding; Gate 5 predates `age > 18`) | pending human review |

So `/schemes` reports PMFME as `reviewed: false`, the UI shows the "not yet
reviewed" note both when choosing the scheme and next to its result, and
`validate.py` prints the reasons as warnings. The release gate
`validate.py --scheme pmfme --require-review` turns them into errors and
currently fails; it passes only after the steps below. The deterministic
verdict, citations and tests are unaffected.

The same classification applies to APY, PMJJBY, PMSBY and PM-KMY, whose
gates are recorded as an AI assistant "needs human confirmation" and were
never presented as reviewed.

## Supported remediation

Run these commands from the repository root in a real interactive terminal.
Do not pipe answers into the scripts and do not use an automatic default --
`review.py` now refuses a non-interactive stdin and refuses agent names as
the reviewer. Replace the placeholder with the actual human reviewer’s name.
Each decision the tool records now includes the content binding, so a later
edit to a reviewed clause or expression automatically returns it to pending.

```powershell
$env:GOVASSIST_REVIEWER = "Actual Human Reviewer Name"
python data/scripts/review.py --scheme pmfme --only all --reviewer "$env:GOVASSIST_REVIEWER"
python data/scripts/review.py --scheme pmfme --conditions --reviewer "$env:GOVASSIST_REVIEWER"
python data/scripts/validate.py --scheme pmfme --require-review
python data/scripts/build.py --scheme pmfme
python data/scripts/build.py --all --check
```

Gate 4 is approved at the end of the clause pass and binds to the accepted
clause set it promotes; Gate 5 is approved at the end of the conditions pass.
Both must be run (in that order) for `--require-review` to pass.

`--only all` is the review tool’s supported way to re-open every clause. The
human must read each quote, source context and gloss, and then answer the
Gate 4 completeness question. The `--conditions` pass shows all eight
expressions and asks the human to accept/reject each one and the final Gate 5
question. The human must specifically confirm this boundary:

> PMFME says “above 18 years of age”; therefore `profile.age > 18` is
> exclusive — age 18 fails, age 19 passes, provided the other conditions pass.

The scripts save each literal decision themselves. Do not edit `.state.json`
by hand. If a reviewer needs to stop, `q` saves progress; re-run the same
command to continue. If an item was previously approved, `--only all` or the
conditions pass is the supported re-review path.

## What may be claimed

Before this re-review, the repository may claim that the corrected source,
generated artifacts, tests and validation are prepared. It may not claim that
Gate 4 or the corrected Gate 5 has human approval. After a named human has
completed both interactive passes and the validation/build checks pass, the
repository may claim those gates were reviewed by that person, with the name
and timestamp recorded by the tool. Gate 6 still needs the required second
human diff review; the PR merge and Vercel deployment do not constitute human
corpus approval.
