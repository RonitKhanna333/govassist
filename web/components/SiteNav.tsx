import Link from "next/link";

interface NavLabels {
  presentation: string;
  live: string;
  evidence: string;
  family: string;
  knowledge?: string;
}

const DEFAULT_LABELS: NavLabels = {
  presentation: "Presentation",
  live: "Check a scheme",
  evidence: "Evidence",
  family: "Family",
  knowledge: "Ask all schemes",
};

type Active = "presentation" | "live" | "evidence" | "family" | "account" | "knowledge";

// One header for every page: brand on the left, primary navigation on the right.
export function SiteNav({ active, labels = DEFAULT_LABELS }: { active?: Active; labels?: NavLabels }) {
  const items: [Active, string, string][] = [
    ["account", "/", "My account"],
    ["live", "/schemes", labels.live],
    ["knowledge", "/knowledge", labels.knowledge ?? DEFAULT_LABELS.knowledge!],
    ["family", "/family", labels.family],
    ["presentation", "/presentation", labels.presentation],
    ["evidence", "/evidence", labels.evidence],
  ];
  return (
    <header className="topbar">
      <Link className="brand" href="/">
        <span className="brand-mark" aria-hidden="true">G</span>
        GovAssist
      </Link>
      <nav className="site-nav" aria-label="Primary navigation">
        {items.map(([key, href, label]) => (
          <Link key={key} href={href} className={active === key ? "active" : undefined}
                aria-current={active === key ? "page" : undefined}>{label}</Link>
        ))}
      </nav>
    </header>
  );
}
