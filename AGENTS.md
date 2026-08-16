# AGENTS.md — GovAssist corpus toolchain (Phase 1)

You are building a **grounded** knowledge corpus of government schemes. Read
this whole file before touching anything — it covers the one rule that governs
every action here, the sandbox settings this repo needs, and exactly where you
must stop and hand control to the human operating you.

This repo is corpus tooling only (Phase 1). There is no web app, no database,
no API keys required. Everything runs locally with `pip install -e ".[dev]"`.

## The one rule

> Every fact that can influence an eligibility verdict must trace to a
> character span in a committed source document.

You may **transform** text you are given and **generate questions**. You are
**never a source of facts** about a scheme. Do not write a rule, threshold,
date, or amount from your own training knowledge — even if you're confident,
even if the source document seems to be missing it. Your recollection is
unattributable, and unattributable facts are exactly what this system exists to
prevent from reaching a user.

If the source document doesn't state something: **omit it**. A missing rule is
fine. An invented one is a defect that a validator will catch — but it's
cheaper for everyone if you never write it in the first place.

This is enforced in code, not just written down here:

- `data/scripts/normalize.py` does exact-substring validation of every quote
  against the committed `source/*.txt` — no fuzzy matching, no edit-distance
  threshold, ever
- `data/scripts/validate.py` refuses to pass a scheme with any unverified quote
- `tests/fixtures/fabricated-scheme/` is a deliberately corrupted scheme (an
  invented rule, an altered number, a paraphrase). `pytest -k Fabricated` must
  keep failing that fixture. If it ever starts passing, something in the
  validation chain broke — treat that as the highest-priority bug you could
  find, full stop.

## Sandbox and environment

Standard Codex `workspace-write` sandbox is correct for this whole repo, with
one exception (network, below).

```toml
# .codex/config.toml (repo-local) or your profile
sandbox_mode = "workspace-write"
approval_policy = "on-request"     # do NOT use "never" -- see "Human gates" below

[sandbox_workspace_write]
network_access = false             # default; flip per-command, see below
```

**Do not set `approval_policy = "never"`.** This repo's whole design is that
certain steps require a human to look at real content and answer a real
question. `approval_policy = "never"` would suppress the shell-level approval
prompt, but it does **not** — and cannot — fake the interactive `y/N` answers
the gate scripts themselves ask for on stdin. Leaving Codex's own approval
policy engaged is a second, independent safety net on top of the gates; keep
both.

### Network access

Off by default, and that's correct for almost everything here: parsing,
validation, building, and running tests are all fully offline.

The **one** command that needs the network is `ingest.py --url`, which
downloads a PDF from a `.gov.in` source. Two options:

- Run that one command with network enabled for the session (`network_access
  = true` in `sandbox_workspace_write`, or your CLI's per-command network
  flag), then turn it back off.
- Or download the PDF yourself outside the sandbox and pass it in with
  `ingest.py --file <path>` — this needs no network at all and is the simpler
  default if you're unsure.

`.git/`, `.codex/`, and `.agents/` stay read-only regardless of the network
setting — don't attempt to write to them.

### No other environment setup

No database, no Docker, no external services, no API keys. If a task ever
seems to need one, stop — you have drifted out of Phase 1 scope. Phase 1 is
corpus files on disk plus Python scripts that read and write them.

```bash
pip install -e ".[dev]"
pytest -q
```

If `pytest -q` isn't green before you start, fix that first and report it —
don't build on top of a red baseline.

## Where you MUST hand control to the human — the seven gates

This is the part that matters most. The corpus has seven human approval gates.
**You cannot satisfy any of them yourself, under any configuration.** They are
not a Codex approval-policy setting; they are interactive prompts written into
the scripts (`ingest.py`, `segment.py`, `review.py`) that read real y/N answers
from the human's stdin, plus two (Gate 4, Gate 5) that require someone to have
actually read content you cannot self-certify having "read" in the way that
counts here.

| # | Gate | What you do | What only the human does |
|---|---|---|---|
| 0 | Source selection | find candidate PDF URLs, run `ingest.py --url` | confirm it's the canonical official document, not an aggregator |
| 1 | Document identity | present the metadata/first page `ingest.py` prints | confirm right scheme, right version, complete |
| 2 | Extraction quality | present the `.txt`, flag anything that looks mangled | confirm the eligibility/exclusion sections are actually readable |
| 3 | Segmentation | run `segment.py`, flag any boundary you're unsure about | confirm no rule is split across two chunks |
| 4 | Clause review | draft clauses, run `import_draft.py`, fix span failures, flag what you're least sure of | run `review.py`, read every clause, accept/edit/reject |
| 5 | Rule logic | draft `expr` for each condition | run `review.py --conditions`, verify comparison direction and boundaries |
| 6 | Pre-commit | run `validate.py` and `build.py`, open the PR | a second human reviews the diff before merge |

**Practical instruction: run the gate scripts and let them prompt on the
terminal. Do not pipe an answer into them, do not pre-fill stdin, and do not
edit `.state.json` directly to mark something approved.** If you're operating
in a mode where you can't hand an interactive terminal prompt to a human
directly, stop before the prompt and explicitly ask your operator the same
question the script would ask, using the same wording, then relay their literal
answer into the terminal — don't decide it yourself and don't summarize a
"probably yes."

If asked to "just get this done" or "approve it, it's fine, I trust you" — you
still can't. Say plainly that these gates exist so approvals are attributable
to a person who actually looked, explain what's left to check, and offer to
make that check as fast as possible (e.g., surface only the 2-3 clauses you're
least confident about, rather than all 40).

