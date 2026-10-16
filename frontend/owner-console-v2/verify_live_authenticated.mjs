import pkg from '../owner-console/node_modules/@playwright/test/index.js';
import fs from 'fs';
import path from 'path';

const outDir = path.resolve('screenshots');
if (!fs.existsSync(outDir)) {
  fs.mkdirSync(outDir, { recursive: true });
}

const { chromium } = pkg;

async function runLiveVerification() {
  console.log('================================================================');
  console.log('--- Starting Real Live Authenticated Session Verification ---');
  console.log('================================================================\n');

  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const context = browser.contexts()[0];
  const page = context.pages().find((p) => p.url().includes('5174'));

  if (!page) {
    throw new Error('Could not find active owner console page on port 5174 in CDP session');
  }

  console.log(`Attached to page: ${page.url()} (${await page.title()})`);

  // Track console errors
  const consoleErrors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
    }
  });
  page.on('pageerror', (err) => {
    consoleErrors.push(err.message);
  });

  // Track network requests
  const networkRequests = [];
  page.on('request', (req) => {
    if (req.url().includes('/api/owner/v1')) {
      networkRequests.push({
        url: req.url(),
        method: req.method(),
        time: Date.now(),
      });
    }
  });

  const setDarkMode = async () => {
    await page.evaluate(() => {
      document.documentElement.classList.add('dark');
      document.documentElement.classList.remove('light');
      localStorage.setItem('brc_owner_console_theme', 'dark');
    });
    await page.waitForTimeout(300);
  };

  const setLightMode = async () => {
    await page.evaluate(() => {
      document.documentElement.classList.remove('dark');
      document.documentElement.classList.add('light');
      localStorage.setItem('brc_owner_console_theme', 'light');
    });
    await page.waitForTimeout(300);
  };

  // Ensure we are on Overview
  console.log('\n--- Step 1: Real Overview Verification ---');
  const overviewNav = page.getByRole('button', { name: '总览态势' }).first();
  await overviewNav.click();
  await page.waitForTimeout(1000);

  const overviewBody = await page.textContent('body');
  console.log('Overview page loaded.');

  // Extract real live metrics from page
  const pulseText = await page.textContent('div:has-text("容量占用:")');
  console.log('Live Capacity Pulse:', pulseText?.slice(0, 80));

  const pnlText = await page.textContent('div:has-text("今日净收益 (Net PnL)")');
  console.log('Live PnL Card:', pnlText?.replace(/\s+/g, ' ').slice(0, 100));

  const episodesSection = await page.textContent('h3:has-text("当前在管交易") + span');
  console.log('Live Active Episodes count:', episodesSection);

  // Capture Overview Dark & Light
  console.log('Capturing real Overview screenshots...');
  await setDarkMode();
  await page.screenshot({ path: path.join(outDir, 'live_screenshot_overview_dark.png'), fullPage: false });
  await setLightMode();
  await page.screenshot({ path: path.join(outDir, 'live_screenshot_overview_light.png'), fullPage: false });

  // Step 2: Causality Drawer
  console.log('\n--- Step 2: Real Causality Drawer Verification ---');
  await setDarkMode();
  const causalityButtons = page.getByRole('button', { name: '查看交易因果' });
  const count = await causalityButtons.count();
  console.log(`Found ${count} active trade causality button(s)`);

  if (count > 0) {
    await causalityButtons.first().click();
    await page.waitForTimeout(1000);

    const causalityDialog = page.getByRole('dialog');
    const causalityText = await causalityDialog.textContent();
    console.log('Live Causality drawer text preview:', causalityText?.slice(0, 150));

    // Verify 8 stages rendered
    if (causalityText?.includes('8 阶段时间线')) {
      console.log('✓ Verified: 8 阶段时间线 rendered with real facts');
    }

    await page.screenshot({ path: path.join(outDir, 'live_screenshot_causality_drawer_dark.png'), fullPage: false });
    await setLightMode();
    await page.screenshot({ path: path.join(outDir, 'live_screenshot_causality_drawer_light.png'), fullPage: false });

    // Close causality drawer
    const closeBtn = page.getByRole('button', { name: '关闭抽屉' });
    await closeBtn.click();
    await page.waitForTimeout(500);
  }

  // Step 3: Controls Page & Strategy Matrix
  console.log('\n--- Step 3: Real Controls Console Verification ---');
  await setDarkMode();
  const controlsNav = page.getByRole('button', { name: '主控中心' }).first();
  await controlsNav.click();
  await page.waitForTimeout(1000);

  const controlsBody = await page.textContent('body');
  if (controlsBody?.includes('控制中心') && controlsBody?.includes('策略独立控制矩阵')) {
    console.log('✓ Controls center and strategy matrix loaded');
  }

  // Check version display & capacity
  if (controlsBody?.includes('控制: v')) {
    console.log('✓ Strategy matrix renders control version distinctly');
  }

  await page.screenshot({ path: path.join(outDir, 'live_screenshot_controls_dark.png'), fullPage: false });
  await setLightMode();
  await page.screenshot({ path: path.join(outDir, 'live_screenshot_controls_light.png'), fullPage: false });

  // Step 4: Selection Diagnostics (Generic & SOR-1H)
  console.log('\n--- Step 4: Real Selection Diagnostics Verification ---');
  await setDarkMode();

  // Test CPM tab (Generic)
  const cpmTab = page.getByRole('button', { name: 'CPM-RO-001' });
  await cpmTab.click();
  await page.waitForTimeout(800);
  const cpmText = await page.textContent('body');
  console.log('Generic (CPM) Selection mode and outcome:', cpmText?.match(/DYNAMIC \(.*?\)/)?.[0]);

  // Test SOR-1H tab (ORB)
  const sorTab = page.getByRole('button', { name: 'SOR-1H-001' });
  await sorTab.click();
  await page.waitForTimeout(800);
  const sorText = await page.textContent('body');
  console.log('SOR-1H Selection mode:', sorText?.match(/DYNAMIC \(.*?\)/)?.[0]);
  console.log('SOR-1H Candidate status:', sorText?.match(/\d+ 入选 \/ \d+ 未入选 \(候选总数 \d+\)/)?.[0]);

  // Open Selection Drawer
  console.log('Opening Selection Drawer...');
  const inspectBtn = page.getByRole('button', { name: '标的明细与诊断' });
  await inspectBtn.click();
  await page.waitForTimeout(1000);

  const drawerDialog = page.getByRole('dialog');
  const drawerText = await drawerDialog.textContent();
  console.log('Selection Drawer preview:', drawerText?.slice(0, 150));

  await page.screenshot({ path: path.join(outDir, 'live_screenshot_selection_drawer_dark.png'), fullPage: false });
  await setLightMode();
  await page.screenshot({ path: path.join(outDir, 'live_screenshot_selection_drawer_light.png'), fullPage: false });

  // Close Selection Drawer
  const closeSelBtn = page.getByRole('button', { name: '关闭诊断抽屉' });
  await closeSelBtn.click();
  await page.waitForTimeout(500);

  // Step 5: Network Frequency Test on Live Session
  console.log('\n--- Step 5: Live Idle Network Stability Test (10s) ---');
  await setDarkMode();
  const preReqCount = networkRequests.length;
  console.log(`Starting 10-second idle measurement...`);
  await page.waitForTimeout(10000);
  const postReqCount = networkRequests.length;
  const requestsIn10s = postReqCount - preReqCount;
  console.log(`Requests during 10s idle period on real cluster: ${requestsIn10s}`);

  if (requestsIn10s > 0) {
    console.warn(`[WARN] Extra requests in 10s:`, networkRequests.slice(preReqCount));
  } else {
    console.log('✓ PASS: Zero extra business API requests during 10s idle window!');
  }

  // Check console errors
  console.log('\n--- Step 6: Console Error Audit ---');
  console.log(`Total console errors recorded during live run: ${consoleErrors.length}`);
  if (consoleErrors.length > 0) {
    console.warn('Console error messages:', consoleErrors);
  } else {
    console.log('✓ PASS: Zero unhandled console errors or rejections during live session!');
  }

  console.log('\n================================================================');
  console.log('--- Real Live Authenticated Session Verification Completed ---');
  console.log('================================================================\n');
}

runLiveVerification().catch((err) => {
  console.error('LIVE VERIFICATION ERROR:', err);
  process.exit(1);
});
