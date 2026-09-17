import { DiagramPreview, type DiagramSpec, type ClassSpec } from "@/components/DiagramPreview";
import { BackendTargetNotice } from "@/components/BackendTargetNotice";
import { SiteNav } from "@/components/SiteNav";

const REPOSITORY = "https://github.com/RonitKhanna333/govassist";
const PR_URL = `${REPOSITORY}/pull/5`;
const SOURCE_PDF = "https://pmfme.mofpi.gov.in/newsletters/docs/SchemeGuidelines.pdf";
const LIVE_SITE = "https://govassist-web-git-main-ronit-khannas-projects.vercel.app";

type StatusKind = "implemented" | "tested" | "deployed" | "limited" | "planned";

function Status({ kind, children }: { kind: StatusKind; children: string }) {
  return <span className={"status status-" + kind}>{children}</span>;
}

function ExternalLink({ href, children }: { href: string; children: React.ReactNode }) {
  return <a href={href} target="_blank" rel="noreferrer">{children}</a>;
}

const useCases: { id: string; title: string; source: string; spec: DiagramSpec }[] = [
  {
    id: "UC-01", title: "Citizen eligibility check",
    source: "docs/diagrams/01-use-case-citizen-eligibility.mmd",
    spec: { kind: "usecase", id: "uc-01", actors: ["Citizen"], cases: [
      { lines: ["Start PMFME", "assessment"], actor: 0 },
      { lines: ["Answer deterministic", "questions"], actor: 0 },
      { lines: ["View verdict"], actor: 0 },
      { lines: ["Open cited evidence"], actor: 0 },
    ] },
  },
  {
    id: "UC-02", title: "Ask a scheme question",
    source: "docs/diagrams/02-use-case-grounded-question.mmd",
    spec: { kind: "usecase", id: "uc-02", actors: ["Citizen"], cases: [
      { lines: ["Ask a scheme", "question"], actor: 0 },
      { lines: ["Route supported", "scheme query"], actor: 0 },
      { lines: ["Read committed", "PMFME clauses"], actor: 0 },
      { lines: ["Return cited answer", "or honest unknown"], actor: 0 },
    ] },
  },
  {
    id: "UC-03", title: "Multilingual typed / voice interaction",
    source: "docs/diagrams/03-use-case-multilingual-interaction.mmd",
    spec: { kind: "usecase", id: "uc-03", actors: ["Citizen", "Browser"], cases: [
      { lines: ["Choose one of", "four languages"], actor: 0 },
      { lines: ["Type a message"], actor: 0 },
      { lines: ["Record English / Hindi", "voice input"], actor: 0 },
      { lines: ["Translate to canonical", "English when configured"], actor: 1 },
      { lines: ["Read localized text", "and optional speech"], actor: 0 },
    ] },
  },
  {
    id: "UC-04", title: "Corpus ingestion and human review",
    source: "docs/diagrams/04-use-case-corpus-review.mmd",
    spec: { kind: "usecase", id: "uc-04", actors: ["Maintainer", "Human reviewer", "CI"], cases: [
      { lines: ["Ingest official", "source"], actor: 0 },
      { lines: ["Confirm identity", "and extraction"], actor: 1 },
      { lines: ["Confirm segment", "boundaries"], actor: 1 },
      { lines: ["Review every clause"], actor: 1 },
      { lines: ["Review conditions", "and boundaries"], actor: 1 },
      { lines: ["Validate corpus"], actor: 2 },
      { lines: ["Build projections"], actor: 2 },
    ] },
  },
];

