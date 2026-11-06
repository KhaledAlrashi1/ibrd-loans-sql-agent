// Display helpers. Table and label text comes formatted from the API (display_rows); these cover what only
// the browser needs: exact values, axis ticks, durations and dates.

import type { Unit, Value } from "./types";

export const MAX_QUESTION_CHARS = 300;
// Same text as src/ui/service.py, so the inline message matches the API's.
export const EMPTY_QUESTION = "Please type a question about IBRD loans.";
export const TOO_LONG = `Please keep your question under ${MAX_QUESTION_CHARS} characters.`;

export function validateQuestion(text: string): string | null {
  const t = text.trim();
  if (!t) return EMPTY_QUESTION;
  if (t.length > MAX_QUESTION_CHARS) return TOO_LONG;
  return null;
}

const usdExact = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const plainExact = new Intl.NumberFormat("en-US", { maximumFractionDigits: 20 });

/** The full, unrounded value: $14,851,719,396.98 for US$, 12.3456% for shares. */
export function exactValue(v: Value, unit: Unit, isYear: boolean): string {
  if (v === null) return "";
  if (typeof v !== "number") return String(v);
  if (unit === "usd") return usdExact.format(v);
  if (unit === "share") return `${plainExact.format(v * 100)}%`;
  return isYear ? String(v) : plainExact.format(v);
}

const YEAR_NAME = /(^|_)(fy|cy|year|fiscal_year|calendar_year)$/i;
export const isYearColumn = (name: string) => YEAR_NAME.test(name);

const usdCompact = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 });

/** Headline figures: $296.7B. */
export const compactUsd = (v: number) => usdCompact.format(v);

/** Compact axis ticks: $10B, $250M, 40%, 1.2K. */
export function tick(v: number, unit: Unit): string {
  if (unit === "share") return `${Math.round(v * 100)}%`;
  const a = Math.abs(v);
  const [d, s] = a >= 1e9 ? [1e9, "B"] : a >= 1e6 ? [1e6, "M"] : a >= 1e3 ? [1e3, "K"] : [1, ""];
  const sign = v < 0 ? "-" : "";
  const n = Number((a / d).toFixed(1)).toString();
  return `${sign}${unit === "usd" ? "$" : ""}${n}${s}`;
}

/** Up to 5 round tick values from min(0, lo) to just past hi. */
export function niceTicks(lo: number, hi: number): number[] {
  const min = Math.min(0, lo), max = Math.max(0, hi);
  const span = max - min || 1;
  const raw = span / 4;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const ticks: number[] = [];
  for (let t = Math.floor(min / step) * step; t < max + step - 1e-9; t += step) ticks.push(Number(t.toPrecision(12)));
  return ticks;
}

export function seconds(ms: number): string {
  return ms < 1000 ? `${(ms / 1000).toFixed(2)}\u00a0s` : `${(ms / 1000).toFixed(1)}\u00a0s`;  // no break before the unit
}

export function longDate(iso: string): string {
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00Z` : iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

export function waitText(s: number): string {
  if (s < 90) return `${s}\u00a0s`;
  const min = Math.ceil(s / 60);
  return min < 90 ? `${min}\u00a0min` : `${Math.ceil(min / 60)}\u00a0h`;
}
