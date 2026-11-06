// "What's in this data": static text, no model call. Every line restates src/agent/data_dictionary.yaml
// (columns, rules guarantees_excluded / fiscal_year / usd_basis / currency_of_commitment_empty) or the
// refusal scope in src/agent/prompt.py. Change it only together with those.

import { longDate } from "@/lib/format";
import type { ExamplesFile } from "@/lib/types";

export function DataPanel({ dataset }: { dataset: ExamplesFile["dataset"] }) {
  const asOf = longDate(dataset.end_of_period);
  return (
    <section aria-labelledby="data-heading" className="data-panel">
      <h2 id="data-heading" className="section-head">What&rsquo;s in this data</h2>
      <dl>
        <div>
          <dt>One row</dt>
          <dd>One IBRD loan or guarantee, by loan number. {dataset.rows.toLocaleString("en-US")}&nbsp;rows, a snapshot as of {asOf}.</dd>
        </div>
        <div>
          <dt>Main fields</dt>
          <dd>
            Country and region, loan type and status, project, board approval date and fiscal year, and amounts in US$:
            approved, cancelled, undisbursed, disbursed, repaid and still owed.
          </dd>
        </div>
        <div>
          <dt>Answers well</dt>
          <dd>Totals, counts and rankings by country, region, fiscal year, loan status or loan type.</dd>
        </div>
        <div>
          <dt>Can&rsquo;t answer</dt>
          <dd>
            Sectors, project results, GDP or other economic indicators, lending by IDA or anyone other than the IBRD,
            the currency of each loan (empty in this snapshot), anything after {asOf}, or forecasts.
          </dd>
        </div>
        <div>
          <dt>Defaults</dt>
          <dd>
            Loan questions leave out guarantees. &ldquo;Year&rdquo; means the World Bank fiscal year (July to June).
            The exchange-rate basis differs by amount column: undisbursed amounts are at end-of-period rates,
            disbursed and repaid amounts at historical rates.
          </dd>
        </div>
      </dl>
    </section>
  );
}