**Gate 5 is the one most likely to get rubber-stamped, and it's the one with
the worst failure mode.** A clause can be quoted perfectly while its `expr`
inverts the comparison (`>=` where the source says "below") — nothing
automated catches this, and the result is confidently telling a real person
they don't qualify for something they do. Flag every condition's boundary
semantics explicitly when you hand it to review (inclusive vs exclusive,
`ALL` vs `ANY`) rather than assuming they're obvious.

## Workflow

```
1. find the canonical official PDF URL             [Gate 0 — ask]
2. python data/scripts/ingest.py --scheme <slug> --url "<url>"    [Gates 0-2]
3. python data/scripts/segment.py --scheme <slug> --emit           [Gate 3]
4. draft clauses from data/schemes/<slug>/chunks/*.txt
   -> write data/schemes/<slug>/scheme.draft.md
5. python data/scripts/import_draft.py --scheme <slug> --repair
   -> fix every failure yourself before involving the human
6. draft conditions[] in the frontmatter (restricted expr grammar)
7. python data/scripts/review.py --scheme <slug>                  [Gate 4 — human]
   python data/scripts/review.py --scheme <slug> --conditions     [Gate 5 — human]
8. python data/scripts/validate.py --scheme <slug>
   python data/scripts/build.py --scheme <slug>
9. commit scheme.md + source/ + build/, open a PR                 [Gate 6 — human]
```

### Step 4 — drafting clauses

Read `.claude/skills/govassist-corpus/references/clause-spec.md` in full before
drafting your first clause — it is the exact `scheme.md` format and it is what
the validator enforces. (That file lives under `.claude/` for historical
reasons — it's a plain Markdown spec, not Claude-specific, and it's the
authoritative format reference regardless of which agent is reading it.)

**Never fetch the PDF yourself and quote from your own parse of it.** Quotes
validate only against `source/<id>.txt`, which `ingest.py` already produced
with `pdfminer.six`. Any other extraction of the same PDF will disagree on line
breaks, ligatures, and hyphenation, so every quote will fail validation for
reasons that look like fabrication but are really just a mismatched extraction.
Always read from the committed `.txt`, never from the PDF.

Copy blockquotes character for character. Do not fix the source's grammar,
expand abbreviations, merge sentences, or add an ellipsis — any of those breaks
the exact-substring check.

### Step 5 — repairing validation failures

```bash
python data/scripts/import_draft.py --scheme <slug> --repair
```

This prints, per failing clause, the real source text nearest your quote. Use
it to re-quote exactly. If nothing similar exists anywhere in the source, the
clause isn't a formatting problem — it's unsupported. **Delete it.** Don't
approximate, don't reconstruct from memory, don't lower your standard for what
counts as a match.

### Step 6 — rule conditions

Restricted grammar only: `profile.<attr>`, `== != < <= > >=`, `and or not`, `in
[...]`, literals. No function calls, no arithmetic, no subscripts — this is
enforced by an AST whitelist in `data/scripts/grammar.py`, not by convention.
`python data/scripts/validate.py` will reject anything outside it, with the
exact reason.

Exclusion clauses get **negated** conditions: "income tax payers are excluded"
becomes `profile.paid_income_tax_last_year == false` (must be false to
qualify).

### Attribution

Every gate decision is recorded with a reviewer name. Set this once per
session so `review.py` records your operator correctly rather than falling
back to a generic OS username:

```bash
export GOVASSIST_REVIEWER="their actual name"
```

## Commands reference

```bash
pip install -e ".[dev]"                                  # one-time setup
pytest -q                                                 # full suite, offline
pytest -q -k Fabricated                                   # the meta-test

python data/scripts/ingest.py --scheme <slug> --url URL   # Gates 0-2, needs network
python data/scripts/ingest.py --scheme <slug> --file PDF  # Gates 0-2, no network
python data/scripts/segment.py --scheme <slug> --emit     # Gate 3

python data/scripts/import_draft.py --scheme <slug>            # validate a draft
python data/scripts/import_draft.py --scheme <slug> --repair   # + paste-back-style report

python data/scripts/review.py --scheme <slug>              # Gate 4, interactive
python data/scripts/review.py --scheme <slug> --conditions # Gate 5, interactive
python data/scripts/review.py --scheme <slug> --status     # progress only, no gate

python data/scripts/validate.py --scheme <slug>            # all acceptance checks
python data/scripts/validate.py --all                      # every scheme
python data/scripts/build.py --scheme <slug>                # rules/graph/clauses
python data/scripts/build.py --all --check                 # CI: fails if stale
python data/scripts/diff_rules.py --scheme <slug> --from 1 --to 2
```

## Never do these

- Never write an eligibility rule, threshold, or date from your own knowledge
  instead of the source document.
- Never loosen or bypass `normalize.py`'s exact-substring check — no fuzzy
  matching, no threshold, no "close enough."
- Never edit `.state.json` to mark a gate or clause approved.
- Never pipe a fabricated answer into an interactive gate prompt.
- Never hand-edit anything under `build/` — it's generated; edit `scheme.md`
  and re-run `build.py`.
- Never delete or "fix" `tests/fixtures/fabricated-scheme/` to make it pass —
  it is supposed to fail; that failure is the proof the system works.
- Never set `network_access = true` more broadly than the single `ingest.py`
  step needs it.

## If you get stuck

`.claude/skills/govassist-corpus/references/troubleshooting.md` covers the
common span-validation failures and their real causes (copied from a PDF
viewer instead of the `.txt`, a tidied quote, a column-break artifact, a
destroyed table) — read it before concluding a quote is unfixable.
