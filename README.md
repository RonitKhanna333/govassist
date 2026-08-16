# GovAssist — corpus toolchain

Tooling for building a **grounded** knowledge corpus of government schemes: every
statement the assistant can make traces back to a verbatim quote from an official
document, and that link is checked automatically rather than trusted.

This repository currently contains the corpus layer only. The web app, agents,
voice layer and retrieval come later; they all consume what is built here.

## The one rule

> Every fact that can influence an eligibility verdict must trace to a character
> span in a committed source document.

An LLM may **transform** source text and **generate questions**. It is never a
source of facts. This is not caution for its own sake — a verifier that checks
model output against model output is theatre, and "where did this rule come
from?" has to have a page number as its answer.

The rule is enforced, not merely documented:

- `source_clause_id` is required on every condition
- every blockquote is checked, character for character, against the committed
  extracted text
- a reviewer cannot accept a clause whose quote is absent
- a reviewer cannot edit a quote out of alignment with its source
- `tests/fixtures/fabricated-scheme/` exists to prove the checks catch invented
  rules, altered numbers and paraphrases — CI fails if it ever validates

## Setup

Windows, macOS or Linux. No system packages, no poppler, no API keys.

```bash
pip install -e ".[dev]"
```

Then confirm everything works:

```bash
pytest
```

## Workflow

Nine steps, seven human gates. The scripts propose; a person decides.

```
1. Find the canonical PDF          browsing assistant or search   [Gate 0]
2. ingest.py --url ...             download, checksum, extract    [Gates 1-2]
3. segment.py --emit               split into paste-ready chunks  [Gate 3]
4. Draft the clauses               assistant reads a chunk
5. Save as scheme.draft.md
6. import_draft.py                 span-validate every quote
7. review.py                       clause + rule-logic review     [Gates 4-5]
8. validate.py                     all acceptance gates
9. build.py                        rules / graph / clause rows    [Gate 6: PR]
```

### Worked example

A complete, valid scheme ships in `data/schemes/demo-scheme/`. Try the back half
of the pipeline on it:

```bash
python data/scripts/validate.py --scheme demo-scheme
python data/scripts/build.py --scheme demo-scheme
```

Now break it and watch the gate catch it — change `Rs. 6000` to `Rs. 6001` in
`data/schemes/demo-scheme/scheme.md` and re-run `validate.py`. It fails, names
the clause, and prints the real source text next to what you wrote.

### Step 1 — find the source (Gate 0)

Locate the official guidelines PDF. A browsing assistant is genuinely good at
this. Prefer the ministry's own `.gov.in` document over any aggregator: an
aggregator paraphrases, and a paraphrase is not citable.

### Step 2 — ingest (Gates 1-2)

```bash
python data/scripts/ingest.py --scheme pm-kisan --url "https://.../guidelines.pdf"
```

Many government sites block automated requests. If the download fails, fetch it
in a browser and pass the file instead:

```bash
python data/scripts/ingest.py --scheme pm-kisan --file ~/Downloads/guidelines.pdf
```

Produces:

```
data/schemes/pm-kisan/source/guidelines.pdf        the authority, checksummed
data/schemes/pm-kisan/source/guidelines.txt        ← quotes validate against THIS
data/schemes/pm-kisan/source/guidelines.meta.json
```

For a scanned document with no text layer, add `--ocr` (needs `pytesseract` and
Tesseract installed separately).

### Step 3 — segment (Gate 3)

```bash
python data/scripts/segment.py --scheme pm-kisan --emit
```

Review the boundaries for the one thing no later check can catch: **a single
eligibility rule that starts in one segment and finishes in the next.** Drafted
from half its text, the resulting quote still validates — both halves really are
in the source. Fix with `--merge 4,5` or `--split 7:1200`.

### Steps 4-6 — draft and validate

For each file in `chunks/`:

1. Open a fresh chat
2. Paste `.claude/skills/govassist-corpus/references/clause-spec.md`
3. Paste one chunk
4. Append the output to `data/schemes/pm-kisan/scheme.draft.md`

Then check it:

```bash
python data/scripts/import_draft.py --scheme pm-kisan
python data/scripts/import_draft.py --scheme pm-kisan --repair   # paste-back message
```

`--repair` prints a message for the drafting chat: which clauses failed, and the
real source text near each. Most failures are PDF line-break artifacts and come
back correct on the first retry.

