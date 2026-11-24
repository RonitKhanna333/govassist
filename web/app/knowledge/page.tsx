"use client";

import { useEffect, useMemo, useState } from "react";
import { Citations } from "@/components/Citations";
import { SiteNav } from "@/components/SiteNav";
import { API_BASE, type Citation } from "@/lib/api";
import { makeTranslator } from "@/lib/i18n";

type Clause = { id: string; type: string; plain: string; quote: string; page: number | null; source_url: string };
type Scheme = { id: string; name: string; authority: string | null; reviewed: boolean; clauses: Clause[] };
type Lang = "en" | "hi";

const COPY = {
  en: {
    title: "Ask about any scheme", deck: "One question, answered from the official rules of every scheme GovAssist covers — with the exact clauses quoted.",
    placeholder: "e.g. Which schemes give a pension?", ask: "Ask", asking: "Finding the rules…",
    unknown: "Not found in the official rules — no answer is made up.", browse: "Knowledge base", search: "Search all rules",
    rules: "rules", unreviewed: "Not yet reviewed", source: "Official source", none: "No rules match.",
    examples: ["Which schemes give a pension?", "What documents do I need for PM-KISAN?", "Who cannot get Ujjwala?"],
    types: { eligibility: "Who qualifies", exclusion: "Who is excluded", benefit: "Benefit", document: "Documents", procedure: "How it works", definition: "Definition" } as Record<string, string>,
  },
  hi: {
    title: "किसी भी योजना के बारे में पूछें", deck: "एक सवाल, GovAssist की हर योजना के सरकारी नियमों से जवाब — नियम हूबहू उद्धृत।",
    placeholder: "जैसे: कौन सी योजनाएँ पेंशन देती हैं?", ask: "पूछें", asking: "नियम खोज रहे हैं…",
    unknown: "सरकारी नियमों में यह नहीं मिला — कोई जवाब गढ़ा नहीं जाता।", browse: "ज्ञान भंडार", search: "सभी नियम खोजें",
    rules: "नियम", unreviewed: "समीक्षा बाकी", source: "सरकारी स्रोत", none: "कोई नियम नहीं मिला।",
    examples: ["कौन सी योजनाएँ पेंशन देती हैं?", "पीएम किसान के लिए कौन से काग़ज़ चाहिए?", "उज्ज्वला किसे नहीं मिलती?"],
    types: { eligibility: "कौन पात्र है", exclusion: "कौन बाहर है", benefit: "लाभ", document: "काग़ज़", procedure: "प्रक्रिया", definition: "परिभाषा" } as Record<string, string>,
  },
};

export default function KnowledgePage() {
  const [lang, setLang] = useState<Lang>("en");
  const [schemes, setSchemes] = useState<Scheme[]>([]);
  const [filter, setFilter] = useState("");
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [reply, setReply] = useState<{ answer: string; grounded: boolean; citations: Citation[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const t = COPY[lang];
  const tr = makeTranslator(lang);

  useEffect(() => {
    fetch(`${API_BASE}/kb?locale=${lang}`).then(r => r.json()).then(d => setSchemes(d.schemes ?? []))
      .catch(() => setError("Could not load the knowledge base."));
  }, [lang]);

  const ask = async (q: string) => {
    if (!q.trim() || busy) return;
    setQuestion(q); setBusy(true); setError(null); setReply(null);
    try {
      const r = await fetch(`${API_BASE}/kb/ask`, { method: "POST", headers: { "Content-Type": "application/json" },
                                                   body: JSON.stringify({ question: q, locale: lang }) });
      if (!r.ok) throw new Error(String(r.status));
      setReply(await r.json());
    } catch { setError("The question could not be answered right now. Try again."); }
    finally { setBusy(false); }
  };

  const needle = filter.trim().toLowerCase();
  const shown = useMemo(() => schemes.map(s => ({ ...s, clauses: needle ? s.clauses.filter(c =>
    `${c.plain} ${c.quote} ${s.name}`.toLowerCase().includes(needle)) : s.clauses })).filter(s => s.clauses.length),
    [schemes, needle]);

  return (
    <div className="shell kb-shell" lang={lang}>
      <SiteNav active="knowledge" />
      <header className="masthead">
        <div className="kb-head">
          <h1>{t.title}</h1>
          <div className="lang-pills" role="group" aria-label="Language">
            {(["en", "hi"] as Lang[]).map(code => <button key={code} type="button" className={`btn ghost${code === lang ? " on" : ""}`}
              aria-pressed={code === lang} onClick={() => { setLang(code); setReply(null); }}>{code === "en" ? "English" : "हिन्दी"}</button>)}
          </div>
        </div>
        <p className="kb-deck">{t.deck}</p>
      </header>

      <main className="panel kb-ask">
        <form onSubmit={e => { e.preventDefault(); ask(question); }} className="kb-form">
          <input value={question} onChange={e => setQuestion(e.target.value)} placeholder={t.placeholder} aria-label={t.placeholder} maxLength={500} />
          <button className="btn" disabled={busy || !question.trim()}>{busy ? t.asking : t.ask}</button>
        </form>
        {!reply && !busy && <div className="kb-examples">{t.examples.map(x => <button key={x} type="button" className="btn ghost" onClick={() => ask(x)}>{x}</button>)}</div>}
        {busy && <p className="muted-copy" role="status">{t.asking}</p>}
        {error && <p className="note error" role="alert">{error}</p>}
        {reply && <div className="kb-reply" role="status">
          <p className="kb-answer">{reply.grounded ? reply.answer : t.unknown}</p>
          {reply.grounded && <Citations citations={reply.citations} t={tr} />}
        </div>}
      </main>

      <section className="kb-browse" aria-labelledby="kb-browse-title">
        <div className="kb-browse-head">
          <h2 id="kb-browse-title">{t.browse}</h2>
          <input type="search" value={filter} onChange={e => setFilter(e.target.value)} placeholder={t.search} aria-label={t.search} />
        </div>
        {schemes.length > 0 && !shown.length && <p className="muted-copy">{t.none}</p>}
        {shown.map(s => <details key={s.id} className="kb-scheme" open={!!needle}>
          <summary><span className="kb-name">{s.name}</span>
            <span className="kb-meta">{s.clauses.length} {t.rules}{!s.reviewed && <em className="tag">{t.unreviewed}</em>}</span></summary>
          {s.authority && <p className="kb-authority">{s.authority}</p>}
          <ul>{s.clauses.map(c => <li key={c.id}>
            <span className={`kb-type kb-type-${c.type}`}>{t.types[c.type] ?? c.type}</span>
            <p>{c.plain}</p>
            <blockquote lang="en">{c.quote}</blockquote>
            {c.source_url && <a href={c.source_url} target="_blank" rel="noopener noreferrer">{t.source}{c.page != null ? ` · ${c.page}` : ""} ↗</a>}
          </li>)}</ul>
        </details>)}
      </section>
    </div>
  );
}
