"use client";

import { useCallback, useEffect, useState } from "react";
import { SiteNav } from "@/components/SiteNav";
import { listSchemes, type SchemeInfo } from "@/lib/api";
import {
  FamilyError,
  family,
  generations,
  loadFamily,
  setToken,
  useToken,
  type FamilyLoad,
  type FamilyGraph,
  type FamilyMember,
  type MemberEligibility,
} from "@/lib/family";

type Lang = "en" | "hi";

// Hindi and English only for now: these strings have not been translated
// into Punjabi or Tamil, and an English page labelled Punjabi would be worse
// than an honest English one.
const T = {
  en: {
    title: "Your family",
    lede: "Link your family so schemes decided per family -- like PMFME's one person per family -- are easier to answer correctly.",
    privacy: "Each person keeps their own login. Nobody can add your account to a family: you join only with a code you redeem yourself. Your answers stay private unless you choose to share them.",
    signIn: "Sign in", register: "Create account", email: "Email", password: "Password (10+ characters)",
    noAccount: "New here?", haveAccount: "Already have an account?",
    start: "Start a family record", yourName: "Your name", familyName: "Family name (optional)", create: "Create",
    orJoin: "Or join your family with a code", code: "Invite code", join: "Join",
    add: "Add a relative", name: "Name", relation: "They are your…", birthYear: "Birth year (optional)",
    spouse: "Husband / wife", child: "Son / daughter", parent: "Father / mother", none: "Not sure yet",
    addBtn: "Add",
    rel: { self: "You", spouse: "Spouse", child: "Child", parent: "Parent", sibling: "Brother / sister",
           grandparent: "Grandparent", grandchild: "Grandchild", parent_in_law: "Parent-in-law",
           child_in_law: "Son / daughter-in-law", relative: "Relative" } as Record<string, string>,
    unlinked: "Not linked yet", account: "Has own account", record: "Record (no account)",
    invite: "Give them a code to join", inviteNote: "Tell them this code in person. It works once and expires in {d} days.",
    received: "Already received", recordBenefit: "Mark a scheme they already received", save: "Save",
    eligibleFor: "Appears eligible for", private: "Answers private", nothingYet: "Not enough answers yet",
    share: "Share my answers with my family", sharing: "Your answers are shared with your family.",
    notSharing: "Your answers are private.", leave: "Leave this family", leaveConfirm: "Leave this family record? Your account will be unlinked.",
    signOut: "Sign out", offline: "Couldn't reach the server.", noDb: "Family records need the database, which isn't configured on this server yet.",
    note: "A family record is a reminder, never a decision. When the app asks whether someone in your family already received a scheme, you still answer it yourself.",
  },
  hi: {
    title: "आपका परिवार",
    lede: "अपने परिवार को जोड़ें, ताकि जिन योजनाओं में परिवार गिना जाता है -- जैसे PMFME में एक परिवार से एक ही व्यक्ति -- उनके सवालों का सही जवाब देना आसान हो।",
    privacy: "हर व्यक्ति का अपना लॉगिन रहता है। कोई आपके खाते को परिवार में नहीं जोड़ सकता: आप ख़ुद कोड डालकर ही जुड़ते हैं। आपके जवाब निजी रहते हैं, जब तक आप उन्हें साझा न करें।",
    signIn: "साइन इन", register: "खाता बनाएँ", email: "ईमेल", password: "पासवर्ड (10+ अक्षर)",
    noAccount: "नए हैं?", haveAccount: "पहले से खाता है?",
    start: "परिवार का रिकॉर्ड शुरू करें", yourName: "आपका नाम", familyName: "परिवार का नाम (ज़रूरी नहीं)", create: "बनाएँ",
    orJoin: "या कोड से अपने परिवार में जुड़ें", code: "कोड", join: "जुड़ें",
    add: "परिवार का सदस्य जोड़ें", name: "नाम", relation: "वे आपके…", birthYear: "जन्म का साल (ज़रूरी नहीं)",
    spouse: "पति / पत्नी", child: "बेटा / बेटी", parent: "पिता / माता", none: "अभी पक्का नहीं",
    addBtn: "जोड़ें",
    rel: { self: "आप", spouse: "पति/पत्नी", child: "संतान", parent: "माता/पिता", sibling: "भाई/बहन",
           grandparent: "दादा-दादी/नाना-नानी", grandchild: "पोता-पोती", parent_in_law: "सास/ससुर",
           child_in_law: "बहू/दामाद", relative: "रिश्तेदार" } as Record<string, string>,
    unlinked: "अभी जुड़े नहीं", account: "अपना खाता है", record: "रिकॉर्ड (खाता नहीं)",
    invite: "जुड़ने के लिए कोड दें", inviteNote: "यह कोड उन्हें आमने-सामने बताएँ। यह एक बार चलेगा और {d} दिन में ख़त्म हो जाएगा।",
    received: "पहले से मिल चुका", recordBenefit: "जो योजना उन्हें पहले मिल चुकी है, उसे दर्ज करें", save: "सेव करें",
    eligibleFor: "इनके लिए पात्र लगते हैं", private: "जवाब निजी हैं", nothingYet: "अभी पूरे जवाब नहीं",
    share: "मेरे जवाब परिवार के साथ साझा करें", sharing: "आपके जवाब परिवार के साथ साझा हैं।",
    notSharing: "आपके जवाब निजी हैं।", leave: "यह परिवार छोड़ें", leaveConfirm: "परिवार का रिकॉर्ड छोड़ें? आपका खाता इससे अलग हो जाएगा।",
    signOut: "साइन आउट", offline: "सर्वर से जुड़ नहीं पाए।", noDb: "परिवार के रिकॉर्ड के लिए डेटाबेस चाहिए, जो इस सर्वर पर अभी सेट नहीं है।",
    note: "परिवार का रिकॉर्ड सिर्फ़ याद दिलाने के लिए है, फ़ैसला नहीं करता। जब ऐप पूछे कि परिवार में किसी को योजना पहले मिली है या नहीं, तो जवाब आप ख़ुद देते हैं।",
  },
};

