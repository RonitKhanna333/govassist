# Family records

Several schemes are decided per family, not per person. PMFME allows only
one person per family; the question "has anyone in your family already taken
money from this scheme?" is the one most likely to be answered wrong, because
the person answering has to remember what their spouse or children received.

`/family` (page and API) lets a household record itself as a small graph.

## The model

* **Members** are nodes. A member either has their own account or is a plain
  record entered by a relative (a child, an elderly parent). A record has no
  login.
* **Relationships** are edges of two kinds only: `parent_of` and `spouse_of`.
  Child, sibling, grandparent, in-law and "relative" are derived by
  traversal, so the graph can't hold two edges that contradict each other.
  Cycles ("my child is my parent") and a third parent are refused.
* **Benefit records** say that a member already received a scheme, and who
  recorded it.

## Linked, not shared

* Accounts are linked; credentials are not. Nobody can sign in as anyone
  else, and no password, token or ID number is stored on the graph.
* An account joins a household only by redeeming an invite code itself.
  Codes are 8 characters to read out in person, single-use, expire in 7 days,
  and only a hash is stored.
* A member's saved answers are private unless they turn on sharing. A record
  for a relative without an account accepts only validated scheme attributes
  — no free text, nowhere to put an Aadhaar number.
* A member with their own account records their own benefits.
* Everything is scoped to the caller's household. Another family's member
  ids return 404, the same as ids that don't exist.
* Leaving unlinks your account and clears what was visible; the last account
  to leave deletes the household.

## How it reaches a verdict — it doesn't

Family records are **reminders**. In the chat, when the family question
comes up and you're signed in, a note says e.g. "Your family record says Sita
(your husband or wife) has already received this scheme." You still answer
the question. The rule engine decides only from what you confirmed.

Who counts as family comes from the scheme's own clause, not from this code.
PMFME's `individual-one-person-per-family` says *"The 'family' for this
purpose would include self, spouse and children"*, so a parent's or
father-in-law's subsidy does **not** produce a reminder. `FAMILY_RULES` in
`api/family/derive.py` records this, and a test fails if the clause stops
saying so.

`/family/eligibility` runs the normal `decide()` for every member whose
answers you may see, across every scheme. A private member shows as private,
not as "not eligible".

## Running it

Family records need a database and sign-in:

| Variable | Needed for |
| --- | --- |
| `DATABASE_URL` | Postgres in production (SQLite locally by default) |
| `JWT_SECRET` | signing sessions |

On Vercel without `DATABASE_URL` the endpoints return 503 and the page says
the database isn't configured — the rest of the app keeps working.

The page is in Hindi and English. Punjabi and Tamil haven't been translated
yet; the chat reminder is in all four languages.
