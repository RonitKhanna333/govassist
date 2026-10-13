"""Onboarding: one general interview that builds a person's profile.

A person shouldn't have to know which scheme they might qualify for before
they can be asked anything. The interview asks what every scheme needs --
shared questions first (age, bank account), then each scheme's own block --
and drops a block as soon as an answer settles that scheme. Nothing about
the order is hand-written: it is derived from the committed rule packs, so
a new scheme joins the interview with no edits here.

Answers come from the web form or from a phone call, and both end up in the
same place: the person's saved profile, which the dashboard evaluates
against every scheme with the same `decide()` the chat uses.
"""
