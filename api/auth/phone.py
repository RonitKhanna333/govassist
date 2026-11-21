"""Issue one-time codes to the demo phones, and bind possession to a login."""
from __future__ import annotations

import argparse
import hashlib
import secrets
import time

from fastapi import HTTPException
from sqlalchemy import delete

from api.auth.models import PhoneCode, VerifiedPhone
from api.db import get_session_factory, init_db
from api.voice import bland


def issue_code(session, phone: str) -> str:
    phone = bland.check_number(phone)
    code = secrets.token_hex(8)
    session.merge(PhoneCode(phone=phone, digest=hashlib.sha256(code.encode()).hexdigest(),
                            expires_at=int(time.time()) + 900))
    return code


def is_verified(session, user_id: int, phone: str) -> bool:
    binding = session.get(VerifiedPhone, user_id)
    return binding is not None and binding.phone == phone


def consume_code(session, phone: str, code: str | None) -> None:
    if code:
        digest = hashlib.sha256(code.strip().lower().encode()).hexdigest()
        used = session.execute(delete(PhoneCode).where(
            PhoneCode.phone == phone, PhoneCode.digest == digest,
            PhoneCode.expires_at > int(time.time())))
        if used.rowcount == 1:
            return
    raise HTTPException(403, {"code": "PHONE_VERIFICATION_REQUIRED",
                              "message": "Enter the current verification code from the demo organiser."})


def main():
    parser = argparse.ArgumentParser(description="Issue a 15-minute code for an allowed demo phone.")
    parser.add_argument("phone", help="Phone number in E.164 format")
    args = parser.parse_args()
    init_db()
    with get_session_factory().begin() as session:
        code = issue_code(session, args.phone)
    print(code)


if __name__ == "__main__":
    main()
