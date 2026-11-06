// Smoke test of the main states against the production build, with /api mocked (no Python, no model calls).

import { expect, test, type Page, type Route } from "@playwright/test";
import examples from "../src/data/examples.json";
import stats from "../src/data/stats.json";
import trust from "../src/data/trust.json";

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

test("idle page: title, stats, examples, data panel, attribution, warm-up ping", async ({ page }) => {
  const health = page.waitForRequest("**/api/health");
  await mockAsk(page, {});
  await page.goto("/");
  await health;
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Ask the IBRD loan book");
  await expect(page.getByRole("heading", { name: "Try an example · instant" })).toBeVisible();
  await expect(page.locator(".examples button")).toHaveCount(4);
  await expect(page.getByText(/Cached · instant|Press Enter|0 \/ 300/)).toHaveCount(0);  // no per-row tags, no UI-describing hints
  const panel = page.getByRole("region", { name: "What the data covers" });
  await expect(panel.getByRole("heading")).toHaveText(["Ask about", "Not in this data"]);
  await expect(panel.getByRole("list").first().getByRole("listitem"))
    .toHaveText(["Countries", "Regions", "Fiscal years", "Loan status", "Loan type", "Approved, disbursed, owed"]);
  await expect(panel.getByRole("list").last().getByRole("listitem"))
    .toHaveText(["Sectors", "Project results", "GDP", "IDA lending", "After Sep 30, 2026"]);
  await expect(page.getByText("Defaults")).toHaveCount(0);
  await expect(page.getByText(/Snapshot Sep 30, 2026/)).toHaveCount(1);
  await expect(page.getByText("Not affiliated with the World Bank.", { exact: false })).toBeVisible();
  await expect(page.getByRole("link", { name: "CC BY 4.0" })).toHaveAttribute("href", /creativecommons\.org\/licenses\/by\/4\.0/);
  await expect(page.getByRole("link", { name: "Code on GitHub" })).toBeVisible();
  await expect(page.getByText(/World Bank logo/i)).toHaveCount(0);
});

test("stat strip shows the numbers in stats.json (checked against pandas in tests/test_stats.py)", async ({ page }) => {
  await mockAsk(page, {});
  await page.goto("/");
  const strip = page.getByRole("region", { name: "The loan book" });
  const usd = (v: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 }).format(v);
  await expect(strip.getByRole("term")).toHaveText(["Outstanding", `Approved since FY${stats.first_fy}`, "Countries", "Loans"]);
  await expect(strip.getByRole("definition")).toHaveText([usd(stats.outstanding_usd), usd(stats.approved_usd), "143", "9,425"]);
  expect(usd(stats.outstanding_usd)).toBe("$296.7B");
  expect(usd(stats.approved_usd)).toBe("$984.7B");
  await expect(strip).toContainText("Snapshot Sep 30, 2026");

  const figure = page.getByRole("figure", { name: "Outstanding by region" });
  await expect(figure.locator("figcaption")).toHaveText("Outstanding by region As of Sep 30, 2026");
  const bars = figure.getByRole("listitem");
  await expect(bars).toHaveCount(stats.outstanding_by_region.length);
  await expect(bars.locator(".name")).toHaveText(stats.outstanding_by_region.map((r) => r.label));
  await expect(bars.locator(".val")).toHaveText(stats.outstanding_by_region.map((r) => usd(r.usd)));
});

test("page order: headline, subtitle, stats, ask box, examples, region chart, trust, data panel (390 and 1200 px)", async ({ page }) => {
  await mockAsk(page, {});
  for (const width of [390, 1200]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    const tops = await page.evaluate(() =>
      ["h1", ".lede", ".stats", "form.ask", ".examples-block", ".region-chart", ".trust", ".data-panel"]
        .map((sel) => document.querySelector(sel)!.getBoundingClientRect().top));
    for (let i = 1; i < tops.length; i++) expect(tops[i]).toBeGreaterThan(tops[i - 1]);
  }
});

