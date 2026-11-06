"use client";

// Hairline rows, numbers right-aligned in tabular figures, sticky header, first column sticky while the
// table scrolls sideways inside the card. "Exact values" swaps the rounded text for the raw values.

import { useState } from "react";
import type { Answer } from "@/lib/types";
import { exactValue, isYearColumn } from "@/lib/format";

/** A rank column only for "top N" results: an ordered, limited ranking. */
export function isRanking(data: Answer): boolean {
  return data.chart?.kind === "bar" && /\border\s+by\b[\s\S]*\blimit\s+\d+\s*;?\s*$/i.test(data.sql);
}

const numericColumns = ({ columns, rows }: Answer) =>
  columns.map((_, j) => rows.every((r) => r[j] === null || typeof r[j] === "number"));

/** True when some value is shown rounded ($14.85B), so "Exact values" has something to show. */
export function hasRoundedValues(data: Answer): boolean {
  const numeric = numericColumns(data);
  return data.columns.some((c, j) => numeric[j] && c.unit !== "plain");
}

export function ExactSwitch({ on, onChange }: { on: boolean; onChange: (on: boolean) => void }) {
  return (
    <button type="button" role="switch" aria-checked={on} className="switch" onClick={() => onChange(!on)}>
      <span className="switch-track" aria-hidden="true"><span className="switch-thumb" /></span>
      Exact values
    </button>
  );
}

/** With `exact` given, the caller owns the switch (the Chart/Table bar); otherwise the table shows its own. */
export function ResultTable({ data, exact: controlled }: { data: Answer; exact?: boolean }) {
  const [own, setOwn] = useState(false);
  const exact = controlled ?? own;
  const { columns, rows, display_rows } = data;
  const numeric = numericColumns(data);
  const rank = isRanking(data);

  return (
    <div className="table-block">
      {controlled === undefined && hasRoundedValues(data) && (
        <div className="table-tools"><ExactSwitch on={own} onChange={setOwn} /></div>
      )}
      <div className="table-scroll" tabIndex={0} role="region" aria-label="Result table">
        <table>
          <thead>
            <tr>
              {rank && <th scope="col" className="num rank">#</th>}
              {columns.map((c, j) => (
                <th key={c.name} scope="col" className={numeric[j] ? "num" : undefined}>{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                {rank && <td className="num rank">{i + 1}</td>}
                {columns.map((c, j) => {
                  const shown = display_rows[i][j];
                  const full = exactValue(r[j], c.unit, isYearColumn(c.name));
                  return (
                    <td key={c.name} className={numeric[j] ? "num" : undefined} title={!exact && full !== shown ? full : undefined}>
                      {r[j] === null ? <span className="null" aria-label="no value">—</span> : exact ? full : shown}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.truncated && (
        <p className="note">First {data.row_limit.toLocaleString("en-US")} rows only. Narrow the question to see the rest.</p>
      )}
    </div>
  );
}
