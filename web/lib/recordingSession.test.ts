import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  MAX_RECORDING_MS,
  NO_SPEECH_GIVE_UP_MS,
  RecordingSession,
  type RecorderDeps,
  type StopReason,
} from "./recordingSession";

/** Behaves like the browser's: stop() is asynchronous, and the last chunk
 *  arrives (dataavailable) before onstop fires. */
class FakeRecorder {
  state: "inactive" | "recording" = "inactive";
  mimeType = "audio/webm";
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: (() => void) | null = null;
  stopCalls = 0;

  start() {
    this.state = "recording";
  }
  stop() {
    this.stopCalls += 1;
    if (this.state === "inactive") throw new Error("InvalidStateError");
    this.state = "inactive";
    void Promise.resolve().then(() => {
      this.ondataavailable?.({ data: new Blob(["tail"], { type: this.mimeType }) });
      this.onstop?.();
    });
  }
  speak(text = "audio") {
    this.ondataavailable?.({ data: new Blob([text], { type: this.mimeType }) });
  }
}

function fakeStream() {
  const track = { stop: vi.fn() };
  return { track, stream: { getTracks: () => [track] } as unknown as MediaStream };
}

function fakeAudio(level: { rms: number }) {
  return {
    state: "running",
    resume: () => Promise.resolve(),
    close: vi.fn(() => Promise.resolve()),
    createAnalyser: () => ({
      fftSize: 1024,
      getFloatTimeDomainData: (samples: Float32Array) => samples.fill(level.rms),
    }),
    createMediaStreamSource: () => ({ connect: () => undefined }),
  } as unknown as AudioContext;
}

function setup(options: { audio?: boolean; getUserMedia?: RecorderDeps["getUserMedia"] } = {}) {
  const { track, stream } = fakeStream();
  const level = { rms: 0 };
  const recorders: FakeRecorder[] = [];
  const completions: { audio: Blob | null; reason: StopReason }[] = [];
  const states: string[] = [];
  const deps: RecorderDeps = {
    getUserMedia: options.getUserMedia ?? (() => Promise.resolve(stream)),
    createRecorder: () => {
      const recorder = new FakeRecorder();
      recorders.push(recorder);
      return recorder as unknown as MediaRecorder;
    },
    isTypeSupported: () => true,
    createAudioContext: () => (options.audio === false ? null : fakeAudio(level)),
    isSecureContext: true,
    now: () => Date.now(),
  };
  const session = new RecordingSession(deps, {
    onState: (state) => states.push(state),
    onLevel: () => undefined,
    onComplete: (audio, reason) => completions.push({ audio, reason }),
  });
  return { session, track, level, recorders, completions, states, stream };
}