test("trust section: three statements, every number from trust.json (checked against the repo by tests/test_trust.py)", async ({ page }) => {
  await mockAsk(page, {});
  await page.goto("/");
  const section = page.getByRole("region", { name: "Why you can trust the answers" });
  await expect(section.getByRole("term")).toHaveText(["Test results", "Guardrails", "Ambiguity"]);
  await expect(section.getByRole("definition")).toHaveText([
    "Dev set 20/20 correct; held-out set 9/10 as first scored. RESULTS.md",
    "Read-only database; SQL checked before it runs; 1,000 rows, 10\u00a0s max. security.md",
    "Asks instead of guessing when a question is ambiguous. Eval case D18",
  ]);
  const allowed = new Set([trust.dev.correct, trust.dev.questions, trust.heldout.correct_first_scored, trust.heldout.questions,
    trust.row_limit, trust.timeout_s, Number(trust.clarify_case.id.replace(/\D/g, ""))]);
  const numbers = ((await section.innerText()).match(/\d[\d,]*/g) ?? []).map((n) => Number(n.replace(/,/g, "")));
  expect(numbers.length).toBe(7);
  for (const n of numbers) expect(allowed.has(n)).toBe(true);

  const repo = "https://github.com/KhaledAlrashi1/ibrd-loans-sql-agent/blob/main/";
  await expect(section.getByRole("link")).toHaveText(["RESULTS.md", "security.md", "Eval case D18"]);
  const hrefs = await section.getByRole("link").evaluateAll((as) => as.map((a) => a.getAttribute("href")));
  const c = trust.clarify_case;
  expect(hrefs).toEqual([repo + trust.results_doc, repo + trust.security_doc, `${repo}${c.file}#L${c.first_line}-L${c.last_line}`]);

  // One line each at 1200 px.
  await page.setViewportSize({ width: 1200, height: 900 });
  for (const dd of await section.getByRole("definition").all()) {
    const lines = await dd.evaluate((el) => Math.round(el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight)));
    expect(lines).toBe(1);
  }
});

test("examples: a tag and an arrow on each row; the arrow moves on hover", async ({ page }) => {
  await mockAsk(page, {});
  await page.setViewportSize({ width: 1200, height: 900 });
  await page.goto("/");
  const rows = page.locator(".examples button");
  await expect(rows.locator(".ex-q")).toHaveText(examples.examples.map((e) => e.question));
  await expect(rows.locator(".ex-tag")).toHaveText(["Ranking", "Region filter", "Trend chart", "Asks before guessing"]);
  await expect(rows.locator("svg")).toHaveCount(4);
  const arrow = rows.first().locator("svg");
  await rows.first().hover();
  await expect(arrow).toHaveCSS("transform", "matrix(1, 0, 0, 1, 2, 0)");
  // Desktop: the tag sits on the question's line; 390 px: below it.
  const sameLine = async () => rows.first().evaluate((b) => {
    const q = b.querySelector(".ex-q")!.getBoundingClientRect(), t = b.querySelector(".ex-tag")!.getBoundingClientRect();
    return t.top < q.bottom && t.left > q.right;
  });
  expect(await sameLine()).toBe(true);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await sameLine()).toBe(false);
});

test("data panel: every tag stays on one line (390 and 1200 px)", async ({ page }) => {
  await mockAsk(page, {});
  await page.goto("/");
  for (const width of [390, 1200]) {
    await page.setViewportSize({ width, height: 900 });
    const heights = await page.locator(".data-panel .tags li").evaluateAll((lis) =>
      lis.map((li) => li.getBoundingClientRect().height / parseFloat(getComputedStyle(li).lineHeight)));
    for (const h of heights) expect(Math.round(h)).toBe(1);
  }
});

test("link preview: Open Graph and Twitter tags, a 1200x630 image, icons", async ({ page, request }) => {
  await mockAsk(page, {});
  await page.goto("/");
  const meta = (sel: string) => page.locator(sel).first().getAttribute("content");
  expect(await meta('meta[property="og:title"]')).toBe("Ask the IBRD loan book");
  expect(await meta('meta[name="twitter:card"]')).toBe("summary_large_image");
  expect(await meta('meta[property="og:description"]')).toBe(await meta('meta[name="description"]'));
  expect(await meta('meta[property="og:image:width"]')).toBe("1200");
  expect(await meta('meta[property="og:image:height"]')).toBe("630");
  for (const sel of ['meta[property="og:image"]', 'meta[name="twitter:image"]']) {
    const path = new URL((await meta(sel))!).pathname;
    const res = await request.get(path);
    expect(res.status()).toBe(200);
    expect(res.headers()["content-type"]).toBe("image/png");
    const png = await res.body();
    expect([png.readUInt32BE(16), png.readUInt32BE(20)]).toEqual([1200, 630]);  // IHDR width, height
  }
  for (const rel of ["icon", "apple-touch-icon"]) {
    for (const href of await page.locator(`link[rel="${rel}"]`).evaluateAll((ls) => ls.map((l) => l.getAttribute("href")!))) {
      expect((await request.get(href)).status()).toBe(200);
    }
  }
});

