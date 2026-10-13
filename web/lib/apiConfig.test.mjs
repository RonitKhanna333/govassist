import assert from "node:assert/strict";
import test from "node:test";
import { HOSTED_API_BASE, LOCAL_API_BASE, resolveApiBase } from "./apiConfig.mjs";

test("local development defaults to the local API", () => {
  assert.equal(resolveApiBase({}), LOCAL_API_BASE);
});

test("Vercel builds without an API setting use the stable hosted API", () => {
  assert.equal(resolveApiBase({ VERCEL: "1" }), HOSTED_API_BASE);
  assert.equal(resolveApiBase({ VERCEL: "1", NEXT_PUBLIC_API_BASE: "  " }), HOSTED_API_BASE);
});

test("explicit environment targets override the default, including previews", () => {
  const preview = "https://govassist-api-git-feature-ronit-khannas-projects.vercel.app";
  assert.equal(resolveApiBase({ VERCEL: "1", NEXT_PUBLIC_API_BASE: ` ${preview} ` }), preview);
  assert.equal(resolveApiBase({ NEXT_PUBLIC_API_BASE: "http://localhost:9000" }), "http://localhost:9000");
});

test("Vercel refuses a loopback override instead of shipping a broken client", () => {
  for (const host of ["127.0.0.1", "localhost", "[::1]"]) {
    assert.throws(() => resolveApiBase({ VERCEL: "1", NEXT_PUBLIC_API_BASE: `http://${host}:8000` }), /hosted API/);
  }
});
