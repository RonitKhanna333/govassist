"use client";

import { useState } from "react";
import type { Pending } from "@/lib/api";

/**
 * Renders the control that can actually answer the pending question,
 * derived from the rule expression rather than assumed.
 *
 * The bug this replaces: a fixed Yes/No pair under every question. It
 * couldn't answer "how many workers do you employ", and the Yes it did
 * send was routed through an LLM to guess which attribute was meant --
 * so with no API key the profile never advanced and the same question
 * repeated forever.
 */
export function AnswerControls({
  pending,
  busy,
  onYesNo,
  onValues,
  t,
}: {
  pending: Pending;
  busy: boolean;
  onYesNo: (affirmative: boolean) => void;
  onValues: (values: Record<string, unknown>) => void;
  t: (key: string) => string;
}) {
  const [draft, setDraft] = useState<Record<string, string>>({});

  const numberFields = pending.fields.filter((f) => f.kind === "number");
  const multiChoice = pending.fields.filter(
    (f) => f.kind === "choice" && f.options.length > 1,
  );

  // Yes/No is only honest when nothing here needs a value typed in.
  const yesNoAnswerable = pending.fields.length > 0 && numberFields.length === 0
    && multiChoice.length === 0;

  const submitValues = () => {
    const values: Record<string, unknown> = {};
    for (const f of pending.fields) {
      const raw = draft[f.attribute];
      if (raw === undefined || raw === "") continue;
      values[f.attribute] = f.kind === "number" ? Number(raw) : raw;
    }
    // Anything the typed fields didn't cover but Yes/No would have: a
    // compound condition like "unincorporated AND under 10 workers" needs
    // both halves, so the booleans come along with the number.
    for (const f of pending.fields) {
      if (f.kind === "boolean" && values[f.attribute] === undefined) {
        values[f.attribute] = f.satisfied_by;
      }
    }
    if (Object.keys(values).length > 0) onValues(values);
    setDraft({});
  };

  const ready = numberFields.every(
    (f) => draft[f.attribute] !== undefined && draft[f.attribute] !== "",
  );

  return (
    <div className="answers">
      {yesNoAnswerable && (
        <div className="quickrow">
          <button type="button" className="btn ghost" disabled={busy}
                  onClick={() => onYesNo(true)}>
            {t("answer.yes")}
          </button>
          <button type="button" className="btn ghost" disabled={busy}
                  onClick={() => onYesNo(false)}>
            {t("answer.no")}
          </button>
        </div>
      )}

      {multiChoice.map((f) => (
        <div key={f.attribute} className="quickrow">
          {f.options.map((option) => (
            <button
              key={String(option)}
              type="button"
              className="btn ghost"
              disabled={busy}
              onClick={() => onValues({ [f.attribute]: option })}
            >
              {String(option)}
            </button>
          ))}
        </div>
      ))}

      {numberFields.length > 0 && (
        <div className="numberrow">
          {numberFields.map((f) => (
            <label key={f.attribute} className="numberfield">
              <span>
                {f.attribute.replace(/_/g, " ")}
                {f.comparator && f.bound !== null
                  ? ` (${f.comparator} ${f.bound})`
                  : ""}
              </span>
              <input
                type="number"
                inputMode="numeric"
                value={draft[f.attribute] ?? ""}
                disabled={busy}
                onChange={(event) =>
                  setDraft((prev) => ({ ...prev, [f.attribute]: event.target.value }))
                }
                onKeyDown={(event) => {
                  if (event.key === "Enter" && ready) submitValues();
                }}
              />
            </label>
          ))}
          <button type="button" className="btn" disabled={busy || !ready}
                  onClick={submitValues}>
            {t("chat.send")}
          </button>
        </div>
      )}
    </div>
  );
}
