"use client";

import { useEffect, useState } from "react";
import { AnswerControls } from "./AnswerControls";
import { SiteNav } from "./SiteNav";
import { AccountDashboard } from "./AccountDashboard";
import { account, AccountError, type AccountLocale, type Dashboard, type InterviewState } from "@/lib/account";
import { setToken, useToken } from "@/lib/family";
import { makeTranslator } from "@/lib/i18n";

const COPY = {
  en: {
    title: "Find the support you qualify for", intro: "One profile. One interview. Explore government schemes with the official rules behind every result.",
    create: "Create account", login: "Log in", name: "Your name", phone: "Phone number", password: "Password", passwordHint: "Use at least 10 characters.",
    haveAccount: "Already have an account? Log in", newAccount: "New here? Create an account", out: "Sign out", choose: "How would you like to fill your profile?",
    call: "Call me back", callInfo: "Our automated assistant asks the questions by phone and reads the result from our server.",
    self: "Fill it myself", selfInfo: "Answer a few questions here. Your answers are saved as you go.",
    consent: "I agree to receive an automated GovAssist call on my account phone number and have its questions and answers saved to my account.",
    callSent: "Your callback was requested. Watch your phone. Refresh the dashboard after the call to see your saved answers.",
    interview: "Your profile interview", basic: "Basics first, then only the follow-ups relevant to your answers.",
    unknown: "I’m not sure — skip for now", done: "You’ve reached the end of the available questions. Skipped answers remain unknown; you can return to them later.",
    dash: "View dashboard", back: "Back to choices", retry: "Try again", working: "Please wait…", loading: "Loading your account…", saved: "answers saved", review: "Review saved answers", anonymous: "Explore a scheme without an account",
  },
  hi: {
    title: "अपने लिए सरकारी सहायता खोजें", intro: "एक प्रोफ़ाइल, एक बातचीत। हर नतीजे के साथ सरकारी नियम देखें।",
    create: "खाता बनाएँ", login: "लॉग इन", name: "आपका नाम", phone: "फ़ोन नंबर", password: "पासवर्ड", passwordHint: "कम से कम 10 अक्षर रखें।",
    haveAccount: "पहले से खाता है? लॉग इन करें", newAccount: "नए हैं? खाता बनाएँ", out: "साइन आउट", choose: "प्रोफ़ाइल कैसे भरना चाहेंगे?",
    call: "मुझे कॉल करें", callInfo: "हमारा स्वचालित सहायक फ़ोन पर सवाल पूछेगा और सर्वर का नतीजा सुनाएगा।",
    self: "मैं ख़ुद भरूँगा", selfInfo: "यहाँ कुछ सवालों के जवाब दें। जवाब साथ-साथ सेव होंगे।",
    consent: "मैं अपने खाते के फ़ोन नंबर पर GovAssist की स्वचालित कॉल पाने और उसके सवाल-जवाब अपने खाते में सेव करने के लिए सहमत हूँ।",
    callSent: "कॉल का अनुरोध भेज दिया गया है। फ़ोन पर ध्यान रखें। कॉल के बाद सेव किए गए जवाब देखने के लिए डैशबोर्ड रीफ़्रेश करें।",
    interview: "आपकी प्रोफ़ाइल के सवाल", basic: "पहले बुनियादी सवाल, फिर आपके जवाबों के अनुसार ज़रूरी सवाल।",
    unknown: "पक्का नहीं — अभी छोड़ें", done: "अभी उपलब्ध सवाल पूरे हुए। छोड़े गए जवाब अज्ञात रहेंगे; बाद में फिर भर सकते हैं।",
    dash: "डैशबोर्ड देखें", back: "विकल्पों पर लौटें", retry: "फिर कोशिश करें", working: "कृपया रुकें…", loading: "खाता लोड हो रहा है…", saved: "जवाब सेव हुए", review: "सेव किए गए जवाब देखें", anonymous: "बिना खाता बनाए योजना देखें",
  },
};