test("tabular figures in the stat strip, the chart values and answer tables", async ({ page }) => {
  await mockAsk(page, {});
  await page.goto("/");
  const numeric = (sel: string) => page.locator(sel).first().evaluate((el) => getComputedStyle(el).fontVariantNumeric);
  expect(await numeric(".stats dd")).toBe("tabular-nums");
  expect(await numeric(".region-chart .val")).toBe("tabular-nums");
  await page.getByRole("button", { name: /Which 10 countries have the most undisbursed/ }).click();
  await page.getByRole("article").getByRole("tab", { name: "Table" }).click();
  expect(await numeric("article td")).toBe("tabular-nums");
  expect(await numeric("article td.num")).toBe("tabular-nums");
});

test("cold server: visible waking state, examples still instant, live question waits with a waking step", async ({ page }) => {
  let wake!: () => void;
  const awake = new Promise<void>((r) => { wake = r; });
  await page.route("**/api/health", async (r) => { await awake; await r.fulfill({ json: { ok: true } }); });
  const calls: string[] = [];
  await page.route("**/api/ask", async (r) => {
    calls.push(JSON.parse(r.request().postData() ?? "{}").question);
    await awake;
    await r.fulfill({ json: live({ question: "Top undisbursed?" }) });
  });
  await page.goto("/");
  const status = page.getByRole("status").filter({ hasText: "Starting the server, about 15 s" });
  await expect(status).toBeVisible();

  await page.getByRole("button", { name: /Which 10 countries have the most undisbursed/ }).click();
  await expect(page.getByRole("article").locator(".source")).toHaveText("Cached");
  expect(calls).toEqual([]);

  await askLive(page, "Top undisbursed?");
  await expect(page.locator(".step.active")).toHaveText(/^Starting the server, about 15\s+s$/);
  await expect(page.locator(".step.todo")).toHaveCount(4);
  wake();
  await expect(status).toHaveCount(0);
  await expect(page.getByRole("article").locator(".source")).toHaveText("Live");
  expect(calls).toEqual(["Top undisbursed?"]);
});

test("warm server: no waking state", async ({ page }) => {
  await mockAsk(page, {});
  await page.goto("/");
  await page.waitForTimeout(1200);
  await expect(page.getByText("Starting the server")).toHaveCount(0);
});

test("examples render instantly with no request: question, chart first, then collapsed assumptions and SQL", async ({ page }) => {
  const calls = await mockAsk(page, {});
  await page.goto("/");
  await page.getByRole("button", { name: /Which 10 countries have the most undisbursed/ }).click();
  const card = page.getByRole("article");
  await expect(card.locator(".source")).toHaveText("Cached");
  await expect(card.getByRole("heading", { level: 2 })).toHaveText(undisbursed.question);
  // The chart comes before the summary sentence.
  const chartFirst = await card.evaluate((el) =>
    !!(el.querySelector(".views")!.compareDocumentPosition(el.querySelector(".summary")!) & Node.DOCUMENT_POSITION_FOLLOWING));
  expect(chartFirst).toBe(true);
  await expect(card.locator(".bars li").first()).toContainText("Turkiye");
  await expect(card.locator(".bars li").first()).toContainText("$14.85B");
  await expect(card.getByText("Undisbursed (USD), by country / economy")).toBeVisible();

  await card.getByRole("tab", { name: "Table" }).click();
  await expect(card.getByRole("columnheader", { name: "Undisbursed (USD)" })).toBeVisible();
  await expect(card.getByRole("row").nth(1)).toContainText("$14.85B");
  await card.getByRole("switch", { name: "Exact values" }).click();
  await expect(card.getByRole("row").nth(1)).toContainText("$14,851,719,396.98");
  await card.getByRole("tab", { name: "Chart" }).click();
  await card.getByRole("tab", { name: "Chart" }).press("ArrowRight");
  await expect(card.getByRole("tab", { name: "Table" })).toHaveAttribute("aria-selected", "true");

  const assumptions = card.getByRole("button", { name: `Assumptions (${undisbursed.assumptions.length})` });
  const sql = card.getByRole("button", { name: "SQL", exact: true });
  await expect(assumptions).toHaveAttribute("aria-expanded", "false");
  await expect(sql).toHaveAttribute("aria-expanded", "false");
  await expect(card.locator(".assumptions")).toBeHidden();
  await expect(card.locator("pre.sql")).toBeHidden();
  await assumptions.click();
  await expect(card.locator(".assumptions li")).toHaveCount(undisbursed.assumptions.length);
  await sql.click();
  await expect(card.locator("pre.sql")).toContainText("SELECT");
  await expect(sql).toHaveAttribute("aria-expanded", "true");
  await sql.click();
  await expect(card.locator("pre.sql")).toBeHidden();
  expect(calls).toEqual([]);
});

