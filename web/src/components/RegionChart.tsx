// "Outstanding by region" from web/src/data/stats.json (checked against pandas in tests/test_stats.py).
// Static: one series in the accent, value at each bar tip, so there is no axis. Hover shows the exact value.
// The subtitle is the snapshot date (End of Period), the date every bar is measured at.

import type { Stats } from "@/lib/types";
import { compactUsd, exactValue, longDate } from "@/lib/format";

export function RegionChart({ regions, endOfPeriod }: { regions: Stats["outstanding_by_region"]; endOfPeriod: string }) {
  const max = Math.max(...regions.map((r) => r.usd), 0) || 1;
  return (
    <figure className="chart region-chart">
      <figcaption className="chart-title">
        Outstanding by region{" "}
        <span className="chart-sub">As of {longDate(endOfPeriod)}</span>
      </figcaption>
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
