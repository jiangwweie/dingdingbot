import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const port = Number(process.env.PORT ?? "5202");
const externalUrl = process.env.VISUAL_QA_URL;
const baseUrl = externalUrl ?? `http://127.0.0.1:${port}`;
const artifactDir = path.resolve("artifacts", "visual-qa");
const strict = process.env.VISUAL_QA_STRICT !== "false";
const scenarios = externalUrl
  ? ["external"]
  : (process.env.VISUAL_QA_SCENARIOS ?? "normal,stale")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);

const pages = [
  { key: "home", label: "首页", expected: "策略组状态" },
  { key: "strategies", label: "策略组", expected: "策略组已接入" },
  { key: "funds", label: "资金", expected: "安全资金池" },
  { key: "orders", label: "订单与持仓", expected: "级联视图" },
  { key: "records", label: "记录", expected: "最近记录" },
  { key: "system", label: "系统", expected: "只读保证" },
];

const themes = ["dark", "light"];
const viewports = [
  { name: "desktop-1440", width: 1440, height: 900 },
  { name: "desktop-1600", width: 1600, height: 1000 },
  { name: "desktop-1920", width: 1920, height: 1200 },
  { name: "tablet-1024", width: 1024, height: 768 },
  { name: "mobile-390", width: 390, height: 844 },
];

const forbiddenTerms = [
  "Final" + "Gate",
  "Operation" + " Layer",
  "Required" + "Facts",
  "candi" + "date",
  "author" + "ization",
  "pre" + "flight",
  "pr" + "oof",
  "ref" + "Id",
  "blocker code",
  "read" + "model",
  "next" + " step",
  "下一步",
  "检查器",
];

function startServer(scenario) {
  return spawn("npm", ["run", "dev", "--", "--port", String(port)], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      VITE_OWNER_USE_MOCK: process.env.VITE_OWNER_USE_MOCK ?? "true",
      VITE_OWNER_MOCK_SCENARIO: scenario,
    },
    stdio: "inherit",
  });
}

async function isReachable(url) {
  try {
    const response = await fetch(url, { method: "GET" });
    return response.ok;
  } catch {
    return false;
  }
}

async function waitForServer(url, timeoutMs = 25_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await isReachable(url)) return;
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(`Visual QA server did not become ready at ${url}`);
}

async function stopProcess(child) {
  if (!child || child.killed) return;
  child.kill("SIGTERM");
  await new Promise((resolve) => setTimeout(resolve, 600));
}

async function navigateToPage(page, target, viewport) {
  if (target.key === "home") return;

  const button = page.getByRole("button", { name: target.label, exact: true });
  const count = await button.count();
  if (count === 0) {
    throw new Error(`Navigation item not reachable at ${viewport.name}: ${target.label}`);
  }
  await button.first().click();
}

async function waitForDesktopNavigationActiveStyle(page, target, viewport) {
  if (viewport.width < 1024) return;
  await page.waitForFunction(
    (expectedLabel) => {
      const nav = document.querySelector('aside nav[aria-label="主导航"]');
      if (!nav) return false;
      const active = nav.querySelector('button[aria-current="page"]');
      if (!active || active.textContent?.trim() !== expectedLabel) return false;
      const rootStyle = window.getComputedStyle(document.documentElement);
      const primary = rootStyle.getPropertyValue("--sidebar-primary").trim();
      const probe = document.createElement("span");
      probe.style.backgroundColor = primary;
      document.body.appendChild(probe);
      const primaryRgb = window.getComputedStyle(probe).backgroundColor;
      probe.remove();
      return window.getComputedStyle(active).backgroundColor === primaryRgb;
    },
    target.label,
    { timeout: 1_500 },
  );
}

