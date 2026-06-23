import { expect, test } from "@playwright/test";

test("login deep link clears stale tokens and signs into the demo cockpit", async ({ page }) => {
  await page.goto("/app/login");
  await page.evaluate(() => {
    localStorage.setItem("autoreach_access_token", "stale-token");
    localStorage.setItem("autoreach_refresh_token", "stale-refresh");
  });

  await page.goto("/app/login");

  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await expect(page.getByText("Session expired")).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => localStorage.getItem("autoreach_access_token"))).toBeNull();

  await page.getByRole("button", { name: "Use demo account" }).click();
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/\/app\/?$/);
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByText("SaaS Founders Q3")).toBeVisible();
  await expect(page.getByText("Agency Outreach")).toBeVisible();
  await expect.poll(() => page.evaluate(() => Boolean(localStorage.getItem("autoreach_access_token")))).toBe(true);
});

test("protected dashboard redirects anonymous visitors to landing", async ({ page }) => {
  await page.goto("/app/");

  await expect(page).toHaveURL(/\/app\/landing$/);
  await expect(page.getByText("deliverability-first outbound")).toBeVisible();
});
