import { expect, test } from "@playwright/test";
import { installApiRoutes } from "./apiRoutes";

test("time, focus, reconnect, and visibility issue no automatic request", async ({ page }) => {
  const counts = await installApiRoutes(page, { authenticated: true });
  await page.goto("/overview");
  await expect(page.getByRole("heading", { name: "总览" })).toBeVisible();
  expect(counts.overview).toBe(1);

  await page.waitForTimeout(500);
  await page.evaluate(() => {
    window.dispatchEvent(new Event("focus"));
    window.dispatchEvent(new Event("online"));
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await page.waitForTimeout(500);
  expect(counts.overview).toBe(1);
});

test("failed manual refresh keeps Last Known Good visible", async ({ page }) => {
  const counts = await installApiRoutes(page, { authenticated: true, failOverviewAfter: 1 });
  await page.goto("/overview");
  await expect(page.getByText("系统运行正常，无需 Owner 操作")).toBeVisible();
  await page.getByRole("button", { name: "刷新当前页" }).click();
  await expect(page.getByText(/刷新失败/)).toBeVisible();
  await expect(page.getByText("系统运行正常，无需 Owner 操作")).toBeVisible();
  expect(counts.overview).toBe(2);
});
