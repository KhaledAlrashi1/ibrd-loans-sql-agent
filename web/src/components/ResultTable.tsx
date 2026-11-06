"use client";

// Hairline rows, numbers right-aligned in tabular figures, sticky header, first column sticky while the
// table scrolls sideways inside the card. "Show exact values" swaps the rounded text for the raw values.

import { useState } from "react";
import type { Answer } from "@/lib/types";
import { exactValue, isYearColumn } from "@/lib/format";

/** A rank column only for "top N" results: an ordered, limited ranking. */
export function isRanking(data: Answer): boolean {
  return data.chart?.kind === "bar" && /\border\s+by\b[\s\S]*\blimit\s+\d+\s*;?\s*$/i.test(data.sql);
}

export function ResultTable({ data }: { data: Answer }) {
  const [exact, setExact] = useState(false);
  const { columns, rows, display_rows } = data;
  const numeric = columns.map((_, j) => rows.every((r) => r[j] === null || typeof r[j] === "number"));
  const rounded = columns.some((c, j) => numeric[j] && c.unit !== "plain");
  const rank = isRanking(data);

  return (
    <div className="table-block">
      {rounded && (
        <div className="table-tools">
          <button type="button" role="switch" aria-checked={exact} className="switch" onClick={() => setExact((v) => !v)}>
            <span className="switch-track" aria-hidden="true"><span className="switch-thumb" /></span>
            Show exact values
          </button>
        </div>
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
        <p className="note">Showing the first {data.row_limit.toLocaleString("en-US")} rows. Ask a narrower question to see the rest.</p>
      )}
    </div>
  );
}
