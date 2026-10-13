"use client";

import { useEffect, useState } from "react";
import { familySuggestions, useToken, type Suggestion } from "@/lib/family";

/**
 * A reminder from the family record, shown next to the question it bears on.
 *
 * It never answers the question: the person still taps Yes or No. A family
 * record can be out of date or entered by someone else, and the rule engine
 * decides only from what the person themselves confirmed. Renders nothing
 * when signed out, when there is no family record, or when nothing applies.
 */
export function FamilyHint({
  scheme,
  attributes,
  t,
}: {
  scheme: string;
  attributes: string[];
  t: (key: string, values?: Record<string, string | number>) => string;
}) {
  const [found, setFound] = useState<Suggestion[]>([]);
  const token = useToken();
  const key = attributes.join(",");

  useEffect(() => {
    let live = true;
    if (!token) return;
    familySuggestions(scheme)
      .then((all) => {
        if (live) setFound(all.filter((s) => key.split(",").includes(s.attribute)));
      })
      .catch(() => {
        if (live) setFound([]); // no family record is the normal case
      });
    return () => {
      live = false;
    };
  }, [scheme, key, token]);

  // Signed out: say nothing, even if an earlier result is still in state.
  if (!token || !found.length) return null;

  return (
    <aside className="family-hint" role="note">
      {found.flatMap((s) =>
        s.because.map((b) => (
          <p key={`${s.attribute}-${b.member_id}`}>
            {t("family.hint", { name: b.name, relation: t(`family.rel.${b.relation}`) })}
          </p>
        )),
      )}
      <p className="muted-copy">{t("family.hint_note")}</p>
    </aside>
  );
}
