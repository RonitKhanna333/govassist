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

from fastapi import HTTPException, Request


# A classroom can put several students behind one NAT/proxy address. Keep the
# warm-instance guard forgiving enough for a full guided flow by a small room;
# this is still only an accidental-refresh safeguard, not an access-control
# boundary.
DEFAULT_LIMIT = 180
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


def _env_limit(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def configured_limit() -> int:
    return _env_limit("GOVASSIST_RATE_LIMIT", DEFAULT_LIMIT)


chat_rate_limiter = InMemoryRateLimiter(configured_limit())

# Routes that spend provider quota (Whisper, TTS) or deliberately expensive
# CPU/memory (scrypt at ~64 MB per call) get their own, tighter buckets so a
# loop on one of them cannot exhaust the others. Same caveat as above: per
# warm instance, keyed on the connecting address -- see docs/deploy.md for
# the deployment-wide limit that must sit in front of this.
transcribe_rate_limiter = InMemoryRateLimiter(
    _env_limit("GOVASSIST_TRANSCRIBE_RATE_LIMIT", 20))
speak_rate_limiter = InMemoryRateLimiter(
    _env_limit("GOVASSIST_SPEAK_RATE_LIMIT", 30))
auth_rate_limiter = InMemoryRateLimiter(
    _env_limit("GOVASSIST_AUTH_RATE_LIMIT", 10))
probe_rate_limiter = InMemoryRateLimiter(
    _env_limit("GOVASSIST_PROBE_RATE_LIMIT", 5))

ALL_LIMITERS = (chat_rate_limiter, transcribe_rate_limiter, speak_rate_limiter,
                auth_rate_limiter, probe_rate_limiter)


def client_key(request) -> str:
    """The connecting address. Forwarded headers are deliberately not
    trusted: any client can set them, which would make the limit optional."""
    return request.client.host if request.client else "unknown"


def too_many(retry_after: int | None) -> HTTPException:
    return HTTPException(
        429,
        "This demo is receiving a lot of requests. Please wait and try again.",
        headers={"Retry-After": str(retry_after or 1)},
    )


def enforce(limiter: InMemoryRateLimiter):
    """A FastAPI dependency that answers 429 + Retry-After before the route
    does any work. Declare it first so it runs before other dependencies."""
    def dependency(request: Request) -> None:
        decision = limiter.check(client_key(request))
        if not decision.allowed:
            raise too_many(decision.retry_after)

    return dependency
