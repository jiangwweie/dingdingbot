import { expect, test } from "@playwright/test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { installApiRoutes } from "./apiRoutes";

const visualDir = process.env.OWNER_CONSOLE_VISUAL_DIR
  ? resolve(process.env.OWNER_CONSOLE_VISUAL_DIR)
  : resolve(
      dirname(fileURLToPath(import.meta.url)),
      "../../../.local/owner-console-visual/strategy-workbench",
    );

test("StrategyVersion paths open a Ticket dialog and browser back restores it", async ({ page }) => {
  const counts = await installApiRoutes(page, { authenticated: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/strategies?view=current");

  await expect(page.getByRole("heading", { name: "策略" })).toBeVisible();
  await expect(page.getByText("BRF2 · v3")).toBeVisible();
  await page.screenshot({ path: resolve(visualDir, "strategies-1440x900.png"), fullPage: false });

  await page.getByRole("button", { name: "TP1 1" }).click();
  await expect(page.getByRole("dialog", { name: /BRF2 v3 · 已达 TP1/ })).toBeVisible();
  await expect(page).toHaveURL(/ticket_modal=1/);
  await page.screenshot({ path: resolve(visualDir, "strategy-ticket-dialog-1440x900.png"), fullPage: false });

  await page.getByRole("link", { name: /BTCUSDT SHORT/ }).click();
  await expect(page).toHaveURL(/\/trades\/ticket%3Astrategy%3Abrf2%3Atp1\?origin=strategy/);
  await page.goBack();
  await expect(page.getByRole("dialog", { name: /BRF2 v3 · 已达 TP1/ })).toBeVisible();
  expect(counts.strategies).toBe(1);
  expect(counts.strategyTickets).toBe(1);
});