const sequences: { id: string; title: string; source: string; spec: DiagramSpec }[] = [
  {
    id: "SD-01", title: "Start an eligibility assessment", source: "docs/diagrams/05-sequence-start-assessment.mmd",
    spec: { kind: "sequence", id: "sd-01", participants: ["Citizen", "Web Chat", "POST /chat", "decide()", "LanguageService"], steps: [
      { from: 0, to: 1, lines: ["Select Start"] }, { from: 1, to: 2, lines: ["profile: {}"] },
      { from: 2, to: 3, lines: ["evaluate empty profile"] }, { from: 3, to: 2, lines: ["pending question"] },
      { from: 2, to: 4, lines: ["plan speech"] }, { from: 2, to: 1, lines: ["greeting + question"] },
      { from: 1, to: 0, lines: ["Render controls"] },
    ] },
  },
  {
    id: "SD-02", title: "Submit an answer and obtain the next question", source: "docs/diagrams/06-sequence-submit-answer.mmd",
    spec: { kind: "sequence", id: "sd-02", participants: ["Citizen", "AnswerControls", "POST /chat", "decide()", "Forms"], steps: [
      { from: 0, to: 1, lines: ["Select Yes / No / number"] }, { from: 1, to: 2, lines: ["answers payload"] },
      { from: 2, to: 3, lines: ["find pending"] }, { from: 3, to: 2, lines: ["pending expression"] },
      { from: 2, to: 4, lines: ["store value"] }, { from: 4, to: 2, lines: ["updated profile"] },
      { from: 2, to: 3, lines: ["evaluate"] }, { from: 2, to: 1, lines: ["next question"] },
      { from: 1, to: 0, lines: ["Render control"] },
    ] },
  },
  {
    id: "SD-03", title: "Reach a final verdict with cited evidence", source: "docs/diagrams/07-sequence-final-verdict.mmd",
    spec: { kind: "sequence", id: "sd-03", participants: ["Citizen", "Web Chat", "POST /chat", "decide()", "Composer", "Verifier"], steps: [
      { from: 0, to: 1, lines: ["Submit final answer"] }, { from: 1, to: 2, lines: ["complete profile"] },
      { from: 2, to: 3, lines: ["restricted expressions"] }, { from: 3, to: 2, lines: ["verdict + citations"] },
      { from: 2, to: 4, lines: ["draft from evidence"] }, { from: 4, to: 5, lines: ["same citations"] },
      { from: 5, to: 2, lines: ["verified / fallback"] }, { from: 2, to: 1, lines: ["answer + citations"] },
      { from: 1, to: 0, lines: ["Show result"] },
    ] },
  },
  {
    id: "SD-04", title: "Ask a free-form scheme question", source: "docs/diagrams/08-sequence-free-form-question.mmd",
    spec: { kind: "sequence", id: "sd-04", participants: ["Citizen", "Web Chat", "POST /chat", "route()", "Conversation", "Clauses"], steps: [
      { from: 0, to: 1, lines: ["Ask question"] }, { from: 1, to: 2, lines: ["message"] },
      { from: 2, to: 3, lines: ["canonical query"] }, { from: 3, to: 2, lines: ["scheme domain"] },
      { from: 2, to: 4, lines: ["classify intent"] }, { from: 4, to: 5, lines: ["pass clause facts"] },
      { from: 5, to: 4, lines: ["plain facts + ids"] }, { from: 4, to: 2, lines: ["verified reply"] },
      { from: 2, to: 1, lines: ["reply + citations"] },
    ] },
  },
  {
    id: "SD-05", title: "Ingest, review, validate and build a scheme pack", source: "docs/diagrams/09-sequence-ingest-review-build.mmd",
    spec: { kind: "sequence", id: "sd-05", participants: ["Maintainer", "Reviewer", "ingest.py", ".state.json", "scheme.md", "CI"], steps: [
      { from: 0, to: 2, lines: ["official PDF"] }, { from: 2, to: 3, lines: ["Gates 0–3"] },
      { from: 1, to: 2, lines: ["inspect source"] }, { from: 2, to: 0, lines: ["chunks"] },
      { from: 0, to: 4, lines: ["draft clauses + expr"] }, { from: 1, to: 2, lines: ["Gate 4 review"] },
      { from: 2, to: 3, lines: ["named decisions"] }, { from: 1, to: 2, lines: ["Gate 5 review"] },
      { from: 2, to: 3, lines: ["boundary decisions"] }, { from: 5, to: 4, lines: ["validate + freshness"] },
    ] },
  },
];

