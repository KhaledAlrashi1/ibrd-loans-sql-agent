// The /api/ask contract (docs/v2-plan.md, section 2). The frontend only renders it.

export type Unit = "usd" | "share" | "plain";
export type Value = string | number | boolean | null;

export type Column = { name: string; label: string; unit: Unit };
export type Chart = { kind: "bar" | "line"; x: string; y: string };

export type AgentStatus = "answer" | "empty" | "clarify" | "refuse" | "error";
export type NoticeStatus = "invalid" | "limited" | "unavailable";

export type Answer = {
  status: AgentStatus;
  question: string;
  summary: string;
  columns: Column[];
  rows: Value[][];
  display_rows: string[][];
  chart: Chart | null;
  assumptions: string[];
  sql: string;
  truncated: boolean;
  row_limit: number;
  latency_ms: number;
  answered_ms: number;
  attempts: number;
  source: "live" | "cache" | "example";
  data_as_of: string;
  retry_after_s: null;
};

export type Notice = {
  status: NoticeStatus;
  message: string;
  retry_after_s: number | null;
  scope?: "ip" | "daily";
};

export type AskResponse = Answer | Notice;

export type ExamplesFile = {
  computed_at: string;
  git_commit: string;
  model: string;
  cache_version: string;
  dataset: { name: string; id: string; source_url: string; end_of_period: string; rows: number };
  examples: Answer[];
};

export function isAnswer(r: AskResponse): r is Answer {
  return r.status === "answer" || r.status === "empty" || r.status === "clarify" || r.status === "refuse" || r.status === "error";
}

/** web/src/data/stats.json, written by scripts/build_stats.py. Loans only, raw US$. */
export type Stats = {
  end_of_period: string;
  loans: number;
  outstanding_usd: number;
  approved_usd: number;
  first_fy: number;
  countries: number;
  outstanding_by_region: { region: string; label: string; usd: number }[];
};
