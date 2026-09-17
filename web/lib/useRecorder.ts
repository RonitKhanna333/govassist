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

// Voice activity detection, so a person can just speak and pause instead of
// having to find and press a Stop button -- the reason taps on the mic
// seemed to do nothing.
const SPEECH_RMS = 0.02; // louder than this counts as speech
const SILENCE_AFTER_SPEECH_MS = 1_500; // pause this long after speaking -> done
const NO_SPEECH_GIVE_UP_MS = 8_000; // never spoke -> stop quietly

export function useRecorder() {
  const [state, setState] = useState<RecorderState>("idle");
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const stream = useRef<MediaStream | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const resolveStop = useRef<((blob: Blob | null) => void) | null>(null);
  const audioCtx = useRef<AudioContext | null>(null);
  const vadTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const heardSpeech = useRef(false);

  const stopVad = () => {
    if (vadTimer.current) clearInterval(vadTimer.current);
    vadTimer.current = null;
    void audioCtx.current?.close().catch(() => undefined);
    audioCtx.current = null;
  };

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
      stopVad();
    };
  }, []);

  /** `onSilence` fires when the person has finished speaking (or never
   *  started); the caller then calls stop() and sends the audio. */
  const start = useCallback(async (onSilence?: () => void): Promise<boolean> => {
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
      stopVad();
      // Nothing louder than room noise was ever heard: don't send it --
      // Whisper invents words for silence.
      const blob = chunks.current.length && heardSpeech.current
        ? new Blob(chunks.current, { type: instance.mimeType || "audio/webm" })
        : null;
      setState("idle");
      resolveStop.current?.(blob);
      resolveStop.current = null;
    };

    recorder.current = instance;
    heardSpeech.current = false;
    instance.start();
    setState("recording");

    try {
      const Ctx =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = new Ctx();
      audioCtx.current = ctx;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      ctx.createMediaStreamSource(stream.current).connect(analyser);
      const samples = new Float32Array(analyser.fftSize);
      const began = Date.now();
      let lastLoud = 0;
      vadTimer.current = setInterval(() => {
        analyser.getFloatTimeDomainData(samples);
        let sum = 0;
        for (const v of samples) sum += v * v;
        const rms = Math.sqrt(sum / samples.length);
        const now = Date.now();
        if (rms > SPEECH_RMS) {
          heardSpeech.current = true;
          lastLoud = now;
        }
        const finished = heardSpeech.current && now - lastLoud > SILENCE_AFTER_SPEECH_MS;
        const gaveUp = !heardSpeech.current && now - began > NO_SPEECH_GIVE_UP_MS;
        if ((finished || gaveUp) && recorder.current?.state === "recording") {
          stopVad();
          onSilence?.();
        }
      }, 100);
    } catch {
      // No Web Audio: fall back to the Stop button, and trust the audio.
      heardSpeech.current = true;
    }
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