**Extract the text yourself; never let the assistant fetch the PDF.** Its
internal rendering will differ from yours on line breaks, hyphenation and
ligatures, so every quote fails for reasons that look like hallucination but
aren't — and the tempting fix, loosening the check, destroys the whole guarantee.

If you are working in Claude Code, the `govassist-corpus` skill collapses steps
4-6 entirely: Claude reads the `.txt`, drafts, runs the validator itself, repairs
its own failures, and stops at each gate to ask you.

### Step 7 — review (Gates 4-5)

```bash
python data/scripts/review.py --scheme pm-kisan               # clauses
python data/scripts/review.py --scheme pm-kisan --conditions  # rule logic
```

Resumable — every decision is saved immediately, so stopping at clause 41 of 60
loses nothing.

**Run the two passes separately, ideally with different people.** A clause can be
quoted perfectly while its expression inverts the rule (`>=` where the document
says "below"). No test in this repository can catch that, and it is the error
with the worst consequence: telling someone they do not qualify when they do.

### Steps 8-9 — validate, build, commit (Gate 6)

```bash
python data/scripts/validate.py --scheme pm-kisan
python data/scripts/build.py --scheme pm-kisan
```

Commit `scheme.md`, `source/`, and `build/`, and have a teammate review the PR.
The `build/` diff is the useful part — it shows exactly what rule logic changed,
in a form that is far easier to audit than prose.

## Scripts

| Script | Does |
|---|---|
| `normalize.py` | Text normalization + span validation. Everything depends on it |
| `grammar.py` | Restricted expression parser/evaluator (AST, never `eval()`) |
| `parse_scheme.py` | `scheme.md` reader/writer, round-trip safe |
| `state.py` | Gate state — who approved what, and where to resume |
| `ingest.py` | Gates 0-2: download, checksum, extract |
| `segment.py` | Gate 3: split into reviewable chunks |
| `import_draft.py` | Validate an assistant's draft; generate a repair message |
| `review.py` | Gates 4-5: interactive, resumable, edit-safe |
| `validate.py` | All acceptance gates. Exit 1 on failure. Run in CI |
| `build.py` | `scheme.md` → rules / graph / clause rows. Deterministic |
| `diff_rules.py` | What changed between two versions of a rule pack |

## How a scheme is stored

```
data/schemes/pm-kisan/
├── scheme.md          ← the only hand-authored file
├── source/            pdf + txt + meta   (committed: this is the provenance anchor)
├── build/             generated; committed so CI can diff it
└── .state.json        gate approvals and per-clause decisions
```

`scheme.md` holds provenance, the rule conditions, and the clauses together —
Markdown rather than JSON because human review is the quality gate, and a clause
corpus has to be reviewable in a pull-request diff.

Each clause has three parts doing three different jobs:

| Part | Role | Shown | Embedded | Translated |
|---|---|---|---|---|
| Blockquote | the citation, verbatim | yes, always | yes | **never** |
| `**Plain:**` | the gloss to paraphrase | yes | yes | yes |
| `**Aliases:**` | how a citizen would say it | **never** | yes | per language |

Embed what matches how people talk; cite what the government actually wrote.

## Three outputs, one source

`build.py` compiles `scheme.md` into three projections:

- `rules.v{n}.json` — conditions and decision, for the deterministic rule engine
- `graph.v{n}.json` — nodes and edges, for multi-hop retrieval
- `clauses.jsonl` — one row per clause, ready to embed

The graph is *generated from* the rule pack rather than authored separately.
Two hand-maintained descriptions of the same rules drift, and the drift is
silent. Here there is one source and three views of it, and `build.py --check`
fails CI if they disagree.

## Eligibility outcomes

The rule engine returns one of three verdicts — never two.

| Verdict | Meaning |
|---|---|
| `ELIGIBLE` | every condition satisfied |
| `NOT_ELIGIBLE` | at least one condition definitely fails, with the clause that says so |
| `INSUFFICIENT_INFO` | the answer depends on something we have not asked |

Evaluation uses three-valued logic, so a missing attribute yields `UNKNOWN`, not
`False`. Collapsing the third outcome into `NOT_ELIGIBLE` would mean confidently
denying someone because we forgot to ask a question.

## Testing

```bash
pytest                                    # everything
pytest tests/test_normalize.py            # the provenance spine
pytest tests/test_validate.py -k Fabricated   # the meta-test
```
