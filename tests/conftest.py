"""Shared test isolation.

The rate limiters are process-wide on purpose (one per warm instance), and
every TestClient request comes from the same "testclient" address -- so
without a reset, one test's requests count against the next test's budget.
"""

from __future__ import annotations

import pytest

from api.rate_limit import ALL_LIMITERS


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    for limiter in ALL_LIMITERS:
        limiter.reset()
    yield
    for limiter in ALL_LIMITERS:
        limiter.reset()
