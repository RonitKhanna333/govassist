"""Small serverless-safe guard for the public demo endpoints.

This is intentionally modest rather than pretending to be a distributed
quota service. Each function instance keeps a bounded fixed-window counter per
client IP. It protects a warm demo instance from accidental refresh loops and
is easy to test without a network or production secret. A deployment-level
limit is still recommended for a larger audience.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass


DEFAULT_LIMIT = 60
DEFAULT_WINDOW_SECONDS = 60.0


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after: int | None = None


class InMemoryRateLimiter:
    """Fixed-window counter with bounded state and an injectable clock."""

    def __init__(self, limit: int = DEFAULT_LIMIT,
                 window_seconds: float = DEFAULT_WINDOW_SECONDS,
                 clock=time.monotonic) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> RateLimitDecision:
        now = self._clock()
        with self._lock:
            # The dict is deliberately bounded to recently active keys. A
            # stale cleanup also keeps long-lived local dev processes tidy.
            cutoff = now - self.window_seconds
            self._windows = {
                client: (started, count)
                for client, (started, count) in self._windows.items()
                if started > cutoff
            }

            started, count = self._windows.get(key, (now, 0))
            if now - started >= self.window_seconds:
                started, count = now, 0

            if count >= self.limit:
                retry_after = max(1, int(self.window_seconds - (now - started) + 0.999))
                self._windows[key] = (started, count)
                return RateLimitDecision(False, 0, retry_after)

            count += 1
            self._windows[key] = (started, count)
            return RateLimitDecision(True, self.limit - count)

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()


def configured_limit() -> int:
    raw = os.environ.get("GOVASSIST_RATE_LIMIT", str(DEFAULT_LIMIT))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_LIMIT
    return value if value > 0 else DEFAULT_LIMIT


chat_rate_limiter = InMemoryRateLimiter(configured_limit())
