"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { SpeechPlan } from "./api";

/**
 * Speech, and honesty about whether it's actually available.
 *
 * The server decides which rung of the fallback ladder applies (it knows
 * whether Bhashini is configured); the client is the only thing that knows
 * which voices this particular device actually has. So the server's plan is
 * checked against `speechSynthesis.getVoices()` before a Listen button is
 * ever shown as enabled.
 *
 * Indic coverage here is genuinely thin and device-dependent -- Hindi
 * usually exists, Punjabi and Tamil frequently do not. A disabled button
 * with a reason beats a button that silently does nothing.
 */
export function useSpeech() {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [speaking, setSpeaking] = useState(false);
  const queue = useRef<string[]>([]);

  useEffect(() => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    const load = () => setVoices(window.speechSynthesis.getVoices());
    load();
    window.speechSynthesis.addEventListener("voiceschanged", load);
    return () => {
      window.speechSynthesis.removeEventListener("voiceschanged", load);
      window.speechSynthesis.cancel();
    };
  }, []);

  const voiceFor = useCallback(
    (bcp47: string | null): SpeechSynthesisVoice | null => {
      if (!bcp47) return null;
      const primary = bcp47.split("-")[0].toLowerCase();
      return (
        voices.find((v) => v.lang.toLowerCase() === bcp47.toLowerCase()) ??
        voices.find((v) => v.lang.toLowerCase().startsWith(primary)) ??
        null
      );
    },
    [voices],
  );

  const canSpeak = useCallback(
    (plan: SpeechPlan | null): boolean => {
      if (!plan || plan.rung === "text_only") return false;
      if (typeof window === "undefined" || !("speechSynthesis" in window)) return false;
      return voiceFor(plan.bcp47) !== null;
    },
    [voiceFor],
  );

  const stop = useCallback(() => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    queue.current = [];
    setSpeaking(false);
  }, []);

  /** Speaks chunk by chunk so playback starts on the first sentence rather
   *  than after the whole answer is synthesised. */
  const speak = useCallback(
    (plan: SpeechPlan | null) => {
      if (!plan || !canSpeak(plan)) return;
      stop();

      const voice = voiceFor(plan.bcp47);
      queue.current = [...plan.chunks];
      setSpeaking(true);

      const next = () => {
        const text = queue.current.shift();
        if (!text) {
          setSpeaking(false);
          return;
        }
        const utterance = new SpeechSynthesisUtterance(text);
        if (voice) utterance.voice = voice;
        if (plan.bcp47) utterance.lang = plan.bcp47;
        utterance.onend = next;
        utterance.onerror = () => setSpeaking(false);
        window.speechSynthesis.speak(utterance);
      };
      next();
    },
    [canSpeak, stop, voiceFor],
  );

  return { speak, stop, speaking, canSpeak };
}

/** Voice input via the browser's recognizer, where it exists. */
export function useDictation(bcp47: string) {
  const [listening, setListening] = useState(false);
  const [supported, setSupported] = useState(false);
  const recognition = useRef<any>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const Recognition =
      (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
    setSupported(Boolean(Recognition));
  }, []);

  const listen = useCallback(
    (onResult: (text: string) => void) => {
      const Recognition =
        (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
      if (!Recognition) return;

      const instance = new Recognition();
      instance.lang = bcp47;
      instance.interimResults = false;
      instance.maxAlternatives = 1;
      instance.onresult = (event: any) => {
        onResult(event.results[0][0].transcript);
        setListening(false);
      };
      instance.onerror = () => setListening(false);
      instance.onend = () => setListening(false);
      recognition.current = instance;
      setListening(true);
      instance.start();
    },
    [bcp47],
  );

  const cancel = useCallback(() => {
    recognition.current?.abort?.();
    setListening(false);
  }, []);

  return { listen, cancel, listening, supported };
}
