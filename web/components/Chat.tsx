"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, detectLocale, sendChat, type ChatResponse } from "@/lib/api";
import { makeTranslator } from "@/lib/i18n";
import { LOCALES, resolveLocale, type LocaleCode } from "@/lib/registry";
import { useDictation, useSpeech } from "@/lib/useSpeech";
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
  const { speak, stop, speaking, canSpeak } = useSpeech();
  const dictation = useDictation(LOCALES[contentLocale].bcp47);
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
      extra?: { answer?: "yes" | "no"; answers?: Record<string, unknown> },
    ) => {
      setBusy(true);
      setError(null);
      stop();
      try {
        const response = await sendChat({
          scheme: SCHEME,
          profile: nextProfile ?? profile,
          message,
          answer: extra?.answer,
          answers: extra?.answers,
          locale: contentLocale,
          messageLocale: contentLocale,
        });
        setProfile(response.profile);
        setLatest(response);
        const text = response.answer ?? response.next_question ?? "";
        if (text) {
          setTurns((prev) => [...prev, { role: "bot", text, verdict: response.verdict }]);
        }
      } catch (err) {
        setError(
          err instanceof ApiError && err.offline ? t("error.offline") : t("error.generic"),
        );
      } finally {
        setBusy(false);
      }
    },
    [contentLocale, profile, stop, t],
  );

  const start = async () => {
    setStarted(true);
    setTurns([]);
    setProfile({});
    setLatest(null);
    await exchange("", {});
  };

  const send = async (text: string) => {
    if (!text.trim() || busy) return;
    setTurns((prev) => [...prev, { role: "user", text }]);
    setDraft("");
    await exchange(text);
  };

  const answerYesNo = async (affirmative: boolean) => {
    if (busy) return;
    setTurns((prev) => [
      ...prev,
      { role: "user", text: affirmative ? t("answer.yes") : t("answer.no") },
    ]);
    await exchange("", undefined, { answer: affirmative ? "yes" : "no" });
  };

  const answerValues = async (values: Record<string, unknown>) => {
    if (busy) return;
    const shown = Object.entries(values)
      .map(([key, value]) => `${key.replace(/_/g, " ")}: ${String(value)}`)
      .join(", ");
    setTurns((prev) => [...prev, { role: "user", text: shown }]);
    await exchange("", undefined, { answers: values });
  };

  const restart = () => {
    stop();
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

  const speechAvailable = canSpeak(latest?.speech ?? null);

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
                onYesNo={answerYesNo}
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
              {dictation.supported && (
                <button
                  type="button"
                  className="btn ghost"
                  onClick={() =>
                    dictation.listening ? dictation.cancel() : dictation.listen(send)
                  }
                  disabled={busy}
                >
                  {dictation.listening ? t("mic.listening") : t("mic.start")}
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
                onClick={() => (speaking ? stop() : speak(latest?.speech ?? null))}
                disabled={!speechAvailable || !latest}
                title={!speechAvailable ? t("speak.unavailable") : undefined}
              >
                {speaking ? t("speak.stop") : t("speak.play")}
              </button>
              <button type="button" className="btn ghost" onClick={restart}>
                {t("chat.restart")}
              </button>
            </div>

            {!speechAvailable && latest && (
              <p className="note">{t("speak.unavailable")}</p>
            )}
            {latest?.speech?.rung === "browser" && speechAvailable && (
              <p className="note">{t("speak.browser")}</p>
            )}
            {latest?.language_note && <p className="note">{latest.language_note}</p>}
            {error && <p className="note error">{error}</p>}

            <div className="profilebox">
              <h3>{t("profile.known")}</h3>
              <div className="facts">
                {Object.keys(profile).length === 0 ? (
                  <span className="fact">{t("profile.empty")}</span>
                ) : (
                  Object.entries(profile).map(([key, value]) => (
                    <span key={key} className="fact">
                      {key}: {String(value)}
                    </span>
                  ))
                )}
              </div>
            </div>
          </>
        )}
      </main>

      {latest && <Citations citations={latest.citations} t={t} />}

      <p className="disclaimer" lang={uiLocale}>
        {t("notice.notAdvice")}
      </p>
    </div>
  );
}
