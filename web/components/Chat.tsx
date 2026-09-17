"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  TranscribeError,
  VOICE_INPUT_LOCALES,
  VOICE_OUTPUT_LOCALES,
  speakAudio,
  detectLocale,
  sendChat,
  transcribe,
  type ChatResponse,
  type Citation,
} from "@/lib/api";
import { makeTranslator } from "@/lib/i18n";
import { resolveLocale, type LocaleCode } from "@/lib/registry";
import { useRecorder } from "@/lib/useRecorder";
import { useSpeech } from "@/lib/useSpeech";
import { AnswerControls } from "./AnswerControls";
import { Citations } from "./Citations";
import { LanguageSwitcher } from "./LanguageSwitcher";

const SCHEME = "pmfme";
const STORAGE_KEY = "govassist.language";

interface Turn {
  role: "bot" | "user";
  text: string;
  verdict?: ChatResponse["verdict"];
}

export function Chat() {
  const [uiLocale, setUiLocale] = useState<LocaleCode>("en");
  const [contentLocale, setContentLocale] = useState<LocaleCode>("en");
  const [contentFollows, setContentFollows] = useState(true);

  const [turns, setTurns] = useState<Turn[]>([]);
  const [profile, setProfile] = useState<Record<string, unknown>>({});
  const [latest, setLatest] = useState<ChatResponse | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [started, setStarted] = useState(false);

  const t = makeTranslator(uiLocale);
  const browserSpeech = useSpeech();
  const { canSpeak } = browserSpeech;
  const audioEl = useRef<HTMLAudioElement | null>(null);
  const [audioPlaying, setAudioPlaying] = useState(false);
  const [audioLoading, setAudioLoading] = useState(false);
  // Replies to a spoken question are read aloud: someone talking to the app
  // may not be reading it.
  const lastInputWasVoice = useRef(false);
  const serverVoice = VOICE_OUTPUT_LOCALES.includes(contentLocale);

  const stop = useCallback(() => {
    browserSpeech.stop();
    audioEl.current?.pause();
    audioEl.current = null;
    setAudioPlaying(false);
  }, [browserSpeech]);
  const speaking = browserSpeech.speaking || audioPlaying;

  /** Server voice first (Hindi and English), the device's voice otherwise. */
  const speakText = useCallback(
    async (text: string, plan: ChatResponse["speech"]) => {
      stop();
      if (!text.trim()) return;
      if (VOICE_OUTPUT_LOCALES.includes(contentLocale)) {
        setAudioLoading(true);
        try {
          const blob = await speakAudio(text, contentLocale);
          const url = URL.createObjectURL(blob);
          const audio = new Audio(url);
          audioEl.current = audio;
          audio.onended = () => {
            setAudioPlaying(false);
            URL.revokeObjectURL(url);
          };
          setAudioPlaying(true);
          await audio.play();
          return;
        } catch {
          setAudioPlaying(false);
        } finally {
          setAudioLoading(false);
        }
      }
      browserSpeech.speak(plan);
    },
    [browserSpeech, contentLocale, stop],
  );
  const recorder = useRecorder();
  const [transcribing, setTranscribing] = useState(false);
  const [micNote, setMicNote] = useState<string | null>(null);
  // Answers to the person's own questions cite clauses too; keep them so
  // the evidence panel shows everything the helper has relied on.
  const [replyCitations, setReplyCitations] = useState<Citation[]>([]);
  const voiceInput = VOICE_INPUT_LOCALES.includes(contentLocale);
  const threadEnd = useRef<HTMLDivElement>(null);

  // Restore an explicit choice; otherwise ask the server what the browser
  // asked for. An explicit choice always beats the header.
  useEffect(() => {
    let stored: { ui?: string; content?: string; follows?: boolean } | null = null;
    try {
      stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
    } catch {
      stored = null;
    }

    if (stored?.ui) {
      setUiLocale(resolveLocale(stored.ui));
      setContentLocale(resolveLocale(stored.content ?? stored.ui));
      setContentFollows(stored.follows ?? true);
      return;
    }

    detectLocale().then((detected) => {
      if (!detected) return;
      const locale = resolveLocale(detected);
      setUiLocale(locale);
      setContentLocale(locale);
    });
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ ui: uiLocale, content: contentLocale, follows: contentFollows }),
      );
    } catch {
      /* private mode, blocked storage -- a remembered preference is a
         convenience, never a requirement */
    }
    document.documentElement.lang = uiLocale;
  }, [uiLocale, contentLocale, contentFollows]);

  useEffect(() => {
    threadEnd.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [turns]);

  const handleUiChange = (locale: LocaleCode) => {
    setUiLocale(locale);
    if (contentFollows) setContentLocale(locale);
  };

  const handleContentChange = (locale: LocaleCode) => {
    setContentLocale(locale);
    setContentFollows(false); // sticky: stops following, one-directionally
  };

  const exchange = useCallback(
    async (
      message: string,
      nextProfile?: Record<string, unknown>,
      extra?: { answer?: "yes" | "no"; answers?: Record<string, unknown>; start?: boolean },
    ) => {
      setBusy(true);
      setError(null);
      stop();
      try {
        const response = await sendChat({
          scheme: SCHEME,
          profile: nextProfile ?? profile,
          message,
          start: extra?.start,
          answer: extra?.answer,
          answers: extra?.answers,
          locale: contentLocale,
          messageLocale: contentLocale,
        });
        setProfile(response.profile);
        setLatest(response);
        // The server says what the helper says, in order: a greeting or a
        // reply to the person's own question, then the next question or the
        // verdict. Older servers only sent answer/next_question.
        const messages = response.bot_messages?.length
          ? response.bot_messages
          : [response.answer ?? response.pending?.fields?.[0]?.ask ?? response.next_question ?? ""];
        const said = messages.filter((text) => text.trim());
        if (said.length && lastInputWasVoice.current) {
          void speakText(said.join(" "), response.speech);
        }
        lastInputWasVoice.current = false;
        if (said.length) {
          setTurns((prev) => [
            ...prev,
            ...said.map((text) => ({ role: "bot" as const, text, verdict: response.verdict })),
          ]);
        }
        if (response.reply_citations?.length) {
          const fresh = response.reply_citations;
          setReplyCitations((prev) => [
            ...prev,
            ...fresh.filter((c) => !prev.some((p) => p.clause_id === c.clause_id)),
          ]);
        }
      } catch (err) {
        setError(
          err instanceof ApiError && err.offline ? t("error.offline") : t("error.generic"),
        );
      } finally {
        setBusy(false);
      }
    },
    [contentLocale, profile, speakText, stop, t],
  );

  const start = async () => {
    setStarted(true);
    setTurns([]);
    setProfile({});
    setLatest(null);
    setReplyCitations([]);
    await exchange("", {}, { start: true });
  };

  const send = async (text: string) => {
    if (!text.trim() || busy) return;
    setTurns((prev) => [...prev, { role: "user", text }]);
    setDraft("");
    await exchange(text);
  };

  /** `shownAs` is what the person sees in their own bubble -- "Yes", "9
   *  people" -- rather than `worker_count: 9`, which is a variable name
   *  leaking into a conversation. */
  const answerValues = async (values: Record<string, unknown>, shownAs: string) => {
    if (busy) return;
    setTurns((prev) => [...prev, { role: "user", text: shownAs }]);
    await exchange("", undefined, { answers: values });
  };

  const finishRecording = async () => {
    const audio = await recorder.stop();
    if (!audio || audio.size < 1000) {
      setMicNote(t("mic.empty"));
      return;
    }
    setTranscribing(true);
    try {
      const text = (await transcribe(audio, contentLocale)).trim();
      if (text) {
        lastInputWasVoice.current = true;
        await send(text);
      } else {
        setMicNote(t("mic.empty"));
      }
    } catch (err) {
      setMicNote(err instanceof TranscribeError ? t("mic.failed") : t("error.offline"));
    } finally {
      setTranscribing(false);
    }
  };
  // The silence detector fires from a timer set up at start; a ref keeps it
  // calling the current closure rather than the one from that moment.
  const finishRef = useRef(finishRecording);
  finishRef.current = finishRecording;

  const toggleMic = async () => {
    setMicNote(null);
    if (recorder.state === "recording") {
      await finishRecording();
      return;
    }
    stop();
    const ok = await recorder.start(() => void finishRef.current());
    if (!ok) setMicNote(t("mic.denied"));
  };

  const restart = () => {
    stop();
    setReplyCitations([]);
    setStarted(false);
    setTurns([]);
    setProfile({});
    setLatest(null);
    setError(null);
  };

  const verdictClass =
    latest?.verdict === "ELIGIBLE"
      ? "eligible"
      : latest?.verdict === "NOT_ELIGIBLE"
        ? "not_eligible"
        : "insufficient";

  const verdictLabel =
    latest?.verdict === "ELIGIBLE"
      ? t("verdict.eligible")
      : latest?.verdict === "NOT_ELIGIBLE"
        ? t("verdict.not_eligible")
        : t("verdict.insufficient");

  const speechAvailable = serverVoice || canSpeak(latest?.speech ?? null);
  const lastBotText = latest?.bot_messages?.join(" ") ?? latest?.answer ?? latest?.next_question ?? "";

  return (
    <div className="shell">
      <header className="masthead">
        <div>
          <h1 lang={uiLocale}>{t("app.title")}</h1>
          <p className="tagline" lang={uiLocale}>
            {t("app.tagline")}
          </p>
        </div>
        <LanguageSwitcher
          uiLocale={uiLocale}
          contentLocale={contentLocale}
          contentFollows={contentFollows}
          onUiChange={handleUiChange}
          onContentChange={handleContentChange}
          t={t}
        />
      </header>

      <main className="panel">
        {!started ? (
          <button type="button" className="btn" onClick={start} disabled={busy}>
            {t("chat.start")}
          </button>
        ) : (
          <>
            {latest?.verdict && (
              <div className={`verdict ${verdictClass}`}>{verdictLabel}</div>
            )}

            <div className="thread" aria-live="polite">
              {turns.map((turn, index) => (
                <div
                  key={index}
                  className={`bubble ${turn.role}`}
                  lang={turn.role === "bot" ? contentLocale : undefined}
                >
                  {turn.text}
                </div>
              ))}
              {busy && <div className="bubble bot">{t("chat.thinking")}</div>}
              <div ref={threadEnd} />
            </div>

            {latest?.pending && !busy && (
              <AnswerControls
                pending={latest.pending}
                busy={busy}
                onValues={answerValues}
                t={t}
              />
            )}

            <div className="composer">
              <input
                value={draft}
                lang={contentLocale}
                placeholder={t("chat.placeholder")}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void send(draft);
                }}
                disabled={busy}
                aria-label={t("chat.placeholder")}
              />
              {voiceInput && recorder.state !== "unsupported" && (
                <button
                  type="button"
                  className={`btn ghost${recorder.state === "recording" ? " recording" : ""}`}
                  onClick={() => void toggleMic()}
                  disabled={busy || transcribing}
                  aria-pressed={recorder.state === "recording"}
                >
                  {transcribing
                    ? t("mic.transcribing")
                    : recorder.state === "recording"
                      ? t("mic.stop")
                      : t("mic.start")}
                </button>
              )}
              <button
                type="button"
                className="btn"
                onClick={() => void send(draft)}
                disabled={busy || !draft.trim()}
              >
                {t("chat.send")}
              </button>
            </div>

            <div className="quickrow">
              {/* Disabled with a reason beats a button that silently does
                  nothing -- Punjabi and Tamil voices are often absent. */}
              <button
                type="button"
                className="btn ghost"
                onClick={() => (speaking ? stop() : void speakText(lastBotText, latest?.speech ?? null))}
                disabled={!speechAvailable || !latest || audioLoading}
                title={!speechAvailable ? t("speak.unavailable") : undefined}
              >
                {audioLoading ? t("speak.loading") : speaking ? t("speak.stop") : t("speak.play")}
              </button>
              <button type="button" className="btn ghost" onClick={restart}>
                {t("chat.restart")}
              </button>
            </div>

            {recorder.state === "recording" && (
              <p className="note">{t("mic.listening")}</p>
            )}
            {micNote && <p className="note error">{micNote}</p>}
            {!voiceInput && <p className="note">{t("mic.voice_limited")}</p>}
            {voiceInput && recorder.state === "unsupported" && (
              <p className="note">{t("mic.unsupported")}</p>
            )}
            {!speechAvailable && latest && (
              <p className="note">{t("speak.unavailable")}</p>
            )}
            {latest?.speech?.rung === "browser" && speechAvailable && !serverVoice && (
              <p className="note">{t("speak.browser")}</p>
            )}
            {latest?.language_note && <p className="note">{latest.language_note}</p>}
            {error && <p className="note error">{error}</p>}

            <div className="profilebox">
              <h3>{t("profile.known")}</h3>
              <div className="facts">
                {!latest?.profile_summary?.length ? (
                  <span className="fact">{t("profile.empty")}</span>
                ) : (
                  latest.profile_summary.map((row) => (
                    <span key={row.attribute} className="fact">
                      {row.label}: <strong>{row.value}</strong>
                    </span>
                  ))
                )}
              </div>
            </div>
          </>
        )}
      </main>

      {latest && (
        <Citations
          citations={[
            ...latest.citations,
            ...replyCitations.filter(
              (c) => !latest.citations.some((l) => l.clause_id === c.clause_id),
            ),
          ]}
          t={t}
        />
      )}

      <p className="disclaimer" lang={uiLocale}>
        {t("notice.notAdvice")}
      </p>
    </div>
  );
}
