from __future__ import annotations

from api.rate_limit import InMemoryRateLimiter


def test_rate_limiter_allows_limit_then_returns_retry_after():
    now = [100.0]
    limiter = InMemoryRateLimiter(limit=2, window_seconds=10, clock=lambda: now[0])

    assert limiter.check("demo-client").allowed
    assert limiter.check("demo-client").remaining == 0
    blocked = limiter.check("demo-client")
    assert not blocked.allowed
    assert blocked.retry_after == 10

    now[0] = 110.1
    assert limiter.check("demo-client").allowed


def test_rate_limiter_keys_clients_independently():
    limiter = InMemoryRateLimiter(limit=1, window_seconds=10, clock=lambda: 100.0)
    assert limiter.check("first").allowed
    assert not limiter.check("first").allowed
    assert limiter.check("second").allowed
