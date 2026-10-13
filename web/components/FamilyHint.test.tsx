import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { makeTranslator } from "@/lib/i18n";
import { generations, setToken, type FamilyGraph } from "@/lib/family";
import { FamilyHint } from "./FamilyHint";

const SUGGESTION = {
  suggestions: [{
    attribute: "family_member_already_received_assistance",
    value: true,
    clause: "individual-one-person-per-family",
    because: [{ member_id: 2, name: "Sita", relation: "spouse", scheme: "pmfme" }],
  }],
};

function mockFetch(body: unknown, ok = true, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue({ ok, status, json: async () => body });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => setToken(null));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  setToken(null);
});

describe("FamilyHint", () => {
  it("reminds the person what their family record says, with the source", async () => {
    setToken("t");
    mockFetch(SUGGESTION);
    render(
      <FamilyHint scheme="pmfme" t={makeTranslator("en")}
                  attributes={["family_member_already_received_assistance"]} />,
    );
    await waitFor(() =>
      expect(screen.getByText(/Sita \(your husband or wife\) has already received/)).toBeTruthy());
    // It is a reminder, not an answer.
    expect(screen.getByText(/Please answer the question yourself/)).toBeTruthy();
  });

  it("speaks Hindi", async () => {
    setToken("t");
    mockFetch(SUGGESTION);
    render(
      <FamilyHint scheme="pmfme" t={makeTranslator("hi")}
                  attributes={["family_member_already_received_assistance"]} />,
    );
    await waitFor(() => expect(screen.getByText(/आपके पति या पत्नी/)).toBeTruthy());
  });

  it("stays out of the way for a question it has nothing to say about", async () => {
    setToken("t");
    const fetchMock = mockFetch(SUGGESTION);
    const { container } = render(
      <FamilyHint scheme="pmfme" t={makeTranslator("en")} attributes={["age"]} />,
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(container.innerHTML).toBe("");
  });

  it("never calls the server when signed out", () => {
    const fetchMock = mockFetch(SUGGESTION);
    const { container } = render(
      <FamilyHint scheme="pmfme" t={makeTranslator("en")}
                  attributes={["family_member_already_received_assistance"]} />,
    );
    expect(fetchMock).not.toHaveBeenCalled();
    expect(container.innerHTML).toBe("");
  });

  it("shows nothing when there is no family record", async () => {
    setToken("t");
    mockFetch({ detail: "You are not in a household yet" }, false, 404);
    const { container } = render(
      <FamilyHint scheme="pmfme" t={makeTranslator("en")}
                  attributes={["family_member_already_received_assistance"]} />,
    );
    await new Promise((r) => setTimeout(r, 20));
    expect(container.innerHTML).toBe("");
  });
});

describe("generations", () => {
  const graph = (relations: FamilyGraph["relations"], ids: number[]): FamilyGraph => ({
    household: { id: 1, name: null },
    me: 1,
    members: ids.map((id) => ({
      id, name: `m${id}`, birth_year: null, relation: null, has_account: false,
      shares_profile: null, benefits: [],
    })),
    relations,
  });

  it("puts parents above, spouses beside and children below", () => {
    const rows = generations(graph([
      { from: 3, predicate: "parent_of", to: 1 },
      { from: 1, predicate: "spouse_of", to: 2 },
      { from: 1, predicate: "parent_of", to: 4 },
    ], [1, 2, 3, 4]));
    expect(rows.map((r) => r.map((m) => m.id))).toEqual([[3], [1, 2], [4]]);
  });

  it("keeps people with no link yet in a row of their own at the end", () => {
    const rows = generations(graph([], [1, 5]));
    expect(rows.map((r) => r.map((m) => m.id))).toEqual([[1], [5]]);
  });
});
