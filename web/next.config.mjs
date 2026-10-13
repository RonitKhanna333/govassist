import { resolveApiBase } from "./lib/apiConfig.mjs";

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Next 16 blocks cross-origin dev resources by default. Without this,
  // opening the dev server on 127.0.0.1 (rather than localhost) silently
  // breaks HMR, and a broken HMR client means hydration never completes --
  // which looks like "the buttons do nothing" rather than like a CORS error.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  // The generated AGENTS.md/CLAUDE.md would collide with the real ones at
  // the repo root, which are hand-written and carry the corpus gate rules.
  agentRules: false,
  // Embed the hosted default on Vercel even when the project setting is absent.
  // Explicit environment settings still support separate preview backends.
  env: {
    NEXT_PUBLIC_API_BASE: resolveApiBase(),
  },
};

export default nextConfig;
