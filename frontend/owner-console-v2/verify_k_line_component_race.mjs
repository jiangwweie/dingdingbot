// ============================================================================
// [ISOLATED UI TEST / 隔离组件级竞态、取消与全屏重置验证]
// Owner Console V2: CausalityDrawer Real Mounted Component Race & Cancellation Test
//
// ⚠️ 证据分类说明 (Evidence Taxonomy):
// 本脚本属于【模拟数据隔离 UI 测试 (Mocked UI Integration Test)】，
// 通过真实挂载 CausalityDrawer React 组件，注入受控的延迟与中断响应，
// 验证：
// 1. 真实 queryFn 接收到的 AbortSignal 随组件状态被物理取消（signal.aborted === true）；
// 2. 明确区分的 OHLC 测试数据（TRXUSDT ~0.15 vs ETHUSDT ~3500），
//    在 B 加载完成后释放 A 的迟到响应，断言图表仍对应 B 的数据，A 绝不覆盖 B；
// 3. 全屏状态与周期重置：Ticket A 开启全屏 (fullscreen=true) 后切换 Ticket B，
//    必须真实经历 true → false 转换，activeTab 复位 timeline，周期复位 1h，
//    重新打开 B 确认请求与数据严格属于 B；
// 4. 不仅检查 Canvas 是否存在，而且直接断言 DOM data 属性与图表内部 OHLC 数据事实。
//
// 绝不可将本测试中的模拟数据混淆为真实生产 API 证据。
// ============================================================================

import pkg from '../owner-console/node_modules/@playwright/test/index.js';
import fs from 'fs';
import path from 'path';
import assert from 'node:assert/strict';

const { chromium } = pkg.default || pkg;

const scriptDir = path.dirname(new URL(import.meta.url).pathname);
const factsPath = fs.existsSync(path.resolve(scriptDir, 'tokyo_live_facts.json'))
  ? path.resolve(scriptDir, 'tokyo_live_facts.json')
  : path.resolve('frontend/owner-console-v2/tokyo_live_facts.json');
const facts = JSON.parse(fs.readFileSync(factsPath, 'utf8'));

function envelope(data) {
  return {
    data,
    freshness: 'fresh',
    now_ms: Date.now(),
    source_watermark_ms: Date.now() - 5000,
  };
}

