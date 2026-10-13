# Account profile and general interview

The homepage `/` provides name + phone + password signup and phone + password
login. After signing in, choose **Call me back** or **Fill it myself**. The
previous anonymous per-scheme chat remains at `/schemes`; family records use
the same session token. The new account interface supports English and Hindi.

Both paths persist answers in `User.profile_json`, use the same committed
attribute input domains, and evaluate every available scheme with `decide()`.
There are no new eligibility conditions or thresholds in this feature. The
general interview asks common facts first, then relevant scheme openers and
follow-ups. A scheme already ruled out stops contributing questions. Skipping
an answer leaves it unknown and does not save a guessed value; returning to
the interview revisits skipped questions. Saved answers can be corrected from
the dashboard. Changes merge into the profile rather than replacing other
answers.

## Account API

All endpoints below require `Authorization: Bearer <session token>`.

| Endpoint | Purpose |
| --- | --- |
| `GET /account/interview?locale=en` | Resume the next relevant question |
| `POST /account/interview` | Validate and merge `answers`, then return the next question; optional `skipped` lists questions to defer this session |
| `POST /account/callback` | Request a general interview for the account's phone; requires `consent: true`, with `locale: en` or `hi` |
| `GET /account/dashboard?locale=en` | All scheme results, exact rule citations, missing questions, source-backed documents, saved questions and call history |

`PUT /auth/profile` also validates attributes and merges answers. The server
rejects unknown attributes, malformed types, fractional ages and values outside
the existing input domains. These are answer validation checks, not scheme
eligibility rules.

## Callback setup

For local accounts set `JWT_SECRET`; SQLite is used by default. Hosted accounts
need a persistent `DATABASE_URL`. The frontend uses `NEXT_PUBLIC_API_BASE` for
the backend URL, which must allow the frontend origin through CORS.
Vercel builds default to `https://govassist-api-ronit-khannas-projects.vercel.app`
when that setting is absent or blank; local builds default to port 8000 on
`127.0.0.1`. Set an explicit preview API URL to isolate preview accounts from
production. A Vercel build rejects a localhost override. Public API settings
are embedded in the browser bundle, so changing them requires a new deployment.

Callbacks additionally require:

- `BLAND_API_KEY`
- `VOICE_ALLOWED_NUMBERS`: existing allowlist, including the account's number
- `VOICE_WEBHOOK_URL`: HTTPS public URL ending in `/voice/webhook`
- `VOICE_WEBHOOK_SECRET`: shared callback/tool token
- `GROQ_API_KEY`: used to locate caller quotes in transcripts after the call
- Optional `VOICE_ASK_URL` and `BLAND_INTERVIEW_MAX_MINUTES` (default 10;
  allowed 1–30). The older single-scheme call keeps its separate 4-minute cap.

If Bland returns 401 or 403, no callback is confirmed. Failed attempts stay in
call history. The API returns `CALLBACK_PROVIDER_ACCESS_DENIED`, the provider
status and the failed operation (for example `GET /tools` or `POST /calls`),
and logs that operation and the selected locale without keys, tool URLs or the
full provider response body. The warning includes a bounded provider error
message, with configured secrets, URLs, email addresses and phone numbers
redacted. For a non-JSON denial it reports the response content type and HTML
title, without logging the HTML page. Hindi uses `language: hi` and English uses `en-IN`;
both are documented Bland language codes. Each locale provisions separate
tools, so working English tools do not prove Hindi tool creation succeeds.
An operator must check the production `BLAND_API_KEY` against the Bland account
and its access to that operation. A configured key alone does not prove access.
The secret-gated `/voice/check` can check account access without placing a call;
it also provisions the scheme-information tool. A denial during tool setup must
be resolved before calling, since the interview needs grounded server tools.

The calling provider receives the general interview script, the grounded
scheme-information tool, and the end-of-call eligibility tool. At the end the
agent posts the caller's spoken answers to `/voice/eligibility`; the server
parses them, evaluates the rules and returns the fixed result to read aloud.
This tool does not write the profile. If the provider truncates a call or fails
to use the tool, an on-call result cannot be guaranteed; the dashboard exposes
the remaining missing answers. Test the actual provider before rollout.

A call record is created before contacting the provider. Provider metadata
carries that record ID so a fast webhook can find it before the provider call
ID is returned. Failed requests are recorded and can be retried. Requests are
rate-limited and a second callback is refused while one is pending.

After the call, `/voice/webhook` verifies the shared token and binds the
provider call to the existing record. It keeps the agent/caller transcript,
caller quotes and accepted values. Model-extracted words must appear in a
caller turn; deterministic parsing and input-domain validation then decide
which values enter the profile. Ambiguous answers remain in call history but
stay out of the profile. A duplicate completed webhook is ignored so retries
cannot overwrite a subsequent website correction. Unrequested calls cannot
create records using a supplied user ID. Dashboard history is limited to the
signed-in account. Provider audio recording remains disabled.

## Validation and limits

`tests/api/test_onboarding.py` covers authentication, interview resume/skip,
conditional questions, input validation, engine parity, callback consent and
tools, failures/retry, transcript verification, account isolation and webhook
replay. `web/components/AccountHome.test.tsx` covers signup, consent/errors,
answer advancement, skipping and dashboard evidence.

Only schemes with committed rule packs are assessed. Missing document clauses
are explicitly shown as unavailable rather than filled from general knowledge.
Existing human review warnings remain visible. Live phone delivery, provider
tool invocation and hosted database behavior require configured integration
testing; local tests use mocked calling and language providers.
