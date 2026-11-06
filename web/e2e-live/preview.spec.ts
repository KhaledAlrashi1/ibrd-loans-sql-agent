// Against a real deployment (no mocks): one live question, then the same question again from the cache.
// Run only through playwright.preview.config.ts. Costs 1 live model call per run on a fresh preview.

import { expect, test } from "@playwright/test";

const QUESTION = "How many IBRD loans has Chile had?";

test.describe.configure({ mode: "serial" });

test("health answers", async ({ request }) => {
  const res = await request.get("/api/health");
  expect(res.ok()).toBe(true);
});

test("page: 4 cached examples and the data panel", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: /Cached · instant$/ })).toHaveCount(4);
  await expect(page.getByRole("region", { name: "What’s in this data" }).getByRole("term")).toHaveCount(5);
  await page.getByRole("button", { name: /Middle East and North Africa/ }).click();
  await expect(page.getByRole("article").getByText("Cached example")).toBeVisible();
});

test("live question, then the same question from the cache", async ({ page }) => {
  await page.goto("/");
  for (const source of [/^(Live|Cached answer)$/, /^Cached answer$/]) {
    await page.getByLabel("Your question about IBRD loans").fill(QUESTION);
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    const card = page.locator("article.result");
    await expect(card).toBeVisible({ timeout: 60_000 });
    await expect(card.locator(".pill")).toHaveText(source);
    await expect(card.getByRole("heading", { name: "Assumptions" })).toBeVisible();
    await expect(card.getByText("SQL", { exact: true })).toBeVisible();
    await page.reload();
  }
});
