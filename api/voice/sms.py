"""Sending the result by SMS, if an SMS provider is configured.

A call cannot show the quoted clause, so the message carries it. Twilio is
used because it is the one provider a student account can get working
without business KYC; any provider with an HTTP API would drop in here.

When nothing is configured this logs and reports "not_configured" rather
than failing the call: the verdict and its citation are still returned to
the caller of /voice/webhook, and losing the SMS must not look like losing
the result.
"""

from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)

# India's commercial-SMS rules (DLT templates, sender ids) apply to real
# traffic. For a demo this sends to the team's own numbers only, same as
# the calling allowlist.
TWILIO_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"


def send_sms(phone: str, body: str, timeout: float = 15.0) -> str:
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    sender = os.environ.get("TWILIO_FROM_NUMBER")
    if not (sid and token and sender):
        log.info("SMS not configured; result for %s not sent", phone)
        return "not_configured"

    try:
        response = requests.post(
            TWILIO_URL.format(sid=sid),
            auth=(sid, token),
            data={"To": phone, "From": sender, "Body": body},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        log.warning("SMS send failed: %s", exc)
        return "failed"

    if response.status_code >= 400:
        log.warning("SMS rejected (%s): %s", response.status_code, response.text[:200])
        return "rejected"
    return "sent"