const classDiagram: ClassSpec = {
  kind: "class", id: "class-architecture",
  nodes: [
    { id: "chat", title: "Chat", lines: ["+send()", "+answerValues()", "+toggleMic()"], x: 20, y: 20, w: 155, h: 92 },
    { id: "client", title: "ApiClient", lines: ["+sendChat(input)", "+transcribe()"], x: 205, y: 20, w: 155, h: 92 },
    { id: "router", title: "ChatRouter", lines: ["+chat(body)", "+health()", "+transcribe()"], x: 390, y: 20, w: 170, h: 92 },
    { id: "engine", title: "RuleEngine", lines: ["+decide()", "+load_rules()", "+load_clauses()"], x: 590, y: 20, w: 180, h: 92 },
    { id: "result", title: "EngineResult", lines: ["verdict", "pending", "citations"], x: 800, y: 20, w: 175, h: 92 },
    { id: "language", title: "LanguageService", lines: ["+translate()", "+plan_speech()", "+transcribe()"], x: 20, y: 165, w: 175, h: 92 },
    { id: "groq", title: "GroqLanguageProvider", lines: ["translate()", "transcribe()", "synthesize()"], x: 220, y: 165, w: 165, h: 92 },
    { id: "bhashini", title: "BhashiniProvider", lines: ["translate()", "synthesize()", "optional credentials"], x: 410, y: 165, w: 165, h: 92 },
    { id: "llm", title: "LLMProvider", lines: ["<<interface>>", "complete(system, user)", "tiered Groq adapter"], x: 600, y: 165, w: 175, h: 92 },
    { id: "composer", title: "Composer + Verifier", lines: ["draft_answer()", "verify()", "fallback if rejected"], x: 800, y: 165, w: 175, h: 92 },
    { id: "corpus", title: "CorpusLoaders", lines: ["scheme.md", "validate.py", "build.py"], x: 20, y: 310, w: 175, h: 92 },
    { id: "graph", title: "GraphTraversal", lines: ["eligibility_evidence()", "exclusions()", "benefits()"], x: 220, y: 310, w: 175, h: 92 },
    { id: "auth", title: "AuthRoutes + Database", lines: ["register / login", "session + profile", "optional / not enabled"], x: 410, y: 310, w: 175, h: 92 },
    { id: "citation", title: "Citation", lines: ["clause_id", "quote / page", "source_url"], x: 620, y: 310, w: 155, h: 92 },
  ],
  relations: [
    { from: "chat", to: "client", label: "calls" }, { from: "client", to: "router", label: "HTTP" },
    { from: "router", to: "engine", label: "decide" }, { from: "engine", to: "result", label: "returns" },
    { from: "engine", to: "corpus", label: "loads" }, { from: "result", to: "citation", label: "contains" },
    { from: "router", to: "language", label: "localizes" }, { from: "language", to: "groq", label: "fallback" },
    { from: "language", to: "bhashini", label: "optional" }, { from: "router", to: "llm", label: "explains" },
    { from: "llm", to: "composer", label: "provides" }, { from: "router", to: "graph", label: "other paths" },
    { from: "router", to: "auth", label: "optional" },
  ],
};

function Stat({ value, label }: { value: string; label: string }) {
  return <div className="presentation-stat"><strong>{value}</strong><span>{label}</span></div>;
}