export function AccountHome() {
  const token = useToken();
  const [locale, setLocale] = useState<AccountLocale>("en");
  const t = COPY[locale];
  const [register, setRegister] = useState(true);
  const [view, setView] = useState<"choose" | "interview" | "dashboard">("choose");
  const [interview, setInterview] = useState<InterviewState | null>(null);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [skipped, setSkipped] = useState<string[]>([]);
  const [consent, setConsent] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadVersion, setLoadVersion] = useState(0);

  const fail = (err: unknown) => {
    if (err instanceof AccountError && err.status === 401) {
      setToken(null); setDashboard(null); setInterview(null);
    }
    setError(err instanceof Error ? err.message : String(err));
  };

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    Promise.all([account.interview(locale, controller.signal), account.dashboard(locale, controller.signal)])
      .then(([state, data]) => { setInterview(state); setDashboard(data); })
      .catch((err: unknown) => { if (!controller.signal.aborted) fail(err); });
    return () => controller.abort();
  }, [token, locale, loadVersion]);

  const run = async (action: () => Promise<void>) => {
    setBusy(true); setError(null);
    try { await action(); } catch (err) { fail(err); } finally { setBusy(false); }
  };
  const openDashboard = () => run(async () => {
    setDashboard(await account.dashboard(locale)); setView("dashboard");
  });
  const answer = (values: Record<string, unknown>) => run(async () => {
    setInterview(await account.answer(values, skipped, locale));
  });

  return <main className="presentation-page account-page" lang={locale}>
    <div className="presentation-shell">
      <SiteNav active="account" />
      <header className="family-head">
        <div><p className="account-eyebrow">GovAssist</p><h1>{t.title}</h1><p className="hero-deck">{t.intro}</p></div>
        <div className="family-actions">
          <label className="account-language">Language / भाषा <select value={locale} disabled={busy} onChange={e => { setLocale(e.target.value as AccountLocale); setSkipped([]); }}><option value="en">English</option><option value="hi">हिन्दी</option></select></label>
          {token && <button className="btn" disabled={busy} onClick={() => { setToken(null); setInterview(null); setDashboard(null); setView("choose"); setNotice(null); setSkipped([]); setConsent(false); }}>{t.out}</button>}
        </div>
      </header>
      {error && <div className="note error" role="alert"><p>{error}</p>{token && <button className="btn" disabled={busy} onClick={() => { setError(null); setLoadVersion(v => v + 1); }}>{t.retry}</button>}</div>}
      {notice && <p className="account-notice" role="status">{notice}</p>}
      {!token ? <section className="family-card account-auth">
        <h2>{register ? t.create : t.login}</h2>
        <form className="family-form" onSubmit={e => {
          e.preventDefault(); const data = new FormData(e.currentTarget);
          void run(async () => {
            const result = register
              ? await account.register(String(data.get("name")), String(data.get("phone")), String(data.get("password")), locale)
              : await account.login(String(data.get("phone")), String(data.get("password")));
            setToken(result.token); setView("choose");
          });
        }}>
          {register && <label>{t.name}<input name="name" autoComplete="name" required maxLength={120} disabled={busy} /></label>}
          <label>{t.phone}<input name="phone" type="tel" autoComplete="tel" placeholder="98765 43210" required maxLength={20} disabled={busy} /></label>
          <label>{t.password}<input name="password" type="password" autoComplete={register ? "new-password" : "current-password"} required minLength={register ? 10 : 1} maxLength={256} disabled={busy} />{register && <small>{t.passwordHint}</small>}</label>
          <button className="btn primary" disabled={busy}>{busy ? t.working : register ? t.create : t.login}</button>
          <button type="button" className="linkish" disabled={busy} onClick={() => { setRegister(!register); setError(null); }}>{register ? t.haveAccount : t.newAccount}</button>
        </form>
      </section> : <>
        <div className="family-actions account-tabs">
          <button className="btn" disabled={busy} onClick={() => setView("choose")}>{t.back}</button>
          <button className="btn" disabled={busy} onClick={() => void openDashboard()}>{t.dash}</button>
        </div>
        {view === "choose" && <section>
          <h2>{t.choose}</h2><div className="family-grid">
            <article className="family-card"><h3>{t.call}</h3><p>{t.callInfo}</p>
              <label className="family-check"><input type="checkbox" checked={consent} disabled={busy} onChange={e => setConsent(e.target.checked)} />{t.consent}</label>
              <button className="btn primary" disabled={busy || !consent} onClick={() => void run(async () => {
                await account.callback(consent, locale); setNotice(t.callSent); setDashboard(await account.dashboard(locale));
              })}>{busy ? t.working : t.call}</button>
            </article>
            <article className="family-card"><h3>{t.self}</h3><p>{t.selfInfo}</p><button className="btn primary" disabled={busy} onClick={() => void run(async () => {
              setSkipped([]); setInterview(await account.interview(locale)); setView("interview");
            })}>{t.self}</button></article>
          </div>
        </section>}
        {view === "interview" && <section className="family-card account-interview" aria-live="polite">
          <h2>{t.interview}</h2><p>{t.basic}</p>
          {interview ? <>
            <p className="muted-copy">{interview.progress.answered} {t.saved}</p>
            {interview.question ? <div key={interview.question.attribute}>
              <h3>{interview.question.ask}</h3>
              <AnswerControls pending={{ condition_id: interview.question.attribute, asks: interview.question.ask, fields: [interview.question] }} busy={busy} onValues={values => void answer(values)} t={makeTranslator(locale)} />
              <button className="linkish account-skip" disabled={busy} onClick={() => void run(async () => {
                const nextSkipped = [...skipped, interview.question!.attribute];
                const next = await account.answer({}, nextSkipped, locale); setSkipped(nextSkipped); setInterview(next);
              })}>{t.unknown}</button>
            </div> : <><p>{t.done}</p><button className="btn primary" disabled={busy} onClick={() => void openDashboard()}>{t.dash}</button></>}
          </> : <p role="status">{t.loading}</p>}
        </section>}
        {view === "dashboard" && (dashboard ? <AccountDashboard data={dashboard} locale={locale} busy={busy} onRefresh={() => void openDashboard()} onContinue={() => void run(async () => { setSkipped([]); setInterview(await account.interview(locale)); setView("interview"); })} onEdit={field => { setInterview(state => ({ profile: dashboard.profile, question: field, progress: state?.progress ?? { answered: 0, remaining: 0 }, verdicts: state?.verdicts ?? {} })); setView("interview"); }} /> : <p role="status">{t.loading}</p>)}
      </>}
      <p className="account-anonymous"><a href="/schemes">{t.anonymous}</a></p>
    </div>
  </main>;
}
