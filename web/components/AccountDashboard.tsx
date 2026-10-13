"use client";

import type { AnswerField, Citation } from "@/lib/api";
import type { AccountLocale, Dashboard, SchemeResult } from "@/lib/account";

const COPY = {
  en: {
    title: "Your dashboard", refresh: "Refresh", continue: "Continue profile", profile: "Your saved answers", emptyProfile: "Start your interview to build your profile.",
    eligible: "Schemes you appear eligible for", missing: "Schemes needing more answers", no: "Schemes whose rules you do not meet", empty: "No schemes in this group yet.",
    note: "Results come from the rule engine and your saved answers. This is guidance, not a government decision.",
    pending: "Human review of this scheme’s rules is still pending. Confirm before applying.", rules: "Official rules", documents: "Documents needed",
    noDocs: "Document requirements are unavailable in the current source material. Check with the scheme authority.", more: "What’s still missing", source: "Official source", edit: "Change", yes: "Yes", noAnswer: "No", other: "Other",
    calls: "Your call history", noCalls: "You haven’t requested a call yet.", heard: "Answers heard on the call", verified: "Saved answer", unverified: "Not verified — left out of your profile", transcript: "Questions and answers from the call", agent: "Assistant", caller: "You", noTranscript: "No transcript is available yet.",
    statuses: { requested: "Requested / in progress", completed: "Completed", not_answered: "Not answered", failed: "Failed" } as Record<string, string>,
  },
  hi: {
    title: "आपका डैशबोर्ड", refresh: "रीफ़्रेश करें", continue: "प्रोफ़ाइल जारी रखें", profile: "आपके सेव किए गए जवाब", emptyProfile: "प्रोफ़ाइल बनाने के लिए सवालों के जवाब दें।",
    eligible: "जिन योजनाओं के लिए आप पात्र लगते हैं", missing: "जिन योजनाओं के लिए और जवाब चाहिए", no: "जिन योजनाओं के नियम पूरे नहीं हुए", empty: "इस समूह में अभी कोई योजना नहीं।",
    note: "नतीजे नियम इंजन और आपके सेव किए गए जवाबों से आते हैं। यह जानकारी है, सरकारी फ़ैसला नहीं।",
    pending: "इस योजना के नियमों की मानवीय समीक्षा अभी बाकी है। आवेदन से पहले पुष्टि करें।", rules: "सरकारी नियम", documents: "ज़रूरी काग़ज़",
    noDocs: "अभी उपलब्ध स्रोत में ज़रूरी काग़ज़ों की जानकारी नहीं है। योजना के कार्यालय से पूछें।", more: "क्या अभी बाकी है", source: "सरकारी स्रोत", edit: "बदलें", yes: "हाँ", noAnswer: "नहीं", other: "अन्य",
    calls: "आपकी कॉल का इतिहास", noCalls: "आपने अभी कोई कॉल नहीं माँगी है।", heard: "कॉल में सुने गए जवाब", verified: "सेव किया गया जवाब", unverified: "पुष्टि नहीं हुई — प्रोफ़ाइल में शामिल नहीं", transcript: "कॉल के सवाल और जवाब", agent: "सहायक", caller: "आप", noTranscript: "अभी बातचीत का रिकॉर्ड उपलब्ध नहीं है।",
    statuses: { requested: "अनुरोध भेजा / जारी है", completed: "पूरी हुई", not_answered: "जवाब नहीं मिला", failed: "असफल" } as Record<string, string>,
  },
};

function Evidence({ items, source }: { items: Citation[]; source: string }) {
  const unique = items.filter((item, i) => items.findIndex(c => c.clause_id === item.clause_id) === i);
  return <div className="account-evidence">{unique.map(item => <div key={item.clause_id}>
    <blockquote>{item.quote}</blockquote>
    {item.source_url && <a href={item.source_url} target="_blank" rel="noopener noreferrer">{source}{item.page != null ? ` · ${item.page}` : ""}</a>}
  </div>)}</div>;
}

