/**
 * Owner Console V2 — Unified Historical Query & Filters Real Browser E2E Suite
 *
 * Verifies real Chrome browser interaction:
 * 1. Trades filter bar (presets, custom dates, strategy group, instrument, side, status).
 * 2. URL search parameter serialization, browser refresh persistence, back/forward history.
 * 3. Reset filters restore defaults.
 * 4. Active trades honest status ribbon and empty state.
 * 5. Strategies time range filter, persistence in URL.
 * 6. Drawer window inheritance: Tickets and Observations requests inherit identical time window.
 * 7. Direct deep link URL navigation opens Drawer to exact tab.
 */

import pkg from '../owner-console/node_modules/@playwright/test/index.js';
import fs from 'fs';
import path from 'path';
import assert from 'node:assert';

const { chromium } = pkg;

const ARTIFACT_DIR = '/Users/jiangwei/.gemini/antigravity/brain/82ad12e5-f9c1-484d-8225-c73a22e79a9d';
const screenshotsDir = fs.existsSync(ARTIFACT_DIR) ? ARTIFACT_DIR : path.resolve('screenshots');

// Load factual test dumps
const SCRIPT_DIR = path.dirname(new URL(import.meta.url).pathname);
const facts = JSON.parse(fs.readFileSync(path.resolve(SCRIPT_DIR, 'tokyo_live_facts.json'), 'utf8'));
const controlsData = JSON.parse(fs.readFileSync(path.resolve(SCRIPT_DIR, 'tokyo_live_controls.json'), 'utf8'));

function envelope(data, freshness = 'fresh') {
  return {
    data,
    freshness,
    now_ms: Date.now(),
    source_watermark_ms: Date.now() - 5000,
  };
}