/** Let the fake recorder's asynchronous stop -> onstop run. */
const settle = async () => {
  for (let i = 0; i < 5; i++) await Promise.resolve();
};

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("RecordingSession: every way a recording ends delivers it once", () => {
  it("delivers audio on a manual stop and releases the microphone", async () => {
    const t = setup();
    expect(await t.session.start()).toBeNull();
    t.recorders[0].speak();
    t.session.stop();
    await settle();

    expect(t.completions).toHaveLength(1);
    expect(t.completions[0].reason).toBe("manual");
    expect(await t.completions[0].audio!.text()).toBe("audiotail");
    expect(t.track.stop).toHaveBeenCalled();
    expect(t.states.at(-1)).toBe("idle");
  });

  it("delivers audio when the 30-second cap is reached (the regression)", async () => {
    const t = setup({ audio: false });
    await t.session.start();
    t.recorders[0].speak();

    await vi.advanceTimersByTimeAsync(MAX_RECORDING_MS);
    await settle();

    expect(t.completions).toEqual([
      { audio: expect.any(Blob), reason: "max_duration" },
    ]);
    expect(t.track.stop).toHaveBeenCalled();
    // The old code returned null here and never transcribed the clip.
    t.session.stop();
    await settle();
    expect(t.completions).toHaveLength(1);
    expect(t.recorders[0].stopCalls).toBe(1);
  });

  it("delivers when the person pauses after speaking", async () => {
    const t = setup();
    await t.session.start();
    t.level.rms = 0.5;
    await vi.advanceTimersByTimeAsync(600);
    t.recorders[0].speak();
    t.level.rms = 0;
    await vi.advanceTimersByTimeAsync(2_000);
    await settle();

    expect(t.completions).toHaveLength(1);
    expect(t.completions[0].reason).toBe("silence");
  });

  it("stops quietly when nothing is ever said, still delivering what it has", async () => {
    const t = setup();
    await t.session.start();
    await vi.advanceTimersByTimeAsync(NO_SPEECH_GIVE_UP_MS + 200);
    await settle();
    expect(t.completions).toHaveLength(1);
    expect(t.completions[0].reason).toBe("silence");
  });

  it("delivers once when Stop and the cap race", async () => {
    const t = setup({ audio: false });
    await t.session.start();
    await vi.advanceTimersByTimeAsync(MAX_RECORDING_MS - 1);
    t.session.stop();
    await vi.advanceTimersByTimeAsync(10);
    t.session.stop();
    await settle();

    expect(t.completions).toHaveLength(1);
    expect(t.completions[0].reason).toBe("manual");
    expect(t.recorders[0].stopCalls).toBe(1);
  });

  it("delivers once when silence and the cap fire together", async () => {
    const t = setup();
    await t.session.start();
    t.level.rms = 0.5;
    await vi.advanceTimersByTimeAsync(MAX_RECORDING_MS - 1_000);
    t.level.rms = 0;
    await vi.advanceTimersByTimeAsync(5_000);
    await settle();
    expect(t.completions).toHaveLength(1);
  });

  it("delivers what it has if the recorder errors", async () => {
    const t = setup({ audio: false });
    await t.session.start();
    t.recorders[0].speak();
    t.recorders[0].onerror?.();
    await settle();
    expect(t.completions).toHaveLength(1);
    expect(t.track.stop).toHaveBeenCalled();
  });
});

describe("RecordingSession: cancellation", () => {
  it("cancel releases everything and delivers nothing", async () => {
    const t = setup();
    await t.session.start();
    t.recorders[0].speak();
    t.session.cancel();
    await vi.advanceTimersByTimeAsync(MAX_RECORDING_MS * 2);
    await settle();

    expect(t.completions).toHaveLength(0);
    expect(t.track.stop).toHaveBeenCalled();
    expect(t.recorders[0].stopCalls).toBe(1);
  });

  it("stopping while the permission prompt is open records nothing and frees the mic", async () => {
    let grant!: (stream: MediaStream) => void;
    const pending = new Promise<MediaStream>((resolve) => (grant = resolve));
    const t = setup({ getUserMedia: () => pending });
    const started = t.session.start();
    t.session.stop();
    grant(t.stream);
    expect(await started).toBeNull();
    await settle();

    expect(t.recorders).toHaveLength(0);
    expect(t.track.stop).toHaveBeenCalled();
    expect(t.completions).toHaveLength(0);
  });

  it("reports a denied microphone without delivering anything", async () => {
    const denied = Object.assign(new Error("denied"), { name: "NotAllowedError" });
    const t = setup({ getUserMedia: () => Promise.reject(denied) });
    expect(await t.session.start()).toBe("denied");
    expect(t.completions).toHaveLength(0);
  });

  it("refuses an insecure page before asking for the microphone", async () => {
    const getUserMedia = vi.fn();
    const t = setup({ getUserMedia });
    (t.session as unknown as { deps: RecorderDeps }).deps.isSecureContext = false;
    expect(await t.session.start()).toBe("insecure");
    expect(getUserMedia).not.toHaveBeenCalled();
  });
});
