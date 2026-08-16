# Span validation failures and what actually causes them

The validator reports three outcomes per quote:

| Status | Meaning |
|---|---|
| `exact` | matched under standard normalization — an unambiguous pass |
| `loose` | matched only after also ignoring hyphens and spaces — flagged for a human |
| `missing` | not present in the source — rejected |

Normalization already folds the differences that don't matter: Unicode NFKC,
soft hyphens, curly quotes and dashes, line-break hyphenation (`instal-\nments`
→ `instalments`), collapsed whitespace, and letter case. So a `missing` result
means the text genuinely differs.

## The one rule for fixing failures

**Fix the quote, or fix the `.txt`. Never loosen the check.**

`normalize.py` is the guarantee. Editing it to make a failure disappear removes
the only thing standing between the corpus and confident nonsense. If you find
yourself reaching for fuzzy matching or an edit-distance threshold, stop — the
answer is somewhere below.

## Causes, most common first

### 1. Quoted from the PDF viewer instead of the `.txt`

By far the most common. A PDF viewer's copy-paste and pdfminer's extraction
disagree on ligatures, spacing and column order.

**Fix:** copy from `source/<id>.txt`. That file is the validation target;
nothing else counts.

### 2. The drafter tidied the quote

Models fix grammar by reflex — expanding "Govt." to "Government", correcting an
odd comma, joining two sentences, or adding an ellipsis where they trimmed.

**Fix:** re-quote verbatim. Add the instruction explicitly if it keeps
happening: *do not fix the source's grammar or expand abbreviations.*

### 3. The quote spans a column or page break

pdfminer reads a two-column layout in visual order, so text that looks
contiguous in the PDF may be interleaved in the `.txt`.

**Fix:** look at the `.txt` around the passage and quote what is actually
contiguous there. If a rule is genuinely split, quote the part that carries it,
or hand-repair the `.txt` (see below).

### 4. The table was destroyed by extraction

Income slabs and benefit tables often survive as unusable column soup.

**Fix:** hand-repair **the `.txt`** into readable lines, and set
`hand_corrected: true` in `source/<id>.meta.json`. This is legitimate and
reviewable — you are correcting a bad extraction of a document you hold. Never
reword the quote to match broken extraction; that inverts the direction of
truth.

### 5. It was written from memory

If `find_context` reports nothing similar anywhere in the document, the text
isn't a mangled quote — it isn't in the document at all.

**Fix:** delete the clause. Do not reconstruct it from another source, do not
approximate it. If the rule really exists, it is in some document; ingest that
document and cite it properly.

### 6. Wrong source cited

The clause's `source:` names a different document than the one the quote came
from.

**Fix:** correct the `source:` field, or ingest the missing document and add it
to the frontmatter.

## Reading a `loose` match

A `loose` result means the quote and source differ only in hyphenation or
spacing — `Land holders` vs `Landholders`. Almost always a PDF artifact, and
almost always fine.

Check it anyway: confirm no word was actually changed. Then accept it, or
tighten the quote to match the source exactly.

`import_draft.py --strict` treats `loose` as failure if you want the harder
standard.

## Debugging a specific quote

```python
import sys; sys.path.insert(0, "data/scripts")
from normalize import normalize, validate_quote, describe_failure

source = open("data/schemes/<slug>/source/<id>.txt", encoding="utf-8").read()
quote = "the text you are trying to use"

match = validate_quote(quote, source)
print(match.status, match.note)
print(describe_failure(quote, match))

# See exactly what the comparison sees:
print(repr(normalize(quote))[:300])
```

Comparing the two normalized strings usually makes the cause obvious in seconds
— a missing word, a changed digit, or a stray character that survived
normalization.

## Things that are never the answer

- Adding fuzzy or edit-distance matching to `normalize.py`
- Lowering a threshold so a near-miss passes
- Deleting the fabricated-scheme fixture because it "always fails" — it is
  supposed to; it is the proof the checks work
- Editing `build/` by hand
- Approving a gate to move past a failure
