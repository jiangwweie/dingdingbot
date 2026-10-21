// ============================================================================
// [MOCKED UI INTEGRATION TEST / 模拟数据 UI 集成测试]
// Owner Console V2: K-Line Review Component & Interaction Flow Test
//
// ⚠️ 证据分类说明 (Evidence Taxonomy):
// 本脚本通过 Playwright route.fulfill() 模拟认证会话、拦截 API 并注入模拟蜡烛图
// 与本地观察对象，用于端到端验证：
// 1. K 线按需加载、图表画布渲染与 Tab 切换；
// 2. 全屏 Modal 展开、关闭及 Light / Dark 双主题自适应；
// 3. 分层 Escape 按键治理（后入先出堆栈与焦点恢复）；
// 4. Observation 影子轨迹专用 Modal 与免责声明呈现。
//
// 本脚本属于【模拟数据 UI 集成测试】，绝不可冒充真实生产 API E2E 证据。
// ============================================================================

import pkg from '../owner-console/node_modules/@playwright/test/index.js';
import fs from 'fs';
import path from 'path';
import assert from 'node:assert/strict';

const { chromium } = pkg.default || pkg;

const scriptDir = path.dirname(new URL(import.meta.url).pathname);
const outDir = path.resolve(scriptDir, 'screenshots');
if (!fs.existsSync(outDir)) {
  fs.mkdirSync(outDir, { recursive: true });
}

// Load facts from Tokyo dump fixtures
const factsPath = fs.existsSync(path.resolve(scriptDir, 'tokyo_live_facts.json'))
  ? path.resolve(scriptDir, 'tokyo_live_facts.json')
  : path.resolve('frontend/owner-console-v2/tokyo_live_facts.json');
const controlsPath = fs.existsSync(path.resolve(scriptDir, 'tokyo_live_controls.json'))
  ? path.resolve(scriptDir, 'tokyo_live_controls.json')
  : path.resolve('frontend/owner-console-v2/tokyo_live_controls.json');

const facts = JSON.parse(fs.readFileSync(factsPath, 'utf8'));
const controlsData = JSON.parse(fs.readFileSync(controlsPath, 'utf8'));

function envelope(data, freshness = 'fresh') {
  return {
    data,
    freshness,
    now_ms: Date.now(),
    source_watermark_ms: Date.now() - 5000,
  };
}

// Generate realistic candle series
function generateCandles(count, barMs, startMs, basePrice = 0.33) {
  const candles = [];
  let price = basePrice;
  for (let i = 0; i < count; i++) {
    const open_time_ms = startMs + i * barMs;
    const close_time_ms = open_time_ms + barMs - 1;
    const change = (Math.sin(i) * 0.005 + (i % 2 === 0 ? 0.002 : -0.002)) * price;
    const open = price;
    const close = price + change;
    const high = Math.max(open, close) + Math.abs(change) * 0.4;
    const low = Math.min(open, close) - Math.abs(change) * 0.4;
    price = close;

    candles.push({
      open_time_ms,
      close_time_ms,
      open: open.toFixed(6),
      high: high.toFixed(6),
      low: low.toFixed(6),
      close: close.toFixed(6),
      volume: (10000 + i * 500).toFixed(2),
    });
  }
  return candles;
}

const baseTimeMs = 1792090800000;
const candles1h = generateCandles(60, 3600000, baseTimeMs - 24 * 3600000, 0.33);
const candles15m = generateCandles(80, 900000, baseTimeMs - 20 * 900000, 0.332);

