/**
 * One microphone recording, from permission prompt to delivered audio.
 *
 * The bug this structure exists to prevent: the 30-second cap called
 * `MediaRecorder.stop()` directly, while the audio was only handed back
 * through a resolver that the manual Stop button registered. A recording
 * that hit the cap was captured and then silently dropped, and the next tap
 * on Stop returned nothing. Every way a recording can end -- the Stop
 * button, the silence detector, the cap -- now goes through `finish()`, and
 * the audio is delivered from exactly one place (`onstop`), exactly once.
 *
 * Framework-free so it can be tested with fake timers and a fake
 * MediaRecorder; `useRecorder` is the thin React wrapper.
 */

export type RecorderState = "idle" | "recording" | "unsupported" | "denied";
/** Why the microphone could not start, from the browser's own error name. */
export type RecorderError = "denied" | "no_device" | "busy" | "insecure" | "other";
export type StopReason = "manual" | "silence" | "max_duration";

// Best-supported first. Safari records mp4; Chrome, Edge, Brave and Firefox
// record webm/opus.
export const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/mp4",
];

// A long ramble is expensive to transcribe and unlikely to be an answer.
export const MAX_RECORDING_MS = 30_000;

// Voice activity detection, so a person can just speak and pause instead of
// having to find and press a Stop button.
export const SPEECH_RMS = 0.02; // louder than this counts as speech
export const SILENCE_AFTER_SPEECH_MS = 1_500; // pause this long after speaking -> done
export const NO_SPEECH_GIVE_UP_MS = 8_000; // never spoke -> stop quietly
const VAD_INTERVAL_MS = 100;

export interface RecorderDeps {
  getUserMedia: (constraints: MediaStreamConstraints) => Promise<MediaStream>;
  createRecorder: (stream: MediaStream, options?: MediaRecorderOptions) => MediaRecorder;
  isTypeSupported: (type: string) => boolean;
  /** Null when Web Audio isn't available; the Stop button and cap still work. */
  createAudioContext: () => AudioContext | null;
  isSecureContext: boolean;
  now: () => number;
}

export interface RecorderEvents {
  onState: (state: RecorderState) => void;
  onLevel: (level: number) => void;
  /** Called once per recording that actually started, never twice. */
  onComplete: (audio: Blob | null, reason: StopReason) => void;
}

function classify(err: unknown): RecorderError {
  const name = err instanceof Error || err instanceof DOMException ? err.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") return "denied";
  if (name === "NotFoundError" || name === "OverconstrainedError") return "no_device";
  if (name === "NotReadableError" || name === "AbortError") return "busy";
  return "other";
}

export class RecordingSession {
  private recorder: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private chunks: Blob[] = [];
  private capTimer: ReturnType<typeof setTimeout> | null = null;
  private vadTimer: ReturnType<typeof setInterval> | null = null;
  private audioCtx: AudioContext | null = null;
  private reason: StopReason = "manual";
  /** Set once the recording is ending; later stop requests are no-ops. */
  private ending = false;
  /** Set by cancel(): tear everything down, deliver nothing. */
  private cancelled = false;
  private delivered = false;

  constructor(
    private readonly deps: RecorderDeps,
    private readonly events: RecorderEvents,
  ) {}

  get active(): boolean {
    return this.recorder !== null && !this.ending;
  }