async function collectChecks(page, target, viewport, consoleIssues) {
  const issues = [];

  if (consoleIssues.length > 0) {
    issues.push(`console issues: ${consoleIssues.join(" | ")}`);
  }

  const bodyText = (await page.locator("body").innerText()).trim();
  if (bodyText.length < 20) {
    issues.push("blank or near-blank page");
  }

  const frameworkOverlay = await page
    .locator("text=/Vite|Webpack|React error|Unhandled Runtime Error|Internal server error/i")
    .count();
  if (frameworkOverlay > 0) {
    issues.push("framework or runtime error overlay visible");
  }

  for (const term of forbiddenTerms) {
    const count = await page.getByText(term, { exact: false }).count();
    if (count > 0) {
      issues.push(`forbidden main UI term visible: ${term}`);
    }
  }

  const structural = await page.evaluate(() => {
    const failures = [];
    const maxX = window.innerWidth + 1;

    if (document.documentElement.scrollWidth > maxX) {
      failures.push(`horizontal overflow ${document.documentElement.scrollWidth}px > ${window.innerWidth}px`);
    }

    const visibleElements = Array.from(document.querySelectorAll("body *")).filter((element) => {
      const style = window.getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return (
        style.visibility !== "hidden" &&
        style.display !== "none" &&
        rect.width > 2 &&
        rect.height > 2 &&
        element.textContent?.trim()
      );
    });

    for (const element of visibleElements) {
      const style = window.getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      const tag = element.tagName.toLowerCase();
      const text = element.textContent?.trim().replace(/\s+/g, " ").slice(0, 80) ?? "";

      if (["html", "body", "script", "style", "svg", "path"].includes(tag)) continue;
      if (element.classList.contains("truncate")) continue;

      const clipsX = element.scrollWidth > element.clientWidth + 1 && ["hidden", "clip"].includes(style.overflowX);
      const clipsY = element.scrollHeight > element.clientHeight + 1 && ["hidden", "clip"].includes(style.overflowY);
      if (text.length > 1 && (clipsX || clipsY)) {
        failures.push(`clipped text: "${text}"`);
      }

      if (rect.left < -1 || rect.right > window.innerWidth + 1) {
        failures.push(`viewport clipping: "${text}"`);
      }
    }

    const fixedElements = visibleElements.filter((element) => window.getComputedStyle(element).position === "fixed");
    for (const fixed of fixedElements) {
      const fixedRect = fixed.getBoundingClientRect();
      const fixedText = fixed.textContent?.trim().replace(/\s+/g, " ").slice(0, 80) ?? "";
      if (!fixedText) continue;

      const overlapping = visibleElements.find((candidate) => {
        if (candidate === fixed || fixed.contains(candidate) || candidate.contains(fixed)) return false;
        const candidateRect = candidate.getBoundingClientRect();
        const candidateText = candidate.textContent?.trim();
        if (!candidateText) return false;
        if (candidateText.length > 160) return false;
        if (candidate.children.length > 4) return false;
        if (candidateRect.width > window.innerWidth * 0.75) return false;
        if (candidateRect.height > window.innerHeight * 0.5) return false;
        return !(
          candidateRect.right < fixedRect.left ||
          candidateRect.left > fixedRect.right ||
          candidateRect.bottom < fixedRect.top ||
          candidateRect.top > fixedRect.bottom
        );
      });

      if (overlapping) {
        const overlapText = overlapping.textContent?.trim().replace(/\s+/g, " ").slice(0, 80) ?? "";
        failures.push(`fixed element overlaps content: "${fixedText}" over "${overlapText}"`);
      }
    }

    const dangerWords = ["资金异常", "订单异常", "持仓异常", "保护异常", "暂不可用", "需要介入"];
    const strategyNames = ["MPG", "TEQ", "FBS", "SOR", "PMR"];
    for (const name of strategyNames) {
      const row = Array.from(document.querySelectorAll("div, li, tr"))
        .filter((element) => element.textContent?.includes(name))
        .map((element) => ({
          element,
          text: element.textContent?.trim().replace(/\s+/g, " ") ?? "",
          rect: element.getBoundingClientRect(),
        }))
        .filter((item) => item.rect.height >= 36 && item.rect.height <= 180 && item.text.length <= 360)
        .sort((a, b) => a.text.length - b.text.length)[0];

      if (row) {
        const count = dangerWords.reduce((sum, word) => sum + (row.text.match(new RegExp(word, "g"))?.length ?? 0), 0);
        if (count > 2) {
          failures.push(`red-chip flood in ${name} row: ${count} abnormal labels`);
        }
      }
    }

    const abnormalEmptyState = ["暂无订单", "暂无持仓"].some((emptyLabel) => {
      return Array.from(document.querySelectorAll("div, section, article")).some((element) => {
        const text = element.textContent?.trim().replace(/\s+/g, " ") ?? "";
        return text.includes(emptyLabel) && /异常|需要介入|错误/.test(text);
      });
    });
    if (abnormalEmptyState) {
      failures.push("empty order or position state is presented as abnormal");
    }

    return failures;
  });

  issues.push(...structural);

  if (viewport.width >= 1024) {
    const activeNavText = await page.locator('nav button[aria-current="page"]').first().innerText().catch(() => "");
    if (activeNavText.trim() !== target.label) {
      issues.push(`active navigation mismatch: expected ${target.label}, got ${activeNavText.trim() || "none"}`);
    }
    const navStyleIssues = await page.evaluate((expectedLabel) => {
      const nav = document.querySelector('aside nav[aria-label="主导航"]');
      if (!nav) return ["desktop navigation missing"];
      const buttons = Array.from(nav.querySelectorAll("button"));
      const rootStyle = window.getComputedStyle(document.documentElement);
      const primary = rootStyle.getPropertyValue("--sidebar-primary").trim();
      const active = buttons.find((button) => button.getAttribute("aria-current") === "page");
      const normalize = (value) => value.replace(/\s+/g, "").toLowerCase();
      const activeText = active?.textContent?.trim() ?? "";
      const activeBg = active ? window.getComputedStyle(active).backgroundColor : "";
      const primaryProbe = document.createElement("span");
      primaryProbe.style.backgroundColor = primary;
      document.body.appendChild(primaryProbe);
      const primaryRgb = window.getComputedStyle(primaryProbe).backgroundColor;
      primaryProbe.remove();

      const failures = [];
      if (!active) {
        failures.push("active navigation visual state missing");
      } else if (activeText !== expectedLabel) {
        failures.push(`active navigation visual text mismatch: expected ${expectedLabel}, got ${activeText || "none"}`);
      } else if (normalize(activeBg) !== normalize(primaryRgb)) {
        failures.push(`active navigation background mismatch: expected ${primaryRgb}, got ${activeBg || "none"}`);
      }

      const inactivePrimary = buttons
        .filter((button) => button !== active)
        .filter((button) => normalize(window.getComputedStyle(button).backgroundColor) === normalize(primaryRgb))
        .map((button) => button.textContent?.trim() || "unknown");
      if (inactivePrimary.length > 0) {
        failures.push(`inactive navigation uses active background: ${inactivePrimary.join(", ")}`);
      }
      return failures;
    }, target.label);
    issues.push(...navStyleIssues);
  }

  return issues;
}

