import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AnswerField, Pending } from "@/lib/api";
import { makeTranslator } from "@/lib/i18n";
import { AnswerControls, parseAnswerNumber } from "./AnswerControls";

afterEach(cleanup);

const workers: AnswerField = {
  attribute: "worker_count", kind: "number", satisfied_by: null, options: [],
  comparator: "<", bound: 10, ask: "How many people work in your business?",
  help: null, unit: "people", warn_if_yes: false, integer: true, minimum: 0,
  maximum: null,
};

function renderNumber(field: AnswerField, locale: "en" | "hi" = "en") {
  const onValues = vi.fn();
  const pending: Pending = { condition_id: "c", asks: null, fields: [field] };
  render(<AnswerControls pending={pending} busy={false} onValues={onValues}
                         t={makeTranslator(locale)} />);
  const input = screen.getByRole("spinbutton");
  const send = (value: string) => {
    fireEvent.change(input, { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: makeTranslator(locale)("chat.send") }));
  };
  return { onValues, input, send };
}

describe("number answers", () => {
  it.each(["-5", "2.5"])("refuses %s people with a reason, sending nothing", (value) => {
    const { onValues, send, input } = renderNumber(workers);
    send(value);
    expect(onValues).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toBe(
      "Please enter a whole number, 0 or more.",
    );
    expect(input.getAttribute("aria-invalid")).toBe("true");
  });

  it("sends a valid count as a number, not a string", () => {
    const { onValues, send } = renderNumber(workers);
    send("12"); // ineligible (< 10 fails), but a perfectly valid answer
    expect(onValues).toHaveBeenCalledWith({ worker_count: 12 }, "12 people");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("constrains the control itself for whole-number fields", () => {
    const { input } = renderNumber(workers);
    expect(input.getAttribute("step")).toBe("1");
    expect(input.getAttribute("min")).toBe("0");
    expect(input.getAttribute("inputmode")).toBe("numeric");
  });

  it("explains a percentage range in the person's language", () => {
    const percent: AnswerField = { ...workers, attribute: "own_contribution_percent",
      integer: false, minimum: 0, maximum: 100, unit: "percent" };
    const { onValues, send } = renderNumber(percent, "hi");
    send("150");
    expect(onValues).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toBe("कृपया 0 से 100 के बीच की संख्या लिखें।");
  });
});

describe("parseAnswerNumber", () => {
  it.each([
    ["", null], ["abc", null], ["1e3", null], ["Infinity", null], ["-0.5", null],
    ["7", 7], ["0", 0], ["10.0", 10],
  ])("%s -> %s", (raw, expected) => {
    expect(parseAnswerNumber(raw, workers)).toBe(expected);
  });
});

describe("yes/no answers", () => {
  it("answers the attribute on screen, not the whole condition", () => {
    const onValues = vi.fn();
    const field: AnswerField = { ...workers, attribute: "is_unincorporated",
      kind: "boolean", unit: null, integer: false, minimum: null };
    render(<AnswerControls pending={{ condition_id: "c", asks: null, fields: [field] }}
                           busy={false} onValues={onValues} t={makeTranslator("en")} />);
    fireEvent.click(screen.getByRole("button", { name: "No" }));
    expect(onValues).toHaveBeenCalledWith({ is_unincorporated: false }, "No");
  });
});