export default function PresentationPage() {
  const verificationCommands = [
    "python -m pytest -q",
    "python data/scripts/validate.py --all",
    "python data/scripts/build.py --all --check",
    "cd web; npm test; npm run build",
  ].join("\n");

  return (
    <main className="presentation-page">
      <div className="presentation-shell">
        <SiteNav active="presentation" />
        <header className="presentation-hero">
          <div>
            <p className="kicker">UCS503 · FULL-STACK PROTOTYPE</p>
            <h1>GovAssist</h1>
            <p className="hero-deck">Government-scheme guidance that shows its work: deterministic eligibility logic, verbatim official evidence, and a conversation a citizen can actually use.</p>
            <div className="hero-actions">
              <a className="presentation-button primary" href="/">Launch the live PMFME demo <span aria-hidden="true">→</span></a>
              <ExternalLink href={REPOSITORY}>Open repository</ExternalLink>
            </div>
          </div>
          <aside className="hero-stamp" aria-label="Presentation status"><span>DEMO FILE</span><strong>PMFME</strong><small>prepared for classroom review</small></aside>
        </header>
        <BackendTargetNotice />

        <section className="status-band" aria-label="Capability status legend">
          <span className="status-label">Read the labels</span>
          <Status kind="implemented">Implemented in repo</Status>
          <Status kind="tested">Automated test</Status>
          <Status kind="deployed">Existing hosted route</Status>
          <Status kind="limited">Limited / disabled</Status>
          <Status kind="planned">Next step</Status>
        </section>
        <section className="stats-row" aria-label="Project at a glance">
          <Stat value="4" label="interface languages" /><Stat value="8" label="PMFME conditions" />
          <Stat value="28" label="source-grounded clauses" /><Stat value="10" label="UML diagrams" />
        </section>

        <section className="presentation-section two-col" id="problem">
          <div><p className="kicker">01 · WHY THIS PROJECT</p><h2>A scheme should not be a guessing game.</h2><p>Government guidance is often long, formal and scattered across PDFs. A citizen may know their situation but not the vocabulary of the circular. GovAssist turns one official source into a guided check, then keeps the evidence attached to the answer.</p></div>
          <div className="story-cards"><article><span className="card-index">USER</span><h3>Intended users</h3><p>Rural entrepreneurs and first-time applicants checking whether an existing micro food-processing unit fits PMFME’s individual-unit route.</p></article><article><span className="card-index">CHOICE</span><h3>Why PMFME</h3><p>It has a concrete eligibility journey, a committed official source PDF, meaningful thresholds, and a useful real-world problem for a grounded prototype.</p></article></div>
        </section>

        <section className="presentation-section" id="solution">
          <p className="kicker">02 · PROPOSED SOLUTION</p><h2>Ask naturally. Decide deterministically. Cite precisely.</h2>
          <div className="solution-grid"><article><span className="solution-number">01</span><h3>Conversation</h3><p>Plain-language questions, four text interfaces, and English/Hindi microphone input where it is enabled.</p><Status kind="implemented">Implemented</Status></article><article><span className="solution-number">02</span><h3>Rule engine</h3><p>The LLM never decides eligibility. A restricted three-valued evaluator applies the reviewed PMFME expressions.</p><Status kind="tested">Tested</Status></article><article><span className="solution-number">03</span><h3>Evidence</h3><p>Every decisive condition resolves to the exact clause, page number and official source URL.</p><Status kind="tested">Tested</Status></article></div>
        </section>

        <section className="presentation-section journey" id="live-prototype">
          <div className="section-heading-row"><div><p className="kicker">03 · IMPLEMENTED USER JOURNEY</p><h2>From “Start” to a defensible answer.</h2></div><a className="text-link" href="/">Open prototype ↗</a></div>
          <ol><li><strong>Start</strong><span>Chat requests an empty PMFME assessment.</span></li><li><strong>Answer</strong><span>Buttons, choice fields, numbers and plain text fill only known profile attributes.</span></li><li><strong>Evaluate</strong><span>Missing information stays unknown; a failed rule becomes not eligible.</span></li><li><strong>Explain</strong><span>Groq may compose a grounded explanation from the deciding citations; the verifier may withhold it.</span></li><li><strong>Inspect</strong><span>The final panel keeps the original-language quotation and official page link visible.</span></li></ol>
          <div className="launch-card"><div><Status kind="deployed">Existing hosted prototype</Status><h3>Run the PMFME demonstration</h3><p>Use the existing hosted root for the signed-out PMFME flow. This PR's presentation and evidence routes are available in its Vercel preview, not production-approved.</p></div><ExternalLink href={LIVE_SITE}>Open existing hosted site <span aria-hidden="true">↗</span></ExternalLink></div>
        </section>

        <section className="presentation-section" id="architecture">
          <p className="kicker">04 · SYSTEM ARCHITECTURE</p><h2>A small chain of accountable components.</h2>
          <div className="architecture-grid"><article><span className="architecture-layer">FRONTEND</span><h3>Next.js Chat</h3><p>Chat, localized catalogs, answer controls, recorder and speech fallback.</p><Status kind="deployed">Root route hosted</Status></article><article><span className="architecture-layer">API</span><h3>FastAPI /chat</h3><p>Routes text, profile answers, language handling and visible degradation.</p><Status kind="tested">Tested with TestClient</Status></article><article><span className="architecture-layer">GROUNDING</span><h3>PMFME corpus</h3><p>Official PDF → extracted text → reviewed clauses → generated rules, graph and clause rows.</p><Status kind="implemented">Committed data</Status></article><article><span className="architecture-layer">OPTIONAL AI</span><h3>Groq + providers</h3><p>Groq is configured for the current deployment. Bhashini and database/auth code are present but not configured for the deployed demo.</p><Status kind="limited">Configuration-dependent</Status></article></div>
          <div className="architecture-note"><strong>Invariant:</strong> the verdict and citations still work without Groq. A missing provider must degrade to an honest visible state, never a fabricated verdict.</div>
        </section>

        <section className="presentation-section diagrams" id="uml">
          <div className="section-heading-row"><div><p className="kicker">05 · UML MATERIAL</p><h2>Ten diagrams, controlled as source.</h2></div><span className="diagram-count">4 use case · 5 sequence · 1 class</span></div>
          <p className="section-intro">These are responsive presentation previews paired with formal Mermaid UML/source artifacts in <code>docs/diagrams/</code>. The SVG previews are maintained as presentation data; the .mmd files remain the reviewable UML sources.</p>
          <h3 className="diagram-group-title">Use case diagrams</h3>
          <div className="diagram-grid">{useCases.map((diagram) => <article className="diagram-card" key={diagram.id}><div className="diagram-card-head"><span>{diagram.id}</span><h3>{diagram.title}</h3></div><DiagramPreview spec={diagram.spec} /><code>{diagram.source}</code></article>)}</div>
          <h3 className="diagram-group-title">Sequence diagrams</h3>
          <div className="diagram-grid">{sequences.map((diagram) => <article className="diagram-card" key={diagram.id}><div className="diagram-card-head"><span>{diagram.id}</span><h3>{diagram.title}</h3></div><DiagramPreview spec={diagram.spec} /><code>{diagram.source}</code></article>)}</div>
          <h3 className="diagram-group-title">Detailed class diagram</h3>
          <article className="diagram-card diagram-wide"><div className="diagram-card-head"><span>CD-01</span><h3>Frontend, API, grounding, providers and optional services</h3></div><DiagramPreview spec={classDiagram} /><code>docs/diagrams/10-class-architecture.mmd</code></article>
        </section>

        <section className="presentation-section" id="scope">
          <p className="kicker">06 · SCOPE HONESTY</p><h2>What is complete, what is bounded, what comes next.</h2>
          <div className="scope-table" role="table" aria-label="Capability status"><div className="scope-row scope-header" role="row"><span>Capability</span><span>Status</span><span>Truthful boundary</span></div><div className="scope-row" role="row"><span>PMFME individual eligibility</span><Status kind="implemented">Implemented</Status><span>Eight deterministic conditions; age boundary is <code>&gt; 18</code>.</span></div><div className="scope-row" role="row"><span>Official citations</span><Status kind="tested">Tested</Status><span>Verbatim quotes, page numbers and source URLs are retained.</span></div><div className="scope-row" role="row"><span>Groq explanation / translation</span><Status kind="deployed">Configured</Status><span>Optional explanation and language service; never the decision-maker.</span></div><div className="scope-row" role="row"><span>Punjabi and Tamil text</span><Status kind="implemented">Implemented</Status><span>Static interface text is supported; microphone input is not enabled for these locales.</span></div><div className="scope-row" role="row"><span>Bhashini</span><Status kind="limited">Not configured</Status><span>Provider code exists; no deployed credentials are claimed.</span></div><div className="scope-row" role="row"><span>Database and authentication</span><Status kind="limited">Not enabled</Status><span>Optional code exists; production database/auth are not configured in the demo.</span></div><div className="scope-row" role="row"><span>Additional schemes and filing</span><Status kind="planned">Planned</Status><span>PMFME is the only demonstrated production scheme; no form filing is performed.</span></div></div>
        </section>

        <section className="presentation-section" id="evidence">
          <p className="kicker">07 · EVIDENCE</p><h2>Claims stay close to what can be checked.</h2>
          <div className="evidence-grid"><article><h3>Repository and source</h3><p>Implementation, tests, corpus and diagrams:</p><ExternalLink href={REPOSITORY}>github.com/RonitKhanna333/govassist</ExternalLink><p className="small-copy">Official PMFME source:</p><ExternalLink href={SOURCE_PDF}>SchemeGuidelines.pdf</ExternalLink></article><article><h3>Verification commands</h3><pre>{verificationCommands}</pre><p>Run these in the repository root. CI repeats the checks on pushes to <code>main</code> and pull requests.</p></article><article><h3>Browser proof</h3><p>Preview verification remains separate from build evidence: desktop/mobile layout, eligible/ineligible flows, the exact age-18 boundary, scheme picker, microphone, TTS, language flows, console and link checks.</p><Status kind="planned">Manual preview verification pending</Status></article></div>
        </section>

        <section className="presentation-section" id="contributions">
          <p className="kicker">08 · TEAM CONTRIBUTION EVIDENCE</p><h2>Named work needs a traceable trail.</h2><p className="section-intro">This table is driven from repository history reviewed for this deliverable. It does not infer work from team membership or presentation roles.</p>
          <div className="contribution-table"><div className="contribution-row contribution-header"><span>Recorded identity</span><span>Verifiable evidence</span><span>Claim allowed now</span></div><div className="contribution-row"><span>RonitKhanna333 / Ronit Khanna</span><span><ExternalLink href={REPOSITORY + "/commits/main"}>main history</ExternalLink> · <ExternalLink href={REPOSITORY + "/commit/81bff08e36e430fb305bc5ba4e75b0f4a3ba93d6"}>chat / voice commit</ExternalLink></span><span>Repository commits exist; the person should demonstrate the specific changes.</span></div><div className="contribution-row"><span>thorb</span><span><ExternalLink href={REPOSITORY + "/commit/0f39b9e506dde864f26a9c3eabb6b24bf4ffec3f"}>Gate 5 commit</ExternalLink> · <ExternalLink href={REPOSITORY + "/commit/ce887fd49819bc78062c143d08526577f8c1f365"}>engine / graph commit</ExternalLink></span><span>Repository commits exist; preserve the recorded identity and re-check the corrected age rule.</span></div><div className="contribution-row"><span>Shreyas / Shreyastacky</span><span><ExternalLink href={PR_URL}>PR #5</ExternalLink>: presentation route, evidence page, UML presentation integration, navigation and supporting frontend work.</span><span>This PR is traceable contribution evidence; do not infer work beyond its diff.</span></div><div className="contribution-row"><span>Bhavneet</span><span><Status kind="limited">Evidence pending</Status></span><span>Do not claim commits, reviews or implementation work until a commit, PR, issue, documentation edit or test link is supplied.</span></div></div>
          <div className="checklist"><h3>Lab demonstration checklist</h3><ul><li>Each member names one exact file, commit/PR/issue or test they can open and explain.</li><li>Each member runs the relevant check and explains one failure boundary.</li><li>Each member makes or points to a small traceable modification without rewriting another person’s history.</li><li>Evidence-pending members supply the exact links before contribution claims are added.</li></ul></div>
        </section>

        <section className="presentation-section final-section" id="next">
          <p className="kicker">09 · NEXT</p><h2>Human review first. Deployment second.</h2>
          <div className="next-grid"><div><Status kind="limited">Human gate required</Status><p>Review PMFME clauses again, then confirm all eight conditions with special attention to <code>age &gt; 18</code>. The exact commands are on the evidence page.</p><a className="text-link" href="/evidence">Open remediation steps ↗</a></div><div><Status kind="planned">Merge after evidence</Status><p>Verify the matching Vercel preview first. After human review and demo checks, merge PR #5, then verify the production deployment.</p><ExternalLink href={PR_URL}>Open PR #5 ↗</ExternalLink></div></div>
        </section>
        <footer className="presentation-footer"><span>GovAssist · UCS503 prototype</span><span>Evidence over theatre.</span></footer>
      </div>
    </main>
  );
}
