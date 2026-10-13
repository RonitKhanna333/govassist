import { afterEach, expect, it, vi } from "vitest";
import { account } from "./account";

afterEach(() => vi.unstubAllGlobals());

it("preserves the provider error code from the callback response", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
    detail: { code: "CALLBACK_PROVIDER_ACCESS_DENIED", message: "Calling access denied",
      provider_status: 403, provider_operation: "GET /tools" },
  }), { status: 503 })));
  await expect(account.callback(true, "hi")).rejects.toMatchObject({
    message: "Calling access denied", status: 503, code: "CALLBACK_PROVIDER_ACCESS_DENIED",
  });
});
