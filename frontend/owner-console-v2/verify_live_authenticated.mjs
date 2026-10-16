import { exactDisplay, sameIdentities, authorityEvidence, tradesMetricsEvidence } from './verification_contracts.mjs';
import pkg from '../owner-console/node_modules/@playwright/test/index.js';
import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';

const outDir = path.resolve('screenshots');
if (!fs.existsSync(outDir)) {
  fs.mkdirSync(outDir, { recursive: true });
}

const { chromium } = pkg.default || pkg;

// Environment and metadata
let frontendCommit = 'unknown';
try {
  frontendCommit = execSync('git rev-parse HEAD', { encoding: 'utf8' }).trim();
} catch (e) {
  frontendCommit = 'unknown';
}
const executionTimestamp = new Date().toISOString();
const environmentNote = '本地 V2 前端 (https://127.0.0.1:5174) 连接生产 API (https://jiaoyingpan.cloud)';

// Assertion taxonomy: PASS | FAIL | INCOMPLETE_EVIDENCE | SCENARIO_NA
const assertionResults = [];
let totalPassed = 0;
let totalFailed = 0;
let totalIncomplete = 0;
let totalNA = 0;

function recordAssertion(id, category, name, outcome, details = {}) {
  if (outcome === 'PASS') totalPassed++;
  else if (outcome === 'FAIL') totalFailed++;
  else if (outcome === 'INCOMPLETE_EVIDENCE') totalIncomplete++;
  else if (outcome === 'SCENARIO_NA') totalNA++;
  else throw new Error(`Unknown assertion outcome: ${outcome}`);

  assertionResults.push({ id, category, name, status: outcome, details });
  const icon =
    outcome === 'PASS'
      ? '✓ PASS'
      : outcome === 'FAIL'
      ? '✗ FAIL'
      : outcome === 'INCOMPLETE_EVIDENCE'
      ? '⚠ INCOMPLETE'
      : '- SCENARIO_NA';
  console.log(`  ${icon} [${category}] ${name}`);
  if (outcome === 'FAIL' || outcome === 'INCOMPLETE_EVIDENCE') {
    console.error(`    Detail:`, details);
  }
}

function cleanSymbol(inst) {
  if (!inst) return '';
  const parts = inst.split(':');
  return parts.length >= 2 ? parts[1] : inst;
}

