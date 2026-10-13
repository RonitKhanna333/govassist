import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatResponse, SchemeInfo } from "@/lib/api";

const api = vi.hoisted(() => ({
  listSchemes: vi.fn(),
  sendChat: vi.fn(),
  transcribe: vi.fn(),
  detectLocale: vi.fn(),
  speakAudio: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  ...api,
}));

import { Chat } from "./Chat";

const UNREVIEWED_NOTE = /a person has not checked them yet/;

const pmfme = (reviewed: boolean): SchemeInfo => ({
  id: "pmfme", name: "Food processing business support (PMFME)",
  name_en: "PMFME", authority: null, reviewed,
});

const asking: ChatResponse = {
  domain: "scheme", supported: true, verdict: "INSUFFICIENT_INFO", answer: null,
  next_question: "How old are you?",
  pending: { condition_id: "age", asks: null, fields: [{
    attribute: "age", kind: "number", satisfied_by: null, options: [],
    comparator: ">", bound: 18, ask: "How old are you?", help: null,
    unit: "years", warn_if_yes: false, integer: true, minimum: 0, maximum: null,
  }] },
  citations: [], profile: {}, profile_summary: [], locale: "en",
  language_note: null, speech: null, bot_messages: ["How old are you?"],
};

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  api.detectLocale.mockResolvedValue(null);
  api.sendChat.mockResolvedValue(asking);
  localStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("review status stays visible", () => {
  it("warns at scheme choice and again next to the result", async () => {
    api.listSchemes.mockResolvedValue([pmfme(false)]);
    render(<Chat />);
    await screen.findByText(UNREVIEWED_NOTE);

    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    await screen.findAllByText("How old are you?");
    expect(screen.getByText(UNREVIEWED_NOTE)).toBeTruthy();
  });

  it("only hides the warning when the server says the scheme is reviewed", async () => {
    api.listSchemes.mockResolvedValue([pmfme(true)]);
    render(<Chat />);
    await screen.findByText("Food processing business support (PMFME)");
    expect(screen.queryByText(UNREVIEWED_NOTE)).toBeNull();
  });

  it("treats an unreachable scheme list as unreviewed", async () => {
    api.listSchemes.mockResolvedValue([]);
    render(<Chat />);
    await waitFor(() => expect(api.listSchemes).toHaveBeenCalled());
    expect(screen.getByText(UNREVIEWED_NOTE)).toBeTruthy();
  });
});

describe("a recording that hits the 30-second cap is transcribed once", () => {
  it("sends the capped clip without the person pressing Stop", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    class FakeRecorder {
      static isTypeSupported = () => true;
      state = "inactive";
      mimeType = "audio/webm";
      ondataavailable: ((e: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      onerror: (() => void) | null = null;
      start() {
        this.state = "recording";
        this.ondataavailable?.({ data: new Blob(["clip"]) });
      }
      stop() {
        this.state = "inactive";
        void Promise.resolve().then(() => this.onstop?.());
      }
    }
    const track = { stop: vi.fn() };
    vi.stubGlobal("MediaRecorder", FakeRecorder);
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: () => Promise.resolve({ getTracks: () => [track] }) },
    });
    Object.defineProperty(window, "isSecureContext", { configurable: true, value: true });
    vi.stubGlobal("AudioContext", undefined);
    api.listSchemes.mockResolvedValue([pmfme(false)]);
    api.transcribe.mockResolvedValue("25");

    render(<Chat />);
    await screen.findByText(UNREVIEWED_NOTE);
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    await screen.findAllByText("How old are you?");

    fireEvent.click(screen.getByRole("button", { name: "Speak" }));
    await screen.findByRole("button", { name: "Stop and send" });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });

    await waitFor(() => expect(api.transcribe).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(api.sendChat).toHaveBeenLastCalledWith(expect.objectContaining({ message: "25" })));
    expect(track.stop).toHaveBeenCalled();
    expect(api.transcribe).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
});
