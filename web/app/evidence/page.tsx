import { SiteNav } from "@/components/SiteNav";
import { BackendTargetNotice } from "@/components/BackendTargetNotice";

const REPOSITORY = "https://github.com/RonitKhanna333/govassist";
const PR_URL = `${REPOSITORY}/pull/5`;
const SOURCE_PDF = "https://pmfme.mofpi.gov.in/newsletters/docs/SchemeGuidelines.pdf";

function EvidenceCard({ title, children }: { title: string; children: React.ReactNode }) {
  return <article className="evidence-page-card"><h2>{title}</h2>{children}</article>;
}
export default function EvidencePage() {
  return (
    <main className="presentation-page evidence-page">
      <div className="presentation-shell">
        <SiteNav active="evidence" />
        <header className="evidence-hero">
          <p className="kicker">EVIDENCE / REPOSITORY</p>
          <h1>Show the work. Keep the boundary.</h1>
          <p className="hero-deck">A compact handoff for the UCS503 demonstration: what is backed by source, what is tested locally, what is configured, and what still needs a human.</p>
        </header>
        <BackendTargetNotice />
        <div className="evidence-page-grid">
          <EvidenceCard title="Repository and official source">
            <p><a href={REPOSITORY} target="_blank" rel="noreferrer">github.com/RonitKhanna333/govassist ↗</a></p>
            <p><a href={SOURCE_PDF} target="_blank" rel="noreferrer">Official PMFME SchemeGuidelines.pdf ↗</a></p>
            <p className="muted-copy">The citations shown in the prototype resolve to the committed extraction of this source. The quote remains in its original language.</p>
          </EvidenceCard>
          <EvidenceCard title="Prepared demo data">
            <p>Use a non-sensitive PMFME profile. For the boundary demonstration, keep every qualifying value the same and change only <code>age</code>:</p>
            <pre>{JSON.stringify({ applicant_type: "individual", is_existing_micro_food_processing_unit: true, identified_in_slup_or_verified: true, is_unincorporated: true, worker_count: 5, has_enterprise_ownership_right: true, age: 18, passed_class_8: true, family_member_already_received_assistance: false, will_formalize: true, own_contribution_percent: 10, will_take_bank_loan: true }, null, 2)}</pre>
            <p className="muted-copy">Expected age 18 result: <strong>NOT_ELIGIBLE</strong>, citing <code>individual-age-and-education</code>. Age 19 with the same profile: <strong>ELIGIBLE</strong>.</p>
          </EvidenceCard>
          <EvidenceCard title="Authoritative checks">
            <pre>{["python -m pytest -q", "python data/scripts/validate.py --all", "python data/scripts/build.py --all --check", "cd web", "npm test", "npm run build"].join("\n")}</pre>
            <p className="muted-copy">The GitHub Actions workflow repeats the backend and frontend checks for pull requests and pushes to <code>main</code>. Build success is not deployment proof.</p>
          </EvidenceCard>
          <EvidenceCard title="Human review still required">
            <p>PMFME Gate 4 is recorded as approved by Codex, and many clause approvals are also attributed to Codex. Gate 5 is recorded as approved by <code>thorb</code>, but the age expression changed and must be reviewed again.</p>
            <pre>{["$env:GOVASSIST_REVIEWER = \"Actual Human Reviewer Name\"", "python data/scripts/review.py --scheme pmfme --only all", "python data/scripts/review.py --scheme pmfme --conditions", "python data/scripts/validate.py --scheme pmfme", "python data/scripts/build.py --scheme pmfme"].join("\n")}</pre>
            <p className="muted-copy">Run interactively. Do not pipe answers or edit <code>.state.json</code>. Confirm: “above 18” means <code>&gt; 18</code>; age 18 fails and age 19 passes.</p>
          </EvidenceCard>
          <EvidenceCard title="Team contribution evidence">
            <ul><li>RonitKhanna333 / Ronit Khanna — commit and merge history is present in the repository.</li><li><code>thorb</code> — corpus, Gate 5 and engine/graph commits are present in the repository.</li><li>Shreyas / Shreyastacky — <a href={PR_URL} target="_blank" rel="noreferrer">PR #5</a>: presentation route, evidence page, UML presentation integration, navigation and supporting frontend work.</li><li>Bhavneet — <strong>Evidence pending</strong>.</li></ul>
            <p className="muted-copy">Add only exact commit, PR, issue, documentation or test links supplied by the team. No shared-work claim is inferred.</p>
          </EvidenceCard>
          <EvidenceCard title="Deployment handoff">
            <p>Preview deployed by Vercel; this PR is not merged to <code>main</code> and is not production-approved.</p>
            <ol><li>Configure the web Preview environment's <code>NEXT_PUBLIC_API_BASE</code> to the matching PR API preview URL.</li><li>Run human PMFME Gate 4/5 re-review for the corrected age boundary.</li><li>Open the matching preview signed out and repeat desktop/mobile, scheme picker, microphone, TTS, eligible/ineligible, age-18, language, link and console checks.</li><li>Merge PR #5 only after those checks; then verify the production deployment separately.</li></ol>
          </EvidenceCard>
        </div>
        <footer className="presentation-footer"><a href="/presentation">← Back to presentation</a><span>Evidence over theatre.</span></footer>
      </div>
    </main>
  );
}
