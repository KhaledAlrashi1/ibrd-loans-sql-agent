// Which assumption, if any, gets the "Partial year" callout on an answer card. The callout repeats the model's own
// assumption text; this only decides whether the text says the answer includes the partial fiscal year.
// Cases (all saved agent answers) are in web/e2e/partial.spec.ts.

/** The fiscal year (Jul-Jun) that contains the snapshot date, or null when the snapshot ends on Jun 30. */
export function partialFiscalYear(dataAsOf: string): number | null {
  const [y, m, d] = dataAsOf.slice(0, 10).split("-").map(Number);
  if (m === 6 && d === 30) return null;
  return m >= 7 ? y + 1 : y;
}

const PARTIAL = /\bpartial(ly)?\b/i;
// Says the partial year is left out: "not in the range", "outside the requested range", "not included",
// "no partial-year figures", "does not apply".
const LEFT_OUT = /\b(not\s+(in|included|within|part\s+of|covered)|outside|excluded|excludes|excluding|no\s+partial|does\s*n[o']t\s+apply)\b/i;

/**
 * The assumption that says the answer covers the partial fiscal year: it names that year (e.g. 2027), says
 * "partial", and no clause about the year or "partial" says the year is left out. Clauses are split at
 * , ; : and sentence ends, so "Guarantees excluded; FY2027 is partial" still counts.
 */
export function partialYearNote(assumptions: string[], dataAsOf: string): string | null {
  const fy = partialFiscalYear(dataAsOf);
  if (fy === null) return null;
  const year = new RegExp(`(?<!\\d)${fy}(?!\\d)`);  // "FY2027", "fiscal year 2027"; not "20271"
  return assumptions.find((a) => {
    if (!PARTIAL.test(a) || !year.test(a)) return false;
    const clauses = a.split(/[,;:]|\.\s/);
    return !clauses.some((c) => (PARTIAL.test(c) || year.test(c)) && LEFT_OUT.test(c));
  }) ?? null;
}
