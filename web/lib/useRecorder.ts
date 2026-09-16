"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Microphone recording, for server-side transcription.
 *
 * What this replaces: the browser's own SpeechRecognition. In Brave that API
 * exists but depends on Google servers Brave blocks, so tapping the mic did
 * nothing at all; Firefox doesn't have it. Recording is plain microphone
 * capture, which every current browser supports, and Whisper on the server
 * does the recognition.
 */
export type RecorderState = "idle" | "recording" | "unsupported" | "denied";

// Best-supported first. Safari records mp4; Chrome, Edge, Brave and Firefox
// record webm/opus.
const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/mp4",
];

// A long ramble is expensive to transcribe and unlikely to be an answer.
const MAX_RECORDING_MS = 30_000;

export function useRecorder() {
  const [state, setState] = useState<RecorderState>("idle");
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const stream = useRef<MediaStream | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const resolveStop = useRef<((blob: Blob | null) => void) | null>(null);

  useEffect(() => {
    if (
      typeof window === "undefined" ||
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === "undefined"
    ) {
      setState("unsupported");
    }
    return () => {
      stream.current?.getTracks().forEach((track) => track.stop());
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  const start = useCallback(async (): Promise<boolean> => {
    if (typeof MediaRecorder === "undefined") {
      setState("unsupported");
      return false;
    }
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setState("denied");
      return false;
    }

    const mimeType = MIME_CANDIDATES.find((type) => MediaRecorder.isTypeSupported(type));
    const instance = new MediaRecorder(stream.current, mimeType ? { mimeType } : undefined);
    chunks.current = [];

    instance.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.current.push(event.data);
    };
    instance.onstop = () => {
      stream.current?.getTracks().forEach((track) => track.stop());
      stream.current = null;
      if (timer.current) clearTimeout(timer.current);
      const blob = chunks.current.length
        ? new Blob(chunks.current, { type: instance.mimeType || "audio/webm" })
        : null;
      setState("idle");
      resolveStop.current?.(blob);
      resolveStop.current = null;
    };

    recorder.current = instance;
    instance.start();
    setState("recording");
    timer.current = setTimeout(() => {
      if (recorder.current?.state === "recording") recorder.current.stop();
    }, MAX_RECORDING_MS);
    return true;
  }, []);

  /** Stops recording and resolves with the audio, or null if nothing was said. */
  const stop = useCallback((): Promise<Blob | null> => {
    return new Promise((resolve) => {
      if (!recorder.current || recorder.current.state !== "recording") {
        resolve(null);
        return;
      }
      resolveStop.current = resolve;
      recorder.current.stop();
    });
  }, []);

  return { state, start, stop };
}
