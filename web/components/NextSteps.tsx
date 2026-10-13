"use client";

import { useState } from "react";
import type { NextStep, NextStepSection, NextSteps as Checklist } from "@/lib/api";

/**
 * "What should I do next?" -- the personalised checklist after a verdict.
 *
 * Every line is a committed clause from the official document: the plain
 * gloss, the verbatim quote (never translated), the page and the source
 * link. What the official text doesn't cover is said out loud instead of
 * being filled in, and anything that still needs confirming comes first.
 */
type T = (key: string, values?: Record<string, string | number>) => string;

/** Reading order: what you get, what to know, what to gather, where to go,
 *  what happens after. Gaps sit in the same place their section would. */
const ORDER: NextStepSection[] = ["benefits", "good_to_know", "documents", "apply", "after"];

const PATHS: Record<NextStepSection | "alert" | "info" | "doc", string> = {
  benefits: "M20 12v9H4v-9M2 7h20v5H2zM12 22V7M12 7H7.5a2.5 2.5 0 1 1 0-5C11 2 12 7 12 7zM12 7h4.5a2.5 2.5 0 1 0 0-5C13 2 12 7 12 7z",
  good_to_know: "M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2z",
  documents: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M9 13h6M9 17h4",
  apply: "M12 21s-7-6.1-7-11.5a7 7 0 0 1 14 0C19 14.9 12 21 12 21zM12 12a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z",
  after: "M8 2v4M16 2v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM9 16l2 2 4-4",
  alert: "M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  info: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16v-4M12 8h.01",
  doc: "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14 21 3",
};

function Glyph({ name, size = 16 }: { name: keyof typeof PATHS; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name]} />
    </svg>
  );
}

function StepBody({ step, t }: { step: NextStep; t: T }) {
  return (
    <div className="ns-body">
      <p className="ns-text">{step.plain}</p>
      <div className="ns-foot">
        <details className="ns-quote">
          <summary>{t("next.official_wording")}</summary>
          <blockquote lang="en">{step.quote.replace(/\s+/g, " ").trim()}</blockquote>
        </details>
        <span className="ns-meta">
          {step.page !== null && <span>{t("citations.page", { page: step.page })}</span>}
          <a href={step.source_url} target="_blank" rel="noopener noreferrer">
            {t("citations.source")}
          </a>
        </span>
      </div>
    </div>
  );
}

function Section({ kind, items, t }: { kind: NextStepSection; items: NextStep[]; t: T }) {
  const [done, setDone] = useState<Record<string, boolean>>({});
  const tickable = kind === "documents";

  return (
    <section className={`ns-card ns-${kind}`}>
      <h3>
        <span className="ns-icon"><Glyph name={kind} /></span>
        {t(`next.section.${kind}`)}
        {tickable && (
          <span className="ns-count" aria-hidden="true">
            {Object.values(done).filter(Boolean).length}/{items.length}
          </span>
        )}
      </h3>
      {tickable && <p className="ns-hint">{t("next.documents.tick")}</p>}
      <ol className="ns-list">
        {items.map((step, index) => (
          <li key={step.clause_id} className={`ns-item${done[step.clause_id] ? " done" : ""}`}>
            {tickable ? (
              <input
                type="checkbox"
                className="ns-check"
                checked={!!done[step.clause_id]}
                aria-label={step.plain}
                onChange={(event) =>
                  setDone((prev) => ({ ...prev, [step.clause_id]: event.target.checked }))
                }
              />
            ) : (
              <span className="ns-num" aria-hidden="true">{index + 1}</span>
            )}
            <StepBody step={step} t={t} />
          </li>
        ))}
      </ol>
    </section>
  );
}

export function NextSteps({ checklist, t }: { checklist: Checklist; t: T }) {
  const count = (key: string) =>
    checklist.sections.find((s) => s.key === key)?.items.length ?? 0;
  const eligible = checklist.status === "eligible";
  const authority = checklist.authority ?? t("next.the_scheme_office");

  const summary = !eligible
    ? t("next.summary.not_eligible")
    : count("documents") > 0
      ? t("next.summary.eligible_documents", { count: count("documents") })
      : t("next.summary.eligible");

  // Anything the server sends outside the known order still renders, last.
  const keys = [
    ...ORDER,
    ...checklist.sections.map((s) => s.key).filter((key) => !ORDER.includes(key)),
  ];

  return (
    <section className={`nextsteps ${eligible ? "is-eligible" : "is-not-eligible"}`}
             aria-labelledby="nextsteps-heading">
      <div className="ns-head">
        <h2 id="nextsteps-heading">{t("next.heading")}</h2>
        <p className="sub">{summary}</p>
      </div>

      {checklist.confirm.length > 0 && (
        <div className="ns-confirm" role="note">
          <h3>
            <span className="ns-icon"><Glyph name="alert" /></span>
            {t("next.confirm.heading")}
          </h3>
          <ul>
            {checklist.confirm.map((item, index) =>
              item.kind === "review_pending" ? (
                <li key={`review-${index}`}>{t("next.confirm.review_pending")}</li>
              ) : (
                <li key={`${item.kind}-${item.clause_id}-${index}`}>
                  <p>{t(`next.confirm.${item.kind}`)}</p>
                  <div className="ns-nested">
                    <StepBody step={item} t={t} />
                  </div>
                </li>
              ),
            )}
          </ul>
        </div>
      )}

      <div className="ns-grid">
        {keys.map((key) => {
          const section = checklist.sections.find((s) => s.key === key);
          if (section && section.items.length > 0) {
            return <Section key={key} kind={key} items={section.items} t={t} />;
          }
          if (checklist.gaps.includes(key)) {
            return (
              <div key={key} className="ns-card ns-gap">
                <h3>
                  <span className="ns-icon"><Glyph name="info" /></span>
                  {t(`next.section.${key}`)}
                </h3>
                <p>{t(`next.gap.${key}`, { authority })}</p>
              </div>
            );
          }
          return null;
        })}
      </div>

      {checklist.sources.length > 0 && (
        <div className="ns-sources">
          {checklist.sources.map((source) => (
            <a key={source.id} className="ns-docbtn" href={source.url}
               target="_blank" rel="noopener noreferrer">
              {t("next.official_document")}
              <Glyph name="doc" size={14} />
            </a>
          ))}
        </div>
      )}
    </section>
  );
}
