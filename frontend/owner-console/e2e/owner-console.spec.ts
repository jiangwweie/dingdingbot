import { expect, test } from "@playwright/test";
import { installApiRoutes } from "./apiRoutes";

test("login, navigate, inspect causality, and logout", async ({ page }) => {
  const counts = await installApiRoutes(page);
  await page.goto("/login");

  await page.getByLabel("用户名").fill("owner");
  await page.getByLabel("密码").fill("wrong password");
  await page.getByLabel("动态验证码").fill("123456");
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page.getByRole("alert")).toHaveText("登录失败");

  await page.getByLabel("密码").fill("correct horse");
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByRole("heading", { name: "总览" })).toBeVisible();

  await page.getByRole("link", { name: "信号" }).click();
  await expect(page.getByRole("heading", { name: "信号" })).toBeVisible();
  await page.getByRole("button", { name: /展开 SOR-LONG/ }).first().click();
  await expect(page.getByText("gross_stop_risk_capacity_exhausted").first()).toBeVisible();

  await page.getByRole("link", { name: "交易" }).click();
  await expect(page.getByRole("heading", { name: "交易" })).toBeVisible();
  await page.getByLabel("StrategyGroup").fill("SOR-LONG");
  await page.getByRole("link", { name: "BNBUSDT LONG" }).click();
  await expect(page).toHaveURL(/\/trades\/ticket%3Aactive%3A1/);
  await expect(page.getByTestId("lifecycle-stage")).toHaveCount(8);
  expect(counts.candles).toBe(0);
  await page.getByRole("button", { name: "展开 K 线" }).click();
  await expect(page.getByTestId("causality-chart")).toBeVisible();
  expect(counts.candles).toBe(1);
  await page.getByRole("button", { name: "刷新当前页" }).click();
  await expect.poll(() => counts.candles).toBe(2);
  await page.getByRole("link", { name: "交易", exact: true }).last().click();
  await expect(page).toHaveURL(/\/trades\?strategy_group_id=SOR-LONG/);

  await page.getByRole("link", { name: "复盘" }).click();
  await expect(page.getByRole("heading", { name: "复盘" })).toBeVisible();
  await expect(page.getByText("Observe Only")).toBeVisible();
  await expect(page.getByText("样本不足 · 当前仅支持观察性结论")).toHaveCount(0);

  await page.getByRole("button", { name: "退出" }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect(counts.login).toBe(2);
  expect(counts.logout).toBe(1);
});

test("expired session redirects protected routes to login", async ({ page }) => {
  await installApiRoutes(page, { authenticated: true, expireSession: true });
  await page.goto("/overview");
  await expect(page).toHaveURL(/\/login$/);
});
