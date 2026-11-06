// Static, no model call. "Ask about" names columns in src/agent/data_dictionary.yaml (country, region,
// board_approval_fy, loan_status, loan_type, original_principal / disbursed / borrowers_obligation);
// "Not in this data" restates the refusal scope in src/agent/prompt.py. Change it only together with those.

import { longDate } from "@/lib/format";

const ASK_ABOUT = ["Countries", "Regions", "Fiscal years", "Loan status", "Loan type", "Approved, disbursed, owed"];
const NOT_HERE = ["Sectors", "Project results", "GDP", "IDA lending"];

export function DataPanel({ endOfPeriod }: { endOfPeriod: string }) {
  const rows = [
    { label: "Ask about", tags: ASK_ABOUT },
    { label: "Not in this data", tags: [...NOT_HERE, `After ${longDate(endOfPeriod)}`] },
  ];
  return (
    <section aria-label="What the data covers" className="data-panel">
      {rows.map((r) => (
        <div key={r.label} className="tag-row">
          <h2>{r.label}</h2>
          <ul className="tags">{r.tags.map((t) => <li key={t}>{t}</li>)}</ul>
        </div>
      ))}
    </section>
  );
}
