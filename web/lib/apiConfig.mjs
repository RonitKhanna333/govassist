export const HOSTED_API_BASE = "https://govassist-api-ronit-khannas-projects.vercel.app";
export const LOCAL_API_BASE = "http://127.0.0.1:8000";

/** Resolve at build time: deployed browsers cannot reach a developer's API. */
export function resolveApiBase(env = process.env) {
  const configured = env.NEXT_PUBLIC_API_BASE?.trim();
  const hosted = env.VERCEL === "1";
  const base = configured || (hosted ? HOSTED_API_BASE : LOCAL_API_BASE);
  if (hosted) {
    const url = new URL(base);
    if (url.hostname === "127.0.0.1" || url.hostname === "localhost" || url.hostname === "[::1]") {
      throw new Error("NEXT_PUBLIC_API_BASE must point to a hosted API on Vercel, not localhost.");
    }
  }
  return base;
}