test("assumptions and SQL start closed on every new answer", async ({ page }) => {
  await mockAsk(page, {});
  await page.goto("/");
  await page.getByRole("button", { name: /Which 10 countries have the most undisbursed/ }).click();
  await page.getByRole("article").getByRole("button", { name: "SQL", exact: true }).click();
  await expect(page.locator("pre.sql")).toBeVisible();
  await page.getByRole("button", { name: /Middle East and North Africa/ }).click();
  await expect(page.getByRole("article").getByRole("button", { name: "SQL", exact: true })).toHaveAttribute("aria-expanded", "false");
  await expect(page.locator("pre.sql")).toBeHidden();
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
  // Its assumption says FY2027 is *not* in the range: no "Partial year" callout.
  expect(fiscalYears.assumptions.some((a) => /partial/i.test(a))).toBe(true);
  await expect(page.getByRole("note")).toHaveCount(0);
});

test("clarifying example: instant, no request, model text unchanged, fixed follow-ups", async ({ page }) => {
  const calls = await mockAsk(page, {});
  await page.goto("/");
  await page.getByRole("button", { name: /Which loans are active\?/ }).click();
  await expect(page.getByRole("button", { name: /Which loans are active\?/ })).toHaveAttribute("aria-current", "true");
  await expect(page.locator(".examples [aria-current]")).toHaveCount(1);
  const card = page.getByRole("article");
  await expect(card.locator(".source")).toHaveText("Cached");
  await expect(card.getByRole("heading", { name: "Which do you mean?" })).toBeVisible();
  await expect(card.getByText(/Nothing was run|Add that detail/)).toHaveCount(0);
  await expect(card.locator("pre.sql")).toHaveCount(0);
  await expect(card.locator(".follow button")).toHaveText([
    "Which countries owe the most?", "How much was approved each fiscal year?", "How many loans are in each status?"]);
  expect(calls).toEqual([]);

  // Body text size, not the serif hero; column names in monospace; the text itself unchanged.
  const msg = card.locator(".state-body");
  await expect(msg).toHaveText(examples.examples[3].summary);
  await expect(msg).toHaveCSS("font-size", "16px");
  const idents = examples.examples[3].summary.match(/[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+/g) ?? [];
  expect(idents.length).toBeGreaterThan(0);
  await expect(msg.locator("code")).toHaveText(idents);
  const font = await msg.locator("code").first().evaluate((el) => getComputedStyle(el).fontFamily);
  expect(font).toMatch(/monospace/);
});

test("line chart x labels never overlap at 390 px", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockAsk(page, {});
  await page.goto("/");
  await page.getByRole("button", { name: /each fiscal year from 2020 to 2025/ }).click();
  const labels = page.locator(".line-wrap text.tick", { hasText: /^FY/ });
  await expect(labels.last()).toHaveText("FY2025");
  const boxes = await labels.evaluateAll((els) => els.map((e) => e.getBoundingClientRect()).map((r) => [r.left, r.right]));
  for (let i = 1; i < boxes.length; i++) expect(boxes[i][0]).toBeGreaterThan(boxes[i - 1][1]);
});

test("live answer: progress steps and skeleton, then the answer with latency", async ({ page }) => {
  const calls = await mockAsk(page, live({ question: "Top undisbursed?" }), { delayMs: 1500 });
  await page.goto("/");
  await askLive(page, "Top undisbursed?");
  await expect(page.getByRole("button", { name: "Asking…" })).toBeDisabled();
  await expect(page.getByText("Reading the question")).toBeVisible();
  await expect(page.locator(".step.active")).toHaveText("Writing SQL");
  await expect(page.locator(".skeleton")).toBeVisible();
  const card = page.getByRole("article");
  await expect(card.locator(".source")).toHaveText("Live");
  await expect(card.locator(".meta")).toHaveText(/^Live\s*·\s*3\.1\u00a0s$/);
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
  await expect(page.locator(".summary")).toHaveText("Number of IBRD loans approved in FY2027.");
  await expect(page.getByRole("note")).toContainText("Partial year.");
});

