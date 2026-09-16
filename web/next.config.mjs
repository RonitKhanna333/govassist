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
  // The API base is read at runtime on the client, so the same build can be
  // promoted from local to staging to prod without a rebuild.
  env: {
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000",
  },
};

export default nextConfig;