async function runComponentRaceTest() {
  console.log('================================================================');
  console.log('--- [ISOLATED UI TEST / 隔离组件级竞态与全屏重置验证] ---');
  console.log('CausalityDrawer Mounted Component Race & Request Cancellation');
  console.log('Timestamp:', new Date().toISOString());
  console.log('================================================================\n');

  const browser = await chromium.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true,
    args: ['--ignore-certificate-errors'],
  });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    ignoreHTTPSErrors: true,
  });
  const page = await context.newPage();

  page.on('pageerror', (err) => console.log('PAGE ERROR STACK:', err.stack || err.message));
  page.on('console', (msg) => console.log('PAGE CONSOLE:', msg.text()));

  // 1. Inject hook into window.fetch to record real AbortSignals passed by queryFn
  await page.addInitScript(() => {
    window.__capturedCandleSignals = [];
    const originalFetch = window.fetch;
    window.fetch = function (input, init) {
      const url = typeof input === 'string' ? input : input?.url;
      const sig = init?.signal || (input instanceof Request ? input.signal : undefined);
      if (url && url.includes('/market/candles')) {
        const record = {
          url,
          hasSignal: Boolean(sig),
          signal: sig,
          get aborted() {
            return sig ? sig.aborted : false;
          },
          timestamp: Date.now(),
        };
        if (sig) {
          sig.addEventListener('abort', () => {
            record.abortedAt = Date.now();
          });
        }
        window.__capturedCandleSignals.push(record);
      }
      return originalFetch.apply(this, arguments);
    };
  });

  // Distinct OHLC test datasets
  // Ticket A (TRXUSDT) ~0.14 - 0.15
  const candlesA_1h = [
    { open_time_ms: 1000000, close_time_ms: 1003599, open: '0.1400', high: '0.1450', low: '0.1380', close: '0.1420', volume: '50000' },
    { open_time_ms: 1003600, close_time_ms: 1007199, open: '0.1420', high: '0.1480', low: '0.1410', close: '0.1460', volume: '60000' },
  ];
  const candlesA_15m = [
    { open_time_ms: 1000000, close_time_ms: 1000899, open: '0.1500', high: '0.1550', low: '0.1480', close: '0.1520', volume: '10000' },
    { open_time_ms: 1000900, close_time_ms: 1001799, open: '0.1520', high: '0.1580', low: '0.1510', close: '0.1570', volume: '12000' },
  ];

  // Ticket B (ETHUSDT) ~3500 - 3575
  const candlesB_1h = [
    { open_time_ms: 2000000, close_time_ms: 2003599, open: '3500.00', high: '3550.00', low: '3490.00', close: '3540.00', volume: '500' },
    { open_time_ms: 2003600, close_time_ms: 2007199, open: '3540.00', high: '3580.00', low: '3530.00', close: '3575.00', volume: '600' },
  ];
  const candlesB_15m = [
    { open_time_ms: 2000000, close_time_ms: 2000899, open: '3520.00', high: '3540.00', low: '3510.00', close: '3535.00', volume: '150' },
    { open_time_ms: 2000900, close_time_ms: 2001799, open: '3535.00', high: '3560.00', low: '3530.00', close: '3555.00', volume: '180' },
  ];

  // Deferred promise controls for late response simulation
  let isTicketADelayed = false;
  let resolveTicketA;
  let pendingTicketA = new Promise((resolve) => {
    resolveTicketA = resolve;
  });

  const candleRequestsDispatched = [];

  // Setup route interception
  await page.route('**/api/owner/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const pathname = url.pathname;

    if (pathname.includes('/auth/session')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ authenticated: true }),
      });
    }

    if (pathname.includes('/causality')) {
      const match = pathname.match(/tickets\/([^/]+)\/causality/);
      const reqId = match ? decodeURIComponent(match[1]) : '';
      const isTicketA = reqId.includes('ticket-A');

      const causalityData = {
        ...facts.causality,
        trade: {
          ...facts.causality.trade,
          ticket_id: reqId,
          exchange_instrument_id: isTicketA ? 'binance-usdm:TRXUSDT:perpetual' : 'binance-usdm:ETHUSDT:perpetual',
          strategy_group_id: isTicketA ? 'CPM-RO-001' : 'BRF2-001',
          position_side: isTicketA ? 'short' : 'long',
          lifecycle_stage: 'protection',
          aggregate_status: 'position_protected',
          ticket_status: 'issued',
          issued_at_ms: isTicketA ? 1000000 : 2000000,
          terminal_at_ms: isTicketA ? 2000000 : 3000000,
        },
        current_stage: 'protection',
        annotations: [
          { kind: 'entry', label: 'Entry Fill', price: isTicketA ? '0.15' : '3500.00', occurred_at_ms: isTicketA ? 1000500 : 2000500 },
        ],
        price_plan: {
          ...facts.causality.price_plan,
          strategy_timeframe: isTicketA ? '15m' : '1h',
          actual_entry_price: isTicketA ? '0.1500' : '3500.00',
          entry_reference_price: isTicketA ? '0.1500' : '3500.00',
          initial_stop_price: isTicketA ? '0.1600' : '3400.00',
          active_stop_price: isTicketA ? '0.1580' : '3450.00',
          tp1_price: isTicketA ? '0.1300' : '3700.00',
        },
      };

      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(envelope(causalityData)),
      });
    }

    if (pathname.includes('/market/candles')) {
      const tf = url.searchParams.get('timeframe');
      const inst = url.searchParams.get('exchange_instrument_id') || '';
      candleRequestsDispatched.push({ url: url.toString(), timeframe: tf, inst, timestamp: Date.now() });

      const isTRX = inst.includes('TRXUSDT');

      if (isTRX) {
        if (tf === '15m' && isTicketADelayed) {
          console.log('  [Route] Intercepted Ticket A 15m candles request -> holding in pending state...');
          await pendingTicketA;
          console.log('  [Route] Releasing delayed Ticket A 15m candles response...');
          return route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(envelope({
              exchange_instrument_id: inst,
              timeframe: '15m',
              candles: candlesA_15m,
            })),
          });
        }

        const candles = tf === '15m' ? candlesA_15m : candlesA_1h;
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(envelope({
            exchange_instrument_id: inst,
            timeframe: tf,
            candles,
          })),
        });
      }

      // Ticket B (ETHUSDT)
      const candles = tf === '15m' ? candlesB_15m : candlesB_1h;
      console.log(`  [Route] Fulfilling Ticket B ${tf} candles request immediately...`);
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(envelope({
          exchange_instrument_id: inst,
          timeframe: tf,
          candles,
        })),
      });
    }

    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(envelope({})),
    });
  });

  try {
    // =========================================================================
    // SECTION 1: 迟到响应隔离与真实取消测试 (Late Response Isolation & Cancellation)
    // =========================================================================
    console.log('----------------------------------------------------------------');
    console.log('Section 1: Late Response Isolation & Real AbortSignal Cancellation');
    console.log('----------------------------------------------------------------');

    // Arm delayed response before initial mount
    pendingTicketA = new Promise((resolve) => {
      resolveTicketA = resolve;
    });
    isTicketADelayed = true;

    // Step 1.1: Mount CausalityDrawer on Ticket A in real browser harness
    console.log('Step 1.1: Navigating to test_race.html (real CausalityDrawer mounted on Ticket A)...');
    await page.goto('https://127.0.0.1:5174/test_race.html', { waitUntil: 'networkidle' });

    const drawer = page.locator('[data-testid="causality-drawer"]');
    await drawer.waitFor({ state: 'visible', timeout: 5000 });
    console.log('  ✓ CausalityDrawer successfully mounted with Ticket A');

    // Step 1.2: Open K-line Tab on Ticket A and switch to 15m (intercepted in-flight)
    console.log('Step 1.2: Opening K-line Tab on Ticket A and switching to 15m (held pending)...');
    const klineTabBtn = drawer.getByRole('button', { name: 'K 线复盘' });
    await klineTabBtn.click();
    await page.waitForTimeout(300);

    const tf15mBtn = drawer.getByRole('button', { name: '15m 执行细节' });
    await tf15mBtn.click();
    await page.waitForTimeout(500);

    // Step 1.3: Verify Ticket A request is pending & real queryFn AbortSignal recorded
    console.log('Step 1.3: Checking queryFn AbortSignal for Ticket A 15m in-flight request...');
    const signalRecordA = await page.evaluate(() => {
      const list = window.__capturedCandleSignals || [];
      const s = list.filter((item) => item.url.includes('timeframe=15m') && item.url.includes('TRXUSDT')).pop();
      return {
        totalDispatched: list.length,
        hasSignal: Boolean(s?.hasSignal),
        aborted: s ? s.aborted : null,
      };
    });
    assert.ok(signalRecordA.totalDispatched >= 1, 'At least 1 candles request must have been dispatched');
    assert.equal(signalRecordA.hasSignal, true, 'queryFn MUST pass real AbortSignal into fetchMarketCandles');
    assert.equal(signalRecordA.aborted, false, 'In-flight Ticket A request MUST NOT be aborted while still active');
    console.log('  ✓ Verified: Ticket A 15m request is in-flight with real AbortSignal (aborted === false)');

    // Step 1.4: Switch to Ticket B while Ticket A request is STILL PENDING
    console.log('Step 1.4: Switching to Ticket B while Ticket A request is pending in-flight...');
    const btnSwitchB = page.locator('#btn-switch-ticket-b');
    await btnSwitchB.click({ force: true });
    await page.waitForTimeout(500);

    // Step 1.5: Verify Ticket A AbortSignal was aborted by TanStack Query
    console.log('Step 1.5: Verifying real queryFn AbortSignal for Ticket A was aborted on switch...');
    const signalStatusAfterSwitch = await page.evaluate(() => {
      const list = window.__capturedCandleSignals || [];
      const s = list.filter((item) => item.url.includes('timeframe=15m') && item.url.includes('TRXUSDT')).pop();
      return {
        aborted: s ? s.aborted : false,
      };
    });
    assert.equal(signalStatusAfterSwitch.aborted, true, 'REAL queryFn AbortSignal MUST be aborted upon ticket switch');
    console.log('  ✓ Verified: queryFn AbortSignal.aborted === true (real cancellation confirmed)');

    // Verify synchronous state reset
    const timelineBtnClass = await drawer.getByRole('button', { name: '8 阶段时间线' }).getAttribute('class');
    assert.ok(timelineBtnClass.includes('border-brand'), 'Active tab must reset to timeline on ticket switch');
    console.log('  ✓ Verified: Active tab synchronously reset to timeline');

    const fullscreenModal = page.locator('[data-testid="chart-fullscreen-modal"]');
    assert.equal(await fullscreenModal.isVisible(), false, 'Fullscreen modal must be false on ticket switch');
    console.log('  ✓ Verified: Fullscreen state is false');

    // Step 1.6: Open K-line tab on Ticket B and wait for Ticket B 1h candles
    console.log('Step 1.6: Opening K-line Tab on Ticket B (loads ETHUSDT 1h candles)...');
    const klineTabBtnB = drawer.getByRole('button', { name: 'K 线复盘' });
    await klineTabBtnB.click();
    await page.waitForTimeout(1000);

    // Check Ticket B drawer header
    const drawerHeaderB = await drawer.locator('span.font-mono.text-sm.font-bold').textContent();
    assert.ok(drawerHeaderB.includes('ETHUSDT'), 'Ticket B header must display ETHUSDT');
    console.log(`  ✓ Verified: Ticket B header displays "${drawerHeaderB.trim()}"`);

    // Check timeframe is reset to 1h
    const btn1h = drawer.getByRole('button', { name: '1h 策略复盘' });
    const btn1hClass = await btn1h.getAttribute('class');
    assert.ok(btn1hClass.includes('border-brand') || btn1hClass.includes('bg-brand'), 'Ticket B timeframe must be reset to 1h');
    console.log('  ✓ Verified: Ticket B active timeframe button is 1h (not 15m)');

    // Check Ticket B chart data attributes and internal candlestick data
    const chartContainerB = drawer.locator('[data-testid="causality-chart"]');
    await chartContainerB.waitFor({ state: 'visible', timeout: 3000 });
    const firstOpenB = await chartContainerB.getAttribute('data-first-open');
    const lastCloseB = await chartContainerB.getAttribute('data-last-close');
    const countB = await chartContainerB.getAttribute('data-candles-count');
    assert.equal(firstOpenB, '3500.00', 'Ticket B 1h first open must be 3500.00 (distinct from A 0.1500)');
    assert.equal(lastCloseB, '3575.00', 'Ticket B 1h last close must be 3575.00 (distinct from A 0.1570)');
    assert.equal(countB, '2', 'Ticket B 1h candle count must be 2');

    const internalDataB = await page.evaluate(() => {
      const el = document.querySelector('[data-testid="causality-chart"]');
      return el ? el.__candlestickData : null;
    });
    assert.ok(internalDataB && internalDataB.length === 2, 'Lightweight Charts must receive 2 candles');
    assert.equal(internalDataB[0].open, 3500, 'Internal chart series open must be 3500');
    console.log(`  ✓ Verified: Ticket B chart data display strictly belongs to B (open: ${firstOpenB}, close: ${lastCloseB})`);

    // Step 1.7: Release Ticket A's delayed 15m response (simulate late/stale response)
    console.log('Step 1.7: Releasing delayed Ticket A 15m response (late arrival simulation)...');
    resolveTicketA();
    await page.waitForTimeout(1000); // Allow any network resolution / microtasks to process

    // Step 1.8: Assert Ticket B UI is strictly protected & not contaminated
    console.log('Step 1.8: Asserting Ticket B chart data display against late response overwrite...');

    // a) Symbol in drawer header must STILL be ETHUSDT, never TRXUSDT
    const drawerHeaderAfter = await drawer.locator('span.font-mono.text-sm.font-bold').textContent();
    assert.ok(drawerHeaderAfter.includes('ETHUSDT'), 'Late Ticket A response must NOT change drawer symbol to TRXUSDT');
    assert.equal(drawerHeaderAfter.includes('TRXUSDT'), false, 'TRXUSDT must NEVER contaminate Ticket B');
    console.log('  ✓ Verified: Symbol remains strictly ETHUSDT');

    // b) Active timeframe must STILL be 1h, never reverted to 15m
    const btn1hClassAfter = await btn1h.getAttribute('class');
    assert.ok(btn1hClassAfter.includes('border-brand') || btn1hClassAfter.includes('bg-brand'), 'Late Ticket A response must NOT revert timeframe to 15m');
    console.log('  ✓ Verified: Timeframe remains strictly 1h (not reverted to 15m)');

    // c) Fullscreen modal must STILL be false
    const isModalOpenLate = await fullscreenModal.isVisible();
    assert.equal(isModalOpenLate, false, 'Late Ticket A response must NOT trigger fullscreen');
    console.log('  ✓ Verified: Fullscreen modal remains false');

    // d) Exact OHLC data assertions (NOT merely checking canvas presence):
    const chartElAfterA = drawer.locator('[data-testid="causality-chart"]');
    const openAfterA = await chartElAfterA.getAttribute('data-first-open');
    const closeAfterA = await chartElAfterA.getAttribute('data-last-close');
    const countAfterA = await chartElAfterA.getAttribute('data-candles-count');

    assert.equal(openAfterA, '3500.00', 'data-first-open MUST remain 3500.00 (Ticket B ETHUSDT), NOT overwritten by 0.1500 (Ticket A TRXUSDT)');
    assert.equal(closeAfterA, '3575.00', 'data-last-close MUST remain 3575.00 (Ticket B ETHUSDT), NOT overwritten by 0.1570 (Ticket A TRXUSDT)');
    assert.equal(countAfterA, '2', 'data-candles-count MUST remain 2');

    const internalDataAfterA = await page.evaluate(() => {
      const el = document.querySelector('[data-testid="causality-chart"]');
      return el ? el.__candlestickData : null;
    });
    assert.ok(internalDataAfterA && internalDataAfterA.length === 2, 'Chart series must retain Ticket B candles');
    assert.equal(internalDataAfterA[0].open, 3500, 'Chart series open MUST remain 3500, never overwritten by TRX 0.15');
    console.log('  ✓ Verified: DOM data attributes and internal chart data strictly retain Ticket B (open: 3500.00, close: 3575.00)');

    // e) CausalityChart canvas is rendered and intact
    const chartCanvas = drawer.locator('[data-testid="causality-chart"] canvas').first();
    const hasCanvas = await chartCanvas.isVisible();
    assert.ok(hasCanvas, 'CausalityChart canvas must remain rendered and visible');
    console.log('  ✓ Verified: CausalityChart canvas is rendered and intact');


    // =========================================================================
    // SECTION 2: 全屏状态重置测试 (Fullscreen State Reset Test: true → false)
    // =========================================================================
    console.log('\n----------------------------------------------------------------');
    console.log('Section 2: Fullscreen State Reset Test (True -> False Transition)');
    console.log('----------------------------------------------------------------');

    // Disarm delay for fullscreen test
    isTicketADelayed = false;

    // Step 2.1: Fresh navigation to test_race.html on Ticket A
    console.log('Step 2.1: Navigating freshly to test_race.html for Fullscreen State test...');
    await page.goto('https://127.0.0.1:5174/test_race.html', { waitUntil: 'networkidle' });

    const drawer2 = page.locator('[data-testid="causality-drawer"]');
    await drawer2.waitFor({ state: 'visible', timeout: 5000 });
    console.log('  ✓ CausalityDrawer successfully mounted with Ticket A');

    // Step 2.2: Open K-line Tab on Ticket A and switch to 15m
    console.log('Step 2.2: Opening K-line Tab on Ticket A and switching to 15m timeframe...');
    await drawer2.getByRole('button', { name: 'K 线复盘' }).click();
    await page.waitForTimeout(300);

    await drawer2.getByRole('button', { name: '15m 执行细节' }).click();
    await page.waitForTimeout(500);

    // Verify Ticket A candles rendered
    const chartContainerA = drawer2.locator('[data-testid="causality-chart"]');
    await chartContainerA.waitFor({ state: 'visible', timeout: 3000 });
    const candleCountA = await chartContainerA.getAttribute('data-candles-count');
    const firstOpenA = await chartContainerA.getAttribute('data-first-open');
    assert.equal(candleCountA, '2', 'Ticket A 15m must have 2 candles');
    assert.equal(firstOpenA, '0.1500', 'Ticket A 15m first open must be 0.1500');
    console.log(`  ✓ Verified: Ticket A 15m candles rendered (first open: ${firstOpenA}, count: ${candleCountA})`);

    // Step 2.3: Open Fullscreen
    console.log('Step 2.3: Clicking Fullscreen Review button on Ticket A...');
    const fullscreenBtn = drawer2.getByRole('button', { name: '全屏复盘' });
    await fullscreenBtn.click();
    await page.waitForTimeout(300);

    // Step 2.4: Confirm Fullscreen is OPEN (fullscreen === true)
    console.log('Step 2.4: Confirming Fullscreen modal is actively open (state: TRUE)...');
    const fullscreenModal2 = page.locator('[data-testid="chart-fullscreen-modal"]');
    await fullscreenModal2.waitFor({ state: 'visible', timeout: 3000 });
    const isModalOpenBefore = await fullscreenModal2.isVisible();
    assert.equal(isModalOpenBefore, true, 'Fullscreen modal MUST be visible (true state confirmed)');
    const modalTitle = await fullscreenModal2.locator('h2').textContent();
    assert.ok(modalTitle.includes('TRXUSDT'), 'Fullscreen modal title must reflect Ticket A (TRXUSDT)');
    console.log(`  ✓ Verified: Fullscreen modal is actively OPEN (true confirmed, title: "${modalTitle}")`);

    // Step 2.5: Switch to Ticket B while Fullscreen is OPEN
    console.log('Step 2.5: Switching to Ticket B while Fullscreen is open...');
    const btnSwitchB2 = page.locator('#btn-switch-ticket-b');
    await btnSwitchB2.click({ force: true });
    await page.waitForTimeout(500);

    // Step 2.6: Verify Fullscreen CLOSED (true → false transition confirmed!)
    console.log('Step 2.6: Verifying Fullscreen closed (true -> false), Tab reset to timeline, timeframe reset to 1h...');
    const isModalOpenAfter = await fullscreenModal2.isVisible();
    assert.equal(isModalOpenAfter, false, 'Fullscreen modal MUST be closed on ticket switch (true -> false verified!)');
    console.log('  ✓ Verified: Fullscreen state successfully transitioned from TRUE -> FALSE');

    // Verify Tab reset to timeline
    const timelineBtnClass2 = await drawer2.getByRole('button', { name: '8 阶段时间线' }).getAttribute('class');
    assert.ok(timelineBtnClass2.includes('border-brand'), 'Active tab must reset to timeline on ticket switch');
    console.log('  ✓ Verified: Active tab synchronously reset to timeline');

    // Step 2.7: Reopen K-line tab on Ticket B and verify timeframe and data identity belong to B
    console.log('Step 2.7: Reopening K-line on Ticket B, confirming 1h timeframe and ETHUSDT data identity...');
    await drawer2.getByRole('button', { name: 'K 线复盘' }).click();
    await page.waitForTimeout(1000);

    // Check Ticket B drawer header
    const drawerHeaderB2 = await drawer2.locator('span.font-mono.text-sm.font-bold').textContent();
    assert.ok(drawerHeaderB2.includes('ETHUSDT'), 'Ticket B header must display ETHUSDT');
    console.log(`  ✓ Verified: Ticket B header displays "${drawerHeaderB2.trim()}"`);

    // Check timeframe is reset to 1h
    const btn1h_2 = drawer2.getByRole('button', { name: '1h 策略复盘' });
    const btn1hClass2 = await btn1h_2.getAttribute('class');
    assert.ok(btn1hClass2.includes('border-brand') || btn1hClass2.includes('bg-brand'), 'Ticket B timeframe must be reset to 1h');
    console.log('  ✓ Verified: Ticket B active timeframe button is 1h (not 15m)');

    // Check Ticket B chart data attributes and internal candlestick data
    const chartContainerB2 = drawer2.locator('[data-testid="causality-chart"]');
    await chartContainerB2.waitFor({ state: 'visible', timeout: 3000 });
    const firstOpenB2 = await chartContainerB2.getAttribute('data-first-open');
    const lastCloseB2 = await chartContainerB2.getAttribute('data-last-close');
    const countB2 = await chartContainerB2.getAttribute('data-candles-count');
    assert.equal(firstOpenB2, '3500.00', 'Ticket B 1h first open must be 3500.00 (distinct from A 0.1500)');
    assert.equal(lastCloseB2, '3575.00', 'Ticket B 1h last close must be 3575.00 (distinct from A 0.1570)');
    assert.equal(countB2, '2', 'Ticket B 1h candle count must be 2');

    const internalDataB2 = await page.evaluate(() => {
      const el = document.querySelector('[data-testid="causality-chart"]');
      return el ? el.__candlestickData : null;
    });
    assert.ok(internalDataB2 && internalDataB2.length === 2, 'Lightweight Charts must receive 2 candles');
    assert.equal(internalDataB2[0].open, 3500, 'Internal chart series open must be 3500');
    console.log(`  ✓ Verified: Ticket B chart data display strictly belongs to B (open: ${firstOpenB2}, close: ${lastCloseB2})`);

    console.log('\n================================================================');
    console.log('ALL COMPONENT RACE, CANCELLATION & FULLSCREEN ASSERTIONS PASSED!');
    console.log('================================================================\n');
  } finally {
    await browser.close().catch(() => {});
  }
}

runComponentRaceTest().catch((err) => {
  console.error('\n✗ Component Race Verification Failed:', err);
  process.exit(1);
});
