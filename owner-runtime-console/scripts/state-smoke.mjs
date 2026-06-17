import { spawn } from "node:child_process";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const basePort = Number(process.env.PORT ?? "5177");
const artifactDir = path.resolve("artifacts", "state-smoke");
const scenarios = [
  { name: "normal", expected: ["当前阶段", "等待市场机会", "L1 只读低交互", "链路演练", "实盘边界", "8 项正常"] },
  { name: "processing", expected: ["当前阶段", "系统处理中", "L1 只读低交互", "处理中", "SOR 正在处理订单"] },
  { name: "paused", expected: ["当前阶段", "等待市场机会", "L1 只读低交互", "已暂停", "Owner 已暂停"] },
  { name: "safety", expected: ["当前阶段", "安全边界阻断", "真实订单路径保持关闭", "有持仓或订单处理中，真实订单保持关闭"] },
  { name: "intervention", expected: ["当前阶段", "需要介入", "L1 只读低交互", "事实不可用，暂不能使用"] },
  { name: "stale", expected: ["当前阶段", "工程状态暂不可用", "链路演练", "系统处理", "数据不可用，暂不能使用"] },
  { name: "empty", expected: ["当前阶段", "工程状态暂不可用", "L1 只读低交互", "状态暂不可用", "MPG"] },
  { name: "error", expected: ["运行状态不可用", "资金路径保持关闭"] },
];

const forbidden = [
  "Final" + "Gate",
  "Operation" + " Layer",
  "Required" + "Facts",
  "candi" + "date",
  "author" + "ization",
  "pre" + "flight",
  "pr" + "oof",
  "ro" + "ute",
  "ref" + "Id",
  "blocker" + " code",
  "read" + "model",
  "需处理",
  "next" + " step",
  "下" + "一步",
  "检查" + "器",
  "系统自动" + "观察中",
  "暂无可用" + "机会",
  "fresh" + " signal",
  "技术" + "证据",
  "Owner 需要" + "判断",
];

async function waitForServer(url, timeoutMs = 20_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { method: "GET" });
      if (response.ok) return;
    } catch {
      // keep polling
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(`Dev server did not become ready at ${url}`);
}

function startServer(scenario, port) {
  return spawn("node", ["scripts/serve-console.mjs", "--port", String(port)], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      VITE_OWNER_USE_MOCK: "true",
      VITE_OWNER_MOCK_SCENARIO: scenario,
    },
    stdio: "inherit",
  });
}

async function runScenario(browser, scenario, index) {
  const port = basePort + index;
  const baseUrl = `http://127.0.0.1:${port}`;
  const server = startServer(scenario.name, port);
  try {
    await waitForServer(baseUrl);
    const page = await browser.newPage({ viewport: { width: 1440, height: 1024 } });
    const errors = [];
    page.on("console", (message) => {
      if (["error", "warning"].includes(message.type())) {
        errors.push(`${message.type()}: ${message.text()}`);
      }
    });

    await page.goto(`${baseUrl}/?scenario=${scenario.name}`, { waitUntil: "networkidle" });

    for (const text of scenario.expected) {
      await page.getByText(text, { exact: false }).first().waitFor({ state: "visible", timeout: 5_000 });
    }

    for (const text of forbidden) {
      const count = await page.getByText(text, { exact: false }).count();
      if (count > 0) {
        throw new Error(`${scenario.name} shows forbidden text: ${text}`);
      }
    }

    await page.screenshot({ path: path.join(artifactDir, `${scenario.name}-desktop.png`), fullPage: true });
    await page.getByLabel("切换深浅模式").click();
    await page.screenshot({ path: path.join(artifactDir, `${scenario.name}-light.png`), fullPage: true });
    await page.setViewportSize({ width: 390, height: 920 });
    await page.goto(`${baseUrl}/?scenario=${scenario.name}`, { waitUntil: "networkidle" });

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    if (overflow) {
      throw new Error(`${scenario.name} mobile viewport has horizontal overflow`);
    }

    await page.screenshot({ path: path.join(artifactDir, `${scenario.name}-mobile.png`), fullPage: true });
    await page.close();

    if (errors.length > 0) {
      throw new Error(`${scenario.name} console issues:\n${errors.join("\n")}`);
    }
  } finally {
    server.kill("SIGTERM");
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
}

await mkdir(artifactDir, { recursive: true });
const browser = await chromium.launch();
try {
  for (const [index, scenario] of scenarios.entries()) {
    await runScenario(browser, scenario, index);
  }
} finally {
  await browser.close();
}

console.log(`State smoke passed: ${scenarios.length} scenarios from port ${basePort}`);
console.log(`Screenshots: ${artifactDir}`);
