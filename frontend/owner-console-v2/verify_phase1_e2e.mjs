import pkg from '../owner-console/node_modules/@playwright/test/index.js';
import fs from 'fs';
import path from 'path';

const { chromium } = pkg;

const outDir = path.resolve('screenshots');
if (!fs.existsSync(outDir)) {
  fs.mkdirSync(outDir, { recursive: true });
}

// Load real Tokyo production dumps
const facts = JSON.parse(fs.readFileSync('tokyo_live_facts.json', 'utf8'));
const controlsData = JSON.parse(fs.readFileSync('tokyo_live_controls.json', 'utf8'));

function envelope(data, freshness = 'fresh') {
  return {
    data,
    freshness,
    now_ms: Date.now(),
    source_watermark_ms: Date.now() - 5000,
  };
}

async function runE2E() {
  console.log('--- Starting Owner Console V2 Real Integration E2E Verification ---');

  const browser = await chromium.launch({
    headless: true,
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 960 },
    deviceScaleFactor: 2,
    ignoreHTTPSErrors: true,
  });

  let sessionAuthenticated = true;
  const requestLog = [];

  // Route requests with real Tokyo production responses
  await context.route('**/api/owner/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const pathname = url.pathname;
    const method = route.request().method();

    requestLog.push({ method, pathname, time: Date.now() });

    if (pathname === '/api/owner/v1/auth/session') {
      if (sessionAuthenticated) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ authenticated: true }),
        });
      } else {
        return route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify({ error: { code: 'unauthorized', message: 'Authentication required' } }),
        });
      }
    }

    if (pathname === '/api/owner/v1/auth/logout') {
      sessionAuthenticated = false;
      return route.fulfill({
        status: 204,
      });
    }

    if (pathname === '/api/owner/v1/overview') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(envelope(facts.overview, 'unavailable')),
      });
    }

    if (pathname === '/api/owner/v1/controls') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(controlsData.controls),
      });
    }

    if (pathname === '/api/owner/v1/tickets') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(envelope(facts.tickets, 'fresh')),
      });
    }

    if (pathname === '/api/owner/v1/strategies') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(envelope(facts.strategies, 'fresh')),
      });
    }

    if (pathname.includes('/selection')) {
      if (pathname.includes('SOR-1H-001')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(controlsData.selection_sor),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(controlsData.selection_cpm),
      });
    }

    if (pathname.includes('/causality')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(envelope(facts.causality, 'fresh')),
      });
    }

    return route.continue();
  });

  const page = await context.newPage();

  const setDarkMode = async () => {
    await page.evaluate(() => {
      document.documentElement.classList.add('dark');
      document.documentElement.classList.remove('light');
      localStorage.setItem('brc_owner_console_theme', 'dark');
    });
    await page.waitForTimeout(200);
  };

  const setLightMode = async () => {
    await page.evaluate(() => {
      document.documentElement.classList.remove('dark');
      document.documentElement.classList.add('light');
      localStorage.setItem('brc_owner_console_theme', 'light');
    });
    await page.waitForTimeout(200);
  };

  console.log('Navigating to https://127.0.0.1:5174 ...');
  await page.goto('https://127.0.0.1:5174', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);

  // ==========================================
  // Test 1: Verify Overview Page & Active Episodes
  // ==========================================
  console.log('Checking Overview page assertions...');

  // Assert 3 Active tickets present
  const episodesBadge = await page.textContent('h3:has-text("当前在管交易") + span');
  console.log('Episodes Badge:', episodesBadge);
  if (!episodesBadge?.includes('3 笔在管')) {
    throw new Error(`Expected "3 笔在管", got "${episodesBadge}"`);
  }

  // Assert direction and symbols
  const pageText = await page.textContent('body');
  if (!pageText.includes('TRXUSDT') || !pageText.includes('BCHUSDT') || !pageText.includes('UNIUSDT')) {
    throw new Error('Missing active ticket symbols TRXUSDT, BCHUSDT, or UNIUSDT');
  }
  if (!pageText.includes('做多 (LONG)') || !pageText.includes('做空 (SHORT)')) {
    throw new Error('Missing directional indicators');
  }

  // Assert Attention & Unavailable facts
  if (pageText.includes('一切正常，无需介入')) {
    throw new Error('CRITICAL BUG: "一切正常，无需介入" appeared while freshness is unavailable!');
  }
  if (!pageText.includes('Required overview evidence is unavailable.')) {
    throw new Error('Missing conclusion summary "Required overview evidence is unavailable."');
  }
  if (!pageText.includes('UNAVAILABLE')) {
    throw new Error('Missing UNAVAILABLE freshness badge');
  }

  // Assert Capacity in pulse shows 3 / 3
  if (!pageText.includes('3 / 3') && !pageText.includes('容量占用: 3 / 3')) {
    throw new Error('Capacity does not show 3 / 3 in pulse header');
  }

  // Capture Overview Dark & Light
  console.log('Capturing Overview Screenshots...');
  await setDarkMode();
  await page.screenshot({ path: path.join(outDir, 'screenshot_overview_dark.png'), fullPage: false });

  await setLightMode();
  await page.screenshot({ path: path.join(outDir, 'screenshot_overview_light.png'), fullPage: false });

  // ==========================================
  // Test 2: Causality Drawer from Overview
  // ==========================================
  console.log('Testing Causality Drawer...');
  await setDarkMode();
  // Click first "查看交易因果" button
  const causalityBtn = page.getByRole('button', { name: '查看交易因果' }).first();
  await causalityBtn.click();
  await page.waitForTimeout(600);

  const drawerText = await page.textContent('[role="dialog"]');
  if (!drawerText.includes('8 阶段时间线') || !drawerText.includes('0.33239') || !drawerText.includes('1756')) {
    throw new Error('Causality drawer did not render real price plan or 8 stages');
  }

  await page.screenshot({ path: path.join(outDir, 'screenshot_causality_drawer_dark.png'), fullPage: false });
  await setLightMode();
  await page.screenshot({ path: path.join(outDir, 'screenshot_causality_drawer_light.png'), fullPage: false });

  // Close drawer
  const closeBtn = page.getByRole('button', { name: '关闭抽屉' });
  await closeBtn.click();
  await page.waitForTimeout(400);

  // ==========================================
  // Test 3: Controls Page (Strategy Matrix & Selection)
  // ==========================================
  console.log('Navigating to Controls tab...');
  const controlsNavBtn = page.getByRole('button', { name: '主控中心' }).first();
  await controlsNavBtn.click();
  await page.waitForTimeout(800);

  const controlsText = await page.textContent('body');
  // Verify CPM has 2, BRF2 has 1
  if (!controlsText.includes('CPM-RO-001') || !controlsText.includes('BRF2-001')) {
    throw new Error('Strategy Matrix missing strategies');
  }
  // Check Capacity section
  if (!controlsText.includes('3 / 3 笔') || !controlsText.includes('已满额')) {
    throw new Error('Capacity section does not show 3 / 3 笔 (已满额)');
  }

  // Switch Selection tab to SOR-1H-001
  console.log('Checking SOR-1H-001 selection...');
  const sorTab = page.getByRole('button', { name: 'SOR-1H-001' });
  await sorTab.click();
  await page.waitForTimeout(600);

  const selectionText = await page.textContent('body');
  if (!selectionText.includes('DYNAMIC (24h 日周期)')) {
    throw new Error('SOR-1H-001 does not show 24h cadence');
  }
  if (!selectionText.includes('7 入围') || !selectionText.includes('17 过滤')) {
    throw new Error(`SOR-1H-001 does not show 7 入围 / 17 过滤. Text: ${selectionText}`);
  }
  if (!selectionText.includes('ACTIVE_NEW')) {
    throw new Error('SOR-1H-001 missing ACTIVE_NEW authority badge');
  }

  // Capture Controls Screenshots Dark & Light
  console.log('Capturing Controls Screenshots...');
  await setDarkMode();
  await page.screenshot({ path: path.join(outDir, 'screenshot_controls_dark.png'), fullPage: false });
  await setLightMode();
  await page.screenshot({ path: path.join(outDir, 'screenshot_controls_light.png'), fullPage: false });

  // Open Selection Drawer
  console.log('Opening Selection Drawer...');
  await setDarkMode();
  const inspectBtn = page.getByRole('button', { name: '标的明细与诊断' });
  await inspectBtn.click();
  await page.waitForTimeout(600);

  const selDrawerText = await page.textContent('[role="dialog"]');
  if (!selDrawerText.includes('ATOMUSDT') || !selDrawerText.includes('SOLUSDT') || !selDrawerText.includes('7 入围 / 17 过滤')) {
    throw new Error('Selection drawer missing 7 tokens or 17 filtered count');
  }

  await page.screenshot({ path: path.join(outDir, 'screenshot_selection_drawer_dark.png'), fullPage: false });
  await setLightMode();
  await page.screenshot({ path: path.join(outDir, 'screenshot_selection_drawer_light.png'), fullPage: false });

  // Close Selection Drawer
  const closeSelBtn = page.getByRole('button', { name: '关闭诊断抽屉' });
  await closeSelBtn.click();
  await page.waitForTimeout(400);

  // ==========================================
  // Test 4: Network Frequency Test (Check idle request count over 10s)
  // ==========================================
  console.log('Testing network request stability over 10 seconds...');
  const preCount = requestLog.length;
  await page.waitForTimeout(10000);
  const postCount = requestLog.length;
  const requestsIn10s = postCount - preCount;
  console.log(`Requests during 10s idle period: ${requestsIn10s}`);
  if (requestsIn10s > 8) {
    throw new Error(`Query stampede detected! ${requestsIn10s} requests in 10s idle.`);
  }

  // ==========================================
  // Test 5: Logout Flow
  // ==========================================
  console.log('Testing Logout Flow...');
  await setDarkMode();
  const logoutBtn = page.getByTestId('navbar-logout-btn');
  await logoutBtn.click();
  await page.waitForTimeout(1000);

  const loginPageText = await page.textContent('body');
  if (!loginPageText.includes('Owner 身份验证')) {
    throw new Error('Logout did not return to login page');
  }

  await page.screenshot({ path: path.join(outDir, 'screenshot_logout_screen.png'), fullPage: false });

  await browser.close();
  console.log('--- ALL E2E VERIFICATION ASSERTIONS PASSED SUCCESSFULLY! ---');
}

runE2E().catch((err) => {
  console.error('E2E TEST FAILURE:', err);
  process.exit(1);
});
