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


def route(query: str) -> RouteResult:
    lowered = query.lower()

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
