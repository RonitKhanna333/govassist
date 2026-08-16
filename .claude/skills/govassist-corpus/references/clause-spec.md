# Clause authoring spec

This file is both the reference for drafting inside Claude Code **and** a
standalone prompt. To use it with a chat assistant: paste this whole file, then
paste the extracted plain text of one chunk of a scheme's official guidelines.

Everything below the line is written as instructions to the drafter.

---

You are helping build a **grounded** knowledge corpus for a government-scheme
eligibility assistant. Grounded means every statement the system can make traces
back to a verbatim quote from an official document. A validator checks this
automatically and rejects anything that fails.

## Your input

The extracted plain text of one scheme's official guidelines document, or one
chunk of it. **Work only from that text.**

- Do **not** use anything you know about this scheme from training. Your
  recollection may be outdated; the pasted document is the only authority.
- If the document doesn't state something, **omit it**. Never fill a gap with a
  plausible value. A missing rule is fine; an invented one is a defect.
- If the text is garbled or ambiguous, emit the clause anyway and add
  `uncertain: true` with a one-line `note`. A human reviews everything.

## Your output

A Markdown file, `scheme.md`, in exactly the format below. Output the file and
nothing else — no preamble, no commentary after.

### Frontmatter

```yaml
---
scheme: <kebab-case-slug>
name_en: <official English name>
tier: 1
version: 1
effective_from: <YYYY-MM-DD, or null if the document doesn't say>
effective_to: null
authority: <issuing ministry or department, as printed>
license: GoI public document
sources:
  - id: guidelines-2024        # short label; clauses reference this
    pdf: source/guidelines-2024.pdf
    txt: source/guidelines-2024.txt
    url: <TODO>
    retrieved_at: <TODO>
    checksum: <TODO>

conditions:
  - id: <snake_case>
    expr: <boolean expression over profile.* -- see grammar below>
    clause: <id of a ## section below>
    asks: <plain question to ask a user who hasn't supplied this yet>
decision: ALL(conditions)
---
```

Leave `<TODO>` literally as-is; `ingest.py` prints the real values.

### Expression grammar for `conditions[].expr`

Deliberately restrictive — parsed by an AST whitelist, never `eval()`. Use only:

- Attribute references: `profile.<snake_case_name>`
- Comparison: `==` `!=` `<` `<=` `>` `>=`
- Boolean: `and` `or` `not`
- Membership: `profile.x in ["a", "b"]`
- Literals: numbers, quoted strings, `true`, `false`
- Parentheses for grouping

No function calls, arithmetic, subscripts, or lambdas. The expression must
evaluate to a boolean — write `profile.age >= 18`, not `profile.age`.

If a rule genuinely can't be expressed this way, split it into several
conditions, or add `uncertain: true` and describe the problem.

Keep attribute names consistent across the file, and prefer general names
reusable across schemes: `age`, `annual_income`, `owns_cultivable_land`,
`land_area_hectares`, `is_government_employee`, `paid_income_tax_last_year`,
`category`, `state`, `household_size`.

**Exclusions are negated.** A clause saying "income tax payers are excluded"
becomes a condition that must be **true** to qualify:
`profile.paid_income_tax_last_year == false`.

### Clause sections

One `##` section per distinct rule, eligibility criterion, exclusion, benefit,
or required document.

````markdown
## <kebab-case-clause-id>

```yaml
type: eligibility | exclusion | benefit | document | procedure | definition
source: guidelines-2024
page: <page number if visible, else null>
tests: [<profile attributes this clause bears on>]
```

> <VERBATIM quote from the source -- copied exactly, character for character>

**Plain:** <one or two sentences, plain language, no jargon, no invented specifics>

**Aliases:** <how an ordinary person would describe this -- 4 to 8 short phrases, separated by ·>
````

## The three parts do three different jobs — do not blur them

| Part | Rule |
|---|---|
| **Blockquote** | **Verbatim.** Copy exactly. Do not fix grammar, expand abbreviations, modernize spelling, merge sentences, or add an ellipsis. An exact-substring check runs against the source; any edit fails it. Keep it to the smallest span that fully carries the rule — usually one or two sentences. |
| **Plain** | Your paraphrase, for a reader with no legal background. It must not contain any fact absent from the blockquote. No added numbers, dates, or thresholds. |
| **Aliases** | Colloquial phrasings for search matching only — never shown to users, never cited. Include misspellings and vague phrasings; real people write "we hav 2 acre land". Include Hindi, Punjabi and Tamil phrasings in native script where natural. |

## Rules for IDs

- Clause IDs: kebab-case, descriptive, unique within the file —
  `landholding-basic`, `exclusion-income-tax`, `benefit-amount`.
- Every `conditions[].clause` **must** match a `##` section id in the same file.
- Every clause's `source` must match a `sources[].id` in the frontmatter.

## Before you output, verify each of these

1. Every blockquote is copied verbatim from the source — re-check character by
   character.
2. No number, date, amount or threshold appears anywhere unless it appears in
   the source text.
3. Every `conditions[].clause` resolves to a `##` section present in the file.
4. Every clause `source` resolves to a frontmatter `sources[].id`.
5. Every `expr` uses only the permitted grammar and evaluates to a boolean.
6. Attribute names are consistent across all conditions and `tests` lists.
7. Nothing in a **Plain** line states a fact the blockquote doesn't support.
8. Exclusions are captured as clauses too — who is *disqualified* matters as
   much as who qualifies.

## Worked example

````markdown
## exclusion-income-tax

```yaml
type: exclusion
source: guidelines-2024
page: 4
tests: [paid_income_tax_last_year]
```

> All Institutional Land holders and farmer families in which one or more of its
> members paid Income Tax in last assessment year are excluded from the benefit
> under the scheme.

**Plain:** You are not eligible if you, or anyone in your family, paid income tax last year. Land held by institutions is also excluded.

**Aliases:** i pay income tax · we filed ITR last year · मैंने टैक्स भरा था · ਅਸੀਂ ਟੈਕਸ ਭਰਿਆ ਸੀ · நாங்க வரி கட்டியிருக்கோம்
````

Its condition, in the frontmatter:

```yaml
  - id: not_income_tax_payer
    expr: profile.paid_income_tax_last_year == false
    clause: exclusion-income-tax
    asks: Did you or anyone in your family pay income tax last year?
```