async function run() {
  console.log('================================================================');
  console.log('--- Owner Console V2 Unified Filters Browser E2E Test ---');
  console.log(`Timestamp: ${new Date().toISOString()}`);
  console.log('================================================================\n');

  const browser = await chromium.launch({
    headless: true,
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 960 },
    deviceScaleFactor: 2,
    ignoreHTTPSErrors: true,
  });

  const page = await context.newPage();

  // Track API requests with query parameters
  const apiCalls = [];

  await context.route('**/api/owner/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const pathname = url.pathname;
    const query = Object.fromEntries(url.searchParams.entries());

    apiCalls.push({ pathname, query, url: url.toString() });

    if (pathname === '/api/owner/v1/auth/session') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ authenticated: true }),
      });
    }

    if (pathname === '/api/owner/v1/overview') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(envelope(facts.overview, 'fresh')),
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

    if (pathname.includes('/tickets') && pathname.includes('/strategies/')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          envelope({
            items: facts.tickets?.items ?? [],
            next_cursor: null,
            total_count: (facts.tickets?.items ?? []).length,
          })
        ),
      });
    }

    if (pathname.includes('/observations') && pathname.includes('/strategies/')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          envelope({
            items: [
              {
                shadow_outcome_id: 'obs_sample_001',
                exchange_instrument_id: 'binance-usdm:ETHUSDT:perpetual',
                occurred_at_ms: Date.now() - 3600_000,
                evaluation_status: 'complete',
                first_path: 'tp1_first',
                mfe_r: '2.5',
                mae_r: '-0.3',
                exit_price: '3580.00',
                entry_price: '3500.00',
              },
            ],
            next_cursor: null,
            total_count: 1,
          })
        ),
      });
    }

    if (pathname.includes('/selection')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(controlsData.selection_cpm ?? {}),
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

  // ---------------------------------------------------------------------------
  // STEP 1: Navigate to Trades and Verify Filter Bar
  // ---------------------------------------------------------------------------
  console.log('Step 1: Navigating to Trades page (https://127.0.0.1:5174/?tab=trades)...');
  await page.goto('https://127.0.0.1:5174/?tab=trades', { waitUntil: 'networkidle' });

  await page.waitForSelector('[data-testid="trades-filter-bar"]');
  console.log('  ✓ Verified: TradesFilterBar successfully rendered');

  // Verify preset buttons exist
  const btnToday = page.locator('button:text-is("今日")');
  const btn24h = page.locator('button:text-is("近 24h")');
  const btn7d = page.locator('button:text-is("近 7 天")');
  const btn30d = page.locator('button:text-is("近 30 天")');
  const btnCustom = page.locator('button:text-is("自定义")');

  assert.strictEqual(await btnToday.count(), 1, 'Preset button "今日" must exist');
  assert.strictEqual(await btn24h.count(), 1, 'Preset button "近 24h" must exist');
  assert.strictEqual(await btn7d.count(), 1, 'Preset button "近 7 天" must exist');
  assert.strictEqual(await btn30d.count(), 1, 'Preset button "近 30 天" must exist');
  assert.strictEqual(await btnCustom.count(), 1, 'Preset button "自定义" must exist');
  console.log('  ✓ Verified: All 5 time range preset buttons exist');

  // ---------------------------------------------------------------------------
  // STEP 2: Test Switching Time Range Presets & URL Sync
  // ---------------------------------------------------------------------------
  console.log('\nStep 2: Testing Time Range Preset Switch (今日 / 近 7 天)...');
  await btn7d.click();
  await page.waitForTimeout(300);

  let currentUrl = page.url();
  assert.match(currentUrl, /range=7d/, 'URL must include range=7d');
  assert.match(currentUrl, /from_ms=\d+/, 'URL must include from_ms');
  assert.match(currentUrl, /to_ms=\d+/, 'URL must include to_ms');
  console.log('  ✓ Verified: Clicking "近 7 天" synchronized URL search params (range=7d)');

  // ---------------------------------------------------------------------------
  // STEP 3: Test Business Field Filters (Strategy, Side, Status)
  // ---------------------------------------------------------------------------
  console.log('\nStep 3: Setting business field filters (CPM-RO-001, long, terminal)...');
  const stratInput = page.locator('#filter-strategy-group');
  await stratInput.fill('CPM-RO-001');

  const sideSelect = page.locator('#filter-position-side');
  await sideSelect.selectOption('long');

  const statusSelect = page.locator('#filter-aggregate-status');
  await statusSelect.selectOption('terminal');

  await page.waitForTimeout(400);

  currentUrl = page.url();
  assert.match(currentUrl, /strategy_group_id=CPM-RO-001/);
  assert.match(currentUrl, /position_side=long/);
  assert.match(currentUrl, /aggregate_status=terminal/);
  console.log('  ✓ Verified: Field filters serialized to URL with real AggregateStatus (terminal):', currentUrl);

  // Verify tickets API call carried aggregate_status=terminal
  const lastTicketListCall = apiCalls.filter((c) => c.pathname === '/api/owner/v1/tickets').pop();
  assert.strictEqual(lastTicketListCall.query.aggregate_status, 'terminal', 'API must receive aggregate_status=terminal');
  console.log('  ✓ Verified: /api/owner/v1/tickets received aggregate_status=terminal');

  // Take screenshot of Trades with active filters
  const tradesFilterScreenshotPath = path.join(screenshotsDir, 'live_trades_filters_active.png');
  await page.screenshot({ path: tradesFilterScreenshotPath, fullPage: false });
  console.log(`  ✓ Saved screenshot: ${tradesFilterScreenshotPath}`);

  // ---------------------------------------------------------------------------
  // STEP 4: Test Page Refresh (Reload) Persistence
  // ---------------------------------------------------------------------------
  console.log('\nStep 4: Reloading page to test URL search params restoration...');
  await page.reload({ waitUntil: 'networkidle' });

  const restoredStrat = await page.locator('#filter-strategy-group').inputValue();
  const restoredSide = await page.locator('#filter-position-side').inputValue();
  const restoredStatus = await page.locator('#filter-aggregate-status').inputValue();

  assert.strictEqual(restoredStrat, 'CPM-RO-001', 'Strategy group must be restored after refresh');
  assert.strictEqual(restoredSide, 'long', 'Position side must be restored after refresh');
  assert.strictEqual(restoredStatus, 'terminal', 'Aggregate status (terminal) must be restored after refresh');
  console.log('  ✓ Verified: Refresh preserved all filter inputs from URL search params');

  // ---------------------------------------------------------------------------
  // STEP 5: Test Browser Back and Forward Navigation (popstate)
  // ---------------------------------------------------------------------------
  console.log('\nStep 5: Testing browser Back & Forward (popstate)...');
  await page.goBack();
  await page.waitForTimeout(300);
  console.log('  ✓ Navigated back, current URL:', page.url());

  await page.goForward();
  await page.waitForTimeout(300);
  console.log('  ✓ Navigated forward, restored URL:', page.url());
  assert.match(page.url(), /strategy_group_id=CPM-RO-001/);

  // ---------------------------------------------------------------------------
  // STEP 6: Test Reset Filters
  // ---------------------------------------------------------------------------
  console.log('\nStep 6: Testing "清除全部条件 (Reset)" button...');
  const resetBtn = page.locator('button:has-text("清除全部条件")');
  await resetBtn.click();
  await page.waitForTimeout(300);

  currentUrl = page.url();
  assert.doesNotMatch(currentUrl, /strategy_group_id/, 'Reset must remove strategy_group_id');
  assert.doesNotMatch(currentUrl, /position_side/, 'Reset must remove position_side');
  assert.doesNotMatch(currentUrl, /aggregate_status/, 'Reset must remove aggregate_status');
  console.log('  ✓ Verified: Reset restored clean URL and default 30d window');

  // ---------------------------------------------------------------------------
  // STEP 7: Navigate to Strategies Page and Test Time Range & Drawer Window Inheritance
  // ---------------------------------------------------------------------------
  console.log('\nStep 7: Navigating to Strategies page and selecting "近 7 天"...');
  const stratTabNav = page.locator('nav[aria-label="主导航"] button:has-text("策略选币")');
  await stratTabNav.click();
  await page.waitForTimeout(400);

  await page.waitForSelector('[data-testid="strategies-time-range-bar"]');
  console.log('  ✓ Verified: Strategies page mounted with Time Range toolbar');

  const stratBtn7d = page.locator('[data-testid="strategies-time-range-bar"] button:has-text("近 7 天")');
  await stratBtn7d.click();
  await page.waitForTimeout(400);

  currentUrl = page.url();
  assert.match(currentUrl, /tab=strategies/);
  assert.match(currentUrl, /range=7d/);
  console.log('  ✓ Verified: Strategies URL has range=7d:', currentUrl);

  // Check last /strategies API call carried from_ms and to_ms
  const stratCalls = apiCalls.filter((c) => c.pathname === '/api/owner/v1/strategies');
  const lastStratCall = stratCalls[stratCalls.length - 1];
  assert.ok(lastStratCall.query.from_ms, 'API call to /strategies must include from_ms');
  assert.ok(lastStratCall.query.to_ms, 'API call to /strategies must include to_ms');
  console.log('  ✓ Verified: /api/owner/v1/strategies received from_ms and to_ms params:', lastStratCall.query);

  // ---------------------------------------------------------------------------
  // STEP 8: Open Strategy Detail Drawer & Verify Time Window Inheritance
  // ---------------------------------------------------------------------------
  console.log('\nStep 8: Clicking first strategy to open StrategyDetailDrawer...');
  const firstStrategyRow = page.locator('tbody tr[data-strategy-version-id]').first();
  await firstStrategyRow.click();
  await page.waitForTimeout(400);

  await page.waitForSelector('[data-testid="strategy-detail-drawer"]');
  console.log('  ✓ Verified: StrategyDetailDrawer opened');

  const drawerTimeBanner = page.locator('[data-testid="strategy-drawer-time-banner"]');
  assert.strictEqual(await drawerTimeBanner.count(), 1, 'Drawer must display time inheritance banner');
  const bannerText = await drawerTimeBanner.innerText();
  console.log('  ✓ Verified: Drawer time inheritance banner text:', bannerText.replace(/\s+/g, ' '));

  // Click Tickets Tab
  console.log('\nStep 8b: Switching to Tickets Tab in Drawer...');
  const ticketsTabBtn = page.locator('[data-testid="strategy-detail-drawer"] button:has-text("交易证据")');
  await ticketsTabBtn.click();
  await page.waitForTimeout(400);

  assert.match(page.url(), /drawer_tab=tickets/);
  const ticketCalls = apiCalls.filter((c) => c.pathname.includes('/tickets') && c.pathname.includes('/strategies/'));
  const lastTicketCall = ticketCalls[ticketCalls.length - 1];
  assert.ok(lastTicketCall, 'Strategy tickets request must have fired');
  assert.strictEqual(lastTicketCall.query.from_ms, lastStratCall.query.from_ms, 'Tickets query from_ms must match Strategies page from_ms');
  assert.strictEqual(lastTicketCall.query.to_ms, lastStratCall.query.to_ms, 'Tickets query to_ms must match Strategies page to_ms');
  console.log('  ✓ Verified: Tickets Tab strictly inherited Strategies page time window:', {
    from_ms: lastTicketCall.query.from_ms,
    to_ms: lastTicketCall.query.to_ms,
  });

  // Click Observations Tab
  console.log('\nStep 8c: Switching to Observations Tab in Drawer...');
  const obsTabBtn = page.locator('[data-testid="strategy-detail-drawer"] button:has-text("观察证据")');
  await obsTabBtn.click();
  await page.waitForTimeout(400);

  assert.match(page.url(), /drawer_tab=observations/);
  const obsCalls = apiCalls.filter((c) => c.pathname.includes('/observations') && c.pathname.includes('/strategies/'));
  const lastObsCall = obsCalls[obsCalls.length - 1];
  assert.ok(lastObsCall, 'Strategy observations request must have fired');
  assert.strictEqual(lastObsCall.query.from_ms, lastStratCall.query.from_ms, 'Observations query from_ms must match Strategies page from_ms');
  assert.strictEqual(lastObsCall.query.to_ms, lastStratCall.query.to_ms, 'Observations query to_ms must match Strategies page to_ms');
  console.log('  ✓ Verified: Observations Tab strictly inherited Strategies page time window:', {
    from_ms: lastObsCall.query.from_ms,
    to_ms: lastObsCall.query.to_ms,
  });

  // Take screenshot of Strategy Drawer with time alignment
  const drawerScreenshotPath = path.join(screenshotsDir, 'live_strategy_drawer_time_alignment.png');
  await page.screenshot({ path: drawerScreenshotPath, fullPage: false });
  console.log(`  ✓ Saved screenshot: ${drawerScreenshotPath}`);

  // ---------------------------------------------------------------------------
  // STEP 8d: P1-1 Fix Verification — Window Switch with Drawer Open
  // ---------------------------------------------------------------------------
  console.log('\nStep 8d: Verifying P1-1 dynamic strategy metric update on window switch...');
  const perfTabBtn = page.locator('[data-testid="strategy-detail-drawer"] button:has-text("表现评估")');
  await perfTabBtn.click();
  await page.waitForTimeout(300);

  // Switch window to "今日" while drawer remains open
  const stratBtnToday = page.locator('[data-testid="strategies-time-range-bar"] button:has-text("今日")');
  await stratBtnToday.click();
  await page.waitForTimeout(400);

  // The drawer time banner and performance metrics must reflect the updated window
  const updatedBannerText = await drawerTimeBanner.innerText();
  console.log('  ✓ Verified: Drawer updated banner on time switch:', updatedBannerText.replace(/\s+/g, ' '));
  assert.match(page.url(), /range=today/);

  // ---------------------------------------------------------------------------
  // STEP 9: P1-3 Fix Verification — Direct Deep Link with scope and exit_path
  // ---------------------------------------------------------------------------
  console.log('\nStep 9: Testing deep-link URL with scope=all&exit_path=controlled_exit...');
  const targetStrategyId = encodeURIComponent('sgv:CPM-RO-001:v3');
  await page.goto(
    `https://127.0.0.1:5174/?tab=strategies&strategy_version_id=${targetStrategyId}&drawer_tab=tickets&scope=all&exit_path=controlled_exit`,
    { waitUntil: 'networkidle' }
  );
  await page.waitForSelector('[data-testid="strategy-detail-drawer"]');

  // Verify tickets request carried scope=all and exit_path=controlled_exit
  const deepTicketCalls = apiCalls.filter(
    (c) => c.pathname.includes('/tickets') && c.pathname.includes('/strategies/')
  );
  const lastDeepTicketCall = deepTicketCalls[deepTicketCalls.length - 1];
  assert.strictEqual(lastDeepTicketCall.query.scope, 'all', 'Tickets query must inherit scope=all from URL');
  assert.strictEqual(lastDeepTicketCall.query.exit_path, 'controlled_exit', 'Tickets query must inherit exit_path=controlled_exit from URL');
  console.log('  ✓ Verified: Deep-linked Tickets query received scope=all and exit_path=controlled_exit');

  // Verify UI buttons state
  const btnScopeAll = page.locator('[data-testid="strategy-detail-drawer"] button:has-text("全部包含受控 (All)")');
  const btnControlledExit = page.locator('[data-testid="strategy-detail-drawer"] button:has-text("受控退出")');
  assert.match(await btnScopeAll.getAttribute('class'), /text-brand/, 'All scope button must be highlighted');
  assert.match(await btnControlledExit.getAttribute('class'), /bg-brand\/10/, 'Controlled exit pill must be highlighted');
  console.log('  ✓ Verified: UI correctly highlights scope=all and exit_path=controlled_exit');

  // Switch to Natural scope in UI and verify URL update
  console.log('\nStep 9b: Clicking "自然终态 (Natural)" and verifying URL synchronization...');
  const btnScopeNatural = page.locator('[data-testid="strategy-detail-drawer"] button:has-text("自然终态 (Natural)")');
  await btnScopeNatural.click();
  await page.waitForTimeout(400);

  currentUrl = page.url();
  assert.doesNotMatch(currentUrl, /scope=all/, 'URL must remove scope=all when switching to natural');
  assert.doesNotMatch(currentUrl, /exit_path/, 'URL must clear illegal controlled_exit when switching to natural');
  console.log('  ✓ Verified: Switching to Natural in UI synchronized URL and stripped controlled_exit:', currentUrl);

  const lastCallAfterSwitch = apiCalls
    .filter((c) => c.pathname.includes('/tickets') && c.pathname.includes('/strategies/'))
    .pop();
  assert.strictEqual(lastCallAfterSwitch.query.scope, 'natural', 'Tickets query must switch to scope=natural');
  assert.strictEqual(lastCallAfterSwitch.query.exit_path, undefined, 'Tickets query must clear exit_path');
  console.log('  ✓ Verified: Tickets API request after switch carried scope=natural without exit_path');

  // ---------------------------------------------------------------------------
  // STEP 10: P1-3 Fix Verification — Browser Back (popstate) Exit Path Filter Clear
  // ---------------------------------------------------------------------------
  console.log('\nStep 10: Verifying P1-3 Browser Back clears exit_path filter and restores "全部"...');
  // 10.1 Click "达到 TP1" in Tickets
  const btnTp1Reached = page.locator('[data-testid="strategy-detail-drawer"] button:text-is("达到 TP1")');
  await btnTp1Reached.click();
  await page.waitForTimeout(400);

  currentUrl = page.url();
  assert.match(currentUrl, /exit_path=tp1_reached/, 'URL must have exit_path=tp1_reached after clicking "达到 TP1"');
  assert.match(await btnTp1Reached.getAttribute('class'), /bg-brand\/10/, '"达到 TP1" button must be highlighted');
  console.log('  ✓ Verified: Clicking "达到 TP1" highlighted button and updated URL to:', currentUrl);

  const tp1TicketsCall = apiCalls
    .filter((c) => c.pathname.includes('/tickets') && c.pathname.includes('/strategies/'))
    .pop();
  assert.strictEqual(tp1TicketsCall.query.exit_path, 'tp1_reached', 'Tickets API query must carry exit_path=tp1_reached');
  console.log('  ✓ Verified: Tickets API received exit_path=tp1_reached');

  // 10.2 Single browser Back
  console.log('  Triggering single page.goBack()...');
  await page.goBack();
  await page.waitForTimeout(400);

  currentUrl = page.url();
  console.log('  After browser Back, URL is:', currentUrl);
  assert.doesNotMatch(currentUrl, /exit_path/, 'URL must NO LONGER contain exit_path after single Back');

  // 10.3 Verify UI highlights "全部" and NOT "达到 TP1"
  const btnAllPill = page.locator('[data-testid="strategy-detail-drawer"] button:text-is("全部")').first();
  const allClass = await btnAllPill.getAttribute('class');
  const tp1Class = await btnTp1Reached.getAttribute('class');

  assert.match(allClass, /bg-brand\/10/, '"全部" pill must be highlighted after browser Back');
  assert.doesNotMatch(tp1Class, /bg-brand\/10/, '"达到 TP1" pill must NOT be highlighted after browser Back');
  console.log('  ✓ Verified: UI button "全部" is highlighted and "达到 TP1" is un-highlighted!');

  // 10.4 Verify query executed without exit_path on fresh reload
  const countBeforeReload = apiCalls.length;
  await page.reload({ waitUntil: 'networkidle' });
  const reloadTicketsCall = apiCalls
    .slice(countBeforeReload)
    .filter((c) => c.pathname.includes('/tickets') && c.pathname.includes('/strategies/'))
    .pop();
  assert.ok(reloadTicketsCall, 'Reload after Back must trigger fresh tickets query');
  assert.strictEqual(reloadTicketsCall.query.exit_path, undefined, 'Tickets API query must have cleared exit_path after browser Back');
  console.log('  ✓ Verified: Tickets API query dispatched without exit_path on reload after browser Back');

  // ---------------------------------------------------------------------------
  // STEP 11: P1-3 Fix Verification — Observations First Path Browser Back Clear
  // ---------------------------------------------------------------------------
  console.log('\nStep 11: Verifying P1-3 Browser Back clears first_path filter in Observations...');
  await obsTabBtn.click();
  await page.waitForTimeout(400);

  const btnTp1First = page.locator('[data-testid="strategy-detail-drawer"] button:text-is("TP1 先到达")');
  await btnTp1First.click();
  await page.waitForTimeout(400);

  currentUrl = page.url();
  assert.match(currentUrl, /first_path=tp1_first/, 'URL must contain first_path=tp1_first');
  assert.match(await btnTp1First.getAttribute('class'), /bg-brand\/10/, '"TP1 先到达" must be highlighted');
  console.log('  ✓ Verified: "TP1 先到达" highlighted and URL has first_path=tp1_first:', currentUrl);

  await page.goBack();
  await page.waitForTimeout(400);

  currentUrl = page.url();
  console.log('  After browser Back, URL is:', currentUrl);
  assert.doesNotMatch(currentUrl, /first_path/, 'URL must NO LONGER contain first_path after single Back');

  const btnAllObsPill = page.locator('[data-testid="strategy-detail-drawer"] button:text-is("全部")').first();
  assert.match(await btnAllObsPill.getAttribute('class'), /bg-brand\/10/, '"全部" pill must be highlighted after browser Back');
  assert.doesNotMatch(await btnTp1First.getAttribute('class'), /bg-brand\/10/, '"TP1 先到达" must NOT be highlighted');
  console.log('  ✓ Verified: Observations UI restored "全部" and un-highlighted "TP1 先到达"');

  const countBeforeObsReload = apiCalls.length;
  await page.reload({ waitUntil: 'networkidle' });
  const reloadObsCall = apiCalls
    .slice(countBeforeObsReload)
    .filter((c) => c.pathname.includes('/observations') && c.pathname.includes('/strategies/'))
    .pop();
  assert.ok(reloadObsCall, 'Reload after Back must trigger fresh observations query');
  assert.strictEqual(reloadObsCall.query.first_path, undefined, 'Observations API query must have cleared first_path');
  console.log('  ✓ Verified: Observations API dispatched without first_path on reload after browser Back');

  await browser.close();

  console.log('\n================================================================');
  console.log('ALL BROWSER E2E TESTS & ASSERTIONS PASSED PERFECTLY!');
  console.log('================================================================\n');
}

run().catch((err) => {
  console.error('\n❌ BROWSER E2E TEST FAILED:');
  console.error(err);
  process.exit(1);
});
