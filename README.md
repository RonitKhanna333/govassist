# GovAssist

A **grounded** government-scheme eligibility assistant: every statement it makes
traces back to a verbatim quote from an official document, and that link is
checked automatically rather than trusted.

**Live:** [app](https://govassist-web-git-main-ronit-khannas-projects.vercel.app) ·
[api](https://govassist-api-ronit-khannas-projects.vercel.app/health)

## What's built

| Layer | State |
|---|---|
| Corpus toolchain (`data/scripts/`) | 7 human review gates, span-validated quotes |
| Rule engine (`api/rules/`) | deterministic; the LLM never decides eligibility |
| Graph store (`api/graph/`) | 5 retrieval patterns, hop-capped, typed |
| Agents (`api/agents/`) | Groq: NLU, composer, verifier, recompose loop |
| Language (`api/language/`) | four text locales; Groq fallback; Bhashini provider code |
| Auth (`api/auth/`) | optional accounts, scrypt + JWT |
| Frontend (`web/`) | Next.js, four languages, voice, citation panel |
| CI (`.github/workflows/`) | backend corpus/API checks and frontend test/build checks |
| Deployment | two Vercel projects; deployment state must be verified separately |

The automated suite uses committed corpus data and mocks; it needs no production
API keys or network calls. Run the commands below for the current result rather
than relying on a hard-coded test count.

The single most important property: **the verdict and its citations need no
API key at all.** The rule engine is deterministic and the corpus is committed
JSON, so a zero-secret deployment still answers correctly — it just can't
phrase the explanation or speak it. Every missing credential degrades visibly
rather than silently. See [docs/deploy.md](docs/deploy.md).

```bash
pip install -e ".[dev,serve]" && pytest -q
uvicorn api.main:app --reload          # :8000
cd web && npm install && npm run dev   # :3000  (use localhost, not 127.0.0.1)
```

## UCS503 presentation and demonstration

The hosted-project presentation is the Next.js route `/presentation`. The
working signed-out PMFME prototype is `/`, and the evidence/remediation page is
`/evidence`. Navigation between all three is built into the site.

The prepared demonstration uses only non-sensitive values. To show the
reviewed boundary, use the complete individual-unit profile in
`docs/human-review-remediation.md` or the evidence page and change only
`age`: **18 must return `NOT_ELIGIBLE` with the age citation; 19 must return
`ELIGIBLE` when every other condition passes**. Punjabi and Tamil text flows
are supported; microphone input is intentionally enabled only for English and
Hindi. PMFME is the only demonstrated production scheme.

The repository contains exactly four use-case diagrams, five sequence diagrams
and one detailed class diagram under [`docs/diagrams/`](docs/diagrams/). The
presentation renders responsive previews from repository-controlled source
descriptions; they are not screenshots of an editor canvas.

The current change is not deployed or pushed by default. After the required
human corpus review, redeploy the API and web projects and repeat the browser
checks. See [`docs/human-review-remediation.md`](docs/human-review-remediation.md)
and [`docs/deploy.md`](docs/deploy.md).

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

Windows, macOS or Linux. The corpus and test suite need no system packages or
production API keys; Groq, Bhashini and Postgres are optional runtime
configuration.

```bash
pip install -e ".[dev,serve]"
```

Then confirm everything works:

```bash
python -m pytest -q
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
python -m pytest -q                        # everything
python -m pytest tests/test_normalize.py   # the provenance spine
python -m pytest tests/test_validate.py -k Fabricated   # the meta-test
python data/scripts/validate.py --all
python data/scripts/build.py --all --check
cd web && npm ci && npm test && npm run build
```

GitHub Actions runs the backend checks, generated-build freshness check,
frontend tests/build and dependency audits on pull requests and pushes to
`main`.
