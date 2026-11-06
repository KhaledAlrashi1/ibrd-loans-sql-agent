// The "Partial year" callout rule (src/lib/partial.ts) on saved agent answers only: no model calls.

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "@playwright/test";
import examples from "../src/data/examples.json";
import { partialFiscalYear, partialYearNote } from "../src/lib/partial";

const AS_OF = examples.dataset.end_of_period;  // 2026-09-30: FY2027 is partial
type Run = { results: { id: string; status: string; question: string; message: string; assumptions: string[] | null }[] };
const run = (file: string): Run => JSON.parse(readFileSync(join(__dirname, "../../eval/results", file), "utf8"));
const saved = (file: string, id: string) => run(file).results.find((r) => r.id === id)!;

const D15_KI1 = saved("20261106-140841_dev.json", "D15");   // also has "FY2027 has no guarantees anyway"
const D15_LATEST = saved("20261106-143430_dev.json", "D15");
const EXAMPLE_3 = examples.examples[2];                       // "FY2027 is not in the range, so no partial-year figures …"

test("partial fiscal year comes from the snapshot date", () => {
  expect(partialFiscalYear(AS_OF)).toBe(2027);
  expect(partialFiscalYear("2026-06-30")).toBeNull();  // a snapshot on Jun 30 ends a full year
  expect(partialFiscalYear("2027-01-15")).toBe(2027);
});

test("D15 (FY2027 count) shows the callout with its partial-year line, in both saved runs", () => {
  expect(D15_KI1.assumptions!.some((a) => /has no guarantees/.test(a))).toBe(true);
  for (const d of [D15_KI1, D15_LATEST]) {
    const note = partialYearNote(d.assumptions!, AS_OF);
    expect(note).toMatch(/^FY2027 is partial in this snapshot/);
  }
});

test("example 3 (FY2020-FY2025) shows no callout", () => {
  expect(EXAMPLE_3.assumptions.some((a) => /partial/i.test(a))).toBe(true);
  expect(partialYearNote(EXAMPLE_3.assumptions, EXAMPLE_3.data_as_of)).toBeNull();
});

test("every other saved line that mentions a partial year", () => {
  const line = (file: string, id: string) => saved(file, id).assumptions!.find((a) => /partial/i.test(a))!;
  // Includes FY2027: callout.
  for (const [file, id] of [["20261103-191552_dev.json", "D17"], ["20261106-140841_dev.json", "D01"], ["20261106-143430_dev.json", "D17"]]) {
    expect(partialYearNote([line(file, id)], AS_OF), `${file} ${id}`).not.toBeNull();
  }
  // Says FY2027 is left out: no callout.
  for (const [file, id] of [["20261101-171538_dev.json", "D07"], ["20261106-143430_dev.json", "D07"]]) {
    expect(partialYearNote([line(file, id)], AS_OF), `${file} ${id}`).toBeNull();
  }
  // "partial" about something other than the partial year: no callout.
  expect(partialYearNote(["Includes partially repaid loans."], AS_OF)).toBeNull();
});

test("on the page: the saved D15 answer shows the callout, example 3 does not", async ({ page }) => {
  const [base] = examples.examples;
  const d15 = {
    ...base, status: "answer", question: D15_LATEST.question, summary: D15_LATEST.message, assumptions: D15_LATEST.assumptions,
    columns: [{ name: "loan_count", label: "Loan count", unit: "plain" }], rows: [[44]], display_rows: [["44"]], chart: null,
    source: "live",
  };
  await page.route("**/api/health", (r) => r.fulfill({ json: { ok: true } }));
  await page.route("**/api/ask", (r) => r.fulfill({ json: d15 }));
  await page.goto("/");
  await page.getByLabel("Your question about IBRD loans").fill(D15_LATEST.question);
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByRole("note")).toHaveText(`Partial year. ${partialYearNote(D15_LATEST.assumptions!, AS_OF)}`);

  await page.getByRole("button", { name: /each fiscal year from 2020 to 2025/ }).click();
  await expect(page.getByRole("article").getByRole("heading", { level: 2 })).toHaveText(EXAMPLE_3.question);
  await expect(page.getByRole("note")).toHaveCount(0);
});
