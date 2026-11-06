"use client";

// One card per result (docs/v2-plan.md 5.5): answer, single value, empty, clarify, refuse, error.
// Every card that ran SQL shows its assumptions and the SQL; status colours always come with an icon and text.

import { useRef, useState } from "react";
import type { Answer } from "@/lib/types";
import { exactValue, isYearColumn, longDate, seconds } from "@/lib/format";
import { BarChart, barsFit } from "./BarChart";
import { LineChart } from "./LineChart";
import { ResultTable } from "./ResultTable";
import { SqlBlock } from "./SqlBlock";
import { IconAlert, IconBlock, IconCalendar, IconQuestion, IconSearchOff } from "./icons";

const UNRELIABLE = "I couldn't answer that reliably.";
const PARTIAL = /\bpartial(ly)?\b/i;
const IDENT = /([A-Za-z0-9]+(?:_[A-Za-z0-9]+)+)/;  // snake_case tokens, e.g. borrowers_obligation_usd

/** Display only: the text is unchanged, column names are set in monospace. */
function WithCode({ text }: { text: string }) {
  return <>{text.split(IDENT).map((part, i) => (i % 2 ? <code key={i}>{part}</code> : part))}</>;
}

export function AnswerCard({ data, computedAt }: { data: Answer; computedAt: string }) {
  return (
    <article className="card result" aria-labelledby="result-heading">
      <Meta data={data} computedAt={computedAt} />
      <p className="q">{data.question}</p>
      <Body data={data} />
    </article>
  );
}

function Meta({ data, computedAt }: { data: Answer; computedAt: string }) {
  const pill = { live: "Live", cache: "Cached answer", example: "Cached example" }[data.source];
  const timing = data.source === "live" ? `Answered in ${seconds(data.latency_ms)}`
    : data.source === "cache" ? `${seconds(data.latency_ms)} · first answered in ${seconds(data.answered_ms)}`
    : `Computed by the live agent on ${longDate(computedAt)} in ${seconds(data.answered_ms)}`;
  return (
    <div className="meta">
      <span className={`pill ${data.source}`}>{pill}</span>
      <span>{timing}</span>
    </div>
  );
}

function Body({ data }: { data: Answer }) {
  switch (data.status) {
    case "clarify":
      return (
        <>
          <h2 id="result-heading" className="state-head clarify"><IconQuestion /> I need a bit more detail</h2>
          <p className="clarify-msg"><WithCode text={data.summary} /></p>
          <p className="state-help">Add that detail to your question above and ask again. Nothing was run.</p>
        </>
      );
    case "refuse":
      return (
        <>
          <h2 id="result-heading" className="state-head neutral"><IconBlock /> I can&rsquo;t answer that from this data</h2>
          <p className="state-msg">{data.summary}</p>
        </>
      );
    case "error":
      return (
        <>
          <h2 id="result-heading" className="state-head critical"><IconAlert /> I couldn’t answer that reliably</h2>
          <p className="state-help">{data.summary.replace(UNRELIABLE, "").trim() || data.summary}</p>
          <Details data={data} sqlTitle="SQL attempted" />
        </>
      );
    case "empty":
      return (
        <>
          <h2 id="result-heading" className="state-head neutral"><IconSearchOff /> No matching rows</h2>
          <p className="state-help">The query ran and returned nothing. Here is what was searched.</p>
          <Details data={data} sqlTitle="SQL" />
        </>
      );
    default:
      return <AnswerBody data={data} />;
  }
}

function AnswerBody({ data }: { data: Answer }) {
  const single = data.rows.length === 1 && data.columns.length === 1;
  const partial = data.assumptions.find((a) => PARTIAL.test(a));
  return (
    <>
      {single ? (
        <div className="hero">
          <p className="hero-n" title={exactValue(data.rows[0][0], data.columns[0].unit, isYearColumn(data.columns[0].name))}>
            {data.display_rows[0][0] || "—"}
          </p>
          <p className="hero-what">{data.columns[0].label}</p>
        </div>
      ) : null}
      <h2 id="result-heading" className={single ? "summary summary-sm" : "summary"}>{data.summary}</h2>
      {partial && (
        <div className="callout" role="note">
          <IconCalendar />
          <p><strong>Partial year.</strong> {partial}</p>
        </div>
      )}
      {single ? null : <Views data={data} />}
      <Details data={data} sqlTitle="SQL" />
    </>
  );
}

function Views({ data }: { data: Answer }) {
  const chart = data.chart && (data.chart.kind === "line" || barsFit(data)) ? data.chart : null;
  const [tab, setTab] = useState<"chart" | "table">(chart ? "chart" : "table");
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  if (!chart) return <ResultTable data={data} />;

  const names = ["chart", "table"] as const;
  function onKey(e: React.KeyboardEvent) {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    const next = tab === "chart" ? 1 : 0;
    setTab(names[next]);
    tabs.current[next]?.focus();
  }

  return (
    <div className="views">
      <div className="seg" role="tablist" aria-label="View" onKeyDown={onKey}>
        {names.map((n, i) => (
          <button key={n} ref={(el) => { tabs.current[i] = el; }} type="button" role="tab" id={`tab-${n}`}
            aria-selected={tab === n} aria-controls={`panel-${n}`} tabIndex={tab === n ? 0 : -1} onClick={() => setTab(n)}>
            {n === "chart" ? "Chart" : "Table"}
          </button>
        ))}
      </div>
      {/* Both panels stay mounted, so the bars grow once and not on every tab switch. */}
      <div role="tabpanel" id="panel-chart" aria-labelledby="tab-chart" hidden={tab !== "chart"}>
        {chart.kind === "bar" ? <BarChart data={data} /> : <LineChart data={data} />}
      </div>
      <div role="tabpanel" id="panel-table" aria-labelledby="tab-table" hidden={tab !== "table"}>
        <ResultTable data={data} />
      </div>
    </div>
  );
}

function Details({ data, sqlTitle }: { data: Answer; sqlTitle: string }) {
  const n = data.rows.length;
  return (
    <>
      {data.assumptions.length > 0 && (
        <section className="section" aria-labelledby="assumptions-heading">
          <h3 id="assumptions-heading" className="section-head">Assumptions</h3>
          <ul className="assumptions">{data.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
        </section>
      )}
      {data.sql && (
        <section className="section">
          <SqlBlock sql={data.sql} title={sqlTitle} />
        </section>
      )}
      <p className="foot-meta">
        <span>{data.attempts === 1 ? "1 attempt" : `${data.attempts} attempts`}</span>
        {data.status !== "error" && <span>{n === 1 ? "1 row" : `${n.toLocaleString("en-US")} rows`}</span>}
        {data.attempts === 2 && data.status !== "error" && <span>Retried once after the first attempt failed.</span>}
        <span>Data as of {longDate(data.data_as_of)}</span>
      </p>
    </>
  );
}
