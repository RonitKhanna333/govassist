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
  if (citations.length === 0) return null;

  return (
    <section className="citations">
      <h2>{t("citations.heading")}</h2>
      <p className="sub">{t("citations.note")}</p>

      {citations.map((citation) => (
        <article key={citation.clause_id} className="citation">
          <blockquote lang="en">{citation.quote.trim()}</blockquote>
          <div className="meta">
            <span>{citation.clause_id}</span>
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