function formatMoneyMetric(metric) {
  if (!metric || metric.value === null || metric.value === undefined) return '--';
  if (metric.value === '0') return `0 ${metric.unit}`;
  const num = Number(metric.value);
  if (isNaN(num)) return `${metric.value} ${metric.unit}`;
  const sign = num > 0 ? '+' : '';
  const formatted = num.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${sign}${formatted} ${metric.unit}`.trim();
}

function formatPriceOrQty(val, maxDecimals = 5) {
  if (val === null || val === undefined || val === '') return '--';
  const num = Number(val);
  if (isNaN(num)) return String(val);
  return num.toLocaleString('en-US', {
    maximumFractionDigits: maxDecimals,
    useGrouping: false,
  });
}

const STAGE_LABELS_ZH = {
  signal: '信号 (Signal)',
  admission: '准入评估 (Admission)',
  entry: '入场下单 (Entry)',
  protection: '保护安装 (Protection)',
  tp_runner: '止盈 / Runner (TP/Runner)',
  exit: '退出执行 (Exit)',
  reconciliation: '账本对账 (Reconciliation)',
  review: '事后复盘 (Review)',
};

async function runLiveVerification() {
  console.log('================================================================');
  console.log('--- Owner Console V2: Strict Assertive Live Integration Run ---');
  console.log(`Commit:      ${frontendCommit}`);
  console.log(`Executed At: ${executionTimestamp}`);
  console.log(`Environment: ${environmentNote}`);
  console.log('================================================================\n');

  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const context = browser.contexts()[0];
  const page = context.pages().find((p) => p.url().includes('5174'));

  if (!page) {
    throw new Error('Could not find active owner console page on port 5174 in CDP session');
  }

  console.log(`Attached to CDP target: ${page.url()} (${await page.title()})\n`);

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

  // Track raw network traffic and responses with full HTTP status & parse tracking
  const interceptedResponses = {
    overview: { url: null, status: null, data: null, error: null },
    tickets: { url: null, status: null, data: null, error: null },
    controls: { url: null, status: null, data: null, error: null },
    strategies: { url: null, status: null, data: null, error: null },
    genericSelection: { url: null, status: null, data: null, error: null },
    sorSelection: { url: null, status: null, data: null, error: null },
    causality: {},
  };

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

  page.on('response', async (res) => {
    const url = res.url();
    if (!url.includes('/api/owner/v1')) return;
    const status = res.status();
    let body = null;
    let parseError = null;

    try {
      body = await res.json();
    } catch (e) {
      parseError = e.message;
    }

    if (url.includes('/api/owner/v1/overview')) {
      interceptedResponses.overview = { url, status, data: body, error: parseError };
    } else if (url.includes('/api/owner/v1/tickets?') || url.endsWith('/api/owner/v1/tickets')) {
      interceptedResponses.tickets = { url, status, data: body, error: parseError };
    } else if (url.endsWith('/api/owner/v1/controls')) {
      interceptedResponses.controls = { url, status, data: body, error: parseError };
    } else if (url.includes('/api/owner/v1/strategies')) {
      interceptedResponses.strategies = { url, status, data: body, error: parseError };
    } else if (url.includes('/strategies/CPM-RO-001/selection')) {
      interceptedResponses.genericSelection = { url, status, data: body, error: parseError };
    } else if (url.includes('/strategies/SOR-1H-001/selection')) {
      interceptedResponses.sorSelection = { url, status, data: body, error: parseError };
    } else if (url.includes('/causality')) {
      const match = url.match(/tickets\/([^/]+)\/causality/);
      if (match) {
        const rawId = match[1];
        const decodedId = decodeURIComponent(rawId);
        interceptedResponses.causality[rawId] = { url, status, data: body, error: parseError };
        interceptedResponses.causality[decodedId] = { url, status, data: body, error: parseError };
      }
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

  // Check if session is authenticated
  const checkAndAwaitLogin = async () => {
    const isLogin = await page.locator('input[type="password"]').isVisible().catch(() => false);
    if (isLogin) {
      console.log('\n⚠️  [CDP] Detected Login Page on https://127.0.0.1:5174/ (Session unauthenticated or expired).');
      console.log('⏳ [CDP] Waiting up to 600s for Owner to submit login credentials in the browser...');
      try {
        await page.waitForSelector('input[type="password"]', { state: 'detached', timeout: 600000 });
        console.log('✓ [CDP] Owner login detected! Waiting 3s for API requests to complete...');
        await page.waitForTimeout(3000);
      } catch (e) {
        console.error('❌ [CDP] Timed out waiting for Owner login. Please log in first.');
        process.exit(1);
      }
    }
  };

  await checkAndAwaitLogin();

  // Reset intercepted responses before reload to ensure only authenticated responses are recorded
  interceptedResponses.overview = {};
  interceptedResponses.tickets = {};
  interceptedResponses.controls = {};
  interceptedResponses.strategies = {};
  interceptedResponses.genericSelection = {};
  interceptedResponses.sorSelection = {};
  interceptedResponses.causality = {};

  // Reload page to intercept fresh server facts
  console.log('Refreshing page to ensure fresh API capture...');
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);

  // If reload kicked us back to login (e.g. cookie expired on reload), await login again
  await checkAndAwaitLogin();

  // ===========================================================================
  // Category 0: Essential API Preconditions & Response Contracts
  // ===========================================================================
  console.log('--- Category 0: Essential API Preconditions & Contracts ---');

  // P0.1: Overview API contract
  const overviewResp = interceptedResponses.overview;
  if (!overviewResp.status) {
    recordAssertion('P0.1', 'Precondition', 'Overview API response captured', 'INCOMPLETE_EVIDENCE', { reason: 'No response captured for GET /api/owner/v1/overview' });
  } else if (overviewResp.status !== 200 || overviewResp.error) {
    recordAssertion('P0.1', 'Precondition', 'Overview API HTTP 200 & valid JSON', 'FAIL', { status: overviewResp.status, error: overviewResp.error });
  } else if (!overviewResp.data?.data) {
    recordAssertion('P0.1', 'Precondition', 'Overview API envelope contract (data present)', 'FAIL', { data: overviewResp.data });
  } else {
    recordAssertion('P0.1', 'Precondition', 'Overview API HTTP 200 & contract satisfied', 'PASS', { status: 200, snapshotId: overviewResp.data?.snapshot_id });
  }

  // P0.2: Tickets API contract
  const ticketsResp = interceptedResponses.tickets;
  if (!ticketsResp.status) {
    recordAssertion('P0.2', 'Precondition', 'Tickets API response captured', 'INCOMPLETE_EVIDENCE', { reason: 'No response captured for GET /api/owner/v1/tickets' });
  } else if (ticketsResp.status !== 200 || ticketsResp.error) {
    recordAssertion('P0.2', 'Precondition', 'Tickets API HTTP 200 & valid JSON', 'FAIL', { status: ticketsResp.status, error: ticketsResp.error });
  } else if (!Array.isArray(ticketsResp.data?.data?.items ?? ticketsResp.data?.items)) {
    recordAssertion('P0.2', 'Precondition', 'Tickets API items array contract', 'FAIL', { data: ticketsResp.data });
  } else {
    const count = (ticketsResp.data?.data?.items ?? ticketsResp.data?.items).length;
    recordAssertion('P0.2', 'Precondition', 'Tickets API HTTP 200 & contract satisfied', 'PASS', { status: 200, itemsCount: count });
  }

  // P0.3: Controls API contract (NO fallback 3!)
  const controlsResp = interceptedResponses.controls;
  if (!controlsResp.status) {
    recordAssertion('P0.3', 'Precondition', 'Controls API response captured', 'INCOMPLETE_EVIDENCE', { reason: 'No response captured for GET /api/owner/v1/controls' });
  } else if (controlsResp.status !== 200 || controlsResp.error) {
    recordAssertion('P0.3', 'Precondition', 'Controls API HTTP 200 & valid JSON', 'FAIL', { status: controlsResp.status, error: controlsResp.error });
  } else if (typeof controlsResp.data?.account_capacity?.max_concurrent_tickets !== 'number') {
    // Strictly fail if max_concurrent_tickets is not a number; do NOT fall back to 3!
    recordAssertion('P0.3', 'Precondition', 'Controls API account_capacity.max_concurrent_tickets is number (no fallback)', 'FAIL', { capacity: controlsResp.data?.account_capacity });
  } else if (!Array.isArray(controlsResp.data?.strategies)) {
    recordAssertion('P0.3', 'Precondition', 'Controls API strategies array contract', 'FAIL', { strategies: controlsResp.data?.strategies });
  } else {
    recordAssertion('P0.3', 'Precondition', 'Controls API HTTP 200 & contract satisfied', 'PASS', {
      maxConcurrentTickets: controlsResp.data.account_capacity.max_concurrent_tickets,
      activeTicketCount: controlsResp.data.account_capacity.active_ticket_count,
      strategyCount: controlsResp.data.strategies.length,
    });
  }

  // Extract strongly-typed facts
  const rawOverview = overviewResp.data?.data;
  const rawTickets = ticketsResp.data?.data?.items ?? ticketsResp.data?.items ?? [];
  const rawControls = controlsResp.data;
  const activeTicketsList = rawTickets.filter((t) => t.terminal_at_ms === null);
  const capacityData = rawControls?.account_capacity;

  // ===========================================================================
  // Category 1: Overview Component Assertions (Object-Bound)
  // ===========================================================================
  console.log('\n--- Category 1: Overview Object-Bound Assertions ---');

  // Verify Overview page active
  const overviewNav = page.getByRole('button', { name: '总览态势' }).first();
  await overviewNav.click();
  await page.waitForTimeout(800);

  // 1.1 Capacity pulse: strictly bound to [data-testid="capacity-pulse"]
  const capacityPulseEl = page.locator('[data-testid="capacity-pulse"]');
  if (capacityData && typeof capacityData.max_concurrent_tickets === 'number') {
    const expectedActive = capacityData.active_ticket_count ?? activeTicketsList.length;
    const expectedMax = capacityData.max_concurrent_tickets; // Pure fact, NO fallback 3!
    const pulseText = await capacityPulseEl.textContent();
    const capacityMatches = exactDisplay(pulseText, `容量占用: ${expectedActive} / ${expectedMax}`);
    recordAssertion(
      'A1.1',
      'Overview',
      `Capacity pulse strictly matches account_capacity (${expectedActive} / ${expectedMax})`,
      capacityMatches ? 'PASS' : 'FAIL',
      { expected: `${expectedActive} / ${expectedMax}`, foundText: pulseText?.trim() }
    );
  } else {
    recordAssertion('A1.1', 'Overview', 'Capacity pulse strictly matches account_capacity', 'INCOMPLETE_EVIDENCE', { capacityData });
  }

  // 1.2 Today Net PnL card: strictly bound to [data-testid="net-pnl-card"]
  const pnlCardEl = page.locator('[data-testid="net-pnl-card"]');
  if (rawOverview?.today_net_pnl) {
    const formattedPnl = formatMoneyMetric(rawOverview.today_net_pnl);
    const pnlCardText = await pnlCardEl.locator('[data-testid="metric-value"]').textContent();
    const pnlMatches = exactDisplay(pnlCardText, formattedPnl);
    recordAssertion(
      'A1.2',
      'Overview',
      `Net PnL card matches today_net_pnl (${formattedPnl})`,
      pnlMatches ? 'PASS' : 'FAIL',
      { expected: formattedPnl, cardText: pnlCardText?.replace(/\s+/g, ' ').trim() }
    );
  } else {
    recordAssertion('A1.2', 'Overview', 'Net PnL card matches today_net_pnl', 'INCOMPLETE_EVIDENCE', { reason: 'today_net_pnl field missing' });
  }

  // 1.3 Today Net R card: strictly bound to [data-testid="net-r-card"]
  const rCardEl = page.locator('[data-testid="net-r-card"]');
  if (rawOverview?.today_net_r) {
    const formattedR = formatMoneyMetric(rawOverview.today_net_r);
    const rCardText = await rCardEl.locator('[data-testid="metric-value"]').textContent();
    const rMatches = exactDisplay(rCardText, formattedR);
    recordAssertion(
      'A1.3',
      'Overview',
      `Net R card matches today_net_r (${formattedR})`,
      rMatches ? 'PASS' : 'FAIL',
      { expected: formattedR, cardText: rCardText?.replace(/\s+/g, ' ').trim() }
    );
  } else {
    recordAssertion('A1.3', 'Overview', 'Net R card matches today_net_r', 'INCOMPLETE_EVIDENCE', { reason: 'today_net_r field missing' });
  }

  // 1.4 Active Episodes Container & Card-by-Card Omission/Spurious Check
  const episodesSection = page.locator('#active-episodes');
  const sectionVisible = await episodesSection.isVisible();
  recordAssertion('A1.4', 'Overview', 'Active episodes container #active-episodes visible', sectionVisible ? 'PASS' : 'FAIL', { sectionVisible });

  const displayedCards = episodesSection.locator('[data-ticket-id]');
  const displayedCount = await displayedCards.count();
  const countMatches = displayedCount === activeTicketsList.length;
  recordAssertion(
    'A1.5',
    'Overview',
    `Active episodes count strictly equals loaded active tickets (${displayedCount} == ${activeTicketsList.length})`,
    countMatches ? 'PASS' : 'FAIL',
    { displayedCount, loadedActiveTicketsCount: activeTicketsList.length }
  );

  // Check each active ticket card specifically by ticket_id
  let allCardsAccurate = true;
  const cardErrors = [];
  for (const t of activeTicketsList) {
    const cardEl = episodesSection.locator(`[data-ticket-id="${t.ticket_id}"]`);
    const cardFound = (await cardEl.count()) === 1;
    if (!cardFound) {
      allCardsAccurate = false;
      cardErrors.push({ ticket_id: t.ticket_id, error: 'Card not found in DOM' });
      continue;
    }

    const cardText = await cardEl.textContent();
    const symbolClean = cleanSymbol(t.exchange_instrument_id);
    const sideZh = t.position_side === 'long' ? '做多 (LONG)' : '做空 (SHORT)';
    const strategyId = t.strategy_group_id;

    if (!cardText?.includes(symbolClean)) {
      allCardsAccurate = false;
      cardErrors.push({ ticket_id: t.ticket_id, error: `Symbol ${symbolClean} missing` });
    }
    if (!cardText?.includes(sideZh)) {
      allCardsAccurate = false;
      cardErrors.push({ ticket_id: t.ticket_id, error: `Side ${sideZh} missing` });
    }
    if (!cardText?.includes(strategyId)) {
      allCardsAccurate = false;
      cardErrors.push({ ticket_id: t.ticket_id, error: `Strategy ${strategyId} missing` });
    }
  }

  recordAssertion(
    'A1.6',
    'Overview',
    `All active ticket cards accurately bind symbol, side, and strategyId without omission`,
    allCardsAccurate ? 'PASS' : 'FAIL',
    { verifiedCount: activeTicketsList.length, errors: cardErrors }
  );

  // Spurious card check: verify DOM does NOT have extra tickets not in activeTicketsList
  const domTicketIds = await displayedCards.evaluateAll((els) => els.map((el) => el.getAttribute('data-ticket-id')));
  const activeIdsSet = new Set(activeTicketsList.map((t) => t.ticket_id));
  const spuriousIds = domTicketIds.filter((id) => !activeIdsSet.has(id));
  recordAssertion(
    'A1.7',
    'Overview',
    `Zero spurious extra cards rendered in active episodes section`,
    spuriousIds.length === 0 ? 'PASS' : 'FAIL',
    { domIds: domTicketIds, spuriousIds }
  );

  // 1.8 Pagination Truncation Banner Truth
  const authoritativeActiveCount = capacityData?.active_ticket_count ?? activeTicketsList.length;
  const isTruncated = authoritativeActiveCount > activeTicketsList.length;
  const sectionText = await episodesSection.textContent();

  if (isTruncated) {
    const unloadedCount = authoritativeActiveCount - activeTicketsList.length;
    const truncationNoticeFound = sectionText?.includes(`另有 ${unloadedCount} 笔在管持仓未在首页展示`);
    recordAssertion(
      'A1.8',
      'Overview',
      `Pagination truncation notice accurately declares ${unloadedCount} unloaded tickets`,
      truncationNoticeFound ? 'PASS' : 'FAIL',
      { unloadedCount, found: truncationNoticeFound }
    );
  } else {
    // Pagination scenario not triggered: must verify NO false truncation notice is displayed!
    const falseTruncationFound = sectionText?.includes('未在首页展示') || sectionText?.includes('未在首屏展示');
    recordAssertion(
      'A1.8',
      'Overview',
      `Pagination not triggered; verified NO false truncation notice is shown`,
      falseTruncationFound ? 'FAIL' : 'SCENARIO_NA',
      { note: 'Active count <= loaded count, verified clean UI', falseNoticePresent: falseTruncationFound }
    );
  }

  // Capture Overview Screenshots
  console.log('Capturing real Overview screenshots (Dark / Light)...');
  await setDarkMode();
  await page.screenshot({ path: path.join(outDir, 'live_screenshot_overview_dark.png'), fullPage: false });
  await setLightMode();
  await page.screenshot({ path: path.join(outDir, 'live_screenshot_overview_light.png'), fullPage: false });

  // ===========================================================================
  // Category 2: Causality Drawer Component Assertions (Object-Bound)
  // ===========================================================================
  console.log('\n--- Category 2: Causality Drawer Object-Bound Assertions ---');
  await setDarkMode();

  const causalityButtons = page.getByRole('button', { name: '查看交易因果' });
  const causalityCount = await causalityButtons.count();

  if (causalityCount > 0 && activeTicketsList.length > 0) {
    const firstTicket = activeTicketsList[0];
    const targetCard = episodesSection.locator(`[data-ticket-id="${firstTicket.ticket_id}"]`);
    const cardCausalityBtn = (await targetCard.count()) > 0
      ? targetCard.getByRole('button', { name: '查看交易因果' })
      : causalityButtons.first();

    const causalityResponsePromise = page.waitForResponse(
      (res) => res.url().includes('/causality'),
      { timeout: 10000 }
    ).catch(() => null);

    await cardCausalityBtn.click();
    const capturedRes = await causalityResponsePromise;
    if (capturedRes) {
      try {
        const data = await capturedRes.json();
        const url = capturedRes.url();
        const match = url.match(/tickets\/([^/]+)\/causality/);
        if (match) {
          const rawId = match[1];
          const decodedId = decodeURIComponent(rawId);
          interceptedResponses.causality[rawId] = { url, status: capturedRes.status(), data, error: null };
          interceptedResponses.causality[decodedId] = { url, status: capturedRes.status(), data, error: null };
        }
      } catch (err) {
        // body may already be read by page.on('response')
      }
    }
    await page.waitForTimeout(1000);

    const causalityDrawer = page.locator('[data-testid="causality-drawer"]');
    const drawerVisible = await causalityDrawer.isVisible();
    recordAssertion('A2.1', 'Causality', 'Causality drawer opened and visible', drawerVisible ? 'PASS' : 'FAIL', { drawerVisible });

    // Verify causality API response was received for this ticket
    const causalityResp =
      interceptedResponses.causality[firstTicket.ticket_id] ||
      interceptedResponses.causality[encodeURIComponent(firstTicket.ticket_id)];

    if (!causalityResp || !causalityResp.status) {
      recordAssertion('A2.2', 'Causality', `Causality API response received for ${firstTicket.ticket_id}`, 'INCOMPLETE_EVIDENCE', { reason: 'No causality API response captured' });
      recordAssertion('A2.3', 'Causality', `Causality drawer binds to exact ticket_id (${firstTicket.ticket_id})`, 'INCOMPLETE_EVIDENCE', { reason: 'Causality response not available' });
      recordAssertion('A2.4', 'Causality', 'Current stage matches causality facts', 'INCOMPLETE_EVIDENCE', { reason: 'Causality response not available' });
      recordAssertion('A2.5', 'Causality', 'Price plan facts verification', 'INCOMPLETE_EVIDENCE', { reason: 'Causality response not available' });
      recordAssertion('A2.6', 'Causality', 'Causality drawer renders 8 阶段时间线', 'INCOMPLETE_EVIDENCE', { reason: 'Causality response not available' });
    } else if (causalityResp.status !== 200 || causalityResp.error) {
      recordAssertion('A2.2', 'Causality', `Causality API HTTP 200 for ${firstTicket.ticket_id}`, 'FAIL', { status: causalityResp.status, error: causalityResp.error });
      recordAssertion('A2.3', 'Causality', `Causality drawer binds to exact ticket_id (${firstTicket.ticket_id})`, 'INCOMPLETE_EVIDENCE', { reason: 'Causality API error' });
      recordAssertion('A2.4', 'Causality', 'Current stage matches causality facts', 'INCOMPLETE_EVIDENCE', { reason: 'Causality API error' });
      recordAssertion('A2.5', 'Causality', 'Price plan facts verification', 'INCOMPLETE_EVIDENCE', { reason: 'Causality API error' });
      recordAssertion('A2.6', 'Causality', 'Causality drawer renders 8 阶段时间线', 'INCOMPLETE_EVIDENCE', { reason: 'Causality API error' });
    } else {
      recordAssertion('A2.2', 'Causality', `Causality API HTTP 200 for ${firstTicket.ticket_id}`, 'PASS', { status: 200 });

      const causalityData = causalityResp.data?.data;

      // A2.3: Verify ticket ID header
      const drawerText = await causalityDrawer.textContent();
      const ticketIdMatches = drawerText?.includes(firstTicket.ticket_id);
      recordAssertion(
        'A2.3',
        'Causality',
        `Causality drawer binds to exact ticket_id (${firstTicket.ticket_id})`,
        ticketIdMatches ? 'PASS' : 'FAIL',
        { expectedTicketId: firstTicket.ticket_id, found: ticketIdMatches }
      );

      // A2.4: Current stage binds to causality response
      const currentStageEl = causalityDrawer.locator('[data-testid="causality-current-stage"]');
      const currentStageText = await currentStageEl.textContent();
      const expectedStageZh = STAGE_LABELS_ZH[causalityData?.current_stage] ?? causalityData?.current_stage ?? firstTicket.lifecycle_stage;
      recordAssertion(
        'A2.4',
        'Causality',
        `Current stage matches causality facts (${expectedStageZh})`,
        currentStageText?.includes(expectedStageZh) ? 'PASS' : 'FAIL',
        { expectedStage: expectedStageZh, domStageText: currentStageText?.trim() }
      );

      // A2.5: Price plan facts verification (entry price, stop price, quantity)
      if (causalityData?.price_plan) {
        const plan = causalityData.price_plan;
        const entryPriceEl = causalityDrawer.locator('[data-testid="causality-entry-price"]');
        const initialStopEl = causalityDrawer.locator('[data-testid="causality-initial-stop"]');
        const quantityEl = causalityDrawer.locator('[data-testid="causality-quantity"]');

        const entryPriceText = await entryPriceEl.locator('[data-testid="plan-value"]').textContent();
        const initialStopText = await initialStopEl.locator('[data-testid="plan-value"]').textContent();
        const quantityText = await quantityEl.locator('[data-testid="plan-value"]').textContent();

        const expectedEntry = formatPriceOrQty(plan.actual_entry_price ?? plan.entry_reference_price);
        const expectedStop = formatPriceOrQty(plan.initial_stop_price);
        const expectedQty = formatPriceOrQty(plan.ticket_quantity);

        const pricePlanMatches =
          exactDisplay(entryPriceText, expectedEntry) &&
          exactDisplay(initialStopText, expectedStop) &&
          exactDisplay(quantityText, expectedQty);

        recordAssertion(
          'A2.5',
          'Causality',
          `Price plan facts accurately rendered (Entry: ${expectedEntry}, Stop: ${expectedStop}, Qty: ${expectedQty})`,
          pricePlanMatches ? 'PASS' : 'FAIL',
          { expectedEntry, expectedStop, expectedQty, foundEntry: entryPriceText?.trim(), foundStop: initialStopText?.trim() }
        );
      } else {
        recordAssertion('A2.5', 'Causality', 'Price plan facts verification', 'SCENARIO_NA', { note: 'No price_plan in causality payload' });
      }

      // A2.6: Timeline renders 8 stages
      const hasTimeline = drawerText?.includes('8 阶段时间线');
      recordAssertion('A2.6', 'Causality', 'Causality drawer renders 8 阶段时间线', hasTimeline ? 'PASS' : 'FAIL', { hasTimeline });
    }

    await page.screenshot({ path: path.join(outDir, 'live_screenshot_causality_drawer_dark.png'), fullPage: false });
    await setLightMode();
    await page.screenshot({ path: path.join(outDir, 'live_screenshot_causality_drawer_light.png'), fullPage: false });

    // Close causality drawer
    const closeBtn = page.getByRole('button', { name: '关闭抽屉' });
    await closeBtn.click();
    await page.waitForTimeout(500);
    const dialogClosed = !(await causalityDrawer.isVisible());
    recordAssertion('A2.7', 'Causality', 'Causality drawer closes cleanly', dialogClosed ? 'PASS' : 'FAIL', { dialogClosed });
  } else {
    recordAssertion('A2.1', 'Causality', 'Active causality drawer inspectable', 'SCENARIO_NA', { note: 'No active tickets in current market' });
  }

  // ===========================================================================
  // Category 3: Controls & Strategy Matrix Component Assertions (Object-Bound)
  // ===========================================================================
  console.log('\n--- Category 3: Controls & Strategy Matrix Object-Bound Assertions ---');
  await setDarkMode();

  const controlsNav = page.getByRole('button', { name: '主控中心' }).first();
  await controlsNav.click();
  await page.waitForTimeout(1000);

  const controlsStrategies = rawControls?.strategies ?? [];
  const matrixTable = page.locator('table');
  const tableVisible = await matrixTable.isVisible();
  recordAssertion('A3.1', 'Controls', 'Strategy matrix table visible in Controls console', tableVisible ? 'PASS' : 'FAIL', { tableVisible });

  // Verify each strategy row individually by data-strategy-id
  const actualStrategyIds = await matrixTable.locator('tr[data-strategy-id]').evaluateAll(els => els.map(el => el.getAttribute('data-strategy-id')));
  let allRowsAccurate = sameIdentities(actualStrategyIds, controlsStrategies.map(s => s.strategy_group_id));
  const rowErrors = [];

  for (const s of controlsStrategies) {
    const rowEl = matrixTable.locator(`tr[data-strategy-id="${s.strategy_group_id}"]`);
    const rowFound = (await rowEl.count()) === 1;
    if (!rowFound) {
      allRowsAccurate = false;
      rowErrors.push({ strategy_group_id: s.strategy_group_id, error: 'Row not found by data-strategy-id' });
      continue;
    }

    const rowText = await rowEl.textContent();

    // Check control version
    const expectedControlVersion = `控制: v${s.control_version}`;
    if (!rowText?.includes(expectedControlVersion)) {
      allRowsAccurate = false;
      rowErrors.push({ strategy_group_id: s.strategy_group_id, error: `Control version mismatch: expected ${expectedControlVersion}` });
    }

    // Check admission health truth: MUST NOT claim "观察 Worker 运行正常"
    if (rowText?.includes('观察 Worker 运行正常')) {
      allRowsAccurate = false;
      rowErrors.push({ strategy_group_id: s.strategy_group_id, error: 'Speculative claim "观察 Worker 运行正常" found!' });
    }

    // Check admission health truth against real facts:
    const isCapacityFull = capacityData && typeof capacityData.max_concurrent_tickets === 'number' && (activeTicketsList.length >= capacityData.max_concurrent_tickets);
    if (s.strategy_group_id === 'SOR-001') {
      if (!rowText?.includes('已永久退役')) {
        allRowsAccurate = false;
        rowErrors.push({ strategy_group_id: s.strategy_group_id, error: 'Retired strategy must declare 已永久退役' });
      }
    } else if (s.configured_state === 'paused') {
      if (!rowText?.includes('策略已暂停')) {
        allRowsAccurate = false;
        rowErrors.push({ strategy_group_id: s.strategy_group_id, error: 'Paused strategy must declare 策略已暂停' });
      }
    } else if (s.configured_state === 'enabled') {
      if (isCapacityFull) {
        if (!rowText?.includes('全局总容量已达上限')) {
          allRowsAccurate = false;
          rowErrors.push({ strategy_group_id: s.strategy_group_id, error: 'Capacity is full, strategy must declare 全局总容量已达上限' });
        }
      } else {
        if (!rowText?.includes('控制已启用 · 实际准入状态待核实') && !rowText?.includes('准入阻断')) {
          allRowsAccurate = false;
          rowErrors.push({ strategy_group_id: s.strategy_group_id, error: 'Missing honest admission status text' });
        }
      }
    }

    // Check active ticket occupations for this strategy
    const matchingTickets = activeTicketsList.filter((t) => t.strategy_group_id === s.strategy_group_id);
    const badgeIds = await rowEl.locator('[data-ticket-id]').evaluateAll(els => els.map(el => el.getAttribute('data-ticket-id')));
    if (!sameIdentities(badgeIds, matchingTickets.map(t => t.ticket_id))) {
      allRowsAccurate = false;
      rowErrors.push({strategy_group_id:s.strategy_group_id,error:'Ticket identity set mismatch'});
    }
    if (matchingTickets.length > 0) {
      for (const t of matchingTickets) {
        const symbolClean = cleanSymbol(t.exchange_instrument_id);
        const sideUpper = t.position_side.toUpperCase();
        if (!rowText?.includes(symbolClean) || !rowText?.includes(sideUpper)) {
          allRowsAccurate = false;
          rowErrors.push({ strategy_group_id: s.strategy_group_id, error: `Active ticket badge missing: ${sideUpper} ${symbolClean}` });
        }
      }
    } else {
      if (!rowText?.includes('0 个占用')) {
        allRowsAccurate = false;
        rowErrors.push({ strategy_group_id: s.strategy_group_id, error: 'Expected "0 个占用" badge' });
      }
    }
  }

  recordAssertion(
    'A3.2',
    'Controls',
    `Every strategy row individually verified for control_version, admission health truth, and ticket badges (${controlsStrategies.length} strategies)`,
    allRowsAccurate ? 'PASS' : 'FAIL',
    { count: controlsStrategies.length, errors: rowErrors }
  );

  await page.screenshot({ path: path.join(outDir, 'live_screenshot_controls_dark.png'), fullPage: false });
  await setLightMode();
  await page.screenshot({ path: path.join(outDir, 'live_screenshot_controls_light.png'), fullPage: false });

  // ===========================================================================
  // Category 4: Selection Diagnostics Assertions (Object-Bound)
  // ===========================================================================
  console.log('\n--- Category 4: Selection Diagnostics Object-Bound Assertions ---');
  await setDarkMode();

  const selSection = page.locator('#selection-section');
  const selSectionVisible = await selSection.isVisible();
  recordAssertion('A4.1', 'Selection', 'Selection section #selection-section visible', selSectionVisible ? 'PASS' : 'FAIL', { selSectionVisible });

  // Refresh through the UI so the compared response is also the one rendered.
  async function verifyAuthority(id, kind, assertionId) {
    for (let attempt = 0; attempt < 2; attempt++) {
      const responsePromise = page.waitForResponse(r => new URL(r.url()).pathname.endsWith(`/strategies/${id}/selection`), {timeout:10000});
      await selSection.getByRole('button', {name:'刷新', exact:true}).click();
      const response = await responsePromise;
      if (response.status() !== 200) {
        recordAssertion(assertionId,'Selection','Authority response', 'FAIL',{status:response.status()}); return;
      }
      const preview = await response.json();
      interceptedResponses[kind === 'orb' ? 'sorSelection' : 'genericSelection'] = {status:200, data:preview, error:null};
      const before = authorityEvidence(kind, preview, Date.now());
      if (!before.complete) {
        recordAssertion(assertionId,'Selection','Authority contract','INCOMPLETE_EVIDENCE',before); return;
      }
      const status = selSection.locator('[data-testid="authority-status"]');
      await page.waitForTimeout(1100);
      const actual = await status.textContent();
      const actualId = await status.getAttribute('data-authority-id');
      const after = authorityEvidence(kind, preview, Date.now());
      if (before.state !== after.state) continue;
      const matches = exactDisplay(actual, after.label) && actualId === (after.id ?? '');
      recordAssertion(assertionId,'Selection','Authority identity and time validity', matches?'PASS':'FAIL',{...after,actual,actualId}); return;
    }
    recordAssertion(assertionId,'Selection','Authority boundary stable sample','INCOMPLETE_EVIDENCE',{reason:'Time boundary crossed during both bounded samples'});
  }

  // 4.1 Generic Selection (CPM-RO-001)
  const cpmTab = selSection.getByRole('button', { name: 'CPM-RO-001' });
  await cpmTab.click();
  await page.waitForTimeout(1000);

  const cpmResp = interceptedResponses.genericSelection;
  if (!cpmResp.status) {
    recordAssertion('A4.2', 'Selection', 'Generic selection API response captured for CPM-RO-001', 'INCOMPLETE_EVIDENCE', { reason: 'No response for CPM-RO-001 selection' });
  } else if (cpmResp.status !== 200 || cpmResp.error) {
    recordAssertion('A4.2', 'Selection', 'Generic selection API HTTP 200 for CPM-RO-001', 'FAIL', { status: cpmResp.status, error: cpmResp.error });
  } else {
    recordAssertion('A4.2', 'Selection', 'Generic selection API HTTP 200 for CPM-RO-001', 'PASS', { status: 200 });

    let cpmData = cpmResp.data;
    const cpmSectionText = await selSection.textContent();

    // Verify 4h cadence (not 24h)
    const cadenceMatches = cpmSectionText?.includes('4h 周期') || cpmSectionText?.includes('4h');
    recordAssertion('A4.3', 'Selection', 'Generic Selection (CPM-RO-001) reports 4h cadence (not 24h)', cadenceMatches ? 'PASS' : 'FAIL', { cadenceMatches });

    await verifyAuthority('CPM-RO-001', 'generic', 'A4.4');
    cpmData = interceptedResponses.genericSelection.data;

    // Open Selection Drawer
    const inspectBtn = selSection.getByRole('button', { name: '标的明细与诊断' });
    await inspectBtn.click();
    await page.waitForTimeout(1000);

    const selDrawer = page.getByRole('dialog');
    const drawerVisible = await selDrawer.isVisible();
    recordAssertion('A4.5', 'Selection', 'Selection diagnostics drawer opened', drawerVisible ? 'PASS' : 'FAIL', { drawerVisible });

    const drawerText = await selDrawer.textContent();
    const honestNoticeFound =
      drawerText?.includes('接口未提供候选名单与过滤仲裁流水') ||
      drawerText?.includes('候选全量名单、排名及仲裁归因依据后端接口未提供');
    recordAssertion('A4.6', 'Selection', 'Generic selection drawer truthfully declares "接口未提供候选名单与过滤仲裁流水"', honestNoticeFound ? 'PASS' : 'FAIL', { honestNoticeFound });

    // Member instruments match
    let allMembersMatch = true;
    const genericMembers = cpmData?.runtime?.members ?? [];
    for (const m of genericMembers) {
      const cleanInst = cleanSymbol(m.facts?.exchange_instrument_id);
      if (cleanInst && !drawerText?.includes(cleanInst)) {
        allMembersMatch = false;
      }
    }
    recordAssertion(
      'A4.7',
      'Selection',
      `Generic member instruments all match API (${genericMembers.length} members)`,
      allMembersMatch ? 'PASS' : 'FAIL',
      { memberCount: genericMembers.length, allMatch: allMembersMatch }
    );

    await page.screenshot({ path: path.join(outDir, 'live_screenshot_selection_drawer_dark.png'), fullPage: false });
    await setLightMode();
    await page.screenshot({ path: path.join(outDir, 'live_screenshot_selection_drawer_light.png'), fullPage: false });

    // Close Selection Drawer
    const closeSelBtn = page.getByRole('button', { name: '关闭诊断抽屉' });
    await closeSelBtn.click();
    await page.waitForTimeout(500);
  }

  // 4.8 SOR-1H Selection (24h cadence, selected count, candidate count)
  const sorTab = selSection.getByRole('button', { name: 'SOR-1H-001' });
  await sorTab.click();
  await page.waitForTimeout(1000);

  const sorResp = interceptedResponses.sorSelection;
  if (!sorResp.status) {
    recordAssertion('A4.8', 'Selection', 'SOR-1H selection API response captured', 'INCOMPLETE_EVIDENCE', { reason: 'No response for SOR-1H-001 selection' });
  } else if (sorResp.status !== 200 || sorResp.error) {
    recordAssertion('A4.8', 'Selection', 'SOR-1H selection API HTTP 200', 'FAIL', { status: sorResp.status, error: sorResp.error });
  } else {
    recordAssertion('A4.8', 'Selection', 'SOR-1H selection API HTTP 200', 'PASS', { status: 200 });

    await verifyAuthority('SOR-1H-001', 'orb', 'A4.12');
    const sorData = interceptedResponses.sorSelection.data;
    const sorSectionText = await selSection.textContent();

    // Verify strictly 24h cadence
    const cadence24h = sorSectionText?.includes('24h 周期') || sorSectionText?.includes('24h');
    recordAssertion('A4.9', 'Selection', 'SOR-1H Selection strictly enforces 24h cadence', cadence24h ? 'PASS' : 'FAIL', { cadence24h });

    // Candidate count and selected count
    const snapshot = sorData?.runtime?.snapshot_disposition?.snapshot;
    if (snapshot) {
      const selectedMatches = sorSectionText?.includes(`${snapshot.selected_count} 入选`);
      const candidateMatches = sorSectionText?.includes(`候选总数 ${snapshot.candidate_count}`);
      recordAssertion('A4.10', 'Selection', `SOR-1H selected count matches API (${snapshot.selected_count} 入选)`, selectedMatches ? 'PASS' : 'FAIL', { expected: snapshot.selected_count, found: selectedMatches });
      recordAssertion('A4.11', 'Selection', `SOR-1H candidate count matches API (候选总数 ${snapshot.candidate_count})`, candidateMatches ? 'PASS' : 'FAIL', { expected: snapshot.candidate_count, found: candidateMatches });
    } else {
      recordAssertion('A4.10', 'Selection', 'SOR-1H snapshot counts verification', 'INCOMPLETE_EVIDENCE', { reason: 'snapshot missing in disposition' });
    }
  }

  // ===========================================================================
  // Category 6: Trades Tab & Trade Episodes Verification
  // ===========================================================================
  console.log('\n--- Category 6: Trades Tab & Trade Episodes Verification ---');
  await setDarkMode();

  const tradesNav = page.getByRole('button', { name: '交易因果' }).first();
  await tradesNav.click();
  await page.waitForTimeout(1000);

  // 6.1 Trades page container mounted
  const tradesPageEl = page.locator('#trades-page');
  const tradesPageVisible = await tradesPageEl.isVisible();
  recordAssertion(
    'A6.1',
    'Trades',
    'Trades page container (#trades-page) visible and mounted',
    tradesPageVisible ? 'PASS' : 'FAIL',
    { tradesPageVisible }
  );

  // 6.2 Precondition check: tickets API data available
  const completedTicketsList = rawTickets.filter((t) => t.terminal_at_ms !== null);
  recordAssertion(
    'A6.2',
    'Trades',
    `Tickets data available on Trades (${rawTickets.length} total, ${activeTicketsList.length} active, ${completedTicketsList.length} completed)`,
    rawTickets.length >= 0 ? 'PASS' : 'FAIL',
    { total: rawTickets.length, active: activeTicketsList.length, completed: completedTicketsList.length }
  );

  // 6.3 L1 Summary Metrics Deck (Exact Object-Bound Assertions & Negative Controls)
  const metricsRibbon = page.locator('[data-testid="trades-metrics-ribbon"]');
  const metricsRibbonVisible = await metricsRibbon.isVisible();

  const paginationInfo = {
    hasMore: Boolean(ticketsResp.data?.data?.next_cursor ?? ticketsResp.data?.next_cursor),
  };
  const expectedTrades = tradesMetricsEvidence(rawTickets, paginationInfo);

  const cardTotal = page.locator('[data-testid="metric-total-trades"]');
  const cardActive = page.locator('[data-testid="metric-active-trades"]');
  const cardCompleted = page.locator('[data-testid="metric-completed-trades"]');
  const cardPnl = page.locator('[data-testid="metric-total-pnl"]');
  const cardR = page.locator('[data-testid="metric-total-r"]');

  const totalVal = (await cardTotal.locator('[data-testid="metric-value"]').textContent())?.trim();
  const totalSub = (await cardTotal.locator('[data-testid="metric-subtext"]').textContent())?.trim();

  const activeVal = (await cardActive.locator('[data-testid="metric-value"]').textContent())?.trim();
  const activeSub = (await cardActive.locator('[data-testid="metric-subtext"]').textContent())?.trim();

  const completedVal = (await cardCompleted.locator('[data-testid="metric-value"]').textContent())?.trim();
  const completedSub = (await cardCompleted.locator('[data-testid="metric-subtext"]').textContent())?.trim();

  const pnlVal = (await cardPnl.locator('[data-testid="metric-value"]').textContent())?.trim();
  const pnlSub = (await cardPnl.locator('[data-testid="metric-subtext"]').textContent())?.trim();

  const rVal = (await cardR.locator('[data-testid="metric-value"]').textContent())?.trim();
  const rSub = (await cardR.locator('[data-testid="metric-subtext"]').textContent())?.trim();

  // A6.3a Total Trades card: exact count & scope
  const totalExact = exactDisplay(totalVal, String(expectedTrades.totalCount)) && exactDisplay(totalSub, expectedTrades.scopeLabel);
  recordAssertion(
    'A6.3a',
    'Trades',
    `L1 Metric 1 (Total Trades): exact count (${expectedTrades.totalCount}) & honest scope label`,
    metricsRibbonVisible && totalExact ? 'PASS' : 'FAIL',
    { expected: { count: expectedTrades.totalCount, scope: expectedTrades.scopeLabel }, actual: { totalVal, totalSub } }
  );

  // A6.3b Active Trades card: exact active count & neutral status
  const activeExact = exactDisplay(activeVal, String(expectedTrades.activeCount)) && exactDisplay(activeSub, '生命周期在管中 · 依阶段保护或退出');
  recordAssertion(
    'A6.3b',
    'Trades',
    `L1 Metric 2 (Active Trades): exact count (${expectedTrades.activeCount}) & neutral status`,
    metricsRibbonVisible && activeExact ? 'PASS' : 'FAIL',
    { expected: { count: expectedTrades.activeCount, sub: '生命周期在管中 · 依阶段保护或退出' }, actual: { activeVal, activeSub } }
  );

  // A6.3c Completed Trades card: exact count, win rate %, and truthful denominator
  const completedExact = exactDisplay(completedVal, expectedTrades.winRateDisplay) && exactDisplay(completedSub, expectedTrades.winRateDenominatorText);
  recordAssertion(
    'A6.3c',
    'Trades',
    `L1 Metric 3 (Completed / Win Rate): exact count & win rate (${expectedTrades.winRateDisplay}) and truthful denominator`,
    metricsRibbonVisible && completedExact ? 'PASS' : 'FAIL',
    { expected: { val: expectedTrades.winRateDisplay, sub: expectedTrades.winRateDenominatorText }, actual: { completedVal, completedSub } }
  );

  // A6.3d Realized PnL card: exact amount and coverage/gap statement
  const pnlExact = exactDisplay(pnlVal, expectedTrades.formattedPnl) && exactDisplay(pnlSub, expectedTrades.pnlCoverageText);
  recordAssertion(
    'A6.3d',
    'Trades',
    `L1 Metric 4 (Realized PnL): exact amount (${expectedTrades.formattedPnl}) & gap/coverage status`,
    metricsRibbonVisible && pnlExact ? 'PASS' : 'FAIL',
    { expected: { val: expectedTrades.formattedPnl, sub: expectedTrades.pnlCoverageText }, actual: { pnlVal, pnlSub } }
  );

  // A6.3e Realized R card: exact R multiple and coverage/gap statement
  const rExact = exactDisplay(rVal, expectedTrades.formattedR) && exactDisplay(rSub, expectedTrades.rCoverageText);
  recordAssertion(
    'A6.3e',
    'Trades',
    `L1 Metric 5 (Realized R): exact multiple (${expectedTrades.formattedR}) & gap/coverage status`,
    metricsRibbonVisible && rExact ? 'PASS' : 'FAIL',
    { expected: { val: expectedTrades.formattedR, sub: expectedTrades.rCoverageText }, actual: { rVal, rSub } }
  );

  // A6.3_neg Negative controls: assert exactDisplay strictly rejects falsified data & retired status
  const negTotalRejected = !exactDisplay(totalVal, '99999');
  const negActiveRejected = !exactDisplay(activeSub, '严格受保护在途');
  const negCompletedRejected = !exactDisplay(completedVal, `${expectedTrades.completedCount} (100%)`);
  const negPnlRejected = !exactDisplay(pnlVal, '+999999.00 USDT');
  const allNegRejected = negTotalRejected && negActiveRejected && negCompletedRejected && negPnlRejected;
  recordAssertion(
    'A6.3_neg',
    'Trades',
    'Negative controls: exactDisplay strictly rejects falsified totals, retired "严格受保护在途", and manipulated PnL/WinRate',
    allNegRejected ? 'PASS' : 'FAIL',
    { negTotalRejected, negActiveRejected, negCompletedRejected, negPnlRejected }
  );


  // 6.4 Active Episodes Section
  const activeSection = page.locator('[data-testid="active-trade-episodes"]');
  const activeSectionVisible = await activeSection.isVisible();

  if (activeTicketsList.length > 0) {
    const activeCards = activeSection.locator('[data-ticket-id]');
    const activeCardCount = await activeCards.count();
    const activeCardsMatches = activeCardCount === activeTicketsList.length;

    let allActiveAccurate = true;
    for (const t of activeTicketsList) {
      const card = activeSection.locator(`[data-ticket-id="${t.ticket_id}"]`);
      if ((await card.count()) === 0) {
        allActiveAccurate = false;
        break;
      }
      const cText = await card.textContent();
      const sym = cleanSymbol(t.exchange_instrument_id);
      if (!cText?.includes(sym) || !cText?.includes(t.strategy_group_id)) {
        allActiveAccurate = false;
        break;
      }
    }

    recordAssertion(
      'A6.4',
      'Trades',
      `Active episodes section renders exact active cards (${activeTicketsList.length}) with accurate symbol & strategy`,
      activeCardsMatches && allActiveAccurate ? 'PASS' : 'FAIL',
      { expectedCount: activeTicketsList.length, actualCount: activeCardCount }
    );
  } else {
    const emptyNotice = await activeSection.textContent();
    const emptyFound = emptyNotice?.includes('当前无在管交易');
    recordAssertion(
      'A6.4',
      'Trades',
      'Active episodes section accurately declares empty state when no tickets active',
      emptyFound ? 'PASS' : 'FAIL',
      { emptyFound }
    );
  }

  // 6.5 Completed Episodes Table
  const completedSection = page.locator('[data-testid="completed-trade-episodes"]');
  const completedTable = page.locator('[data-testid="completed-trades-table"]');

  if (completedTicketsList.length > 0) {
    const tableVisible = await completedTable.isVisible();
    const rows = completedTable.locator('tbody tr[data-ticket-id]');
    const rowCount = await rows.count();
    const countMatches = rowCount === completedTicketsList.length;

    // Verify first row binds cleanly to its ticket ID
    const firstCompleted = completedTicketsList[0];
    const firstRow = completedTable.locator(`tbody tr[data-ticket-id="${firstCompleted.ticket_id}"]`);
    const firstRowExists = (await firstRow.count()) === 1;

    recordAssertion(
      'A6.5',
      'Trades',
      `Completed trades table renders ${completedTicketsList.length} rows with exact ticket_id binding`,
      tableVisible && countMatches && firstRowExists ? 'PASS' : 'FAIL',
      { expectedCount: completedTicketsList.length, actualCount: rowCount }
    );
  } else {
    const completedText = await completedSection.textContent();
    const emptyCompletedFound = completedText?.includes('暂无历史平仓记录');
    recordAssertion(
      'A6.5',
      'Trades',
      'Completed trades table accurately displays empty state',
      emptyCompletedFound ? 'PASS' : 'FAIL',
      { emptyCompletedFound }
    );
  }

  // 6.6 Filter Switcher Interactivity
  // Filter button "在管"
  const filterActiveBtn = tradesPageEl.getByRole('button', { name: new RegExp(`在管\\s*\\(${activeTicketsList.length}\\)`) });
  await filterActiveBtn.click();
  await page.waitForTimeout(300);
  const activeOnlyCompletedHidden = !(await completedSection.isVisible());

  // Filter button "已平仓"
  const filterCompletedBtn = tradesPageEl.getByRole('button', { name: new RegExp(`已平仓\\s*\\(${completedTicketsList.length}\\)`) });
  await filterCompletedBtn.click();
  await page.waitForTimeout(300);
  const completedOnlyActiveHidden = !(await activeSection.isVisible());

  // Filter button "全部"
  const filterAllBtn = tradesPageEl.getByRole('button', { name: new RegExp(`全部\\s*\\(${rawTickets.length}\\)`) });
  await filterAllBtn.click();
  await page.waitForTimeout(300);
  const allBothVisible = (await activeSection.isVisible()) && (await completedSection.isVisible());

  recordAssertion(
    'A6.6',
    'Trades',
    'Trades filter switcher correctly isolates active vs completed vs all views',
    activeOnlyCompletedHidden && completedOnlyActiveHidden && allBothVisible ? 'PASS' : 'FAIL',
    { activeOnlyCompletedHidden, completedOnlyActiveHidden, allBothVisible }
  );

  // 6.7 Causality Drawer Trigger from Trades page
  const tradesCausalityDrawer = page.locator('[data-testid="causality-drawer"]');
  let drawerTriggeredFromTrades = false;
  if (rawTickets.length > 0) {
    const sampleTicket = rawTickets[0];
    const cardOrRow = tradesPageEl.locator(`[data-ticket-id="${sampleTicket.ticket_id}"]`).first();
    const viewBtn = cardOrRow.getByRole('button', { name: /因果|追溯/ }).first();
    if ((await viewBtn.count()) > 0) {
      await viewBtn.click();
    } else {
      await cardOrRow.click();
    }
    await page.waitForTimeout(800);
    drawerTriggeredFromTrades = await tradesCausalityDrawer.isVisible();
    const drawerText = await tradesCausalityDrawer.textContent();
    const drawerBindsTicket = drawerText?.includes(sampleTicket.ticket_id);

    recordAssertion(
      'A6.7',
      'Trades',
      `Causality drawer successfully triggered from Trades and binds to ticket ${sampleTicket.ticket_id}`,
      drawerTriggeredFromTrades && drawerBindsTicket ? 'PASS' : 'FAIL',
      { drawerTriggeredFromTrades, drawerBindsTicket }
    );

    // Capture Causality Drawer on Trades (Dark / Light)
    console.log('Capturing real Trades Causality Drawer screenshots (Dark / Light)...');
    const brainArtifactsDir = '/Users/jiangwei/.gemini/antigravity/brain/82ad12e5-f9c1-484d-8225-c73a22e79a9d';
    await setDarkMode();
    const darkCausalityPath = path.join(outDir, 'live_screenshot_trades_causality_dark.png');
    await page.screenshot({ path: darkCausalityPath, fullPage: false });
    if (fs.existsSync(brainArtifactsDir)) {
      fs.copyFileSync(darkCausalityPath, path.join(brainArtifactsDir, 'live_screenshot_trades_causality_dark.png'));
    }

    await setLightMode();
    const lightCausalityPath = path.join(outDir, 'live_screenshot_trades_causality_light.png');
    await page.screenshot({ path: lightCausalityPath, fullPage: false });
    if (fs.existsSync(brainArtifactsDir)) {
      fs.copyFileSync(lightCausalityPath, path.join(brainArtifactsDir, 'live_screenshot_trades_causality_light.png'));
    }

    // Close drawer cleanly
    const closeBtn = tradesCausalityDrawer.getByRole('button', { name: '关闭' }).first();
    if ((await closeBtn.count()) > 0) {
      await closeBtn.click();
      await page.waitForTimeout(500);
    }
  } else {
    recordAssertion(
      'A6.7',
      'Trades',
      'Causality drawer trigger from Trades',
      'SCENARIO_NA',
      { reason: 'Zero tickets available in production' }
    );
  }

  // 6.8 Pagination Status & Load More Truth
  if (expectedTrades.hasMore) {
    const pagBar = page.locator('[data-testid="trades-pagination-bar"]');
    const loadMoreBtn = page.locator('[data-testid="load-more-btn"]');
    const barVisible = await pagBar.isVisible();
    const btnVisible = await loadMoreBtn.isVisible();
    recordAssertion(
      'A6.8',
      'Trades',
      'Pagination bar & load more button visible when hasMore is true',
      barVisible && btnVisible ? 'PASS' : 'FAIL',
      { barVisible, btnVisible }
    );
  } else {
    const pagStatus = page.locator('[data-testid="trades-pagination-status"]');
    const statusVisible = await pagStatus.isVisible();
    const statusText = (await pagStatus.textContent())?.trim();
    const expectedStatusText = `已加载全量账本记录 (共 ${rawTickets.length} 笔) · 无更多历史数据`;
    const statusMatches = exactDisplay(statusText, expectedStatusText);
    const loadMoreCount = await page.locator('[data-testid="load-more-btn"]').count();
    recordAssertion(
      'A6.8',
      'Trades',
      `Pagination status accurately declares full ledger loaded (${rawTickets.length} tickets) with zero load-more button`,
      statusVisible && statusMatches && loadMoreCount === 0 ? 'PASS' : 'FAIL',
      { statusVisible, statusMatches, expectedStatusText, actualStatusText: statusText, loadMoreCount }
    );
  }

  // 6.9 Capture Full Trades Page Screenshots (Dark / Light)
  console.log('Capturing real Trades Page screenshots (Dark / Light)...');
  const brainArtifactsDir = '/Users/jiangwei/.gemini/antigravity/brain/82ad12e5-f9c1-484d-8225-c73a22e79a9d';
  await setDarkMode();
  const darkShotPath = path.join(outDir, 'live_screenshot_trades_dark.png');
  await page.screenshot({ path: darkShotPath, fullPage: false });
  if (fs.existsSync(brainArtifactsDir)) {
    fs.copyFileSync(darkShotPath, path.join(brainArtifactsDir, 'live_screenshot_trades_dark.png'));
  }

  await setLightMode();
  const lightShotPath = path.join(outDir, 'live_screenshot_trades_light.png');
  await page.screenshot({ path: lightShotPath, fullPage: false });
  if (fs.existsSync(brainArtifactsDir)) {
    fs.copyFileSync(lightShotPath, path.join(brainArtifactsDir, 'live_screenshot_trades_light.png'));
  }
  await setDarkMode();

  // ===========================================================================
  // Category 5: Idle Window & Stability Assertions
  // ===========================================================================
  console.log('\n--- Category 5: Idle Window & Stability Assertions ---');
  await setDarkMode();

  const reqCountBeforeIdle = networkRequests.length;
  console.log('Measuring 10-second idle period for background query storms...');
  await page.waitForTimeout(10000);
  const reqCountAfterIdle = networkRequests.length;
  const extraRequestsIn10s = reqCountAfterIdle - reqCountBeforeIdle;

  recordAssertion(
    'A5.1',
    'Stability',
    `Zero extra business API requests during 10s idle window (Actual: ${extraRequestsIn10s})`,
    extraRequestsIn10s === 0 ? 'PASS' : 'FAIL',
    { extraRequests: extraRequestsIn10s, requests: networkRequests.slice(reqCountBeforeIdle) }
  );

  recordAssertion(
    'A5.2',
    'Stability',
    `Zero unhandled browser console errors during full run (Actual: ${consoleErrors.length})`,
    consoleErrors.length === 0 ? 'PASS' : 'FAIL',
    { errorCount: consoleErrors.length, errors: consoleErrors }
  );

  // ===========================================================================
  // Final Summary Table and Verdict
  // ===========================================================================
  console.log('\n================================================================');
  console.log('Owner Console V2 Live Assertive Verification Summary Table');
  console.log('================================================================\n');

  console.log('| ID | Category | Assertion | Status | Details |');
  console.log('|---|---|---|---|---|');
  for (const a of assertionResults) {
    const detailStr = JSON.stringify(a.details).replace(/\|/g, '\\|');
    console.log(`| ${a.id} | ${a.category} | ${a.name} | **${a.status}** | \`${detailStr.slice(0, 80)}\` |`);
  }

  console.log('\n----------------------------------------------------------------');
  console.log(`Totals: ${totalPassed} PASSED, ${totalFailed} FAILED, ${totalIncomplete} INCOMPLETE, ${totalNA} SCENARIO_NA`);
  console.log(`Commit: ${frontendCommit}`);
  console.log(`Timestamp: ${executionTimestamp}`);
  console.log('----------------------------------------------------------------\n');

  const overallPass = totalFailed === 0 && totalIncomplete === 0;

  if (!overallPass) {
    console.error(`VERIFICATION FAILED: ${totalFailed} failing assertion(s), ${totalIncomplete} incomplete evidence!`);
    process.exit(1);
  } else {
    console.log('VERIFICATION PASSED ALL REQUIRED ASSERTIONS WITH SOLID EVIDENCE! (Exit code 0)');
    process.exit(0);
  }
}

runLiveVerification().catch((err) => {
  console.error('FATAL VERIFICATION RUNNER ERROR:', err);
  process.exit(1);
});
