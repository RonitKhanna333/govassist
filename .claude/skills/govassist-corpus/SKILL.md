---
name: govassist-corpus
description: Build or extend the GovAssist grounded scheme corpus - ingest an official government scheme PDF, draft clauses from it, span-validate every quote against the source, and drive the human review gates. Use when adding a scheme, drafting or repairing clauses in a scheme.md, fixing span-validation failures, or authoring rule conditions.
---

# Building the GovAssist scheme corpus

## The rule that governs everything here

> Every fact that can influence an eligibility verdict must trace to a character
> span in a committed source document.

You may **transform** source text and **generate questions**. You are never a
source of facts about a scheme. Do not write an eligibility rule, threshold,
date or amount from your own knowledge, even if you are confident and even if
the document seems to be missing it. Your recollection may be outdated, and it
is unattributable — which makes it useless to a system whose entire claim is
that answers are grounded.

If the source document does not state something, **omit it**. A missing rule is
fine; an invented one is a defect that survives to the demo.

## The gates are the user's, not yours

Seven human gates, listed in `references/gates.md`. **Never mark a gate
approved on the user's behalf, and never advise skipping one.**

You may draft, validate, repair, and present. The person reviewing must actually
read the clause. A skill that approves its own output turns the provenance chain
into theatre — present the evidence and wait for their answer.

Concretely: the gate scripts prompt interactively. Run them and let the user
respond, or show the user what needs checking and ask directly in conversation.
Do not pipe input into a gate prompt, and do not edit `.state.json` to record an
approval.

## Workflow

Scripts live in `data/scripts/` and are invoked from the repository root. Never
duplicate them into the skill.

### 1. Ingest the source document (Gates 0-2)

```bash
python data/scripts/ingest.py --scheme <slug> --url "<official pdf url>"
python data/scripts/ingest.py --scheme <slug> --file <local.pdf>   # if blocked
```

Help the user find the canonical ministry PDF if they ask — that is a good use
of web search. Prefer a `.gov.in` / `.nic.in` document over any aggregator: an
aggregator paraphrases, and a paraphrase is not citable.

**Never fetch the PDF and quote from your own rendering of it.** Quotes validate
against the `.txt` this script produces. Your extraction will differ on line
breaks, hyphenation and ligatures, so every quote will fail for reasons that look
like hallucination but are not.

### 2. Segment (Gate 3)

```bash
python data/scripts/segment.py --scheme <slug> --emit
```

When presenting boundaries, flag the failure no later check can catch: a single
eligibility rule starting in one segment and finishing in the next. Suggest
`--merge A,B` or `--split N:OFFSET`.

### 3. Draft clauses

Read `references/clause-spec.md` in full before drafting — it is the exact output
format, and the validator enforces it.

Read one chunk from `data/schemes/<slug>/chunks/` at a time. Work only from that
text. Write to `data/schemes/<slug>/scheme.draft.md`.

Copy blockquotes **from the `.txt`**, character for character. Do not fix the
source's grammar, expand abbreviations, merge sentences, or add an ellipsis.

### 4. Validate and repair

```bash
python data/scripts/import_draft.py --scheme <slug>
python data/scripts/import_draft.py --scheme <slug> --repair
```

Fix every failure before involving the user. The report prints the real source
text near each failed quote — use it and re-quote. Most failures are line-break
artifacts.

If a quote cannot be found anywhere in the source, **delete that clause**. Do not
reconstruct it, do not approximate it, and do not relax the check.

Then draft the rule conditions in the frontmatter. Every condition needs a
`clause` that exists in the same file and an `expr` in the restricted grammar
(see `references/clause-spec.md`). Be careful with comparison direction and
boundary inclusivity — "up to 2 hectares" is `<= 2`, "below 2" is `< 2`.

### 5. Hand over for review (Gates 4-5)

```bash
python data/scripts/review.py --scheme <slug>
python data/scripts/review.py --scheme <slug> --conditions
```

This is the user's work, not yours. Before handing over, tell them what you are
least sure about — clauses you marked `uncertain`, quotes that matched only
loosely, rules whose boundary semantics were ambiguous in the source. That list
is more useful than a summary of what went fine.

Remind them of the one thing automation cannot check: **is anything missing?**
You only proposed what you found. They should read the source's eligibility and
exclusion sections themselves.

Suggest the two passes be done by different people. A clause can be quoted
perfectly while its expression inverts the rule, and no test catches that.

### 6. Validate and build (Gate 6)

```bash
python data/scripts/validate.py --scheme <slug>
python data/scripts/build.py --scheme <slug>
```

Both must pass before a PR. Never edit anything in `build/` — it is generated.

## Common situations

**"Add scheme X"** — start at step 1. Ask for the official PDF URL if you cannot
confidently identify the canonical one.

**"Fix the validation failures"** — run `import_draft.py --repair`, re-quote from
the printed source text, re-run. Do not touch `normalize.py` to make failures go
away; that module is the guarantee.

**"The quote is right but validation fails"** — see
`references/troubleshooting.md`. Usually the `.txt` is mangled, not the quote. The
fix is to repair the `.txt` and set `hand_corrected: true` in the meta — never to
reword the quote to match broken extraction.

**"Just approve it, it's fine"** — you cannot. Explain that the gate records who
reviewed what, and offer to walk them through the clauses instead.

## Reference files

- `references/clause-spec.md` — the exact `scheme.md` format; read before drafting
- `references/gates.md` — the seven gates and what a human checks at each
- `references/troubleshooting.md` — span failures and their real causes
