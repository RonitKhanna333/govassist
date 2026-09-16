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
  locale: LocaleCode;
  /** Set when the answer was degraded -- e.g. translation rejected because
   *  it altered a number. The UI shows this rather than hiding it. */
  language_note: string | null;
  speech: SpeechPlan | null;
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