type Text = (typeof T)["en"];

export default function FamilyPage() {
  const [lang, setLang] = useState<Lang>("hi");
  const t: Text = T[lang];
  const signedIn = Boolean(useToken());
  const [graph, setGraph] = useState<FamilyGraph | null>(null);
  const [noFamily, setNoFamily] = useState(false);
  const [eligibility, setEligibility] = useState<MemberEligibility[]>([]);
  const [schemes, setSchemes] = useState<SchemeInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [codes, setCodes] = useState<Record<number, string>>({});

  const explain = useCallback(
    (err: unknown) => {
      if (err instanceof FamilyError) {
        if (err.status === 0) return t.offline;
        if (err.status === 503) return t.noDb;
        return err.message;
      }
      return String(err);
    },
    [t],
  );

  const apply = useCallback(
    (result: FamilyLoad) => {
      if (result.kind === "ok") {
        setGraph(result.graph);
        setEligibility(result.eligibility);
        setNoFamily(false);
      } else if (result.kind === "none") {
        setGraph(null);
        setNoFamily(true);
      } else if (result.kind === "signed_out") {
        setGraph(null);
        setToken(null);
      } else {
        setError(explain(result.error));
      }
    },
    [explain],
  );

  const refresh = useCallback(async () => apply(await loadFamily()), [apply]);

  useEffect(() => {
    if (!signedIn) return;
    let live = true;
    void loadFamily().then((result) => {
      if (live) apply(result);
    });
    return () => {
      live = false;
    };
  }, [signedIn, apply]);

  useEffect(() => {
    void listSchemes(lang).then(setSchemes);
  }, [lang]);

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(explain(err));
    } finally {
      setBusy(false);
    }
  };

  const schemeName = (id: string) => schemes.find((s) => s.id === id)?.name ?? id;

  return (
    <main className="presentation-page family-page" lang={lang}>
      <div className="presentation-shell">
        <SiteNav active="family" />
        <header className="family-head">
          <div>
            <h1>{t.title}</h1>
            <p className="hero-deck">{t.lede}</p>
          </div>
          <div className="lang-pills" role="group" aria-label="Language">
            {(["hi", "en"] as Lang[]).map((code) => (
              <button
                key={code}
                type="button"
                className={`btn ghost${lang === code ? " on" : ""}`}
                aria-pressed={lang === code}
                onClick={() => setLang(code)}
              >
                {code === "hi" ? "हिन्दी" : "English"}
              </button>
            ))}
          </div>
        </header>

        <p className="family-privacy">{t.privacy}</p>
        {error && <p className="note error" role="alert">{error}</p>}

        {!signedIn && <SignIn t={t} busy={busy} run={run} />}

        {signedIn && noFamily && (
          <StartOrJoin t={t} busy={busy} run={run} onDone={(g) => { setGraph(g); setNoFamily(false); void refresh(); }} />
        )}

        {signedIn && graph && (
          <>
            <Tree
              t={t}
              graph={graph}
              eligibility={eligibility}
              schemeName={schemeName}
              codes={codes}
              busy={busy}
              onInvite={(id) =>
                run(async () => {
                  const { code } = await family.invite(id);
                  setCodes((prev) => ({ ...prev, [id]: code }));
                })
              }
              onBenefit={(id, scheme) =>
                run(async () => {
                  setGraph(await family.recordBenefit(id, scheme));
                })
              }
              schemes={schemes}
            />

            <AddRelative t={t} busy={busy} run={run} onDone={() => void refresh()} />

            <section className="family-card">
              <p>{graph.members.find((m) => m.id === graph.me)?.shares_profile ? t.sharing : t.notSharing}</p>
              <label className="family-check">
                <input
                  type="checkbox"
                  checked={Boolean(graph.members.find((m) => m.id === graph.me)?.shares_profile)}
                  disabled={busy}
                  onChange={(event) =>
                    run(async () => {
                      setGraph(await family.share(event.target.checked));
                      setEligibility((await family.eligibility()).members);
                    })
                  }
                />
                {t.share}
              </label>
              <div className="family-actions">
                <button
                  type="button"
                  className="btn ghost"
                  disabled={busy}
                  onClick={() => {
                    if (window.confirm(t.leaveConfirm)) {
                      void run(async () => {
                        await family.leave();
                        await refresh();
                      });
                    }
                  }}
                >
                  {t.leave}
                </button>
                <button
                  type="button"
                  className="btn ghost"
                  onClick={() => {
                    setToken(null);
                    setGraph(null);
                    setNoFamily(false);
                  }}
                >
                  {t.signOut}
                </button>
              </div>
            </section>
            <p className="note">{t.note}</p>
          </>
        )}
      </div>
    </main>
  );
}

