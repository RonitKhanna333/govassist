"use client";

import { useState } from "react";
import type { AnswerField, Pending } from "@/lib/api";

/**
 * One plain-language question at a time.
 *
 * What this replaces: the government's own wording, put straight in front
 * of an applicant -- "Has your unit been identified in the SLUP for an ODOP
 * product or verified by the Resource Person?" -- with a fixed Yes/No pair
 * under it and number inputs labelled `worker_count (< 10)`. That is the
 * jargon-heavy PDF this project exists to replace, retyped into a chat box.
 *
 * Compound conditions are split, because "is it unincorporated, and does it
 * employ fewer than 10 workers" is two questions to a person even though
 * it is one rule to the engine.
 */
export function AnswerControls({
  pending,
  busy,
  onValues,
  t,
}: {
  pending: Pending;
  busy: boolean;
  onValues: (values: Record<string, unknown>, shownAs: string) => void;
  t: (key: string) => string;
}) {
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [openHelp, setOpenHelp] = useState<string | null>(null);

  const fields = pending.fields;
  if (fields.length === 0) return null;

  // Ask one thing at a time. Answering a compound rule feels like several
  // small questions rather than one dense one.
  const current: AnswerField = fields[0];
  const remaining = fields.length - 1;

  const label = current.ask ?? pending.asks ?? current.attribute.replace(/_/g, " ");

  const submitNumber = () => {
    const raw = draft[current.attribute];
    if (raw === undefined || raw === "") return;
    onValues({ [current.attribute]: Number(raw) }, `${raw}${current.unit ? " " + current.unit : ""}`);
    setDraft({});
  };

  /** Answer THIS field, not the whole condition.
   *
   *  A generic yes/no goes to the server's answer_yes_no, which refuses --
   *  correctly -- when the same rule still has an unanswered number, so on a
   *  compound like "unincorporated AND under 10 workers" the tap would
   *  silently do nothing. The client knows which attribute is on screen, so
   *  it answers that one. */
  const answerYes = (affirmative: boolean) => {
    const value =
      current.kind === "choice"
        ? affirmative
          ? current.satisfied_by
          : "__other__"
        : affirmative;
    onValues(
      { [current.attribute]: value },
      affirmative ? t("answer.yes") : t("answer.no"),
    );
  };

  const helpOpen = openHelp === current.attribute;

  return (
    <div className="answers">
      {current.help && (
        <>
          <button
            type="button"
            className="helptoggle"
            aria-expanded={helpOpen}
            onClick={() => setOpenHelp(helpOpen ? null : current.attribute)}
          >
            {helpOpen ? "−" : "?"} {t("help.what")}
          </button>
          {helpOpen && <p className="help">{current.help}</p>}
        </>
      )}

      {current.kind === "number" ? (
        <div className="numberrow">
          <label className="numberfield">
            <input
              type="number"
              inputMode="decimal"
              step="any"
              autoFocus
              value={draft[current.attribute] ?? ""}
              disabled={busy}
              aria-label={label}
              onChange={(event) =>
                setDraft({ [current.attribute]: event.target.value })
              }
              onKeyDown={(event) => {
                if (event.key === "Enter") submitNumber();
              }}
            />
            {current.unit && <span className="unit">{current.unit}</span>}
          </label>
          <button
            type="button"
            className="btn"
            disabled={busy || !draft[current.attribute]}
            onClick={submitNumber}
          >
            {t("chat.send")}
          </button>
        </div>
      ) : current.kind === "choice" && current.options.length > 1 ? (
        <div className="quickrow">
          {current.options.map((option) => (
            <button
              key={String(option)}
              type="button"
              className="btn ghost"
              disabled={busy}
              onClick={() => onValues({ [current.attribute]: option }, String(option))}
            >
              {String(option)}
            </button>
          ))}
        </div>
      ) : (
        <div className="quickrow">
          <button type="button" className="btn ghost" disabled={busy}
                  onClick={() => answerYes(true)}>
            {t("answer.yes")}
          </button>
          <button type="button" className="btn ghost" disabled={busy}
                  onClick={() => answerYes(false)}>
            {t("answer.no")}
          </button>
        </div>
      )}

      {remaining > 0 && (
        <p className="remaining">{t("answer.more")}</p>
      )}
    </div>
  );
}
