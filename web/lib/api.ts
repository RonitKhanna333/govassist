/** Typed client for the FastAPI backend. */

import type { LocaleCode } from "./registry";

const BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export interface Citation {
  clause_id: string;
  quote: string;
  plain: string;
  source_url: string;
  page: number | null;
}

export type Verdict = "ELIGIBLE" | "NOT_ELIGIBLE" | "INSUFFICIENT_INFO";

export interface SpeechPlan {
  chunks: string[];
  /** Which rung of the fallback ladder: provider audio, the browser's own
   *  voice, or no voice at all for this language on this device. */
  rung: "provider" | "browser" | "text_only";
  bcp47: string | null;
  note: string | null;
}

export interface AnswerField {
  attribute: string;
  kind: "boolean" | "number" | "choice";
  satisfied_by: unknown;
  options: unknown[];
  comparator: string | null;
  bound: number | null;
  /** Plain-language question from data/attributes.json. The technical
   *  wording lives in `Pending.asks` and is for reviewers, not applicants. */
  ask: string | null;
  /** Explains any term someone would have no reason to know (ODOP, SLUP). */
  help: string | null;
  unit: string | null;
  warn_if_yes: boolean;
}

/** The question being asked, plus what would actually answer it. Derived
 *  server-side from the rule expression, so the client never has to guess
 *  which attribute a "Yes" referred to. */
export interface Pending {
  condition_id: string;
  asks: string | null;
  fields: AnswerField[];
}

export interface ChatResponse {
  domain: string;
  supported: boolean;
  verdict: Verdict | null;
  answer: string | null;
  next_question: string | null;
  missing_attributes?: string[];
  pending: Pending | null;
  citations: Citation[];
  profile: Record<string, unknown>;
  /** The same answers in words a person recognises -- never a raw attribute
   *  name, never the __other__ sentinel. */
  profile_summary?: { attribute: string; label: string; value: string }[];
  locale: LocaleCode;
  /** Set when the answer was degraded -- e.g. translation rejected because
   *  it altered a number. The UI shows this rather than hiding it. */
  language_note: string | null;
  speech: SpeechPlan | null;
  /** What the helper says this turn, in order: maybe a greeting or a reply
   *  to the person's own question, then the next question or the verdict. */
  bot_messages?: string[];
  /** Set when the person asked something of their own this turn. */
  reply?: string | null;
  reply_citations?: Citation[];
  /** True when this turn recorded an answer to the question on screen. */
  acknowledged?: boolean;
}

export class ApiError extends Error {
  constructor(message: string, readonly offline = false) {
    super(message);
  }
}

async function post<T>(path: string, body: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError("offline", true);
  }
  if (!response.ok) {
    throw new ApiError(`${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function sendChat(input: {
  scheme: string;
  profile: Record<string, unknown>;
  message?: string;
  /** First turn: the helper greets before asking anything. */
  start?: boolean;
  /** Deterministic answer to the pending question -- no model call. */
  answer?: "yes" | "no";
  answers?: Record<string, unknown>;
  locale: LocaleCode;
  messageLocale?: LocaleCode;
}): Promise<ChatResponse> {
  return post<ChatResponse>("/chat", {
    scheme: input.scheme,
    profile: input.profile,
    message: input.message ?? "",
    start: input.start ?? false,
    answer: input.answer,
    answers: input.answers,
    locale: input.locale,
    message_locale: input.messageLocale ?? input.locale,
  });
}

export async function detectLocale(): Promise<string | null> {
  try {
    const response = await fetch(`${BASE}/detect-locale`);
    if (!response.ok) return null;
    const body = (await response.json()) as { locale: string };
    return body.locale;
  } catch {
    return null;
  }
}

/** Languages with voice input enabled. Mirrors VOICE_INPUT_LOCALES on the
 *  server -- Hindi (and English) for now, by decision. */
export const VOICE_INPUT_LOCALES: LocaleCode[] = ["en", "hi"];

export class TranscribeError extends Error {}

/** Send a recording to the server for Whisper transcription. */
export async function transcribe(audio: Blob, locale: LocaleCode): Promise<string> {
  let response: Response;
  try {
    response = await fetch(`${BASE}/transcribe?locale=${encodeURIComponent(locale)}`, {
      method: "POST",
      headers: { "Content-Type": audio.type || "audio/webm" },
      body: audio,
    });
  } catch {
    throw new ApiError("offline", true);
  }
  if (!response.ok) {
    let detail = `${response.status}`;
    try {
      detail = ((await response.json()) as { detail?: string }).detail ?? detail;
    } catch {
      /* keep the status code */
    }
    throw new TranscribeError(detail);
  }
  return ((await response.json()) as { text: string }).text;
}

/** Languages the server can speak aloud (Hindi and English, for now). */
export const VOICE_OUTPUT_LOCALES: LocaleCode[] = ["hi", "en"];

/** Server-side speech: MP3 audio for `text`. */
export async function speakAudio(text: string, locale: LocaleCode): Promise<Blob> {
  const response = await fetch(`${BASE}/speak`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, locale }),
  });
  if (!response.ok) throw new Error(`speak ${response.status}`);
  return response.blob();
}