  async start(): Promise<RecorderError | null> {
    if (!this.deps.isSecureContext) return "insecure";

    let stream: MediaStream;
    try {
      stream = await this.deps.getUserMedia({ audio: true });
    } catch (err) {
      return classify(err);
    }
    // Stopped or unmounted while the permission prompt was still open: the
    // stream arrived for nobody. Release the microphone and record nothing.
    if (this.cancelled || this.ending) {
      stream.getTracks().forEach((track) => track.stop());
      return null;
    }
    this.stream = stream;

    const mimeType = MIME_CANDIDATES.find((type) => this.deps.isTypeSupported(type));
    const recorder = this.deps.createRecorder(stream, mimeType ? { mimeType } : undefined);
    this.recorder = recorder;
    this.chunks = [];

    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) this.chunks.push(event.data);
    };
    recorder.onstop = () => this.deliver(recorder);
    recorder.onerror = () => this.finish(this.reason);

    // Timeslice: chunks arrive while recording, so an abrupt stop still has audio.
    recorder.start(250);
    this.events.onState("recording");
    this.capTimer = setTimeout(() => this.finish("max_duration"), MAX_RECORDING_MS);
    await this.startVad(stream);
    return null;
  }

  /** End the recording and deliver what was captured. Safe to call any
   *  number of times, from any path; only the first one counts. */
  stop(reason: StopReason = "manual"): void {
    this.finish(reason);
  }

  /** End the recording and discard it -- e.g. the component unmounted. */
  cancel(): void {
    this.cancelled = true;
    this.finish("manual");
  }

  private finish(reason: StopReason): void {
    if (this.ending) return;
    this.ending = true;
    this.reason = reason;
    this.clearTimers();
    const recorder = this.recorder;
    if (recorder && recorder.state !== "inactive") {
      try {
        recorder.stop(); // onstop -> deliver()
        return;
      } catch {
        /* fall through and deliver what we have */
      }
    }
    if (recorder) this.deliver(recorder);
    else this.releaseStream();
  }

  private deliver(recorder: MediaRecorder): void {
    this.clearTimers();
    this.releaseStream();
    this.events.onState("idle");
    if (this.delivered || this.cancelled) return;
    this.delivered = true;
    // Always hand back what was recorded. An earlier version dropped
    // recordings the level meter judged silent -- but the meter reads zeros
    // whenever the browser keeps its AudioContext suspended, so real speech
    // was thrown away before it was ever sent. The server filters silence.
    const audio = this.chunks.length
      ? new Blob(this.chunks, { type: recorder.mimeType || "audio/webm" })
      : null;
    this.events.onComplete(audio, this.reason);
  }

  private releaseStream(): void {
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
  }

  private clearTimers(): void {
    if (this.capTimer) clearTimeout(this.capTimer);
    this.capTimer = null;
    this.stopVad();
  }

  private stopVad(): void {
    if (this.vadTimer) clearInterval(this.vadTimer);
    this.vadTimer = null;
    this.events.onLevel(0);
    const ctx = this.audioCtx;
    this.audioCtx = null;
    void ctx?.close().catch(() => undefined);
  }

  private async startVad(stream: MediaStream): Promise<void> {
    try {
      const ctx = this.deps.createAudioContext();
      if (!ctx) return;
      this.audioCtx = ctx;
      // Created after an await, so browsers may start it suspended. A
      // suspended context reports pure silence; without it running, rely on
      // the Stop button and the cap instead of guessing.
      if (ctx.state !== "running") await ctx.resume().catch(() => undefined);
      if (ctx.state !== "running") throw new Error("audio context suspended");
      if (this.ending) return;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      ctx.createMediaStreamSource(stream).connect(analyser);
      const samples = new Float32Array(analyser.fftSize);
      const began = this.deps.now();
      let lastLoud = 0;
      let heardSpeech = false;
      this.vadTimer = setInterval(() => {
        analyser.getFloatTimeDomainData(samples);
        let sum = 0;
        for (const v of samples) sum += v * v;
        const rms = Math.sqrt(sum / samples.length);
        const now = this.deps.now();
        if (rms > SPEECH_RMS) {
          heardSpeech = true;
          lastLoud = now;
        }
        this.events.onLevel(Math.min(1, rms * 8));
        const finished = heardSpeech && now - lastLoud > SILENCE_AFTER_SPEECH_MS;
        const gaveUp = !heardSpeech && now - began > NO_SPEECH_GIVE_UP_MS;
        if (finished || gaveUp) this.finish("silence");
      }, VAD_INTERVAL_MS);
    } catch {
      this.stopVad();
    }
  }
}

/** The real browser implementations. */
export function browserDeps(): RecorderDeps {
  return {
    getUserMedia: (constraints) => navigator.mediaDevices.getUserMedia(constraints),
    createRecorder: (stream, options) => new MediaRecorder(stream, options),
    isTypeSupported: (type) => MediaRecorder.isTypeSupported(type),
    createAudioContext: () => {
      const Ctx =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      return Ctx ? new Ctx() : null;
    },
    isSecureContext: window.isSecureContext,
    now: () => Date.now(),
  };
}

export function recordingSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== "undefined"
  );
}