test("clarify keeps the question; a follow-up fills in the box and asks it", async ({ page }) => {
  const calls = await mockAsk(page, live({ status: "clarify", summary: "Do you mean disbursing loans or loans with a balance?", sql: "", assumptions: [], ...noRows }));
  await page.goto("/");
  await askLive(page, "Which loans are active?");
  await expect(page.getByRole("heading", { name: "Which do you mean?" })).toBeVisible();
  await expect(page.locator(".state-body")).toHaveText("Do you mean disbursing loans or loans with a balance?");
  await expect(page.getByLabel("Your question about IBRD loans")).toHaveValue("Which loans are active?");
  await expect(page.locator("pre.sql")).toHaveCount(0);

  await page.unrouteAll();
  const next = await mockAsk(page, live({ question: "Which countries owe the most?" }));
  await page.getByRole("button", { name: "Which countries owe the most?" }).click();
  await expect(page.getByLabel("Your question about IBRD loans")).toHaveValue("Which countries owe the most?");
  await expect(page.getByRole("article").getByRole("heading", { level: 2 })).toHaveText("Which countries owe the most?");
  expect(calls).toEqual(["Which loans are active?"]);
  expect(next).toEqual(["Which countries owe the most?"]);
});

test("refuse is neutral and shows no SQL", async ({ page }) => {
  await mockAsk(page, live({ status: "refuse", summary: "I can only read the loans table.", sql: "", assumptions: [], ...noRows }));
  await page.goto("/");
  await askLive(page, "Delete all rows from the loans table");
  const head = page.getByRole("heading", { name: "Can’t answer that from this data" });
  await expect(head).toBeVisible();
  await expect(head).toHaveClass(/neutral/);
  await expect(page.locator(".state-body")).toHaveCSS("font-size", "16px");
  await expect(page.getByText("Nothing was run.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /SQL|Assumptions/ })).toHaveCount(0);
});

test("error shows the reason and the SQL attempted", async ({ page }) => {
  await mockAsk(page, live({ status: "error", attempts: 2, summary: "I couldn't answer that reliably. The query failed: Binder Error.", sql: "SELECT nope", ...noRows }));
  await page.goto("/");
  await askLive(page, "Something odd");
  await expect(page.getByRole("heading", { name: "I couldn’t answer that reliably" })).toBeVisible();
  await expect(page.getByText("The query failed: Binder Error.")).toBeVisible();
  await page.getByRole("button", { name: "SQL attempted" }).click();
  await expect(page.locator("pre.sql")).toHaveText("SELECT nope");
  await expect(page.locator(".meta")).toContainText("retried once");
});

test("empty result", async ({ page }) => {
  await mockAsk(page, live({ status: "empty", summary: "No matching rows", ...noRows, columns: [{ name: "x", label: "X", unit: "plain" }] }));
  await page.goto("/");
  await askLive(page, "Loans to Atlantis?");
  await expect(page.getByRole("heading", { name: "No matching rows" })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Assumptions \(\d+\)/ })).toBeVisible();
});

const PER_IP = "Live questions from your network are limited to 20 per hour.";

test("rate limited: countdown, no answer", async ({ page }) => {
  await mockAsk(page, { status: "limited", scope: "ip", message: PER_IP, retry_after_s: 40 }, { status: 429 });
  await page.goto("/");
  await askLive(page, "one more");
  await expect(page.getByRole("heading", { name: PER_IP })).toBeVisible();
  await expect(page.getByText(/Try again in (40|39)\u00a0s/)).toBeVisible();
  await expect(page.getByText(/Try again in 3[0-8]\u00a0s/)).toBeVisible({ timeout: 4000 });
});

test("rate limited per network: wait in minutes, examples still work", async ({ page }) => {
  await mockAsk(page, { status: "limited", scope: "ip", message: PER_IP, retry_after_s: 1500 }, { status: 429 });
  await page.goto("/");
  await askLive(page, "one more");
  await expect(page.getByRole("heading", { name: PER_IP })).toBeVisible();
  await expect(page.locator(".state-help")).toHaveText("Try again in 25\u00a0min. Examples and repeat questions still work.");
});

test("daily limit: says the demo is at its limit, not the visitor", async ({ page }) => {
  const heading = "This demo has reached today's limit of 150 live questions.";
  await mockAsk(page, { status: "limited", scope: "daily", message: heading, retry_after_s: 30000 }, { status: 429 });
  await page.goto("/");
  await askLive(page, "one more");
  await expect(page.getByRole("heading", { name: heading })).toBeVisible();
  await expect(page.locator(".state-help")).toHaveText("Live questions resume at midnight UTC. Examples and repeat questions still work.");
  await expect(page.getByText(/your network|you've asked/i)).toHaveCount(0);
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
  await page.getByLabel("Your question about IBRD loans").fill("short");
  await expect(page.locator(".count")).toHaveCount(0);
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
