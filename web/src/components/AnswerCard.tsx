"use client";

// One card per result (docs/v2-plan.md 5.5): answer, single value, empty, clarify, refuse, error.
// An answer leads with the number or the chart/table; assumptions and SQL are one click away, closed on every
// new card. Status colours always come with an icon and text.

import { useId, useRef, useState } from "react";
import type { Answer } from "@/lib/types";
import { exactValue, isYearColumn, seconds } from "@/lib/format";
import { partialYearNote } from "@/lib/partial";
import { BarChart, barsFit } from "./BarChart";
import { LineChart } from "./LineChart";
import { ExactSwitch, ResultTable, hasRoundedValues } from "./ResultTable";
import { SqlBlock } from "./SqlBlock";
import { IconAlert, IconBlock, IconCalendar, IconChevron, IconQuestion, IconSearchOff } from "./icons";

const UNRELIABLE = "I couldn't answer that reliably.";
const IDENT = /([A-Za-z0-9]+(?:_[A-Za-z0-9]+)+)/;  // snake_case tokens, e.g. borrowers_obligation_usd

// Fixed follow-ups on a clarify card, each checked on the live agent to return an answer (Nov 6, 2026).
export const FOLLOW_UPS = [
  "Which countries owe the most?",
  "How much was approved each fiscal year?",
  "How many loans are in each status?",
];

/** Display only: the text is unchanged, column names are set in monospace. */
function WithCode({ text }: { text: string }) {
  return <>{text.split(IDENT).map((part, i) => (i % 2 ? <code key={i} className="ident" translate="no">{part}</code> : part))}</>;
}

export function AnswerCard({ data, onAsk }: { data: Answer; onAsk: (question: string) => void }) {
  return (
    <article className="card result" aria-labelledby="result-heading">
      <Body data={data} onAsk={onAsk} />
    </article>
  );
}

function Meta({ data }: { data: Answer }) {
  const ms = data.source === "live" ? data.latency_ms : data.answered_ms;
  return (
    <p className="meta">
      <span className={`source ${data.source}`}>{data.source === "live" ? "Live" : "Cached"}</span>
      <span aria-hidden="true">·</span>
      <span>{seconds(ms)}</span>
      {data.attempts === 2 && <><span aria-hidden="true">·</span><span>retried once</span></>}
    </p>
  );
}

function Body({ data, onAsk }: { data: Answer; onAsk: (question: string) => void }) {
  switch (data.status) {
    case "clarify":
      return (
        <>
          <h2 id="result-heading" className="state-head clarify"><IconQuestion /> Which do you mean?</h2>
          <p className="state-body"><WithCode text={data.summary} /></p>
          <div className="follow">
            <h3 className="follow-head">Or ask</h3>
            <ul>
              {FOLLOW_UPS.map((q) => (
                <li key={q}><button type="button" className="chip" onClick={() => onAsk(q)}>{q}</button></li>
              ))}
            </ul>
          </div>
          <Meta data={data} />
        </>
      );
    case "refuse":
      return (
        <>
          <h2 id="result-heading" className="state-head neutral"><IconBlock /> Can&rsquo;t answer that from this data</h2>
          <p className="state-body"><WithCode text={data.summary} /></p>
          <p className="state-help">Nothing was run.</p>
          <Meta data={data} />
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
          <Details data={data} sqlTitle="SQL" />
        </>
      );
    default:
      return <AnswerBody data={data} />;
  }
}

function AnswerBody({ data }: { data: Answer }) {
  const single = data.rows.length === 1 && data.columns.length === 1;
  const partial = partialYearNote(data.assumptions, data.data_as_of);
  return (
    <>
      <h2 id="result-heading" className="answer-q">{data.question}</h2>
      {single ? (
        <p className="hero-n" title={exactValue(data.rows[0][0], data.columns[0].unit, isYearColumn(data.columns[0].name))}>
          {data.display_rows[0][0] || "—"}
        </p>
      ) : (
        <Views data={data} />
      )}
      <p className={single ? "summary summary-hero" : "summary"}>{data.summary}</p>
      {partial && (
        <div className="callout" role="note">
          <IconCalendar />
          <p><strong>Partial year.</strong> {partial}</p>
        </div>
      )}
      <Details data={data} sqlTitle="SQL" />
    </>
  );
}

function Views({ data }: { data: Answer }) {
  const chart = data.chart && (data.chart.kind === "line" || barsFit(data)) ? data.chart : null;
  const [tab, setTab] = useState<"chart" | "table">(chart ? "chart" : "table");
  const [exact, setExact] = useState(false);
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
      <div className="views-bar">
        <div className="seg" role="tablist" aria-label="View" onKeyDown={onKey}>
          {names.map((n, i) => (
            <button key={n} ref={(el) => { tabs.current[i] = el; }} type="button" role="tab" id={`tab-${n}`}
              aria-selected={tab === n} aria-controls={`panel-${n}`} tabIndex={tab === n ? 0 : -1} onClick={() => setTab(n)}>
              {n === "chart" ? "Chart" : "Table"}
            </button>
          ))}
        </div>
        {tab === "table" && hasRoundedValues(data) && <ExactSwitch on={exact} onChange={setExact} />}
      </div>
      {/* Both panels stay mounted, so the bars grow once and not on every tab switch. */}
      <div role="tabpanel" id="panel-chart" aria-labelledby="tab-chart" hidden={tab !== "chart"}>
        {chart.kind === "bar" ? <BarChart data={data} /> : <LineChart data={data} />}
      </div>
      <div role="tabpanel" id="panel-table" aria-labelledby="tab-table" hidden={tab !== "table"}>
        <ResultTable data={data} exact={exact} />
      </div>
    </div>
  );
}

/** "Assumptions (n)" and "SQL" toggles, both closed by default; the open state lives only in this card. */
function Details({ data, sqlTitle }: { data: Answer; sqlTitle: string }) {
  const id = useId();
  const [open, setOpen] = useState({ assumptions: false, sql: false });
  const n = data.assumptions.length;
  const toggle = (k: keyof typeof open) => setOpen((o) => ({ ...o, [k]: !o[k] }));
  return (
    <div className="details">
      <div className="details-bar">
        {n > 0 && (
          <button type="button" className="disclose" aria-expanded={open.assumptions} aria-controls={`${id}-a`}
            onClick={() => toggle("assumptions")}>
            Assumptions ({n}) <IconChevron size={14} />
          </button>
        )}
        {data.sql && (
          <button type="button" className="disclose" aria-expanded={open.sql} aria-controls={`${id}-s`}
            onClick={() => toggle("sql")}>
            {sqlTitle} <IconChevron size={14} />
          </button>
        )}
        <Meta data={data} />
      </div>
      {n > 0 && (
        <ul id={`${id}-a`} className="assumptions" hidden={!open.assumptions}>
          {data.assumptions.map((a) => <li key={a}><WithCode text={a} /></li>)}
        </ul>
      )}
      {data.sql && (
        <div id={`${id}-s`} hidden={!open.sql}>
          <SqlBlock sql={data.sql} />
        </div>
      )}
    </div>
  );
}
