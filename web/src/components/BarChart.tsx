// Ranking bars (docs/v2-plan.md 5.4): horizontal, one teal series, zero baseline, value label at each tip,
// so there is no axis. Row order is the agent's order. Hover shows the exact value.

import type { Answer } from "@/lib/types";
import { exactValue } from "@/lib/format";

export function BarChart({ data }: { data: Answer }) {
  const { chart, columns, rows, display_rows } = data;
  if (!chart) return null;
  const xi = columns.findIndex((c) => c.name === chart.x);
  const yi = columns.findIndex((c) => c.name === chart.y);
  const values = rows.map((r) => Number(r[yi]));
  const max = Math.max(...values, 0) || 1;

  return (
    <figure className="chart">
      <figcaption className="chart-title">
        {columns[yi].label}, by {columns[xi].label.charAt(0).toLowerCase() + columns[xi].label.slice(1)}
      </figcaption>
      <ol className="bars">
        {rows.map((r, i) => (
          <li key={i} title={`${r[xi]}: ${exactValue(r[yi], columns[yi].unit, false)}`}>
            <span className="name">{String(r[xi])}</span>
            <span className="track">
              <span className="bar" style={{ "--w": `${(values[i] / max) * 100}%`, "--i": i } as React.CSSProperties} />
              <span className="val">{display_rows[i][yi]}</span>
            </span>
          </li>
        ))}
      </ol>
    </figure>
  );
}

/** Bars are drawn from zero to the right, so a negative value would be misleading: use the table instead. */
export function barsFit(data: Answer): boolean {
  if (!data.chart) return false;
  const yi = data.columns.findIndex((c) => c.name === data.chart!.y);
  return data.rows.every((r) => typeof r[yi] === "number" && (r[yi] as number) >= 0);
}
