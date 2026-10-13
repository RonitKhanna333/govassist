"""Households: family members linked as a graph.

Why this exists in an eligibility assistant: several schemes are decided per
FAMILY, not per person. PMFME allows one person per family; PM-KISAN counts
a family's land together. A person answering alone has to remember what
their spouse or parents already received -- and "has anyone in your family
already taken money from this scheme?" is the question most likely to be
answered wrong.

What "linked" means here, precisely:

* Each person keeps their own login. Accounts are linked, credentials are
  not -- no member can sign in as another, and no password, token or ID
  number is stored on the graph.
* Nobody is added to a household against their will. A member WITH an
  account joins only by redeeming an invite code themselves. A member
  without one (a child, an elderly parent) can be added as a record, and
  carries no login at all.
* A member's own saved answers stay private unless they choose to share
  them with the household.
* Family records never answer a question silently. They are offered to the
  person as a suggestion with its source ("your father recorded that he
  received PMFME"), and the person still answers. The rule engine decides
  only from what the person confirmed.
"""
