// Smoke test of the main states against the production build, with /api mocked (no Python, no model calls).

import { expect, test, type Page, type Route } from "@playwright/test";
import examples from "../src/data/examples.json";

const [undisbursed, , fiscalYears] = examples.examples;

const live = (over: object) => ({ ...undisbursed, source: "live", latency_ms: 3120, answered_ms: 3120, ...over });
const noRows = { columns: [], rows: [], display_rows: [], chart: null };

/** Mock /api/ask with one response (optionally delayed) and count the calls. /api/health always answers ok. */
async function mockAsk(page: Page, body: object | null, opts: { status?: number; delayMs?: number } = {}) {
  const calls: string[] = [];
  await page.route("**/api/health", (r) => r.fulfill({ json: { ok: true } }));
  await page.route("**/api/ask", async (route: Route) => {
    calls.push(JSON.parse(route.request().postData() ?? "{}").question);
    if (opts.delayMs) await new Promise((r) => setTimeout(r, opts.delayMs));
    if (body === null) return route.abort("internetdisconnected");
    return route.fulfill({ status: opts.status ?? 200, json: body });
  });
  return calls;
}

async function askLive(page: Page, question: string) {
  await page.getByLabel("Your question about IBRD loans").fill(question);
  await page.getByRole("button", { name: "Ask", exact: true }).click();
}

async function noHorizontalScroll(page: Page) {
  const [scroll, client] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
  expect(scroll).toBeLessThanOrEqual(client);
}

test("idle page: title, examples, attribution, warm-up ping", async ({ page }) => {
  const health = page.waitForRequest("**/api/health");
  await mockAsk(page, {});
  await page.goto("/");
  await health;
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Ask the IBRD loan book");
  await expect(page.getByRole("button", { name: /Instant$/ })).toHaveCount(4);
  await expect(page.getByText("Independent project, not affiliated with the World Bank.")).toBeVisible();
  await expect(page.getByRole("link", { name: "CC BY 4.0" })).toHaveAttribute("href", /creativecommons\.org\/licenses\/by\/4\.0/);
  await expect(page.getByRole("link", { name: "Code on GitHub" })).toBeVisible();
  await expect(page.getByText(/World Bank logo/i)).toHaveCount(0);
});

test("examples render instantly with no request, chart and table", async ({ page }) => {
  const calls = await mockAsk(page, {});
  await page.goto("/");
  await page.getByRole("button", { name: /Which 10 countries have the most undisbursed/ }).click();
  const card = page.getByRole("article");
  await expect(card.getByText("Cached example")).toBeVisible();
  await expect(card.locator(".bars li").first()).toContainText("Turkiye");
  await expect(card.locator(".bars li").first()).toContainText("$14.85B");
  await expect(card.getByText("Undisbursed (USD), by country / economy")).toBeVisible();

  await card.getByRole("tab", { name: "Table" }).click();
  await expect(card.getByRole("columnheader", { name: "Undisbursed (USD)" })).toBeVisible();
  await expect(card.getByRole("row").nth(1)).toContainText("$14.85B");
  await card.getByRole("switch", { name: "Show exact values" }).click();
  await expect(card.getByRole("row").nth(1)).toContainText("$14,851,719,396.98");
  await card.getByRole("tab", { name: "Chart" }).click();
  await card.getByRole("tab", { name: "Chart" }).press("ArrowRight");
  await expect(card.getByRole("tab", { name: "Table" })).toHaveAttribute("aria-selected", "true");

  await expect(card.getByText("Assumptions")).toBeVisible();
  await card.getByText("SQL", { exact: true }).click();
  await expect(card.locator("pre.sql")).toContainText("SELECT");
  expect(calls).toEqual([]);
});

test("line chart example", async ({ page }) => {
  await mockAsk(page, {});
  await page.goto("/");
  await page.getByRole("button", { name: /each fiscal year from 2020 to 2025/ }).click();
  const svg = page.getByRole("img", { name: /by fiscal year, FY2020 to FY2025/ });
  await expect(svg).toBeVisible();
  await expect(svg.getByText("FY2020")).toBeVisible();
  await expect(page.getByRole("article").getByRole("tab", { name: "Chart" })).toHaveAttribute("aria-selected", "true");
  expect(fiscalYears.display_rows[0][1]).toBe("$26.86B");
});

test("live answer: progress steps and skeleton, then the answer with latency", async ({ page }) => {
  const calls = await mockAsk(page, live({ question: "Top undisbursed?" }), { delayMs: 1500 });
  await page.goto("/");
  await askLive(page, "Top undisbursed?");
  await expect(page.getByRole("button", { name: "Asking…" })).toBeDisabled();
  await expect(page.getByText("Understanding the question")).toBeVisible();
  await expect(page.locator(".step.active")).toHaveText("Writing SQL");
  await expect(page.locator(".skeleton")).toBeVisible();
  const card = page.getByRole("article");
  await expect(card.getByText("Live", { exact: true })).toBeVisible();
  await expect(card.getByText("Answered in 3.1\u00a0s")).toBeVisible();
  expect(calls).toEqual(["Top undisbursed?"]);
});

test("single value: hero number and partial-year caveat", async ({ page }) => {
  await mockAsk(page, live({
    question: "How many IBRD loans were approved in fiscal year 2027?", summary: "Number of IBRD loans approved in FY2027.",
    columns: [{ name: "loan_count", label: "Loan count", unit: "plain" }], rows: [[44]], display_rows: [["44"]], chart: null,
    assumptions: ["FY2027 is only partially covered: the snapshot ends 2026-09-30."],
  }));
  await page.goto("/");
  await askLive(page, "How many IBRD loans were approved in fiscal year 2027?");
  await expect(page.locator(".hero-n")).toHaveText("44");
  await expect(page.locator(".hero-what")).toHaveText("Loan count");
  await expect(page.getByRole("note")).toContainText("Partial year.");
});

