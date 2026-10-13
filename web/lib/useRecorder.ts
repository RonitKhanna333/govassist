"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import {
  RecordingSession,
  browserDeps,
  recordingSupported,
  type RecorderDeps,
  type RecorderError,
  type RecorderState,
  type StopReason,
} from "./recordingSession";

export type { RecorderError, RecorderState, StopReason } from "./recordingSession";

/**
 * Microphone recording, for server-side transcription.
 *
 * What this replaces: the browser's own SpeechRecognition. In Brave that API
 * exists but depends on Google servers Brave blocks, so tapping the mic did
 * nothing at all; Firefox doesn't have it. Recording is plain microphone
 * capture, which every current browser supports, and Whisper on the server
 * does the recognition.
 *
 * `start(onComplete)` registers the one place the audio arrives, whichever
 * way the recording ends -- Stop, a pause after speaking, or the 30-second
 * cap -- and it arrives there once. See recordingSession.ts.
 */
const noSubscription = () => () => undefined;

export function useRecorder(deps?: () => RecorderDeps) {
  // Detected on the client only. The server snapshot assumes support so the
  // server-rendered markup matches the common case.
  const supported = useSyncExternalStore(noSubscription, recordingSupported, () => true);
  const [recording, setRecording] = useState<RecorderState>("idle");
  const [error, setError] = useState<RecorderError | null>(null);
  const [level, setLevel] = useState(0);
  const session = useRef<RecordingSession | null>(null);

  // Unmounting mid-recording releases the microphone and delivers nothing:
  // there is no component left to show a transcript to.
  useEffect(() => () => session.current?.cancel(), []);

  const start = useCallback(
    async (onComplete: (audio: Blob | null, reason: StopReason) => void) => {
      if (!recordingSupported()) return "other" as RecorderError;
      session.current?.cancel();
      setError(null);
      const current = new RecordingSession((deps ?? browserDeps)(), {
        onState: (next) => {
          if (session.current === current) setRecording(next);
        },
        onLevel: (next) => {
          if (session.current === current) setLevel(next);
        },
        onComplete,
      });
      session.current = current;
      const failure = await current.start();
      if (failure) {
        if (session.current === current) session.current = null;
        if (failure === "denied") setRecording("denied");
        setError(failure);
        if (failure !== "insecure") console.warn("microphone failed:", failure);
      }
      return failure;
    },
    [deps],
  );

  /** Ends the recording; the audio goes to the `onComplete` given to start. */
  const stop = useCallback(() => session.current?.stop("manual"), []);
  /** Ends the recording and discards it. */
  const cancel = useCallback(() => session.current?.cancel(), []);

  const state: RecorderState = supported ? recording : "unsupported";
  return { state, error, level, start, stop, cancel };
}
