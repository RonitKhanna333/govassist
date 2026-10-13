import { API_BASE, type AnswerField, type Citation, type Verdict } from "./api";
import { getToken } from "./family";

export type AccountLocale = "en" | "hi";
export interface InterviewState {
  profile: Record<string, unknown>;
  question: AnswerField | null;
  progress: { answered: number; remaining: number };
  verdicts: Record<string, Verdict>;
}
export interface SchemeResult {
  scheme: string;
  name: string;
  verdict: Verdict;
  reviewed: boolean;
  citations: Citation[];
  failed_citations: Citation[];
  missing_questions: AnswerField[];
  documents: Citation[];
  documents_available: boolean;
}
export interface CallRecord {
  id: number;
  status: string;
  locale: string;
  created_at: string;
  completed_at: string | null;
  transcript: { who: "agent" | "caller"; text: string }[];
  heard: Record<string, unknown>;
  answers: Record<string, unknown>;
}
export interface Dashboard {
  name: string | null;
  phone: string | null;
  profile: Record<string, unknown>;
  profile_questions: AnswerField[];
  schemes: SchemeResult[];
  calls: CallRecord[];
}
export class AccountError extends Error {
  constructor(message: string, public status: number, public code?: string) { super(message); }
}
async function request<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const token = getToken();
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store", signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new AccountError("Couldn't reach the server. Please try again.", 0);
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({})) as { detail?: unknown };
    if (data.detail && typeof data.detail === "object" && "message" in data.detail) {
      const detail = data.detail as { message?: unknown; code?: unknown };
      throw new AccountError(typeof detail.message === "string" ? detail.message : "The request failed.",
        response.status, typeof detail.code === "string" ? detail.code : undefined);
    }
    throw new AccountError(typeof data.detail === "string" ? data.detail : "Please check your answers and try again.", response.status);
  }
  return response.json() as Promise<T>;
}
export const account = {
  register: (display_name: string, phone: string, password: string, locale: AccountLocale) =>
    request<{ token: string }>("/auth/register", { display_name, phone, password, locale }),
  login: (phone: string, password: string) => request<{ token: string }>("/auth/login", { phone, password }),
  interview: (locale: AccountLocale, signal?: AbortSignal) => request<InterviewState>(`/account/interview?locale=${locale}`, undefined, signal),
  answer: (answers: Record<string, unknown>, skipped: string[], locale: AccountLocale) =>
    request<InterviewState>("/account/interview", { answers, skipped, locale }),
  callback: (consent: boolean, locale: AccountLocale) =>
    request<{ id: number; status: string }>("/account/callback", { consent, locale }),
  dashboard: (locale: AccountLocale, signal?: AbortSignal) => request<Dashboard>(`/account/dashboard?locale=${locale}`, undefined, signal),
};