test("clarify keeps the question and says nothing was run", async ({ page }) => {
  await mockAsk(page, live({ status: "clarify", summary: "Do you mean disbursing loans or loans with a balance?", sql: "", assumptions: [], ...noRows }));
  await page.goto("/");
  await askLive(page, "Which loans are active?");
  await expect(page.getByRole("heading", { name: "I need a bit more detail" })).toBeVisible();
  await expect(page.getByText("Nothing was run.")).toBeVisible();
  await expect(page.getByLabel("Your question about IBRD loans")).toHaveValue("Which loans are active?");
  await expect(page.locator("pre.sql")).toHaveCount(0);
});

test("refuse is neutral and shows no SQL", async ({ page }) => {
  await mockAsk(page, live({ status: "refuse", summary: "I can only read the loans table.", sql: "", assumptions: [], ...noRows }));
  await page.goto("/");
  await askLive(page, "Delete all rows from the loans table");
  const head = page.getByRole("heading", { name: "I can’t answer that from this data" });
  await expect(head).toBeVisible();
  await expect(head).toHaveClass(/neutral/);
  await expect(page.getByText("SQL", { exact: true })).toHaveCount(0);
});

test("error shows the reason and the SQL attempted", async ({ page }) => {
  await mockAsk(page, live({ status: "error", attempts: 2, summary: "I couldn't answer that reliably. The query failed: Binder Error.", sql: "SELECT nope", ...noRows }));
  await page.goto("/");
  await askLive(page, "Something odd");
  await expect(page.getByRole("heading", { name: "I couldn’t answer that reliably" })).toBeVisible();
  await expect(page.getByText("The query failed: Binder Error.")).toBeVisible();
  await expect(page.getByText("SQL attempted")).toBeVisible();
});

test("empty result", async ({ page }) => {
  await mockAsk(page, live({ status: "empty", summary: "No matching rows", ...noRows, columns: [{ name: "x", label: "X", unit: "plain" }] }));
  await page.goto("/");
  await askLive(page, "Loans to Atlantis?");
  await expect(page.getByRole("heading", { name: "No matching rows" })).toBeVisible();
  await expect(page.getByText("Assumptions")).toBeVisible();
});

test("rate limited: countdown, no answer", async ({ page }) => {
  await mockAsk(page, { status: "limited", scope: "ip", message: "You've asked a lot of questions in a short time.", retry_after_s: 40 }, { status: 429 });
  await page.goto("/");
  await askLive(page, "one more");
  await expect(page.getByRole("heading", { name: "You've asked a lot of questions in a short time." })).toBeVisible();
  await expect(page.getByText(/Try again in (40|39)\u00a0s/)).toBeVisible();
  await expect(page.getByText(/Try again in 3[0-8]\u00a0s/)).toBeVisible({ timeout: 4000 });
});

test("unavailable and offline offer a retry", async ({ page }) => {
  await mockAsk(page, { status: "unavailable", message: "Demo limit reached, please try again later.", retry_after_s: null }, { status: 503 });
  await page.goto("/");
  await askLive(page, "anything");
  await expect(page.getByRole("heading", { name: "Demo is temporarily unavailable" })).toBeVisible();
  await expect(page.getByText("Demo limit reached, please try again later.")).toBeVisible();

  await page.unrouteAll();
  const calls = await mockAsk(page, null);
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("heading", { name: "Couldn’t reach the server" })).toBeVisible();
  expect(calls).toEqual(["anything"]);
});

test("empty and over-long input show an inline message and send nothing", async ({ page }) => {
  const calls = await mockAsk(page, live({}));
  await page.goto("/");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.locator("#q-problem")).toHaveText("Please type a question about IBRD loans.");
  await askLive(page, "x".repeat(301));
  await expect(page.locator("#q-problem")).toHaveText("Please keep your question under 300 characters.");
  await expect(page.getByText("301 / 300")).toBeVisible();
  expect(calls).toEqual([]);
});

test("dark mode is applied and remembered", async ({ page }) => {
  await mockAsk(page, {});
  await page.goto("/");
  await page.getByRole("radio", { name: "Dark theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(bg).toBe("rgb(18, 18, 17)");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("radio", { name: "Match system theme" }).click();
  await expect(page.locator("html")).not.toHaveAttribute("data-theme", /.+/);
});

test("mobile 390 px: no horizontal page scroll with a wide table", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const wide = live({
    columns: ["project_name", "country", "loan_status", "original_principal_amount_usd", "borrowers_obligation_usd"].map(
      (n) => ({ name: n, label: n.replace(/_/g, " "), unit: n.endsWith("usd") ? "usd" : "plain" })),
    rows: [["A very long project name for a test", "Turkiye", "Disbursing", 1e9, 5e8]],
    display_rows: [["A very long project name for a test", "Turkiye", "Disbursing", "$1.00B", "$500.0M"]], chart: null,
  });
  await mockAsk(page, wide);
  await page.goto("/");
  await noHorizontalScroll(page);
  await askLive(page, "wide table");
  await expect(page.getByRole("table")).toBeVisible();
  await noHorizontalScroll(page);
  await page.getByRole("button", { name: /Which 10 countries/ }).click();
  await noHorizontalScroll(page);
});
