# The phone channel

A third way into the same conversation as the web app. The questions come
from `scheme.md`, the answers are parsed by `api/rules/spoken.py`, and the
verdict comes from `decide()` — the call only collects answers.

```
POST /voice/call      place a call that asks one scheme's questions
POST /voice/webhook   the provider posts what it heard -> verdict -> SMS
GET  /voice/script    the script and answer schema, to read before calling
GET  /voice/health    what is configured (never the keys)
```

This runs on the existing Vercel deployment: both endpoints are ordinary
HTTP requests. A websocket-based agent (Pipecat, LiveKit) would need a
long-running host instead; that is the main reason a platform is used here.

## What the call will and will not do

* It never says whether the person qualifies. The script forbids it, a test
  asserts the line is still in the prompt, and the verdict is computed after
  the call from the rule pack.
* It never asks for an OTP, Aadhaar, bank password or money.
* An answer that `spoken.py` cannot read is **not** recorded. It comes back
  in `unparsed`, the attribute stays unknown, and the SMS says the result
  could not be worked out. 8 kHz phone audio mishears numbers, and a guessed
  number flips a verdict.
* Every number is read back to the person for confirmation during the call.

## Environment

| Variable | What it does |
| --- | --- |
| `BLAND_API_KEY` | Bland AI key. Without it, `/voice/call` returns 503. |
| `VOICE_ALLOWED_NUMBERS` | Comma-separated E.164 numbers that may be called. **Empty means nobody**, by design. |
| `VOICE_WEBHOOK_URL` | Public URL of `/voice/webhook`. Without it the call still happens, but no SMS is sent. |
| `VOICE_WEBHOOK_SECRET` | Shared token appended to the webhook URL. Without it the webhook returns 503. |
| `BLAND_VOICE_HI` | Override the Hindi voice if the default name changes. |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` | SMS delivery. Without them the verdict is returned and logged but not texted. |

## Getting the keys

**Bland AI** (the calling agent — one key is enough to ring a phone)
1. Sign up at <https://app.bland.ai>.
2. Dashboard → **API Keys** → copy the key.
3. Set `BLAND_API_KEY`. The header is the raw key, not `Bearer <key>`.
4. The free tier covers a demo. Check the current allowance in the
   dashboard; it changes.

**Twilio** (only for the result SMS)
1. Sign up at <https://twilio.com/try-twilio>, verify your own phone.
2. Console home shows **Account SID** and **Auth Token**.
3. Get a number under **Phone Numbers → Buy a number**, or use the trial
   number. Trial accounts can only message numbers you have verified —
   which is what you want here anyway.
4. Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`.

**Alternatives, same shape** — `api/voice/bland.py` is the only file that
would change: Vapi (<https://dashboard.vapi.ai>, Bearer token,
`POST /call`) and Retell (<https://dashboard.retellai.com>, Bearer token,
`POST /create-phone-call`). Both run the conversation from a prompt and can
post a transcript to a webhook, so `read_answers()` and everything after it
is unchanged.

Set keys in Vercel → Project → Settings → Environment Variables, and in
`.env` for local work. Never commit them.

## Before you call anyone

Automated voice calls to Indian numbers are regulated: commercial
automated calling requires DLT registration, and calling numbers on the DND
registry can get a number blocked. `VOICE_ALLOWED_NUMBERS` is default-deny
so this cannot happen by accident, and `/voice/call` requires
`consent: true` in the request body as a record that the person agreed.

For a demo: put your own team's numbers in the allowlist and call those.
For real users the honest design is inbound — the person calls a helpline
number — which also sidesteps most of the above.

## Trying it without spending a call

The webhook is plain JSON, so the whole path can be replayed:

```bash
curl -s -X POST "http://localhost:8000/voice/webhook?token=$VOICE_WEBHOOK_SECRET" \
  -H 'Content-Type: application/json' \
  -d '{"call_id":"test","to":"+919000000000","metadata":{"scheme":"pmsby","locale":"hi"},
       "analysis":{"has_bank_or_post_office_account":"हाँ जी","age":30,
                   "consents_to_auto_debit":"हाँ"}}'
```

You get the verdict, the parsed profile, anything unparsed, and the exact
SMS text. `tests/api/test_voice.py` does the same for every scheme, both
verdicts, and the mishearing cases.

Read the script before the first real call:

```bash
curl -s "http://localhost:8000/voice/script?scheme=pmsby&locale=hi" | jq -r .task
```

## Placing a real call

```bash
curl -s -X POST http://localhost:8000/voice/call \
  -H 'Content-Type: application/json' \
  -d '{"scheme":"pmsby","locale":"hi","phone":"+919000000000","consent":true}'
```

Hindi and English only: those are the languages the voice path has been
tested in. Punjabi and Tamil are refused with 422 rather than half-working.