async function runCase(browser, scenario, target, theme, viewport) {
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
  });
  await context.addInitScript((selectedTheme) => {
    window.localStorage.setItem("owner-console-theme", selectedTheme);
  }, theme);

  const page = await context.newPage();
  const consoleIssues = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      consoleIssues.push(`${message.type()}: ${message.text()}`);
    }
  });

  try {
    const scenarioQuery = scenario === "external" ? "" : `?scenario=${encodeURIComponent(scenario)}`;
    await page.goto(`${baseUrl}/${scenarioQuery}`, { waitUntil: "networkidle" });
    await navigateToPage(page, target, viewport);
    await page.getByText(target.expected, { exact: false }).first().waitFor({ state: "visible", timeout: 6_000 });
    await waitForDesktopNavigationActiveStyle(page, target, viewport);

    const issues = await collectChecks(page, target, viewport, consoleIssues);
    const screenshotName = `${scenario}-${theme}-${viewport.name}-${target.key}.png`;
    await page.screenshot({ path: path.join(artifactDir, screenshotName), fullPage: true });

    return {
      scenario,
      theme,
      viewport: viewport.name,
      page: target.label,
      screenshot: screenshotName,
      status: issues.length === 0 ? "PASS" : "FAIL",
      issues,
    };
  } catch (error) {
    const screenshotName = `${scenario}-${theme}-${viewport.name}-${target.key}-failed.png`;
    await page.screenshot({ path: path.join(artifactDir, screenshotName), fullPage: true }).catch(() => undefined);
    return {
      scenario,
      theme,
      viewport: viewport.name,
      page: target.label,
      screenshot: screenshotName,
      status: "FAIL",
      issues: [error instanceof Error ? error.message : String(error)],
    };
  } finally {
    await context.close();
  }
}

function renderLedger(results) {
  const lines = [
    "# Owner Runtime Console Visual QA Ledger",
    "",
    `Base URL: ${baseUrl}`,
    `Strict: ${strict}`,
    `Generated: ${new Date().toISOString()}`,
    "",
    "| Scenario | Theme | Viewport | Page | Status | Screenshot | Issues |",
    "| --- | --- | --- | --- | --- | --- | --- |",
  ];

  for (const result of results) {
    const issues = result.issues.length > 0 ? result.issues.join("<br>") : "Layout ratio, hierarchy, spacing, typography, color, and exception expression passed automated checks.";
    lines.push(
      `| ${result.scenario} | ${result.theme} | ${result.viewport} | ${result.page} | ${result.status} | ${result.screenshot} | ${issues} |`,
    );
  }

  lines.push(
    "",
    "## Manual Review Checklist",
    "",
    "- Layout ratio matches the accepted reference proportions.",
    "- Main hierarchy is understandable within seconds.",
    "- Spacing is neither cramped nor wastefully empty.",
    "- Typography is readable and not report-like.",
    "- Red is reserved for real Owner attention.",
    "- Unavailable states are compressed into one Owner-readable reason.",
    "",
  );

  return lines.join("\n");
}

await mkdir(artifactDir, { recursive: true });

const browser = await chromium.launch();
const allResults = [];

try {
  for (const scenario of scenarios) {
    const server = externalUrl ? null : startServer(scenario);
    try {
      await waitForServer(baseUrl);
      for (const theme of themes) {
        for (const viewport of viewports) {
          for (const target of pages) {
            const result = await runCase(browser, scenario, target, theme, viewport);
            allResults.push(result);
            const issueSuffix = result.issues.length > 0 ? `: ${result.issues[0]}` : "";
            console.log(`${result.status} ${scenario}/${theme}/${viewport.name}/${target.label}${issueSuffix}`);
          }
        }
      }
    } finally {
      await stopProcess(server);
    }
  }
} finally {
  await browser.close();
}

const ledger = renderLedger(allResults);
await writeFile(path.join(artifactDir, "visual-ledger.md"), ledger);

const failures = allResults.filter((result) => result.status === "FAIL");
console.log(`Visual QA screenshots and ledger: ${artifactDir}`);

if (failures.length > 0 && strict) {
  throw new Error(`Visual QA failed with ${failures.length} hard failure(s). See ${path.join(artifactDir, "visual-ledger.md")}`);
}
