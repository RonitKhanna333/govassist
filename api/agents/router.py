"""Domain router: scheme | ITR (stub) | GST (stub).

Keyword-based, not LLM-based, and that's a scope decision worth stating
plainly rather than leaving implicit. docs/phase2-design.md describes the
NLU/router pair as both LLM-backed (fast tier); this implementation only
does that for the NLU slot-filler (nlu.py). The router stays a deterministic
heuristic here because there is exactly one domain with real data behind it
today (scheme) -- ITR and GST return the same "not yet supported" stub no
matter how a smarter router classified the query, so spending an LLM call
and a piece of free-tier budget on that classification buys nothing yet.
Revisit this the day a second domain has real rule packs to route to.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Domain(str, Enum):
    SCHEME = "scheme"
    ITR = "itr"
    GST = "gst"


@dataclass
class RouteResult:
    domain: Domain
    supported: bool
    message: str | None = None  # set when not supported, e.g. the ITR/GST stub text


_ITR_HINTS = ("itr", "income tax", "tax return", "tds", "form 16")
_GST_HINTS = ("gst", "gstr", "goods and services tax")

# Mentioning a tax is not asking for tax help. "I have never paid income tax"
# answers APY's own income-tax question; "Do I need GST registration for
# PMFME?" is a question about the scheme. Switching domain needs an actual
# request to file, register or claim something.
_FILING_INTENT = re.compile(
    r"\b(file|files|filed|filing|e-?file|return|returns|gstr-?\w*|itr-?\d+|"
    r"form\s*16|refund|register|registration)\b"
)
# Words that keep a message about the scheme even when it mentions a tax.
_SCHEME_CONTEXT = re.compile(
    r"\b(scheme|yojana|subsidy|grant|eligible|eligibility|qualify|benefit|"
    r"pension|insurance|loan|pmfme|apy|pmsby|pmjjby|pm-kmy)\b"
)


def has_filing_intent(lowered: str, scheme: str | None = None) -> bool:
    if not _FILING_INTENT.search(lowered):
        return False
    if _SCHEME_CONTEXT.search(lowered) or (scheme and scheme.lower() in lowered):
        return False
    return True


def route(query: str, scheme: str | None = None) -> RouteResult:
    """`scheme` is the scheme the person is in the middle of, if any."""
    lowered = query.lower()

    if not has_filing_intent(lowered, scheme):
        return RouteResult(domain=Domain.SCHEME, supported=True)

    if any(hint in lowered for hint in _ITR_HINTS):
        return RouteResult(
            domain=Domain.ITR, supported=False,
            message="Income tax filing help isn't available yet -- this scheme "
                    "eligibility assistant covers government schemes only for now.",
        )
    if any(hint in lowered for hint in _GST_HINTS):
        return RouteResult(
            domain=Domain.GST, supported=False,
            message="GST return help isn't available yet -- this scheme "
                    "eligibility assistant covers government schemes only for now.",
        )
    return RouteResult(domain=Domain.SCHEME, supported=True)
