interface NavLabels {
  presentation: string;
  live: string;
  evidence: string;
}

const DEFAULT_LABELS: NavLabels = {
  presentation: "Presentation",
  live: "Live prototype",
  evidence: "Evidence / repository",
};

export function SiteNav({
  active,
  labels = DEFAULT_LABELS,
}: {
  active?: "presentation" | "live" | "evidence";
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
      {link("evidence", "/evidence")}
    </nav>
  );
}