type Run = (action: () => Promise<unknown>) => Promise<void>;

function SignIn({ t, busy, run }: { t: Text; busy: boolean; run: Run }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  return (
    <form
      className="family-card family-form"
      onSubmit={(event) => {
        event.preventDefault();
        void run(async () => {
          const { token } = mode === "login"
            ? await family.login(email, password)
            : await family.register(email, password);
          setToken(token); // useToken() re-renders the page as signed in
        });
      }}
    >
      <h2>{mode === "login" ? t.signIn : t.register}</h2>
      <label>
        {t.email}
        <input type="email" autoComplete="email" required value={email}
               onChange={(e) => setEmail(e.target.value)} />
      </label>
      <label>
        {t.password}
        <input type="password" minLength={10} required value={password}
               autoComplete={mode === "login" ? "current-password" : "new-password"}
               onChange={(e) => setPassword(e.target.value)} />
      </label>
      <button type="submit" className="btn" disabled={busy}>
        {mode === "login" ? t.signIn : t.register}
      </button>
      <button type="button" className="linkish" onClick={() => setMode(mode === "login" ? "register" : "login")}>
        {mode === "login" ? `${t.noAccount} ${t.register}` : `${t.haveAccount} ${t.signIn}`}
      </button>
    </form>
  );
}

function StartOrJoin({ t, busy, run, onDone }: {
  t: Text; busy: boolean; run: Run; onDone: (g: FamilyGraph) => void;
}) {
  const [myName, setMyName] = useState("");
  const [familyName, setFamilyName] = useState("");
  const [code, setCode] = useState("");
  return (
    <div className="family-grid">
      <form
        className="family-card family-form"
        onSubmit={(event) => {
          event.preventDefault();
          void run(async () => onDone(await family.create(myName, familyName)));
        }}
      >
        <h2>{t.start}</h2>
        <label>
          {t.yourName}
          <input required maxLength={120} value={myName} onChange={(e) => setMyName(e.target.value)} />
        </label>
        <label>
          {t.familyName}
          <input maxLength={120} value={familyName} onChange={(e) => setFamilyName(e.target.value)} />
        </label>
        <button type="submit" className="btn" disabled={busy}>{t.create}</button>
      </form>
      <form
        className="family-card family-form"
        onSubmit={(event) => {
          event.preventDefault();
          void run(async () => onDone(await family.join(code)));
        }}
      >
        <h2>{t.orJoin}</h2>
        <label>
          {t.code}
          <input required minLength={6} maxLength={64} autoCapitalize="characters"
                 value={code} onChange={(e) => setCode(e.target.value)} />
        </label>
        <button type="submit" className="btn" disabled={busy}>{t.join}</button>
      </form>
    </div>
  );
}

