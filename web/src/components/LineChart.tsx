"use client";

// Fiscal-year series (docs/v2-plan.md 5.4): 2 px line, ringed markers, y axis from zero with compact ticks,
// hairline gridlines, FY ticks, only the last point labelled, crosshair + tooltip on hover.
// Drawn at the container's real pixel width so text is never stretched.

import { useEffect, useRef, useState } from "react";
import type { Answer } from "@/lib/types";
import { exactValue, niceTicks, tick } from "@/lib/format";

const H = 240;
const PAD = { top: 16, right: 64, bottom: 30, left: 52 };

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

export function LineChart({ data }: { data: Answer }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const { chart, columns, rows, display_rows } = data;
  if (!chart) return null;

  const xi = columns.findIndex((c) => c.name === chart.x);
  const yi = columns.findIndex((c) => c.name === chart.y);
  const unit = columns[yi].unit;
  const pts = rows.map((r, i) => ({ x: Number(r[xi]), y: Number(r[yi]), i })).sort((a, b) => a.x - b.x);
  const ys = pts.map((p) => p.y);
  const ticks = niceTicks(Math.min(...ys), Math.max(...ys));
  const [y0, y1] = [ticks[0], ticks[ticks.length - 1]];
  const [x0, x1] = [pts[0].x, pts[pts.length - 1].x];

  const w = Math.max(width, 280);
  const innerW = w - PAD.left - PAD.right, innerH = H - PAD.top - PAD.bottom;
  const sx = (x: number) => PAD.left + (x1 === x0 ? innerW / 2 : ((x - x0) / (x1 - x0)) * innerW);
  const sy = (y: number) => PAD.top + innerH - ((y - y0) / (y1 - y0 || 1)) * innerH;
  const every = Math.max(1, Math.ceil(pts.length / Math.max(2, Math.floor(innerW / 64))));
  const path = pts.map((p, k) => `${k ? "L" : "M"}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join("");
  const last = pts[pts.length - 1];
  const active = hover === null ? null : pts[hover];

  function onMove(e: React.PointerEvent<SVGRectElement>) {
    const box = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - box.left + PAD.left;
    let best = 0;
    pts.forEach((p, k) => { if (Math.abs(sx(p.x) - px) < Math.abs(sx(pts[best].x) - px)) best = k; });
    setHover(best);
  }

  return (
    <figure className="chart">
      <figcaption className="chart-title">{columns[yi].label}, by fiscal year</figcaption>
      <div className="line-wrap" ref={ref}>
        {width > 0 && (
          <svg width={w} height={H} role="img"
            aria-label={`${columns[yi].label} by fiscal year, FY${x0} to FY${x1}. The table view lists every value.`}>
            {ticks.map((t) => (
              <g key={t}>
                <line x1={PAD.left} x2={w - PAD.right} y1={sy(t)} y2={sy(t)} className={t === 0 ? "axis" : "grid"} />
                <text x={PAD.left - 8} y={sy(t)} dy="0.32em" textAnchor="end" className="tick">{tick(t, unit)}</text>
              </g>
            ))}
            {pts.map((p, k) => (k % every === 0 || k === pts.length - 1) && (
              <text key={p.x} x={sx(p.x)} y={H - 8} textAnchor="middle" className="tick">FY{p.x}</text>
            ))}
            {active && <line x1={sx(active.x)} x2={sx(active.x)} y1={PAD.top} y2={PAD.top + innerH} className="crosshair" />}
            <path d={path} className="series" />
            {pts.map((p, k) => (
              <circle key={p.x} cx={sx(p.x)} cy={sy(p.y)} r={hover === k ? 5 : 4} className="marker" />
            ))}
            <text x={sx(last.x) + 10} y={sy(last.y)} dy="0.32em" className="end-label">{display_rows[last.i][yi]}</text>
            <rect x={PAD.left} y={0} width={innerW} height={H} fill="transparent"
              onPointerMove={onMove} onPointerLeave={() => setHover(null)} />
          </svg>
        )}
        {active && (
          <div className="tooltip" style={{ left: sx(active.x), top: sy(active.y) }} aria-hidden="true">
            <span className="tooltip-k">FY{active.x}</span>
            <span className="tooltip-v">{display_rows[active.i][yi]}</span>
            <span className="tooltip-x">{exactValue(active.y, unit, false)}</span>
          </div>
        )}
      </div>
    </figure>
  );
}