function SchemeCard({ result, locale }: { result: SchemeResult; locale: AccountLocale }) {
  const t = COPY[locale];
  return <article className="family-card account-scheme">
    <h3>{result.name}</h3>
    {!result.reviewed && <p className="account-review-note">{t.pending}</p>}
    {result.missing_questions.length > 0 && <><h4>{t.more}</h4><ul>{result.missing_questions.map(q => <li key={q.attribute}>{q.ask}</li>)}</ul></>}
    <details open={result.verdict === "ELIGIBLE"}><summary>{t.rules}</summary><Evidence items={result.verdict === "NOT_ELIGIBLE" ? result.failed_citations : result.citations} source={t.source} /></details>
    <h4>{t.documents}</h4>
    {result.documents_available ? <Evidence items={result.documents} source={t.source} /> : <p className="muted-copy">{t.noDocs}</p>}
  </article>;
}

export function AccountDashboard({ data, locale, busy, onRefresh, onContinue, onEdit }: {
  data: Dashboard; locale: AccountLocale; busy: boolean;
  onRefresh: () => void; onContinue: () => void; onEdit: (question: AnswerField) => void;
}) {
  const t = COPY[locale];
  const questionFor = (attribute: string) => data.profile_questions.find(f => f.attribute === attribute);
  const display = (value: unknown) => value === true ? t.yes : value === false ? t.noAnswer : value === "__other__" ? t.other : String(value);
  const groups = [
    { verdict: "ELIGIBLE", title: t.eligible },
    { verdict: "INSUFFICIENT_INFO", title: t.missing },
    { verdict: "NOT_ELIGIBLE", title: t.no },
  ];
  return <section className="account-dashboard">
    <header className="family-head"><div><h2>{t.title}{data.name ? ` · ${data.name}` : ""}</h2><p>{data.phone}</p></div>
      <div className="family-actions"><button className="btn" disabled={busy} onClick={onRefresh}>{t.refresh}</button><button className="btn primary" disabled={busy} onClick={onContinue}>{t.continue}</button></div>
    </header>
    <p className="family-privacy">{t.note}</p>
    <details className="family-card"><summary>{t.profile} ({Object.keys(data.profile).length})</summary>
      {Object.keys(data.profile).length === 0 ? <p>{t.emptyProfile}</p> : <dl className="account-answers">{Object.entries(data.profile).map(([attribute, value]) => {
        const field = questionFor(attribute);
        return <div key={attribute}><dt>{field?.ask ?? attribute.replaceAll("_", " ")}</dt><dd>{display(value)}{field && <button className="linkish" disabled={busy} onClick={() => onEdit(field)}>{t.edit}</button>}</dd></div>;
      })}</dl>}
    </details>
    {groups.map(group => {
      const results = data.schemes.filter(result => result.verdict === group.verdict);
      return <section key={group.verdict} className="account-results"><h2>{group.title} <span className="pill">{results.length}</span></h2>
        {results.length ? <div className="family-grid">{results.map(result => <SchemeCard key={result.scheme} result={result} locale={locale} />)}</div> : <p className="muted-copy">{t.empty}</p>}
      </section>;
    })}
    <section className="account-calls"><h2>{t.calls}</h2>
      {!data.calls.length && <p>{t.noCalls}</p>}
      {data.calls.map(call => <details key={call.id} className="family-card">
        <summary>{t.statuses[call.status] ?? call.status} · {new Date(call.created_at.endsWith("Z") || /[+-]\d\d:\d\d$/.test(call.created_at) ? call.created_at : call.created_at + "Z").toLocaleString(locale === "hi" ? "hi-IN" : "en-IN")} · {call.locale === "hi" ? "हिन्दी" : "English"}</summary>
        <h3>{t.heard}</h3><dl className="account-answers">{Object.entries(call.heard).map(([attribute, value]) => <div key={attribute}>
          <dt>{questionFor(attribute)?.ask ?? attribute.replaceAll("_", " ")}</dt><dd>{display(value)}<small>{attribute in call.answers ? `${t.verified}: ${display(call.answers[attribute])}` : t.unverified}</small></dd>
        </div>)}</dl>
        <h3>{t.transcript}</h3>{call.transcript.length ? <ol className="account-transcript">{call.transcript.map((line, i) => <li key={i}><strong>{line.who === "agent" ? t.agent : t.caller}: </strong>{line.text}</li>)}</ol> : <p>{t.noTranscript}</p>}
      </details>)}
    </section>
  </section>;
}
