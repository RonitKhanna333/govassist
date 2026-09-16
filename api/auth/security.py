"""Password hashing and tokens.

Password hashing uses `hashlib.scrypt` from the standard library rather
than bcrypt or argon2. That's a deliberate trade, not a shortcut: scrypt is
memory-hard and well-regarded, and avoiding a compiled dependency keeps the
serverless bundle small and the build reproducible. The cost parameters
below are the interactive-login recommendations, not the defaults.

Two properties worth naming, because they're the ones that get quietly
wrong in hand-rolled auth:

* Every password gets its own 16-byte salt, stored alongside the hash. A
  shared or derived salt makes a rainbow table viable again.
* Verification uses `hmac.compare_digest`, not `==`. A plain comparison
  short-circuits on the first differing byte, which leaks hash prefix
  information through timing.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt

# Interactive-login parameters: ~64MB memory, well under a serverless
# function's limit, and slow enough to make offline cracking expensive.
_SCRYPT_N = 2 ** 15
_SCRYPT_R = 8
_SCRYPT_P = 1
_KEY_LEN = 32
_SALT_BYTES = 16

# scrypt needs 128 * N * r bytes = 32MB here, which is over OpenSSL's default
# cap, so the call fails with an opaque "memory limit exceeded" unless maxmem
# is raised explicitly. Doubling it rather than matching the formula exactly:
# OpenSSL wants headroom, and a maxmem equal to the theoretical minimum still
# fails. The alternative -- halving N to fit the default -- would weaken every
# password hash to work around an env var, which is the wrong trade.
_SCRYPT_MAXMEM = 128 * _SCRYPT_N * _SCRYPT_R * 2

TOKEN_TTL = timedelta(days=7)
ALGORITHM = "HS256"


class AuthConfigError(RuntimeError):
    """Raised when the signing secret is missing or unsafe."""


def jwt_secret() -> str:
    """The signing key. Never has a default.

    A hardcoded fallback secret is the single worst thing this file could
    do -- it would let anyone who reads this public repository mint a valid
    token for any account. Missing config fails loudly instead.
    """
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise AuthConfigError(
            "JWT_SECRET is not set. Generate one with "
            "`python -c \"import secrets; print(secrets.token_urlsafe(48))\"` "
            "and set it in the environment -- there is deliberately no default."
        )
    if len(secret) < 32:
        raise AuthConfigError("JWT_SECRET is too short; use at least 32 characters.")
    return secret


def hash_password(password: str) -> str:
    """Returns `scrypt$<salt_b64>$<hash_b64>` -- salt travels with the hash."""
    salt = os.urandom(_SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt,
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_KEY_LEN,
        maxmem=_SCRYPT_MAXMEM,
    )
    return "scrypt${}${}".format(
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(derived).decode("ascii"),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, TypeError):
        return False

    candidate = hashlib.scrypt(
        password.encode("utf-8"), salt=salt,
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=len(expected),
        maxmem=_SCRYPT_MAXMEM,
    )
    return hmac.compare_digest(candidate, expected)


def create_token(user_id: int, email: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "email": email,
            "iat": now,
            "exp": now + TOKEN_TTL,
            # A per-token id, so a future revocation list has something to
            # key on without invalidating every token at once.
            "jti": secrets.token_urlsafe(8),
        },
        jwt_secret(),
        algorithm=ALGORITHM,
    )


def decode_token(token: str) -> dict | None:
    """Returns the claims, or None for anything invalid.

    Expiry, signature and malformed tokens all collapse to None on purpose
    -- the caller's correct response is identical for all of them, and
    distinguishing them in an error message tells an attacker which part
    they got right.
    """
    try:
        return jwt.decode(token, jwt_secret(), algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