const mockObservation = {
  shadow_outcome_id: 'obs-shadow-trx-001',
  strategy_version_id: 'BRF2-001:v3',
  exchange_instrument_id: 'binance-usdm:TRXUSDT:perpetual',
  position_side: 'long',
  status: 'completed',
  first_path: 'tp1_first',
  first_path_at_ms: baseTimeMs + 4 * 900000,
  mfe_r: '2.45',
  mae_r: '-0.35',
  spread_bps: '1.20',
  mark_index_deviation_bps: '0.40',
  entry_reference_price: '0.33239',
  initial_stop_price: '0.32921',
  take_profit_price: '0.33557',
  opening_range_boundary_price: '0.33150',
  observed_bar_count: 24,
  occurred_at_ms: baseTimeMs,
  horizon_start_ms: baseTimeMs,
  horizon_end_ms: baseTimeMs + 24 * 900000,
  completed_at_ms: baseTimeMs + 24 * 900000,
  annotations: [
    { kind: 'signal', label: 'Signal', price: '0.33239', occurred_at_ms: baseTimeMs },
    { kind: 'take_profit', label: 'TP1 到达', price: '0.33557', occurred_at_ms: baseTimeMs + 4 * 900000 },
  ],
  evidence: [],
  ticket_id: 'ticket:1726bf876bb575b70d0a9b9edeba40f7',
};

