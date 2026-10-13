"use client";

import type { NextStep, NextSteps as Checklist } from "@/lib/api";

/**
 * "What should I do next?" -- the personalised checklist after a verdict.
 *
 * Every line is a committed clause from the official document: the plain
 * gloss, the verbatim quote (never translated), the page and the source
 * link. What the official text doesn't cover is said out loud instead of
 * being filled in, and anything that still needs confirming comes first.
 */
type T = (key: string, values?: Record<string, string | number>) => string;

function Step({ step, t }: { step: NextStep; t: T }) {
  return (
    <li className="step">
      <p className="steptext">{step.plain}</p>
      <details className="stepquote">
        <summary>{t("next.official_wording")}</summary>
        <blockquote lang="en">{step.quote.trim()}</blockquote>
      </details>
      <p className="meta">
        {step.page !== null && <span>{t("citations.page", { page: step.page })}</span>}
        <a href={step.source_url} target="_blank" rel="noopener noreferrer">
          {t("citations.source")}
        </a>
      </p>
    </li>
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

  return (
    <section className="nextsteps" aria-labelledby="nextsteps-heading">
      <h2 id="nextsteps-heading">{t("next.heading")}</h2>
      <p className="sub">{summary}</p>

      {checklist.confirm.length > 0 && (
        <div className="confirm" role="note">
          <h3>{t("next.confirm.heading")}</h3>
          <ul>
            {checklist.confirm.map((item, index) =>
              item.kind === "review_pending" ? (
                <li key={`review-${index}`}>{t("next.confirm.review_pending")}</li>
              ) : (
                <li key={`${item.kind}-${item.clause_id}`}>
                  <p>{t(`next.confirm.${item.kind}`)}</p>
                  <ul className="steps">
                    <Step step={item} t={t} />
                  </ul>
                </li>
              ),
            )}
          </ul>
        </div>
      )}

      {checklist.sections.map((section) => (
        <div key={section.key} className="stepgroup">
          <h3>{t(`next.section.${section.key}`)}</h3>
          <ol className="steps">
            {section.items.map((step) => (
              <Step key={step.clause_id} step={step} t={t} />
            ))}
          </ol>
        </div>
      ))}

      {checklist.gaps.map((gap) => (
        <div key={gap} className="stepgroup gap">
          <h3>{t(`next.section.${gap}`)}</h3>
          <p>{t(`next.gap.${gap}`, { authority })}</p>
        </div>
      ))}

      {checklist.sources.length > 0 && (
        <p className="meta">
          {checklist.sources.map((source) => (
            <a key={source.id} href={source.url} target="_blank" rel="noopener noreferrer">
              {t("next.official_document")}
            </a>
          ))}
        </p>
      )}
    </section>
  );
}
