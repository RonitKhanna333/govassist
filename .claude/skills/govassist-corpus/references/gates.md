# The seven gates

Nothing enters the corpus unreviewed. Each gate blocks until a human approves,
and each approval is recorded in `.state.json` with a name and a timestamp.

**An assistant may present a gate. It may never approve one.**

| # | Gate | Human confirms | Blocks |
|---|---|---|---|
| 0 | Source selection | this URL is the canonical official document | download |
| 1 | Document identity | right scheme, right version, complete, has a text layer | extraction |
| 2 | Extraction quality | the `.txt` is readable where it matters | drafting |
| 3 | Segmentation | no rule is split across a boundary | LLM calls |
| 4 | Clause review | every quote verbatim and complete, every gloss faithful | corpus entry |
| 5 | Rule logic | comparison directions and boundaries correct | rule build |
| 6 | Pre-commit | validated, built, reviewed by a second person | merge |

## Gate 0 — source selection

Reject: news articles, coaching-site summaries, aggregator pages, press
releases, superseded versions.

Accept: the ministry's or department's own guidelines or notification PDF.

An aggregator paraphrases. Citing a paraphrase puts the grounding claim one hop
from the authority, which is exactly what this project exists to avoid.

## Gate 1 — document identity

One minute here saves an afternoon later. Check the scheme name, the year, the
page count, and whether page 1 has extractable text at all. An empty page 1
means a scanned image — needs `--ocr`.

## Gate 2 — extraction quality

Read the `.txt`, specifically the **eligibility** and **exclusions** sections.
Mangled text elsewhere is tolerable. Mangled eligibility text is not: every
quote validates against this file, so a broken `.txt` makes correct quotes fail.

If a rule-bearing table is destroyed, hand-repair **the `.txt`** and set
`hand_corrected: true` in the meta. Repairing the `.txt` is honest and
reviewable. Rewording quotes later to match broken extraction is not.

## Gate 3 — segmentation

One question: **does any single eligibility rule start in one segment and finish
in the next?**

This is the only place that failure is catchable. A rule drafted from half its
text produces a quote that still validates — both halves genuinely are in the
source — so no later check flags it.

Fix with `--merge A,B` or `--split N:OFFSET`.

## Gate 4 — clause review

Per clause:

- Is the quote **complete**? A quote that stops before "...except in cases
  where" inverts the rule.
- Does **Plain** introduce any number, date or condition not in the quote?
- Is `type` right? An exclusion mislabelled as eligibility flips its meaning
  everywhere downstream.
- Do the `tests` attributes match what the clause actually turns on?

And once, at the end, the question no automated check can ask:

- **Is anything missing?** The drafter only proposed what it found. Read the
  source's eligibility and exclusion sections yourself. An omission is invisible
  to every check in this system.

## Gate 5 — rule logic

**The gate people skip, and shouldn't.** A clause can be quoted perfectly while
its expression inverts the rule. Nothing automated catches it, and the
consequence is the worst one available: confidently telling someone they do not
qualify when they do.

Run it as a separate pass, with fresh eyes, ideally a different person than the
one who accepted the clauses.

- Comparison direction: "below ₹X" is `< X` — not `<=`, and certainly not `>`
- Boundary: "up to 2 hectares" is inclusive (`<= 2`); "less than 2" is not
- `ALL` vs `ANY` on `decision`
- Exclusions negated correctly — must be **false** to qualify
- Every threshold in the expression appears in the quote it cites

## Gate 6 — pre-commit

`validate.py` green, `build.py` regenerated and committed, and a second teammate
reviews the PR. The `build/` diff is the useful artifact: it shows exactly what
rule logic changed, in a form far easier to audit than prose.

## Resumability

All gate state lives in `data/schemes/<slug>/.state.json`, written after every
individual decision. Nobody reviews sixty clauses in one sitting, and Ctrl-C
must never lose work.

```bash
python data/scripts/review.py --scheme <slug> --status
```
