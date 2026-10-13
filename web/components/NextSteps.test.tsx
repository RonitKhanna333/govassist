import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { NextStep, NextSteps as Checklist } from "@/lib/api";
import { makeTranslator } from "@/lib/i18n";
import { NextSteps } from "./NextSteps";

afterEach(cleanup);

const SOURCE = "https://pmfme.mofpi.gov.in/newsletters/docs/SchemeGuidelines.pdf";

const step = (id: string, plain: string, quote: string): NextStep => ({
  clause_id: id, plain, quote, page: 26, source_url: SOURCE, uncertain: false,
});

const eligible: Checklist = {
  status: "eligible",
  sections: [
    { key: "benefits", items: [step("individual-capital-subsidy", "A 35% subsidy.", "35% of the eligible project cost")] },
    { key: "documents", items: [step("loan-documents-required", "Bring loan documents.", "lease/ownership documents of land")] },
  ],
  gaps: ["apply"],
  confirm: [{ kind: "review_pending" }],
  authority: "Ministry of Food Processing Industries",
  sources: [{ id: "scheme-guidelines", url: SOURCE }],
};

describe("NextSteps", () => {
  it("says what to do next, from official text, with the count of documents", () => {
    render(<NextSteps checklist={eligible} t={makeTranslator("en")} />);
    expect(screen.getByRole("heading", { name: "What should I do next?" })).toBeTruthy();
    expect(screen.getByText(/keep the documents below ready \(1\)/)).toBeTruthy();
    expect(screen.getByText("Bring loan documents.")).toBeTruthy();
    // The verbatim quote is available, unchanged, next to the step.
    expect(screen.getByText("lease/ownership documents of land")).toBeTruthy();
  });

  it("names the gap instead of inventing where to apply", () => {
    render(<NextSteps checklist={eligible} t={makeTranslator("en")} />);
    const gap = screen.getByRole("heading", { name: "Where and how to apply" }).parentElement!;
    expect(within(gap).getByText(/doesn't say where to apply/)).toBeTruthy();
    expect(within(gap).getByText(/Ministry of Food Processing Industries/)).toBeTruthy();
  });

  it("puts the confirmation first when a person hasn't checked the rules", () => {
    render(<NextSteps checklist={eligible} t={makeTranslator("en")} />);
    const note = screen.getByRole("note");
    expect(note.textContent).toMatch(/has not yet checked these rules/);
    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings[0]).toBe("Please confirm first");
  });

  it("links every step and the document itself to the official source, safely", () => {
    render(<NextSteps checklist={eligible} t={makeTranslator("en")} />);
    for (const link of screen.getAllByRole("link")) {
      expect(link.getAttribute("href")).toBe(SOURCE);
      expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    }
  });

  it("shows only what to check when not eligible", () => {
    const failed: Checklist = {
      ...eligible, status: "not_eligible", sections: [], gaps: [],
      confirm: [{ kind: "failed", ...step("individual-age-and-education", "Must be over 18.", "above 18 years of age") }],
    };
    render(<NextSteps checklist={failed} t={makeTranslator("en")} />);
    expect(screen.getByText(/don't appear to be eligible/)).toBeTruthy();
    expect(screen.getByText(/start over and correct it/)).toBeTruthy();
    expect(screen.queryByText("Documents to keep ready")).toBeNull();
  });

  it("renders in Hindi, keeping the official quote in its published language", () => {
    render(<NextSteps checklist={eligible} t={makeTranslator("hi")} />);
    expect(screen.getByRole("heading", { name: "अब मुझे क्या करना चाहिए?" })).toBeTruthy();
    expect(screen.getByText("lease/ownership documents of land").getAttribute("lang")).toBe("en");
  });
});
