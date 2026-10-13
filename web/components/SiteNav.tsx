interface NavLabels {
  presentation: string;
  live: string;
  evidence: string;
  family: string;
}

const DEFAULT_LABELS: NavLabels = {
  presentation: "Presentation",
  live: "Live prototype",
  evidence: "Evidence / repository",
  family: "Family",
};

export function SiteNav({
  active,
  labels = DEFAULT_LABELS,
}: {
  active?: "presentation" | "live" | "evidence" | "family";
  labels?: NavLabels;
}) {
  const link = (key: keyof NavLabels, href: string) => (
    <a
      href={href}
      className={active === key ? "active" : undefined}
      aria-current={active === key ? "page" : undefined}
    >
      {labels[key]}
    </a>
  );

  return (
    <nav className="site-nav" aria-label="Primary navigation">
      {link("presentation", "/presentation")}
      {link("live", "/")}
      {link("family", "/family")}
      {link("evidence", "/evidence")}
    </nav>
  );
}
