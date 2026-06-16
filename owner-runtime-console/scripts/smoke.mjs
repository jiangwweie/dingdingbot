import { spawn } from "node:child_process";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const port = process.env.PORT ?? "5186";
const externalUrl = process.env.SMOKE_URL;
const baseUrl = externalUrl ?? `http://127.0.0.1:${port}`;
const artifactDir = path.resolve("artifacts", "smoke");
const scenario = process.env.VITE_OWNER_MOCK_SCENARIO ?? "normal";

async function isReachable(url) {
  try {
    const response = await fetch(url, { method: "GET" });
    return response.ok;
  } catch {
    return false;
  }
}

async function waitForServer(url, timeoutMs = 20_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await isReachable(url)) return;
    await new Promise((resolve) => setTimeout(resolve, 350));
  }
  throw new Error(`Dev server did not become ready at ${url}`);
}

function startServer() {
  return spawn("node", ["scripts/serve-console.mjs", "--port", port], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      VITE_OWNER_USE_MOCK: process.env.VITE_OWNER_USE_MOCK ?? "true",
      VITE_OWNER_MOCK_SCENARIO: scenario,
    },
    stdio: "inherit",
  });
}

async function expectVisible(page, text) {
  const locator = page.getByText(text, { exact: false }).first();
  await locator.waitFor({ state: "visible", timeout: 5_000 });
}

async function expectAbsent(page, text) {
  const count = await page.getByText(text, { exact: false }).count();
  if (count > 0) {
    throw new Error(`Forbidden text visible: ${text}`);
  }
}

async function openNav(page, label, expectedText) {
  await page.getByRole("button", { name: label, exact: true }).click();
  await expectVisible(page, expectedText);
}

let server = null;

try {
  const alreadyRunning = externalUrl ? await isReachable(baseUrl) : false;
  if (!alreadyRunning) {
    server = startServer();
    await waitForServer(baseUrl);
  }

  await mkdir(artifactDir, { recursive: true });

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1024 } });
  await page.goto(`${baseUrl}/?scenario=${encodeURIComponent(scenario)}`, { waitUntil: "networkidle" });

  await expectVisible(page, "BRC Owner Console");
  await expectVisible(page, "系统安全运行");
  await expectVisible(page, "策略组状态");
  await expectVisible(page, "当前策略组");
  await expectVisible(page, "安全资金池");
  await expectVisible(page, "重要变化");
  await expectVisible(page, "等待机会");
  await expectVisible(page, "无需操作");

  await openNav(page, "策略组", "策略族已接入");
  await expectVisible(page, "运行设置");
  await expectVisible(page, "风险档");
  await expectVisible(page, "观察模式");
  await openNav(page, "资金", "账户只读");
  await openNav(page, "订单与持仓", "级联视图");
  await expectVisible(page, "成交单");
  await expectVisible(page, "保护单");
  await openNav(page, "记录", "最近记录");
  await openNav(page, "系统", "只读保证");
  await openNav(page, "首页", "系统安全运行");

  const forbidden = [
    "Final" + "Gate",
    "Operation" + " Layer",
    "Required" + "Facts",
    "candi" + "date",
    "author" + "ization",
    "pre" + "flight",
    "pr" + "oof",
    "ref" + "Id",
    "next" + " step",
    "下" + "一步",
    "检查" + "器",
    "系统自动" + "观察中",
    "暂无可用" + "机会",
    "read" + "model",
  ];

  for (const text of forbidden) {
    await expectAbsent(page, text);
  }

  await page.screenshot({ path: path.join(artifactDir, "desktop-dark.png"), fullPage: true });

  await page.getByLabel("切换深浅模式").click();
  await expectVisible(page, "系统安全运行");
  await page.screenshot({ path: path.join(artifactDir, "desktop-light.png"), fullPage: true });

  await page.setViewportSize({ width: 390, height: 920 });
  await page.goto(`${baseUrl}/?scenario=${encodeURIComponent(scenario)}`, { waitUntil: "networkidle" });
  await expectVisible(page, "系统安全运行");
  await page.screenshot({ path: path.join(artifactDir, "mobile.png"), fullPage: true });

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  if (overflow) {
    throw new Error("Mobile viewport has horizontal overflow");
  }

  await browser.close();
  console.log(`Smoke passed: ${baseUrl} (${scenario})`);
  console.log(`Screenshots: ${artifactDir}`);
} finally {
  if (server) {
    server.kill("SIGTERM");
  }
}
