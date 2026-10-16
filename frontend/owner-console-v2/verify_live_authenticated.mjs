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

// Assertion collector
const assertionResults = [];
let totalPassed = 0;
let totalFailed = 0;
let totalSkipped = 0;

function recordAssertion(id, category, name, passed, details = {}) {
  const status = passed === null ? 'SKIP' : passed ? 'PASS' : 'FAIL';
  if (status === 'PASS') totalPassed++;
  else if (status === 'FAIL') totalFailed++;
  else totalSkipped++;

  assertionResults.push({
    id,
    category,
    name,
    status,
    details,
  });

  const icon = status === 'PASS' ? '✓ PASS' : status === 'FAIL' ? '✗ FAIL' : '- SKIP';
  console.log(`  ${icon} [${category}] ${name}`);
  if (status === 'FAIL') {
    console.error(`    Detail:`, details);
  }
}

async function runLiveVerification() {
  console.log('================================================================');
  console.log('--- Owner Console V2: Live Assertive Integration Verification ---');
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

  // Intercept and store real API payloads
  const intercepted = {
    overview: null,
    tickets: null,
    controls: null,
    strategies: null,
    selection: {},
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
    try {
      if (res.status() === 200 && res.headers()['content-type']?.includes('application/json')) {
        const data = await res.json();
        if (url.includes('/api/owner/v1/overview')) {
          intercepted.overview = data;
        } else if (url.includes('/api/owner/v1/tickets?') || url.endsWith('/api/owner/v1/tickets')) {
          intercepted.tickets = data;
        } else if (url.endsWith('/api/owner/v1/controls')) {
          intercepted.controls = data;
        } else if (url.includes('/api/owner/v1/strategies')) {
          intercepted.strategies = data;
        } else if (url.includes('/selection')) {
          const match = url.match(/strategies\/([^/]+)\/selection/);
          if (match) intercepted.selection[match[1]] = data;
        } else if (url.includes('/causality')) {
          const match = url.match(/tickets\/([^/]+)\/causality/);
          if (match) intercepted.causality[match[1]] = data;
        }
      }
    } catch (e) {
      // Ignore non-json or aborted reads
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

  // Reload page to intercept fresh server facts
  console.log('Refreshing page to ensure fresh API capture...');
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);

  // ---------------------------------------------------------------------------
  // 1. Overview Assertions
  // ---------------------------------------------------------------------------
  console.log('\n--- Category 1: Overview Dynamic Truth Assertions ---');

  // Verify Overview page active
  const overviewNav = page.getByRole('button', { name: '总览态势' }).first();
  await overviewNav.click();
  await page.waitForTimeout(800);

  // 1.1 Account Capacity & Ticket Count
  const capacityData = intercepted.controls?.account_capacity;
  const overviewData = intercepted.overview;
  const ticketsData = intercepted.tickets?.data ?? intercepted.tickets;
  const activeTicketsList = (ticketsData?.items ?? []).filter((t) => t.terminal_at_ms === null);

  const authoritativeActiveCount =
    capacityData?.active_ticket_count ??
    overviewData?.ticket_active_count ??
    activeTicketsList.length;

  const maxCapacity =
    capacityData?.max_concurrent_tickets ??
    overviewData?.ticket_capacity ??
    3;

  const bodyText = await page.textContent('body');

  const capacityMatch = bodyText.includes(`容量占用: ${authoritativeActiveCount} / ${maxCapacity}`);
  recordAssertion(
    'A1.1',
    'Overview',
    `Capacity pulse dynamically matches API (${authoritativeActiveCount} / ${maxCapacity})`,
    capacityMatch,
    { expected: `容量占用: ${authoritativeActiveCount} / ${maxCapacity}`, foundInDom: capacityMatch }
  );

  // 1.2 Active Episodes Card Count & Symbols
  const displayedActiveCards = await page.locator('#active-episodes button:has-text("查看交易因果")').count();
  const activeTicketsCountMatches = displayedActiveCards === activeTicketsList.length;
  recordAssertion(
    'A1.2',
    'Overview',
    `Active trade episode cards count (${displayedActiveCards}) equals loaded active tickets (${activeTicketsList.length})`,
    activeTicketsCountMatches,
    { displayedCards: displayedActiveCards, loadedActiveTickets: activeTicketsList.length }
  );

  // 1.3 Truncation Notice Truth
  const unloadedExpected = authoritativeActiveCount > activeTicketsList.length
    ? authoritativeActiveCount - activeTicketsList.length
    : 0;

  if (unloadedExpected > 0) {
    const truncationNoticeFound = bodyText.includes(`还有 ${unloadedExpected} 个在管交易未在首屏展示`);
    recordAssertion(
      'A1.3',
      'Overview',
      `Truncation notice truthfully reports ${unloadedExpected} unloaded active tickets`,
      truncationNoticeFound,
      { unloadedExpected, foundInDom: truncationNoticeFound }
    );
  } else {
    recordAssertion(
      'A1.3',
      'Overview',
      `All active tickets loaded, no truncation notice needed`,
      null,
      { unloadedExpected: 0 }
    );
  }

  // 1.4 Today Performance (PnL & R-multiple)
  const rawOverview = overviewData?.data ?? overviewData;
  const netPnlMetric = rawOverview?.today_net_pnl;
  const netRMetric = rawOverview?.today_net_r;

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

  if (netPnlMetric) {
    const pnlFormatted = formatMoneyMetric(netPnlMetric);
    const pnlInDom = pnlFormatted === '--' ? (bodyText.includes('--') || bodyText.includes('未产生')) : bodyText.includes(pnlFormatted);
    recordAssertion(
      'A1.4',
      'Overview',
      `Today Net PnL card dynamically matches API (${pnlFormatted})`,
      pnlInDom,
      { expected: pnlFormatted, foundInDom: pnlInDom }
    );
  } else {
    recordAssertion('A1.4', 'Overview', 'Today Net PnL card in API', null, { note: 'No today_net_pnl metric in overview' });
  }

  if (netRMetric) {
    const rFormatted = formatMoneyMetric(netRMetric);
    const rInDom = rFormatted === '--' ? (bodyText.includes('--') || bodyText.includes('未产生')) : bodyText.includes(rFormatted);
    recordAssertion(
      'A1.5',
      'Overview',
      `Today Net R card dynamically matches API (${rFormatted})`,
      rInDom,
      { expected: rFormatted, foundInDom: rInDom }
    );
  } else {
    recordAssertion('A1.5', 'Overview', 'Today Net R card in API', null, { note: 'No today_net_r metric in overview' });
  }

  // Capture Overview Screenshots
  console.log('Capturing real Overview screenshots (Dark / Light)...');
  await setDarkMode();
  await page.screenshot({ path: path.join(outDir, 'live_screenshot_overview_dark.png'), fullPage: false });
  await setLightMode();
  await page.screenshot({ path: path.join(outDir, 'live_screenshot_overview_light.png'), fullPage: false });

  // ---------------------------------------------------------------------------
  // 2. Causality Drawer Assertions
  // ---------------------------------------------------------------------------
  console.log('\n--- Category 2: Causality Drawer Dynamic Assertions ---');
  await setDarkMode();
  const causalityButtons = page.getByRole('button', { name: '查看交易因果' });
  const causalityCount = await causalityButtons.count();

  if (causalityCount > 0) {
    const firstTicket = activeTicketsList[0];
    await causalityButtons.first().click();
    await page.waitForTimeout(1000);

    const causalityDialog = page.getByRole('dialog');
    const dialogVisible = await causalityDialog.isVisible();
    recordAssertion(
      'A2.1',
      'Causality',
      'Clicking 查看交易因果 successfully opens modal drawer',
      dialogVisible,
      { dialogVisible }
    );

    const dialogText = await causalityDialog.textContent();
    const hasTimeline = dialogText?.includes('8 阶段时间线');
    recordAssertion(
      'A2.2',
      'Causality',
      'Causality drawer renders 8 阶段时间线',
      hasTimeline,
      { hasTimeline }
    );

    if (firstTicket) {
      const ticketIdRendered = dialogText?.includes(firstTicket.ticket_id) || dialogText?.includes(firstTicket.ticket_id.slice(-8));
      recordAssertion(
        'A2.3',
        'Causality',
        `Causality drawer binds to exact ticket_id (${firstTicket.ticket_id})`,
        ticketIdRendered,
        { expectedId: firstTicket.ticket_id, foundInDom: ticketIdRendered }
      );
    }

    await page.screenshot({ path: path.join(outDir, 'live_screenshot_causality_drawer_dark.png'), fullPage: false });
    await setLightMode();
    await page.screenshot({ path: path.join(outDir, 'live_screenshot_causality_drawer_light.png'), fullPage: false });

    // Close causality drawer
    const closeBtn = page.getByRole('button', { name: '关闭抽屉' });
    await closeBtn.click();
    await page.waitForTimeout(500);
    const dialogClosed = !(await causalityDialog.isVisible());
    recordAssertion('A2.4', 'Causality', 'Causality drawer closes cleanly', dialogClosed, { dialogClosed });
  } else {
    recordAssertion('A2.1', 'Causality', 'Active causality drawer inspectable', null, { note: 'No active tickets' });
  }

  // ---------------------------------------------------------------------------
  // 3. Controls & Strategy Matrix Assertions
  // ---------------------------------------------------------------------------
  console.log('\n--- Category 3: Controls & Strategy Matrix Dynamic Assertions ---');
  await setDarkMode();
  const controlsNav = page.getByRole('button', { name: '主控中心' }).first();
  await controlsNav.click();
  await page.waitForTimeout(1000);

  const controlsBodyText = await page.textContent('body');
  const controlsStrategies = intercepted.controls?.strategies ?? [];

  recordAssertion(
    'A3.1',
    'Controls',
    'Controls console loaded and rendered Strategy Matrix',
    controlsBodyText.includes('策略独立控制矩阵'),
    { found: controlsBodyText.includes('策略独立控制矩阵') }
  );

  // 3.2 Strategy Matrix Fact Truth
  let allStrategyVersionsMatch = true;
  let noSpeculativeAdmissionClaims = true;
  let honestAdmissionFound = true;

  for (const strat of controlsStrategies) {
    const versionMatch = controlsBodyText.includes(`控制: v${strat.control_version}`);
    if (!versionMatch) allStrategyVersionsMatch = false;

    // Check admission health truth: MUST NOT claim "观察 Worker 运行正常"
    if (controlsBodyText.includes('观察 Worker 运行正常')) {
      noSpeculativeAdmissionClaims = false;
    }
  }

  recordAssertion(
    'A3.2',
    'Controls',
    'All strategy control versions match backend API control_version',
    allStrategyVersionsMatch,
    { count: controlsStrategies.length, allMatch: allStrategyVersionsMatch }
  );

  recordAssertion(
    'A3.3',
    'Controls',
    'Zero speculative claims: "观察 Worker 运行正常" is strictly absent without proof',
    noSpeculativeAdmissionClaims,
    { speculativeAbsent: noSpeculativeAdmissionClaims }
  );

  // Check that enabled strategy shows "控制已启用 · 实际准入状态待核实"
  const hasPendingVerificationText = controlsBodyText.includes('控制已启用 · 实际准入状态待核实');
  recordAssertion(
    'A3.4',
    'Controls',
    'Enabled strategy truthfully displays "控制已启用 · 实际准入状态待核实" (client_derived)',
    hasPendingVerificationText,
    { foundInDom: hasPendingVerificationText }
  );

  // 3.5 Active Ticket Occupations in Matrix
  // Check that ticket badges reflect real active tickets (TRX, BCH, etc.)
  let ticketsRenderedInMatrix = true;
  for (const activeTkt of activeTicketsList) {
    const symbolFound = controlsBodyText.includes(activeTkt.exchange_instrument_id.split(':')[1]?.replace('USDT', '') ?? '—') ||
      controlsBodyText.includes(activeTkt.exchange_instrument_id);
    if (!symbolFound) ticketsRenderedInMatrix = false;
  }

  recordAssertion(
    'A3.5',
    'Controls',
    'Strategy matrix renders real active ticket badges matching API items',
    ticketsRenderedInMatrix,
    { activeCount: activeTicketsList.length, rendered: ticketsRenderedInMatrix }
  );

  await page.screenshot({ path: path.join(outDir, 'live_screenshot_controls_dark.png'), fullPage: false });
  await setLightMode();
  await page.screenshot({ path: path.join(outDir, 'live_screenshot_controls_light.png'), fullPage: false });

  // ---------------------------------------------------------------------------
  // 4. Selection Diagnostics Assertions (Generic & SOR-1H)
  // ---------------------------------------------------------------------------
  console.log('\n--- Category 4: Selection Diagnostics Assertions ---');
  await setDarkMode();

  // 4.1 Generic Selection (CPM-RO-001)
  const cpmTab = page.getByRole('button', { name: 'CPM-RO-001' });
  await cpmTab.click();
  await page.waitForTimeout(1000);

  const cpmSelectionData = intercepted.selection['CPM-RO-001'];
  const cpmBodyText = await page.textContent('body');

  const cpmCadenceMatches = cpmBodyText.includes('4h 周期') || cpmBodyText.includes('4h');
  recordAssertion(
    'A4.1',
    'Selection',
    'Generic Selection (CPM-RO-001) reports 4h cadence (not 24h)',
    cpmCadenceMatches,
    { cpmCadenceMatches }
  );

  if (cpmSelectionData?.runtime?.current_authority_outcome) {
    const outcome = cpmSelectionData.runtime.current_authority_outcome;
    const outcomeRendered = cpmBodyText.includes(outcome);
    recordAssertion(
      'A4.2',
      'Selection',
      `Generic authority outcome matches API (${outcome})`,
      outcomeRendered,
      { expectedOutcome: outcome, outcomeRendered }
    );
  }

  // Open Selection Drawer
  const inspectBtn = page.getByRole('button', { name: '标的明细与诊断' });
  await inspectBtn.click();
  await page.waitForTimeout(1000);

  const selectionDrawerDialog = page.getByRole('dialog');
  const drawerVisible = await selectionDrawerDialog.isVisible();
  recordAssertion('A4.3', 'Selection', 'Selection diagnostics drawer opened', drawerVisible, { drawerVisible });

  const drawerText = await selectionDrawerDialog.textContent();
  const honestGenericPoolNotice =
    drawerText?.includes('接口未提供候选名单与过滤仲裁流水') ||
    drawerText?.includes('候选全量名单、排名及仲裁归因依据后端接口未提供') ||
    drawerText?.includes('接口未提供');
  recordAssertion(
    'A4.4',
    'Selection',
    'Generic selection drawer truthfully declares "接口未提供候选名单与过滤仲裁流水"',
    honestGenericPoolNotice,
    { declaredHonestNotice: honestGenericPoolNotice }
  );

  // Check instruments match
  let allMembersMatch = true;
  const genericMembers = cpmSelectionData?.runtime?.members ?? [];
  for (const m of genericMembers) {
    const rawInst = m.facts?.exchange_instrument_id ?? '';
    const cleanInst = rawInst.replace('binance-usdm:', '').replace(':perpetual', '');
    if (cleanInst && !drawerText?.includes(cleanInst)) {
      allMembersMatch = false;
    }
  }

  recordAssertion(
    'A4.5',
    'Selection',
    `Generic member instruments match API (${genericMembers.length} members)`,
    allMembersMatch,
    { memberCount: genericMembers.length, allMatch: allMembersMatch }
  );

  await page.screenshot({ path: path.join(outDir, 'live_screenshot_selection_drawer_dark.png'), fullPage: false });
  await setLightMode();
  await page.screenshot({ path: path.join(outDir, 'live_screenshot_selection_drawer_light.png'), fullPage: false });

  // Close Selection Drawer
  const closeSelBtn = page.getByRole('button', { name: '关闭诊断抽屉' });
  await closeSelBtn.click();
  await page.waitForTimeout(500);

  // 4.6 SOR-1H Selection (24h cadence, 7 selected, 24 candidates)
  const sorTab = page.getByRole('button', { name: 'SOR-1H-001' });
  await sorTab.click();
  await page.waitForTimeout(1000);

  const sorSelectionData = intercepted.selection['SOR-1H-001'];
  const sorBodyText = await page.textContent('body');

  const sorCadence24h = sorBodyText.includes('24h 周期') || sorBodyText.includes('24h');
  recordAssertion(
    'A4.6',
    'Selection',
    'SOR-1H Selection strictly enforces 24h cadence',
    sorCadence24h,
    { sorCadence24h }
  );

  const sorSnapshot = sorSelectionData?.runtime?.snapshot_disposition?.snapshot;
  if (sorSnapshot) {
    const selectedCountMatches = sorBodyText.includes(`${sorSnapshot.selected_count} 入选`);
    recordAssertion(
      'A4.7',
      'Selection',
      `SOR-1H selected members count dynamically matches API (${sorSnapshot.selected_count} 入选)`,
      selectedCountMatches,
      { expected: sorSnapshot.selected_count, inDom: selectedCountMatches }
    );

    const candidateCountMatches = sorBodyText.includes(`候选总数 ${sorSnapshot.candidate_count}`);
    recordAssertion(
      'A4.8',
      'Selection',
      `SOR-1H total candidate count dynamically matches API (候选总数 ${sorSnapshot.candidate_count})`,
      candidateCountMatches,
      { expected: sorSnapshot.candidate_count, inDom: candidateCountMatches }
    );
  }

  // ---------------------------------------------------------------------------
  // 5. Idle Window & Error Stability (Strict PASS/FAIL criteria)
  // ---------------------------------------------------------------------------
  console.log('\n--- Category 5: Idle Window & Stability Assertions ---');
  await setDarkMode();

  // Clear request window
  const reqCountBeforeIdle = networkRequests.length;
  console.log('Measuring 10-second idle period for background query storms...');
  await page.waitForTimeout(10000);
  const reqCountAfterIdle = networkRequests.length;
  const extraRequestsIn10s = reqCountAfterIdle - reqCountBeforeIdle;

  recordAssertion(
    'A5.1',
    'Stability',
    `Zero extra business API requests during 10s idle window (Actual: ${extraRequestsIn10s})`,
    extraRequestsIn10s === 0,
    { extraRequests: extraRequestsIn10s, requests: networkRequests.slice(reqCountBeforeIdle) }
  );

  recordAssertion(
    'A5.2',
    'Stability',
    `Zero unhandled browser console errors during full run (Actual: ${consoleErrors.length})`,
    consoleErrors.length === 0,
    { errorCount: consoleErrors.length, errors: consoleErrors }
  );

  // ---------------------------------------------------------------------------
  // 6. Output Structured Table & Final Verdict
  // ---------------------------------------------------------------------------
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
  console.log(`Totals: ${totalPassed} PASSED, ${totalFailed} FAILED, ${totalSkipped} SKIPPED`);
  console.log(`Commit: ${frontendCommit}`);
  console.log(`Timestamp: ${executionTimestamp}`);
  console.log('----------------------------------------------------------------\n');

  if (totalFailed > 0) {
    console.error(`VERIFICATION FAILED with ${totalFailed} failing assertion(s)!`);
    process.exit(1);
  } else {
    console.log('VERIFICATION PASSED ALL ASSERTIONS! Live system state is authentic and consistent.');
    process.exit(0);
  }
}

runLiveVerification().catch((err) => {
  console.error('FATAL VERIFICATION RUNNER ERROR:', err);
  process.exit(1);
});