function AddRelative({ t, busy, run, onDone }: { t: Text; busy: boolean; run: Run; onDone: () => void }) {
  const [name, setName] = useState("");
  const [relation, setRelation] = useState<"spouse" | "child" | "parent" | "">("spouse");
  const [year, setYear] = useState("");
  return (
    <form
      className="family-card family-form"
      onSubmit={(event) => {
        event.preventDefault();
        void run(async () => {
          await family.addMember(name, relation || null, year ? Number(year) : undefined);
          setName("");
          setYear("");
          onDone();
        });
      }}
    >
      <h2>{t.add}</h2>
      <div className="family-row">
        <label>
          {t.name}
          <input required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          {t.relation}
          <select value={relation} onChange={(e) => setRelation(e.target.value as typeof relation)}>
            <option value="spouse">{t.spouse}</option>
            <option value="child">{t.child}</option>
            <option value="parent">{t.parent}</option>
            <option value="">{t.none}</option>
          </select>
        </label>
        <label>
          {t.birthYear}
          <input inputMode="numeric" pattern="[0-9]{4}" value={year} onChange={(e) => setYear(e.target.value)} />
        </label>
      </div>
      <button type="submit" className="btn" disabled={busy}>{t.addBtn}</button>
    </form>
  );
}

function Tree({ t, graph, eligibility, schemeName, codes, busy, onInvite, onBenefit, schemes }: {
  t: Text;
  graph: FamilyGraph;
  eligibility: MemberEligibility[];
  schemeName: (id: string) => string;
  codes: Record<number, string>;
  busy: boolean;
  onInvite: (id: number) => void;
  onBenefit: (id: number, scheme: string) => void;
  schemes: SchemeInfo[];
}) {
  const rows = generations(graph);
  return (
    <section className="family-tree" aria-label={t.title}>
      {rows.map((row, index) => (
        <div key={index} className="family-generation">
          {row.map((member) => (
            <MemberCard
              key={member.id}
              t={t}
              member={member}
              isMe={member.id === graph.me}
              eligibility={eligibility.find((e) => e.member_id === member.id)}
              schemeName={schemeName}
              code={codes[member.id]}
              busy={busy}
              onInvite={() => onInvite(member.id)}
              onBenefit={(scheme) => onBenefit(member.id, scheme)}
              schemes={schemes}
            />
          ))}
        </div>
      ))}
    </section>
  );
}

function MemberCard({ t, member, isMe, eligibility, schemeName, code, busy, onInvite, onBenefit, schemes }: {
  t: Text;
  member: FamilyMember;
  isMe: boolean;
  eligibility?: MemberEligibility;
  schemeName: (id: string) => string;
  code?: string;
  busy: boolean;
  onInvite: () => void;
  onBenefit: (scheme: string) => void;
  schemes: SchemeInfo[];
}) {
  const [scheme, setScheme] = useState("");
  const eligible = eligibility
    ? Object.entries(eligibility.schemes).filter(([, v]) => v === "ELIGIBLE").map(([k]) => k)
    : [];
  // Someone with their own account records their own benefits.
  const canRecord = isMe || !member.has_account;

  return (
    <article className={`member-card${isMe ? " me" : ""}`}>
      <header>
        <strong>{member.name}</strong>
        <span className="member-rel">{member.relation ? t.rel[member.relation] : t.unlinked}</span>
      </header>
      <p className="member-meta">
        {member.birth_year ? `${member.birth_year} · ` : ""}
        {member.has_account ? t.account : t.record}
      </p>

      {member.benefits.length > 0 && (
        <p className="member-line">
          <span className="muted-copy">{t.received}:</span>{" "}
          {member.benefits.map((b) => <span key={b} className="pill seal">{schemeName(b)}</span>)}
        </p>
      )}

      <p className="member-line">
        {eligibility?.private ? (
          <span className="muted-copy">{t.private}</span>
        ) : eligible.length ? (
          <>
            <span className="muted-copy">{t.eligibleFor}:</span>{" "}
            {eligible.map((s) => <span key={s} className="pill good">{schemeName(s)}</span>)}
          </>
        ) : (
          <span className="muted-copy">{t.nothingYet}</span>
        )}
      </p>

      {!member.has_account && !isMe && (
        code ? (
          <p className="invite-code">
            <code>{code}</code>
            <span className="muted-copy">{t.inviteNote.replace("{d}", "7")}</span>
          </p>
        ) : (
          <button type="button" className="btn ghost small" disabled={busy} onClick={onInvite}>
            {t.invite}
          </button>
        )
      )}

      {canRecord && (
        <form
          className="member-benefit"
          onSubmit={(event) => {
            event.preventDefault();
            if (scheme) onBenefit(scheme);
          }}
        >
          <select aria-label={t.recordBenefit} value={scheme} onChange={(e) => setScheme(e.target.value)}>
            <option value="">{t.recordBenefit}</option>
            {schemes.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <button type="submit" className="btn ghost small" disabled={busy || !scheme}>{t.save}</button>
        </form>
      )}
    </article>
  );
}
