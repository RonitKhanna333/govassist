# The phone channel

A third way into the same conversation as the web app. The questions come
from `scheme.md`, the answers are parsed by `api/rules/spoken.py`, and the
verdict comes from `decide()` — the call only collects answers.

```
GET  /voice/check     free: key, credit balance, tools, Hindi voices -- no call
POST /voice/call      place a call that asks one scheme's questions
POST /voice/ask       called BY the agent mid-call when the person asks
                      something: a grounded, verified answer to speak
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
* If it can't hear, it says so the way a person would -- "माफ़ कीजिए जी, लाइन
  में आवाज़ थोड़ी कट गई" -- blaming the line, never the caller. After three
  tries it skips the question and leaves the answer blank.
* If the caller starts reading out an OTP, Aadhaar or account number, the
  agent stops them, tells them not to share it with anyone on the phone, and
  does not repeat it.
* If asked, it says honestly that it is an automated assistant.

## Answering questions on the call

The person can ask things mid-call ("मुझे कितने पैसे मिलेंगे?"). The agent
is given one tool, `scheme_info`, which posts the question to `/voice/ask`.
That endpoint answers exactly like the web chat: from the scheme's clauses
only, through the verifier, with "I don't have that information" when the
clauses don't cover it. The agent is told to say the answer as returned and
never answer from its own knowledge.

The tool is only attached when `VOICE_WEBHOOK_SECRET` is set -- otherwise
`/voice/ask` would be a free public LLM endpoint. Its URL defaults to the
webhook URL's sibling (`.../voice/ask`); set `VOICE_ASK_URL` to override.

Tool schemas differ slightly between Bland, Vapi and Retell, and the exact
field names in `api/voice/bland.py::scheme_info_tool` should be checked
against the provider's current docs before the first real call.

## Environment

| Variable | What it does |
| --- | --- |
| `BLAND_API_KEY` | Bland AI key. Without it, `/voice/call` returns 503. |
| `VOICE_ALLOWED_NUMBERS` | Comma-separated E.164 numbers that may be called. **Empty means nobody**, by design. |
| `VOICE_WEBHOOK_URL` | Public URL of `/voice/webhook`. Without it the call still happens, but no SMS is sent. |
| `VOICE_WEBHOOK_SECRET` | Shared token appended to the webhook and ask URLs. Without it the webhook returns 503 and the call can't answer questions. |
| `VOICE_ASK_URL` | Public URL of `/voice/ask`, if not next to the webhook. |
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

## Checked against Bland's API (October 2026)

An earlier version guessed at three fields and got them wrong; all three are
fixed and pinned by tests that mock Bland's documented responses:

* `language` is `"hi"` (or `"en-IN"`), not `"hin"`.
* There is no `analysis_schema` on `POST /v1/calls`. Answers are found in the
  transcript afterwards (`api/voice/extract.py`): a model may only *quote* the
  caller, every quote must appear verbatim in one of the caller's own turns,
  and then it goes through the same parser as a typed answer.
* `tools` takes tool IDs. The question tool is created once per scheme and
  language with `POST /v1/tools`, found again by name after a cold start, and
  re-created if its URL changed.

Calls are capped at `BLAND_MAX_MINUTES` (default 4) and wait for the person to
say hello first. Unanswered calls and voicemail send no SMS.

### Before spending credit

Open `/voice/check?token=<VOICE_WEBHOOK_SECRET>` on the API. It places no
call, and reports whether the key works, the credit balance, the question
tool's id (creating it if needed), Hindi-tagged voices, and anything missing.
`"ready": true` means a call can be placed.
