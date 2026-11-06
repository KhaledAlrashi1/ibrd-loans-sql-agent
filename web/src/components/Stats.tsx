// Headline numbers from web/src/data/stats.json (scripts/build_stats.py; tests/test_stats.py checks every value
// against pandas). Loans only. Rounded here for display; hover shows the exact value.

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
      <p className="snapshot">Snapshot {longDate(stats.end_of_period)} · guarantees excluded</p>
    </section>
  );
}
