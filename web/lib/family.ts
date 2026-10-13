import { useSyncExternalStore } from "react";
import { API_BASE } from "./api";

/** The household graph, as /family returns it. */
export interface FamilyMember {
  id: number;
  name: string;
  birth_year: number | null;
  /** How this person relates to you; null when not connected by an edge yet. */
  relation:
    | "self" | "spouse" | "child" | "parent" | "sibling" | "grandparent" | "grandchild"
    | "parent_in_law" | "child_in_law" | "relative" | null;
  has_account: boolean;
  shares_profile: boolean | null;
  benefits: string[];
}

export interface FamilyGraph {
  household: { id: number; name: string | null };
  me: number;
  members: FamilyMember[];
  relations: { from: number; predicate: "parent_of" | "spouse_of"; to: number }[];
}

export interface MemberEligibility {
  member_id: number;
  name: string;
  private: boolean;
  schemes: Record<string, "ELIGIBLE" | "NOT_ELIGIBLE" | "INSUFFICIENT_INFO">;
}

export class FamilyError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

const TOKEN_KEY = "govassist.token";

// sessionStorage: a shared phone at a service centre should not stay signed
// in after the tab closes. Wrapped because storage can throw (private mode).
export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

const TOKEN_EVENT = "govassist:token";

export function setToken(token: string | null): void {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* the session still works for this page load */
  }
  if (typeof window !== "undefined") window.dispatchEvent(new Event(TOKEN_EVENT));
}

function subscribeToken(onChange: () => void): () => void {
  window.addEventListener(TOKEN_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(TOKEN_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

/** The sign-in token, re-rendering on sign-in and sign-out. Null on the
 *  server, so the first render matches the static page. */
export function useToken(): string | null {
  return useSyncExternalStore(subscribeToken, getToken, () => null);
}

export type FamilyLoad =
  | { kind: "ok"; graph: FamilyGraph; eligibility: MemberEligibility[] }
  | { kind: "none" }
  | { kind: "signed_out" }
  | { kind: "error"; error: FamilyError };

/** Everything the family page shows, without touching component state. */
export async function loadFamily(): Promise<FamilyLoad> {
  try {
    const graph = await family.get();
    const { members } = await family.eligibility();
    return { kind: "ok", graph, eligibility: members };
  } catch (err) {
    const error = err instanceof FamilyError ? err : new FamilyError(String(err), -1);
    if (error.status === 404) return { kind: "none" };
    if (error.status === 401) return { kind: "signed_out" };
    return { kind: "error", error };
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init.headers ?? {}),
      },
    });
  } catch {
    throw new FamilyError("offline", 0);
  }
  if (!response.ok) {
    let detail = String(response.status);
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* keep the status */
    }
    throw new FamilyError(detail, response.status);
  }
  return (await response.json()) as T;
}

const post = <T,>(path: string, body: unknown) =>
  call<T>(path, { method: "POST", body: JSON.stringify(body) });

export const family = {
  register: (email: string, password: string) =>
    post<{ token: string }>("/auth/register", { email, password }),
  login: (email: string, password: string) =>
    post<{ token: string }>("/auth/login", { email, password }),
  get: () => call<FamilyGraph>("/family"),
  create: (myName: string, name?: string) =>
    post<FamilyGraph>("/family", { my_name: myName, name: name || null }),
  addMember: (name: string, relation: "spouse" | "child" | "parent" | null, birthYear?: number) =>
    post<FamilyGraph>("/family/members", {
      name,
      relation,
      birth_year: birthYear ?? null,
    }),
  invite: (memberId: number) =>
    post<{ code: string; expires_in_days: number }>("/family/invites", { member_id: memberId }),
  join: (code: string) => post<FamilyGraph>("/family/join", { code }),
  recordBenefit: (memberId: number, scheme: string) =>
    post<FamilyGraph>("/family/benefits", { member_id: memberId, scheme }),
  share: (share: boolean) =>
    call<FamilyGraph>("/family/sharing", { method: "PUT", body: JSON.stringify({ share }) }),
  eligibility: () => call<{ members: MemberEligibility[] }>("/family/eligibility"),
  leave: () => post<{ left: boolean }>("/family/leave", {}),
};

/** Lay members out in generations: parents above, children below. */
export function generations(graph: FamilyGraph): FamilyMember[][] {
  const level = new Map<number, number>([[graph.me, 0]]);
  const parentEdges = graph.relations.filter((r) => r.predicate === "parent_of");
  const spouseEdges = graph.relations.filter((r) => r.predicate === "spouse_of");

  // Breadth-first from you: a parent is one row up, a child one row down, a
  // spouse on the same row.
  const queue = [graph.me];
  while (queue.length) {
    const node = queue.shift()!;
    const here = level.get(node)!;
    const visit = (other: number, at: number) => {
      if (!level.has(other)) {
        level.set(other, at);
        queue.push(other);
      }
    };
    for (const r of parentEdges) {
      if (r.from === node) visit(r.to, here + 1);
      if (r.to === node) visit(r.from, here - 1);
    }
    for (const r of spouseEdges) {
      if (r.from === node) visit(r.to, here);
      if (r.to === node) visit(r.from, here);
    }
  }

  const rows = new Map<number, FamilyMember[]>();
  const unlinked: FamilyMember[] = [];
  for (const member of graph.members) {
    const at = level.get(member.id);
    if (at === undefined) unlinked.push(member);
    else rows.set(at, [...(rows.get(at) ?? []), member]);
  }
  const ordered = [...rows.keys()].sort((a, b) => a - b).map((k) => rows.get(k)!);
  return unlinked.length ? [...ordered, unlinked] : ordered;
}

export interface Suggestion {
  attribute: string;
  value: unknown;
  clause: string;
  because: { member_id: number; name: string; relation: string; scheme: string }[];
}

/** Family facts relevant to one scheme -- reminders, never answers. */
export async function familySuggestions(scheme: string): Promise<Suggestion[]> {
  const body = await call<{ suggestions: Suggestion[] }>(
    `/family/suggestions?scheme=${encodeURIComponent(scheme)}`,
  );
  return body.suggestions;
}
