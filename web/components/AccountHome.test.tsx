import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AccountHome } from "./AccountHome";
import { setToken } from "@/lib/family";
import { AccountError } from "@/lib/account";

const mocks = vi.hoisted(() => ({ register: vi.fn(), login: vi.fn(), interview: vi.fn(), dashboard: vi.fn(), answer: vi.fn(), callback: vi.fn() }));
vi.mock("@/lib/account", async original => ({ ...(await original<typeof import("@/lib/account")>()), account: mocks }));
const question = { attribute: "age", kind: "number", ask: "How old are you?", help: null, unit: "years", options: [], integer: true, minimum: 0, satisfied_by: null, warn_if_yes: false };
const state = { profile: {}, question, progress: { answered: 0, remaining: 10 }, verdicts: {} };
const dashboard = { name: "Asha", phone: "+919000000001", profile: {}, profile_questions: [question], schemes: [], calls: [] };

beforeEach(() => {
  setToken(null); vi.resetAllMocks();
  mocks.interview.mockResolvedValue(state); mocks.dashboard.mockResolvedValue(dashboard);
});
afterEach(() => { cleanup(); setToken(null); });

it("sets the password in the same signup as the name and phone number", async () => {
  mocks.register.mockResolvedValue({ token: "signed-in" });
  render(<AccountHome />);
  fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "Asha" } });
  fireEvent.change(screen.getByLabelText("Phone number"), { target: { value: "9000000001" } });
  fireEvent.change(screen.getByLabelText(/Password/), { target: { value: "my-test-password" } });
  fireEvent.click(screen.getByRole("button", { name: "Create account" }));
  await screen.findByText("How would you like to fill your profile?");
  expect(mocks.register).toHaveBeenCalledWith("Asha", "9000000001", "my-test-password", "en");
});

it("requires explicit callback consent and exposes provider failure", async () => {
  setToken("signed-in"); mocks.callback.mockRejectedValue(new Error("Calling is not configured"));
  render(<AccountHome />);
  const button = screen.getByRole("button", { name: "Call me back" }) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  fireEvent.click(screen.getByRole("checkbox")); fireEvent.click(button);
  await screen.findByRole("alert");
  expect(screen.getByText("Calling is not configured")).toBeTruthy();
  expect(mocks.callback).toHaveBeenCalledWith(true, "en");
});

it("removes the previous success notice when a later callback fails", async () => {
  setToken("signed-in");
  mocks.callback.mockResolvedValueOnce({ id: 1, status: "requested" })
    .mockRejectedValueOnce(new AccountError("Denied", 503, "CALLBACK_PROVIDER_ACCESS_DENIED"));
  render(<AccountHome />);
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "Call me back" }));
  await screen.findByText(/Your callback was requested/);
  await waitFor(() => expect((screen.getByRole("button", { name: "Call me back" }) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button", { name: "Call me back" }));
  await screen.findByText(/No callback was confirmed/);
  expect(screen.queryByText(/Your callback was requested/)).toBeNull();
});

it("keeps callback success translated when the language changes", async () => {
  setToken("signed-in"); mocks.callback.mockResolvedValue({ id: 1, status: "requested" });
  render(<AccountHome />);
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "Call me back" }));
  await screen.findByText(/Your callback was requested/);
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "hi" } });
  expect(screen.getByText(/कॉल का अनुरोध भेज दिया गया है/)).toBeTruthy();
  expect(screen.queryByText(/Your callback was requested/)).toBeNull();
});

it("explains calling access failure in Hindi without a success notice", async () => {
  setToken("signed-in"); mocks.callback.mockRejectedValue(new AccountError("Denied", 503, "CALLBACK_PROVIDER_ACCESS_DENIED"));
  render(<AccountHome />);
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "hi" } });
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "मुझे कॉल करें" }));
  await screen.findByText(/कॉल की पुष्टि नहीं हुई है/);
  expect(screen.queryByText(/कॉल का अनुरोध भेज दिया गया है/)).toBeNull();
});

it("saves a typed answer and advances using the question returned by the server", async () => {
  setToken("signed-in");
  mocks.answer.mockResolvedValue({ ...state, profile: { age: 30 }, question: { ...question, attribute: "is_street_vendor", kind: "boolean", ask: "Do you sell on the street?" }, progress: { answered: 1, remaining: 9 } });
  render(<AccountHome />);
  fireEvent.click(screen.getByRole("button", { name: "Fill it myself" }));
  await screen.findByRole("spinbutton");
  fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "30" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await screen.findByRole("heading", { name: "Do you sell on the street?" });
  expect(mocks.answer).toHaveBeenCalledWith({ age: 30 }, [], "en");
});

it("skips an uncertain answer without submitting a guessed value", async () => {
  setToken("signed-in"); mocks.answer.mockResolvedValue({ ...state, question: null });
  render(<AccountHome />);
  fireEvent.click(screen.getByRole("button", { name: "Fill it myself" }));
  await screen.findByRole("spinbutton");
  fireEvent.click(screen.getByRole("button", { name: /skip for now/ }));
  await screen.findByText(/reached the end/);
  expect(mocks.answer).toHaveBeenCalledWith({}, ["age"], "en");
});

it("shows quoted rules, missing document gaps and unverified call answers", async () => {
  setToken("signed-in"); mocks.dashboard.mockResolvedValue({ ...dashboard, schemes: [{
    scheme: "test", name: "Example scheme", verdict: "ELIGIBLE", reviewed: false, missing_questions: [],
    citations: [{ clause_id: "rule", quote: "Exact official rule", source_url: "https://example.gov.in/rules", page: 1 }],
    failed_citations: [], documents: [], documents_available: false,
  }], calls: [{ id: 1, status: "completed", locale: "en", created_at: "2026-10-14T10:00:00Z", transcript: [{ who: "agent", text: "Your age?" }, { who: "caller", text: "not sure" }], heard: { age: "not sure" }, answers: {} }] });
  render(<AccountHome />);
  fireEvent.click(screen.getByRole("button", { name: "View dashboard" }));
  await waitFor(() => expect(screen.getByText("Exact official rule")).toBeTruthy());
  expect(screen.getByText(/Document requirements are unavailable/)).toBeTruthy();
  expect(screen.getByText(/Not verified/)).toBeTruthy();
  expect(screen.getByText("Your age?")).toBeTruthy();
});
