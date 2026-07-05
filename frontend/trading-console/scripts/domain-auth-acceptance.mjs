import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "../../..");
const outputDir = process.env.TRADING_CONSOLE_SCREENSHOT_DIR
  ? path.resolve(process.env.TRADING_CONSOLE_SCREENSHOT_DIR)
  : path.join(repoRoot, "output/playwright/trading-console");

const baseUrl = normalizeBaseUrl(process.env.TRADING_CONSOLE_BASE_URL || "https://jiaoyingpan.cloud/trading-console/");
const credentials = {
  username: process.env.TRADING_CONSOLE_OPERATOR_USERNAME || "",
  password: process.env.TRADING_CONSOLE_OPERATOR_PASSWORD || "",
  totpCode: process.env.TRADING_CONSOLE_OPERATOR_TOTP_CODE || "",
};

const required = [
  ["TRADING_CONSOLE_OPERATOR_USERNAME", credentials.username],
  ["TRADING_CONSOLE_OPERATOR_PASSWORD", credentials.password],
  ["TRADING_CONSOLE_OPERATOR_TOTP_CODE", credentials.totpCode],
];

const missing = required.filter(([, value]) => !value).map(([name]) => name);
if (missing.length) {
  console.error(`Missing required environment variables: ${missing.join(", ")}`);
  console.error("No credential, password, TOTP secret, or TOTP code is stored by this script.");
  process.exit(2);
}

if (!/^\d{6,8}$/.test(credentials.totpCode)) {
  console.error("TRADING_CONSOLE_OPERATOR_TOTP_CODE must be a 6-8 digit current authenticator code.");
  process.exit(2);
}

await fs.mkdir(outputDir, { recursive: true });

const { chromium } = await import("playwright");
const browser = await chromium.launch({ headless: process.env.PW_HEADED !== "1" });
const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });

try {
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  await page.screenshot({ path: shot("13-domain-auth-login-before.png"), fullPage: true });

  await page.getByRole("textbox", { name: "用户名" }).fill(credentials.username);
  await page.getByRole("textbox", { name: "密码" }).fill(credentials.password);
  await page.getByRole("textbox", { name: "认证器验证码" }).fill(credentials.totpCode);
  await page.getByRole("button", { name: "安全登录" }).click();

  const failureText = page.getByText("登录失败：用户名、密码或认证器验证码无效。");
  const loginOutcome = await Promise.race([
    failureText.waitFor({ state: "visible", timeout: 15000 }).then(() => "failure"),
    page.getByText("仪表盘", { exact: false }).first().waitFor({ state: "visible", timeout: 15000 }).then(() => "success"),
  ]);

  if (loginOutcome === "failure") {
    await page.screenshot({ path: shot("14-domain-auth-login-failed.png"), fullPage: true });
    throw new Error("Authenticated acceptance failed: login failure text is visible.");
  }

  await page.waitForLoadState("networkidle");
  await expectVisibleText(page, "仪表盘");
  await page.screenshot({ path: shot("14-domain-auth-dashboard.png"), fullPage: true });

  const routes = [
    ["账户风险", "15-domain-auth-account-risk.png"],
    ["订单台账", "16-domain-auth-order-ledger.png"],
    ["策略组", "17-domain-auth-strategy-groups.png"],
    ["异常信息", "18-domain-auth-exceptions.png"],
  ];

  for (const [label, filename] of routes) {
    await page.getByRole("button", { name: label }).click();
    await expectVisibleText(page, label);
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: shot(filename), fullPage: true });
  }

  await page.getByRole("button", { name: "切换主题" }).click();
  await page.screenshot({ path: shot("19-domain-auth-theme-toggle.png"), fullPage: true });

  const sessionResponse = await page.request.get(new URL("/api/auth/session", baseUrl).toString());
  if (sessionResponse.status() !== 200) {
    throw new Error(`Expected authenticated /api/auth/session to return 200, got ${sessionResponse.status()}.`);
  }

  console.log(`Authenticated domain acceptance passed. Screenshots: ${outputDir}`);
} finally {
  await browser.close();
}

function shot(filename) {
  return path.join(outputDir, filename);
}

function normalizeBaseUrl(value) {
  return value.endsWith("/") ? value : `${value}/`;
}

async function expectVisibleText(page, text) {
  await page.getByText(text, { exact: false }).first().waitFor({ state: "visible", timeout: 15000 });
}
