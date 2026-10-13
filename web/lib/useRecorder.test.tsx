import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MAX_RECORDING_MS, type RecorderDeps } from "./recordingSession";
import { useRecorder } from "./useRecorder";

class FakeRecorder {
  state: "inactive" | "recording" = "inactive";
  mimeType = "audio/webm";
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: (() => void) | null = null;
  start() {
    this.state = "recording";
    this.ondataavailable?.({ data: new Blob(["speech"]) });
  }
  stop() {
    this.state = "inactive";
    void Promise.resolve().then(() => this.onstop?.());
  }
}

function harness() {
  const track = { stop: vi.fn() };
  const stream = { getTracks: () => [track] } as unknown as MediaStream;
  const deps: RecorderDeps = {
    getUserMedia: () => Promise.resolve(stream),
    createRecorder: () => new FakeRecorder() as unknown as MediaRecorder,
    isTypeSupported: () => true,
    createAudioContext: () => null,
    isSecureContext: true,
    now: () => Date.now(),
  };
  return { track, deps: () => deps };
}

beforeEach(() => {
  vi.useFakeTimers();
  // recordingSupported() looks for these.
  vi.stubGlobal("MediaRecorder", FakeRecorder);
  Object.defineProperty(navigator, "mediaDevices", {
    value: { getUserMedia: vi.fn() }, configurable: true,
  });
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const flush = () => act(async () => {
  for (let i = 0; i < 5; i++) await Promise.resolve();
});

describe("useRecorder", () => {
  it("hands a capped recording to the caller once and returns to idle", async () => {
    const { deps } = harness();
    const onComplete = vi.fn();
    const { result } = renderHook(() => useRecorder(deps));

    await act(async () => {
      await result.current.start(onComplete);
    });
    expect(result.current.state).toBe("recording");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(MAX_RECORDING_MS);
    });
    await flush();

    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onComplete.mock.calls[0][1]).toBe("max_duration");
    expect(onComplete.mock.calls[0][0]).toBeInstanceOf(Blob);
    expect(result.current.state).toBe("idle");

    act(() => result.current.stop());
    await flush();
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it("delivers a manual stop through the same callback", async () => {
    const { deps } = harness();
    const onComplete = vi.fn();
    const { result } = renderHook(() => useRecorder(deps));
    await act(async () => {
      await result.current.start(onComplete);
    });
    act(() => result.current.stop());
    await flush();
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onComplete.mock.calls[0][1]).toBe("manual");
  });

  it("releases the microphone and delivers nothing when unmounted mid-recording", async () => {
    const { deps, track } = harness();
    const onComplete = vi.fn();
    const { result, unmount } = renderHook(() => useRecorder(deps));
    await act(async () => {
      await result.current.start(onComplete);
    });

    unmount();
    await vi.advanceTimersByTimeAsync(MAX_RECORDING_MS * 2);
    await flush();

    expect(track.stop).toHaveBeenCalled();
    expect(onComplete).not.toHaveBeenCalled();
  });

  it("reports unsupported browsers instead of offering a dead button", () => {
    vi.stubGlobal("MediaRecorder", undefined);
    const { result } = renderHook(() => useRecorder(harness().deps));
    expect(result.current.state).toBe("unsupported");
  });
});
