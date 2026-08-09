import { expect, test } from "@playwright/test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { installApiRoutes } from "./apiRoutes";

const visualDir = resolve(dirname(fileURLToPath(import.meta.url)), "../../../.local/owner-console-visual/task-21");

test("primary pages and exact Ticket detail remain aligned at approved viewports", async ({ page }) => {
  await installApiRoutes(page, { authenticated: true });
  const routes = [
    ["overview", "/overview", "总览"],
    ["signals", "/signals", "信号"],
    ["trades", "/trades", "交易"],
    ["ticket", "/trades/ticket%3Aactive%3A1", "生命周期 · 8 阶段"],
    ["review", "/review", "复盘"],
  ] as const;

  for (const viewport of [{ width: 1280, height: 800 }, { width: 1440, height: 900 }, { width: 1920, height: 1080 }]) {
    await page.setViewportSize(viewport);
    for (const [name, route, identity] of routes) {
      await page.goto(route);
      await expect(page.getByText(identity, { exact: true }).first()).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
      expect(overflow).toBe(false);
      await page.screenshot({ path: resolve(visualDir, `${viewport.width}-${name}.png`), fullPage: false });
    }
  }
});

test("below 1024px tables scroll internally without page-wide overflow", async ({ page }) => {
  await installApiRoutes(page, { authenticated: true });
  await page.setViewportSize({ width: 900, height: 900 });
  await page.goto("/review");
  await expect(page.getByRole("table", { name: "完成 Ticket 复盘列表" })).toBeVisible();

  const metrics = await page.evaluate(() => {
    const table = document.querySelector("table");
    const container = table?.parentElement;
    return {
      pageOverflow: document.documentElement.scrollWidth > window.innerWidth,
      tableHasInternalOverflow: Boolean(container && container.scrollWidth > container.clientWidth),
    };
  });
  expect(metrics.pageOverflow).toBe(false);
  expect(metrics.tableHasInternalOverflow).toBe(true);
});