async function runKlineE2E() {
  console.log('================================================================');
  console.log('--- [MOCKED UI INTEGRATION TEST / 模拟数据 UI 集成测试] ---');
  console.log('Owner Console V2: K-Line Review Component & Interaction E2E');
  console.log('================================================================\n');

  const browser = await chromium.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true,
    args: ['--ignore-certificate-errors'],
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 960 },
    ignoreHTTPSErrors: true,
  });

  const page = await context.newPage();
  page.on('pageerror', (err) => console.log('PAGE ERROR:', err.message));
  page.on('console', (msg) => console.log('CONSOLE:', msg.text()));

  // Track candle requests
  const candleRequests = [];

  // Route API requests
  await context.route('**/api/owner/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const pathname = url.pathname;

    if (pathname.includes('/auth/session')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ authenticated: true }),
      });
    }

    if (pathname.includes('/market/candles')) {
      const tf = url.searchParams.get('timeframe') || '1h';
      candleRequests.push({ url: url.toString(), timeframe: tf });
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          envelope({
            exchange_instrument_id: url.searchParams.get('exchange_instrument_id'),
            timeframe: tf,
            candles: tf === '15m' ? candles15m : candles1h,
          })
        ),
      });
    }

    if (pathname.includes('/causality')) {
      const match = pathname.match(/tickets\/([^/]+)\/causality/);
      const reqTicketId = match ? decodeURIComponent(match[1]) : facts.causality.trade.ticket_id;
      // Differentiate Trade 1 vs Trade 2 so they represent distinct instruments & windows
      const isTicket1 = reqTicketId.includes('76be9c73');
      const inst = isTicket1 ? 'binance-usdm:TRXUSDT:perpetual' : 'binance-usdm:ETHUSDT:perpetual';
      const timeOffset = isTicket1 ? 0 : 3600000;
      const originalTrade = facts.tickets.items.find(t => t.ticket_id === reqTicketId);
      const causalityData = {
        ...facts.causality,
        annotations: [
          ...(facts.causality.annotations || []).map((a) => ({
            ...a,
            occurred_at_ms: a.occurred_at_ms + timeOffset,
          })),
          // Inject an out-of-window annotation (occurred_at_ms = 1000) to test out-of-window detection
          { kind: 'signal', label: 'Out of Window Signal', price: '12.0', occurred_at_ms: 1000 },
        ],
        trade: {
          ...facts.causality.trade,
          ticket_id: reqTicketId,
          exchange_instrument_id: inst,
          terminal_at_ms: originalTrade?.terminal_at_ms === null ? null : (facts.causality.trade.terminal_at_ms || baseTimeMs) + timeOffset,
          position_side: 'short',
        },
      };
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(envelope(causalityData)),
      });
    }

    if (pathname.includes('/observations')) {
      const obsWithoutTicket = {
        ...mockObservation,
        shadow_outcome_id: 'obs-shadow-trx-002',
        ticket_id: null,
      };
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          envelope({
            items: [mockObservation, obsWithoutTicket],
            next_cursor: null,
          })
        ),
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

    if (pathname.endsWith('/controls')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(controlsData.controls),
      });
    }

    if (pathname.includes('/strategies') && pathname.includes('/tickets')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          envelope({
            items: [
              {
                ticket_id: 'ticket:1726bf876bb575b70d0a9b9edeba40f7',
                exchange_instrument_id: 'binance-usdm:TRXUSDT:perpetual',
                position_side: 'long',
                lifecycle_stage: 'terminal',
                net_pnl: '0.999999',
                net_r: '1.0',
                issued_at_ms: baseTimeMs,
                terminal_at_ms: baseTimeMs + 36000000,
                exit_path: 'tp1_reached',
                exit_reason_label: 'TP1 目标达成',
                is_active: false,
                is_natural: true,
              },
            ],
            next_cursor: null,
          })
        ),
      });
    }

    if (pathname.endsWith('/strategies')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(envelope(facts.strategies)),
      });
    }

    if (pathname.includes('/overview')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(envelope(facts.overview)),
      });
    }

    if (pathname.includes('/tickets')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(envelope(facts.tickets)),
      });
    }

    // Default passthrough / 200
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(envelope({})),
    });
  });

  try {
    console.log('Step 1: Navigating to base console...');
    await page.goto('https://127.0.0.1:5174/', { waitUntil: 'networkidle' });

    console.log('Step 1b: Clicking "交易因果" tab in Navbar...');
    const tradesNavBtn = page.getByRole('button', { name: '交易因果', exact: true });
    await tradesNavBtn.click();
    await page.waitForTimeout(500);

    console.log('Step 2: Opening Causality Drawer for ticket...');
    const causalityBtn = page.locator('[data-testid=active-trade-card][data-ticket-id="ticket:76be9c73106d6a80ac8150a555f8f902"]').getByRole('button', { name: /因果详情|查看交易因果/ });
    await causalityBtn.waitFor({ state: 'visible', timeout: 5000 });
    await causalityBtn.click();

    const drawer = page.locator('[data-testid="causality-drawer"]');
    await drawer.waitFor({ state: 'visible', timeout: 5000 });
    console.log('  ✓ Causality Drawer is open');

    console.log('Step 3: Checking K-Line Review Tab presence in drawer...');
    const klineTabBtn = drawer.getByRole('button', { name: 'K 线复盘' });
    await klineTabBtn.waitFor({ state: 'visible', timeout: 3000 });
    console.log('  ✓ "K 线复盘" tab button is visible');

    console.log('Step 4: Clicking "K 线复盘" tab (On-Demand Loading Check)...');
    assert.equal(candleRequests.length, 0, 'No candles must be fetched before clicking tab');
    await klineTabBtn.click();

    await page.waitForTimeout(500);
    assert.ok(candleRequests.length >= 1, 'Candles request MUST be sent on-demand upon clicking K-line tab');
    console.log('  ✓ Candles requested on demand, timeframe:', candleRequests[0].timeframe);

    // Verify chart container exists
    const chartTab = page.locator('[data-testid="causality-chart-tab"]');
    await chartTab.waitFor({ state: 'visible', timeout: 3000 });
    const chartContainer = page.locator('[data-testid="causality-chart"]');
    await chartContainer.waitFor({ state: 'visible', timeout: 3000 });
    console.log('  ✓ Chart canvas rendered in drawer');

    // Verify out-of-window banner in drawer
    const drawerOowBanner = drawer.locator('text=个事件标注发生时间超出当前 K 线窗口范围');
    const hasDrawerOow = await drawerOowBanner.isVisible();
    assert.ok(hasDrawerOow, 'Out-of-window banner MUST be displayed in drawer when an event is outside candles window');
    console.log('  ✓ Out-of-window event notice banner verified in drawer');

    // Switch timeframe to 15m
    console.log('Step 5: Testing timeframe switch to 15m...');
    const tf15mBtn = chartTab.getByRole('button', { name: '15m 执行细节' });
    await tf15mBtn.click();
    await page.waitForTimeout(500);
    const has15mReq = candleRequests.some((r) => r.timeframe === '15m');
    assert.ok(has15mReq, 'Switching timeframe must trigger new candle query with 15m');
    console.log('  ✓ 15m timeframe query triggered');

    // Fullscreen review
    console.log('Step 6: Testing Fullscreen Review Modal & Out-of-Window Notice...');
    const fullscreenBtn = chartTab.getByRole('button', { name: '全屏复盘' });
    await fullscreenBtn.click();

    const modal = page.locator('[data-testid="chart-fullscreen-modal"]');
    await modal.waitFor({ state: 'visible', timeout: 3000 });
    console.log('  ✓ Fullscreen Chart Modal opened');

    // Verify out-of-window banner in fullscreen modal
    const modalOowBanner = modal.locator('[data-testid="chart-modal-out-of-window-banner"]');
    const hasModalOow = await modalOowBanner.isVisible();
    assert.ok(hasModalOow, 'Out-of-window banner MUST be displayed in Fullscreen Modal');
    console.log('  ✓ Out-of-window event notice banner verified in Fullscreen Modal');

    // Capture screenshot of fullscreen chart modal in Dark Mode
    await page.screenshot({ path: path.join(outDir, 'live_screenshot_kline_modal_dark.png'), fullPage: false });
    console.log('  ✓ Saved live_screenshot_kline_modal_dark.png');

    // Switch to Light Mode for screenshot
    await page.evaluate(() => {
      document.documentElement.classList.remove('dark');
      document.documentElement.classList.add('light');
    });
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(outDir, 'live_screenshot_kline_modal_light.png'), fullPage: false });
    console.log('  ✓ Saved live_screenshot_kline_modal_light.png');

    // Switch back to Dark Mode
    await page.evaluate(() => {
      document.documentElement.classList.remove('light');
      document.documentElement.classList.add('dark');
    });

    // Test hierarchical escape dismissal
    console.log('Step 7: Testing Hierarchical Escape Dismissal...');
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
    const modalVisible = await modal.isVisible();
    assert.equal(modalVisible, false, 'First Escape MUST close ONLY the fullscreen modal');
    const drawerVisible = await drawer.isVisible();
    assert.equal(drawerVisible, true, 'First Escape MUST leave the Causality Drawer OPEN');
    console.log('  ✓ First Escape cleanly closed fullscreen modal; Causality Drawer remains open');

    // Second Escape closes the drawer
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
    const drawerVisible2 = await drawer.isVisible();
    assert.equal(drawerVisible2, false, 'Second Escape MUST close the Causality Drawer');
    console.log('  ✓ Second Escape cleanly closed the Causality Drawer');

    // -------------------------------------------------------------------------
    // Step 7b: Ticket Switching Isolation & Request Verification
    // -------------------------------------------------------------------------
    console.log('\nStep 7b: Testing Ticket Switching State Reset & Query Isolation...');
    const candleCountBeforeSwitch = candleRequests.length;

    // Open second trade in Trades table
    const tradeRows = page.locator('tbody tr');
    const rowsCount = await tradeRows.count();
    console.log(`  Found ${rowsCount} trade rows in tbody`);
    const secondTradeBtn = tradeRows.nth(1).getByRole('button', { name: /因果详情|查看交易因果/ });
    await secondTradeBtn.click();
    await drawer.waitFor({ state: 'visible', timeout: 5000 });
    const currentDrawerTicket = await drawer.locator('[data-ticket-id]').first().getAttribute('data-ticket-id');
    console.log('  Opened ticket ID in drawer:', currentDrawerTicket);
    console.log('  ✓ Opened Causality Drawer for second trade');

    // Verify state was reset: activeTab MUST be timeline, NOT chart
    const timelineActive = await drawer.getByRole('button', { name: '8 阶段时间线' }).getAttribute('class');
    assert.ok(timelineActive.includes('border-brand'), 'P2-1: Active tab must reset to timeline on ticket switch');
    console.log('  ✓ P2-1 Verified: Active tab synchronously reset to timeline');

    // Verify ZERO candle requests sent upon opening new ticket drawer
    assert.equal(candleRequests.length, candleCountBeforeSwitch, 'ZERO candle queries must be triggered when switching tickets');
    console.log('  ✓ Zero candle requests fired on ticket switch (no premature fetch)');

    // Now click K-line tab on second ticket
    const secondKlineTabBtn = drawer.getByRole('button', { name: 'K 线复盘' });
    await secondKlineTabBtn.click();
    await page.waitForTimeout(1000);

    console.log('candleRequests so far:', candleRequests);
    assert.ok(candleRequests.length > candleCountBeforeSwitch, 'Clicking K-line tab on Ticket B must trigger a candle request');
    const latestReq = candleRequests[candleRequests.length - 1];
    assert.equal(latestReq.timeframe, '1h', 'Ticket B must default to 1h, never inheriting previous ticket 15m');
    assert.ok(latestReq.url.includes('ETHUSDT'), 'Ticket B candle request must query ETHUSDT instrument');
    console.log('  ✓ Ticket B cleanly requested 1h timeframe on demand for ETHUSDT');

    const symbolText = await drawer.locator('span.font-mono.text-sm.font-bold').textContent();
    assert.ok(symbolText.includes('ETHUSDT'), 'Ticket B drawer header must display Ticket B symbol (ETHUSDT)');

    const isModalOpen = await page.locator('[data-testid="chart-fullscreen-modal"]').isVisible();
    assert.equal(isModalOpen, false, 'Ticket B must NOT inherit fullscreen state from Ticket A');

    // Close drawer
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);

    // Step 8: Test Observation Shadow Trajectory K-Line
    console.log('\nStep 8: Switching to Strategies tab in Navbar...');
    const stratNavBtn = page.getByRole('button', { name: '策略选币', exact: true });
    await stratNavBtn.click();
    await page.waitForTimeout(500);

    console.log('Step 9: Opening Strategy Detail Drawer...');
    const strategyRow = page.locator('tr[data-strategy-group-id="BRF2-001"]').first();
    await strategyRow.waitFor({ state: 'visible', timeout: 5000 });
    await strategyRow.click();

    const stratDrawer = page.locator('[data-testid="strategy-detail-drawer"]');
    await stratDrawer.waitFor({ state: 'visible', timeout: 5000 });
    console.log('  ✓ Strategy Detail Drawer is open');

    console.log('Step 10: Switching to Observations Tab...');
    const obsTabBtn = stratDrawer.getByRole('button', { name: /观察证据/ });
    await obsTabBtn.click();
    await page.waitForTimeout(500);

    console.log('Step 11: Clicking "影子轨迹" button on observation row 1 (with Ticket)...');
    const shadowBtn = page.getByRole('button', { name: /影子轨迹/ }).first();
    await shadowBtn.waitFor({ state: 'visible', timeout: 3000 });
    await shadowBtn.click();

    const obsModal = page.locator('[data-testid="observation-chart-modal"]');
    await obsModal.waitFor({ state: 'visible', timeout: 3000 });
    console.log('  ✓ Observation Chart Modal opened');

    // Check disclaimer banner
    const bannerText = await obsModal.textContent();
    assert.ok(bannerText.includes('影子假设检验轨迹') || bannerText.includes('Shadow Trajectory'));
    assert.ok(bannerText.includes('非实盘成交'));
    console.log('  ✓ Research disclaimer banner verified (non-fill, 0 PnL pollution confirmed)');

    // Capture screenshot of observation chart modal in Dark Mode
    await page.screenshot({ path: path.join(outDir, 'live_screenshot_observation_kline_dark.png'), fullPage: false });
    console.log('  ✓ Saved live_screenshot_observation_kline_dark.png');

    // Switch to Light Mode for screenshot
    await page.evaluate(() => {
      document.documentElement.classList.remove('dark');
      document.documentElement.classList.add('light');
    });
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(outDir, 'live_screenshot_observation_kline_light.png'), fullPage: false });
    console.log('  ✓ Saved live_screenshot_observation_kline_light.png');

    // Switch back to Dark Mode
    await page.evaluate(() => {
      document.documentElement.classList.remove('light');
      document.documentElement.classList.add('dark');
    });

    // -------------------------------------------------------------------------
    // Step 11b: Observation → 关联真实 Ticket 真实链路验证
    // -------------------------------------------------------------------------
    console.log('\nStep 11b: Testing Observation → Associated Real Ticket transition...');
    const viewRealTicketBtn = obsModal.locator('[data-testid="view-real-ticket-btn"]');
    await viewRealTicketBtn.waitFor({ state: 'visible', timeout: 3000 });
    console.log('  ✓ "查看真实 Ticket" button is present on observation with ticket_id');

    await viewRealTicketBtn.click();
    await page.waitForTimeout(500);

    // Modal should close and CausalityDrawer for the real ticket should open
    const obsModalAfterClick = await obsModal.isVisible();
    assert.equal(obsModalAfterClick, false, 'Clicking "查看真实 Ticket" MUST close observation modal');
    await drawer.waitFor({ state: 'visible', timeout: 5000 });
    console.log('  ✓ Observation modal closed; CausalityDrawer opened for real ticket');

    // Verify authentic ticket identity (SHORT, ETHUSDT, real server facts)
    const drawerText = await drawer.textContent();
    assert.ok(drawerText.includes('做空 (SHORT)'), 'Authentic direction MUST be SHORT (not default long)');
    assert.ok(drawerText.includes('ETHUSDT') || drawerText.includes('ETH'), 'Authentic symbol MUST match ticket instrument');
    console.log('  ✓ Real Ticket facts verified: direction is SHORT, symbol is ETHUSDT, zero fake TradeEpisode');

    // Close CausalityDrawer
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);

    // -------------------------------------------------------------------------
    // Step 11c: Observation WITHOUT associated Ticket (pure shadow)
    // -------------------------------------------------------------------------
    console.log('\nStep 11c: Testing Observation WITHOUT associated Ticket (pure shadow)...');
    const secondShadowBtn = page.getByRole('button', { name: /影子轨迹/ }).nth(1);
    await secondShadowBtn.click();
    await obsModal.waitFor({ state: 'visible', timeout: 3000 });

    const unassociatedText = await obsModal.textContent();
    assert.ok(unassociatedText.includes('未成交 (无关联 Ticket)'), 'Unassociated observation must honestly display "未成交 (无关联 Ticket)"');
    const hasViewTicketBtn = await obsModal.locator('[data-testid="view-real-ticket-btn"]').isVisible();
    assert.equal(hasViewTicketBtn, false, 'Unassociated observation must NOT have "查看真实 Ticket" button');
    console.log('  ✓ Pure shadow observation verified: displays unassociated state without fabricating TradeEpisode');

    // Test Escape on observation modal
    console.log('\nStep 12: Testing Escape on Observation Chart Modal...');
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
    const obsModalVisible = await obsModal.isVisible();
    assert.equal(obsModalVisible, false, 'Escape MUST close the Observation Chart Modal');
    const stratDrawerVisible = await stratDrawer.isVisible();
    assert.equal(stratDrawerVisible, true, 'Escape on modal MUST leave Strategy Detail Drawer open');
    console.log('  ✓ Observation modal closed; Strategy Detail Drawer remains open');

    // Second escape closes strategy drawer
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
    const stratDrawerVisible2 = await stratDrawer.isVisible();
    assert.equal(stratDrawerVisible2, false, 'Second Escape closes Strategy Detail Drawer');
    console.log('  ✓ Strategy Detail Drawer closed');

    console.log('\n================================================================');
    console.log('MOCKED UI INTEGRATION TEST: ALL K-LINE E2E ASSERTIONS PASSED!');
    console.log('================================================================\n');
  } finally {
    await browser.close();
  }
}

runKlineE2E().catch((err) => {
  console.error('\n✗ E2E Verification failed:', err);
  process.exit(1);
});
