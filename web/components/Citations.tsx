"use client";

import type { Citation } from "@/lib/api";

/**
 * The evidence panel.
 *
 * The quote is rendered exactly as the government published it and is never
 * translated -- a translated quote is no longer a quote. Its `lang` is not
 * set to the UI locale for the same reason: the surrounding explanation is
 * localized, the quoted clause is not.
 */
export function Citations({
  citations,
  t,
}: {
  citations: Citation[];
  t: (key: string, values?: Record<string, string | number>) => string;
}) {
  // The API can cite one clause for several conditions (APY, PMJJBY). The
  // quote is the same either way, so show it once.
  const unique = citations.filter(
    (citation, index) =>
      citations.findIndex((other) => other.clause_id === citation.clause_id) === index,
  );
  if (unique.length === 0) return null;

  return (
    <section className="citations">
      <h2>{t("citations.heading")}</h2>
      <p className="sub">{t("citations.note")}</p>

      {unique.map((citation, index) => (
        <article key={citation.clause_id} className="citation">
          <span className="citeno" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
          {/* PDF extraction leaves hard line breaks and double spaces;
              collapsing whitespace changes the layout, not the words. */}
          <blockquote lang="en" title={citation.clause_id}>
            {citation.quote.replace(/\s+/g, " ").trim()}
          </blockquote>
          <div className="meta">
            {citation.page !== null && (
              <span>{t("citations.page", { page: citation.page })}</span>
            )}
            {citation.source_url && (
              <a href={citation.source_url} target="_blank" rel="noopener noreferrer">
                {t("citations.source")}
              </a>
            )}
          </div>
        </article>
      ))}
    </section>
  );
}
