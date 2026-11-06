// Headline numbers from web/src/data/stats.json (scripts/build_stats.py; tests/test_stats.py checks every value
// against pandas). Loans only. Rounded here for display; hover shows the exact value.
// The region chart is static: one series in the accent, value at each bar tip, so there is no axis.

import type { Stats as StatsFile } from "@/lib/types";
import { compactUsd, exactValue, longDate } from "@/lib/format";

export function Stats({ stats }: { stats: StatsFile }) {
  const items = [
    { label: "Outstanding", value: compactUsd(stats.outstanding_usd), exact: exactValue(stats.outstanding_usd, "usd", false) },
    { label: `Approved since FY${stats.first_fy}`, value: compactUsd(stats.approved_usd), exact: exactValue(stats.approved_usd, "usd", false) },
    { label: "Countries", value: stats.countries.toLocaleString("en-US") },
    { label: "Loans", value: stats.loans.toLocaleString("en-US") },
  ];
  return (
    <section className="stats" aria-label="The loan book">
      <dl>
        {items.map((s) => (
          <div key={s.label}>
            <dt>{s.label}</dt>
            <dd title={s.exact}>{s.value}</dd>
          </div>
        ))}
      </dl>
      <RegionChart regions={stats.outstanding_by_region} />
      <p className="snapshot">Snapshot {longDate(stats.end_of_period)} · guarantees excluded</p>
    </section>
  );
}

function RegionChart({ regions }: { regions: StatsFile["outstanding_by_region"] }) {
  const max = Math.max(...regions.map((r) => r.usd), 0) || 1;
  return (
    <figure className="chart region-chart">
      <figcaption className="chart-title">Outstanding by region</figcaption>
      <ol className="bars">
        {regions.map((r) => (
          <li key={r.region} title={`${r.label}: ${exactValue(r.usd, "usd", false)}`}>
            <span className="name">{r.label}</span>
            <span className="track">
              <span className="bar" style={{ "--w": `${(r.usd / max) * 100}%` } as React.CSSProperties} />
              <span className="val">{compactUsd(r.usd)}</span>
            </span>
          </li>
        ))}
      </ol>
    </figure>
  );
}
