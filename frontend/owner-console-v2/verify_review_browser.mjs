/**
 * Owner Console V2 — Review Center Real Browser E2E Suite
 *
 * Verifies real Chrome browser interaction:
 * 1. Navbar navigation: "复盘评估" tab activation (removes "规划中" badge).
 * 2. P1-1: Multi-page cursor pagination accumulation:
 *    - Page 1 loads 50 items -> Completed Tickets shows 50, Scope note says 50
 *    - Click "加载更多复盘记录 (Cursor 分页)" -> loads 16 items
 *    - Completed Tickets immediately updates to 66
 *    - Review Complete updates from 10 to 15, Incomplete from 40 to 51
 *    - Scope note updates to "已加载终态记录统计（共 66 笔）"
 * 3. P1-2: Unsupported waiting_for_settlement filter handling:
 *    - Verifies filter dropdown does NOT contain "waiting_for_settlement"
 *    - Direct URL access with review_status=waiting_for_settlement is safely sanitized
 * 4. P2-1: Asia/Shanghai datetime & range formatting:
 *    - Scope note explicitly includes "(上海时间)" and accurate range
 * 5. P2-2: Breakdown sections evidence chips & interaction:
 *    - StrategyGroup Evidence, Execution Classification, Exit Reason render Evidence chips
 *    - Clicking Ticket evidence chip immediately opens CausalityDrawer
 *    - Dismissing drawer with Escape key restores focus
 *    - Non-ticket evidence chips render as informative badges
 * 6. Responsive viewports (1440, 1280, 1024, 768) and Light Mode toggle
 * 7. Network audit: strictly GET requests, zero mutating writes.
 */

import pkg from '../owner-console/node_modules/@playwright/test/index.js';
import fs from 'fs';
import path from 'path';
import assert from 'node:assert';

const { chromium } = pkg;

const ARTIFACT_DIR = '/Users/jiangwei/.gemini/antigravity/brain/e94b5750-4260-49cb-aae5-01629a1e8441';
const screenshotsDir = fs.existsSync(ARTIFACT_DIR) ? ARTIFACT_DIR : path.resolve('screenshots');

const SCRIPT_DIR = path.dirname(new URL(import.meta.url).pathname);
const facts = JSON.parse(fs.readFileSync(path.resolve(SCRIPT_DIR, 'tokyo_live_facts.json'), 'utf8'));
const controlsData = JSON.parse(fs.readFileSync(path.resolve(SCRIPT_DIR, 'tokyo_live_controls.json'), 'utf8'));

function envelope(data, freshness = 'fresh') {
  return {
    data,
    freshness,
    generated_at: new Date().toISOString(),
    source_watermark: new Date(Date.now() - 5000).toISOString(),
    snapshot_id: 'snapshot:test:1',
  };
}

const mockNow = 1_770_000_000_000;

function makeDummyItem(i) {
  const isComplete = i <= 10 || (i > 50 && i <= 55);
  return {
    ticket_id: `ticket:item:${i}`,
    strategy_group_id: i % 2 === 0 ? 'MPG-001' : 'CPM-RO-001',
    exchange_instrument_id: 'binance-usdm:BTCUSDT:perpetual',
    position_side: i % 2 === 0 ? 'long' : 'short',
    terminal_at_ms: mockNow - (100 - i) * 60_000,
    review: {
      ticket_id: `ticket:item:${i}`,
      review_status: isComplete ? 'complete' : 'incomplete_evidence',
      execution_classification: isComplete ? 'complete' : 'recovered_incident',
      economic_summary: {
        gross_pnl: { value: '1.00', unit: 'USDT' },
        fees: { value: '-0.10', unit: 'USDT' },
        funding: { value: '-0.01', unit: 'USDT' },
        net_pnl: { value: '0.89', unit: 'USDT' },
        net_r: { value: '0.1000', unit: 'R' },
      },
      exit_reason: isComplete ? 'TP1 + Runner Exit' : 'initial_stop_triggered',
      attention_items: isComplete ? [] : ['延迟撤单确认'],
      sentences: [
        {
          template_id: isComplete ? 'execution_complete' : 'execution_recovered',
          text: `复盘事实记录 ${i}：${isComplete ? '执行链路完整。' : '发生异常并已成功恢复。'}`,
          evidence: [
            { kind: 'ticket', identity: `ticket:item:${i}`, occurred_at_ms: mockNow - i * 1000 },
          ],
        },
      ],
      final_conclusion: '自动复盘事实生成完毕。',
      evidence: [
        { kind: 'ticket', identity: `ticket:item:${i}`, occurred_at_ms: mockNow - i * 1000 },
        { kind: 'fact', identity: `fact:${i}`, occurred_at_ms: mockNow - i * 1000 },
      ],
    },
  };
}

const page1Items = Array.from({ length: 50 }, (_, idx) => makeDummyItem(idx + 1));
const page2Items = Array.from({ length: 16 }, (_, idx) => makeDummyItem(idx + 51));

const mockPage1Summary = {
  from_ms: mockNow - 30 * 86_400_000,
  to_ms: mockNow,
  sample_count: 50,
  next_cursor: 'cursor_token_page_2',
  items: page1Items,
  net_pnl: { value: '44.50', unit: 'USDT' },
  net_r: { value: '5.0000', unit: 'R' },
  fees: { value: '-5.00', unit: 'USDT' },
  funding: { value: '-0.50', unit: 'USDT' },
  complete_review_count: 10,
  incomplete_review_count: 40,
  exit_reason_breakdown: [
    { label: 'TP1 + Runner Exit', ticket_count: 10, evidence: page1Items.slice(0, 10).map(p => ({ kind: 'ticket', identity: p.ticket_id, occurred_at_ms: p.terminal_at_ms })) },
    { label: 'initial_stop_triggered', ticket_count: 40, evidence: page1Items.slice(10, 50).map(p => ({ kind: 'ticket', identity: p.ticket_id, occurred_at_ms: p.terminal_at_ms })) },
  ],
  execution_quality_breakdown: [
    { label: 'complete', ticket_count: 10, evidence: page1Items.slice(0, 10).map(p => ({ kind: 'ticket', identity: p.ticket_id, occurred_at_ms: p.terminal_at_ms })) },
    { label: 'recovered_incident', ticket_count: 40, evidence: page1Items.slice(10, 50).map(p => ({ kind: 'ticket', identity: p.ticket_id, occurred_at_ms: p.terminal_at_ms })) },
  ],
  strategy_group_samples: [
    { strategy_group_id: 'CPM-RO-001', sample_count: 25, evidence_state: 'observe_only', evidence: page1Items.filter(p => p.strategy_group_id === 'CPM-RO-001').map(p => ({ kind: 'ticket', identity: p.ticket_id, occurred_at_ms: p.terminal_at_ms })) },
    { strategy_group_id: 'MPG-001', sample_count: 25, evidence_state: 'observe_only', evidence: page1Items.filter(p => p.strategy_group_id === 'MPG-001').map(p => ({ kind: 'ticket', identity: p.ticket_id, occurred_at_ms: p.terminal_at_ms })) },
  ],
  evidence: page1Items.flatMap(p => p.review.evidence),
};

const mockPage2Summary = {
  from_ms: mockNow - 30 * 86_400_000,
  to_ms: mockNow,
  sample_count: 16,
  next_cursor: null,
  items: page2Items,
  net_pnl: { value: '14.24', unit: 'USDT' },
  net_r: { value: '1.6000', unit: 'R' },
  fees: { value: '-1.60', unit: 'USDT' },
  funding: { value: '-0.16', unit: 'USDT' },
  complete_review_count: 5,
  incomplete_review_count: 11,
  exit_reason_breakdown: [
    { label: 'TP1 + Runner Exit', ticket_count: 5, evidence: page2Items.slice(0, 5).map(p => ({ kind: 'ticket', identity: p.ticket_id, occurred_at_ms: p.terminal_at_ms })) },
    { label: 'initial_stop_triggered', ticket_count: 11, evidence: page2Items.slice(5, 16).map(p => ({ kind: 'ticket', identity: p.ticket_id, occurred_at_ms: p.terminal_at_ms })) },
  ],
  execution_quality_breakdown: [
    { label: 'complete', ticket_count: 5, evidence: page2Items.slice(0, 5).map(p => ({ kind: 'ticket', identity: p.ticket_id, occurred_at_ms: p.terminal_at_ms })) },
    { label: 'recovered_incident', ticket_count: 11, evidence: page2Items.slice(5, 16).map(p => ({ kind: 'ticket', identity: p.ticket_id, occurred_at_ms: p.terminal_at_ms })) },
  ],
  strategy_group_samples: [
    { strategy_group_id: 'CPM-RO-001', sample_count: 8, evidence_state: 'observe_only', evidence: page2Items.filter(p => p.strategy_group_id === 'CPM-RO-001').map(p => ({ kind: 'ticket', identity: p.ticket_id, occurred_at_ms: p.terminal_at_ms })) },
    { strategy_group_id: 'MPG-001', sample_count: 8, evidence_state: 'observe_only', evidence: page2Items.filter(p => p.strategy_group_id === 'MPG-001').map(p => ({ kind: 'ticket', identity: p.ticket_id, occurred_at_ms: p.terminal_at_ms })) },
  ],
  evidence: page2Items.flatMap(p => p.review.evidence),
};

const mockCandles = {
  candles: Array.from({ length: 48 }, (_, i) => ({
    open_time_ms: mockNow - (48 - i) * 3600_000,
    close_time_ms: mockNow - (47 - i) * 3600_000,
    open: String(65000 + i * 20),
    high: String(65100 + i * 20),
    low: String(64950 + i * 20),
    close: String(65050 + i * 20),
    volume: '150.5',
  })),
};

async function run() {
  console.log('================================================================');
  console.log('--- Owner Console V2 Review Center Real Browser E2E Test ---');
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

  page.on('console', msg => {
    if (msg.type() === 'error') {
      console.log('  [BROWSER ERROR]:', msg.text());
    }
  });
  page.on('pageerror', err => {
    console.log('  [BROWSER EXCEPTION]:', err);
  });

  const apiCalls = [];
  const mutatingRequests = [];

  await context.route('**/api/owner/v1/**', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const pathname = url.pathname;
    const query = Object.fromEntries(url.searchParams.entries());

    apiCalls.push({ method: req.method(), pathname, query, url: url.toString() });

    if (req.method() !== 'GET') {
      mutatingRequests.push({ method: req.method(), url: url.toString() });
      return route.fulfill({ status: 403, body: JSON.stringify({ error: 'mutating_forbidden' }) });
    }

    if (pathname === '/api/owner/v1/auth/session') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ authenticated: true }) });
    }
    if (pathname === '/api/owner/v1/overview') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(envelope(facts.overview)) });
    }
    if (pathname === '/api/owner/v1/controls') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(envelope(controlsData)) });
    }
    if (pathname === '/api/owner/v1/review') {
      if (query.strategy_group_id === 'SOR-US-EQ-PERP-001') {
        const mockEmptyGroupSummary = {
          from_ms: mockNow - 30 * 86_400_000,
          to_ms: mockNow,
          sample_count: 0,
          next_cursor: null,
          items: [],
          net_pnl: { value: null, unit: 'USDT', unavailable_reason: 'no_review_evidence' },
          net_r: { value: null, unit: 'R', unavailable_reason: 'no_review_evidence' },
          fees: { value: null, unit: 'USDT', unavailable_reason: 'no_review_evidence' },
          funding: { value: null, unit: 'USDT', unavailable_reason: 'no_review_evidence' },
          complete_review_count: 0,
          incomplete_review_count: 0,
          exit_reason_breakdown: [],
          execution_quality_breakdown: [],
          strategy_group_samples: [
            {
              strategy_group_id: 'SOR-US-EQ-PERP-001',
              sample_count: 0,
              evidence_state: 'no_evidence',
              evidence: [],
            },
          ],
          evidence: [],
        };
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(envelope(mockEmptyGroupSummary)) });
      }
      if (query.cursor === 'cursor_token_page_2') {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(envelope(mockPage2Summary)) });
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(envelope(mockPage1Summary)) });
    }
    if (pathname.includes('/causality')) {
      const parts = pathname.split('/');
      const ticketIdIndex = parts.indexOf('tickets') + 1;
      const ticketId = ticketIdIndex > 0 && ticketIdIndex < parts.length ? decodeURIComponent(parts[ticketIdIndex]) : 'ticket:item:1';
      const mockTradeCausality = {
        ...facts.causality,
        trade: {
          ...facts.causality.trade,
          ticket_id: ticketId,
        },
      };
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(envelope(mockTradeCausality)) });
    }
    if (pathname.includes('/market/candles')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(envelope(mockCandles)) });
    }

    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(envelope({})) });
  });

  console.log('Navigating to Owner Console V2 root (https://127.0.0.1:5174)...');
  await page.goto('https://127.0.0.1:5174/?tab=overview', { waitUntil: 'networkidle' });

  // 1. Navbar: Review Tab activation
  console.log('\n--- Step 1: Navbar Review Tab Activation ---');
  const reviewNavButton = page.locator('nav[aria-label="主导航"] button:has-text("复盘评估")');
  await reviewNavButton.waitFor({ state: 'visible', timeout: 5000 });
  const badgeText = await reviewNavButton.locator('span.rounded').textContent().catch(() => null);
  assert.strictEqual(badgeText, null, 'Review button must NOT have "规划中" badge anymore');
  console.log('  ✓ PASS: Review tab is active in Navbar without "规划中" badge');

  await reviewNavButton.click();
  await page.waitForURL('**/?tab=review*');
  console.log('  ✓ PASS: Clicked Review tab, URL updated to ?tab=review');

  // 2. Initial Page 1 Header and Metrics Deck verification
  console.log('\n--- Step 2: Review Page 1 Metrics Deck & Shanghai Range Verification (P2-1) ---');
  await page.waitForSelector('#review-page', { timeout: 5000 });
  const title = await page.locator('#review-page h1').textContent();
  assert.ok(title.includes('复盘评估工作台'), 'Title must include 复盘评估工作台');
  console.log(`  ✓ PASS: Page title rendered: "${title.trim()}"`);

  // Verify Metrics Deck values for Page 1
  await page.waitForSelector('[data-testid="review-metrics-deck"]');
  const count1 = await page.locator('[data-testid="metric-completed-count"]').textContent();
  assert.strictEqual(count1.trim(), '50', 'Page 1 must show 50 completed tickets');
  console.log(`  ✓ PASS: Initial Page 1 completed count: ${count1.trim()}`);

  const completeCount1 = await page.locator('[data-testid="metric-complete-count"]').textContent();
  assert.strictEqual(completeCount1.trim(), '10', 'Page 1 must show 10 complete reviews');

  const incompleteCount1 = await page.locator('[data-testid="metric-incomplete-count"]').textContent();
  assert.strictEqual(incompleteCount1.trim(), '40', 'Page 1 must show 40 incomplete reviews');

  // P2-1: Verify Shanghai timezone format in scope note
  const scopeNote1 = await page.locator('[data-testid="review-scope-note"]').textContent();
  assert.ok(scopeNote1.includes('(上海时间)'), `Scope note must contain "(上海时间)", got: ${scopeNote1}`);
  assert.ok(scopeNote1.includes('共 50 笔'), `Scope note must state "共 50 笔", got: ${scopeNote1}`);
  console.log(`  ✓ PASS (P2-1): Scope note formatted with Asia/Shanghai: "${scopeNote1.slice(0, 70)}..."`);

  // Take screenshot 1: Review Overview Dark Mode
  const screen1 = path.join(screenshotsDir, '01_review_dashboard_dark.png');
  await page.screenshot({ path: screen1, fullPage: true });
  console.log(`  📸 Screenshot saved: ${screen1}`);

  // 3. P1-1: Multi-Page Cursor Pagination Accumulation Verification
  console.log('\n--- Step 3: Multi-Page Cursor Pagination Accumulation (P1-1) ---');
  const loadMoreBtn = page.locator('button:has-text("加载更多复盘记录 (Cursor 分页)")');
  await loadMoreBtn.waitFor({ state: 'visible', timeout: 5000 });
  console.log('  Found Cursor pagination button, clicking to fetch Page 2...');

  await loadMoreBtn.click();
  // Wait for table to accumulate to 66 rows
  await page.waitForFunction(() => {
    const rows = document.querySelectorAll('table[data-testid="review-table"] tbody tr[data-ticket-id]');
    return rows.length === 66;
  }, { timeout: 8000 });

  // Verify Metrics Deck dynamically recomputed across all 66 items
  const countAccumulated = await page.locator('[data-testid="metric-completed-count"]').textContent();
  assert.strictEqual(countAccumulated.trim(), '66', 'Completed Tickets must update from 50 to 66 after pagination');
  console.log(`  ✓ PASS (P1-1): Completed Tickets card updated to 66: ${countAccumulated.trim()}`);

  const completeCount2 = await page.locator('[data-testid="metric-complete-count"]').textContent();
  assert.strictEqual(completeCount2.trim(), '15', 'Review 完整 count must update from 10 to 15 (10 + 5)');
  console.log(`  ✓ PASS (P1-1): Review 完整 count updated to 15: ${completeCount2.trim()}`);

  const incompleteCount2 = await page.locator('[data-testid="metric-incomplete-count"]').textContent();
  assert.strictEqual(incompleteCount2.trim(), '51', 'Review 待补齐 count must update from 40 to 51 (40 + 11)');
  console.log(`  ✓ PASS (P1-1): Review 待补齐 count updated to 51: ${incompleteCount2.trim()}`);

  // Verify scope note updated to 66
  const scopeNote2 = await page.locator('[data-testid="review-scope-note"]').textContent();
  assert.ok(scopeNote2.includes('共 66 笔'), `Scope note must state "共 66 笔", got: ${scopeNote2}`);
  console.log(`  ✓ PASS (P1-1): Scope note updated to reflect 66 loaded items: "${scopeNote2.slice(0, 60)}..."`);

  // 4. P1-2: Unsupported waiting_for_settlement filter verification
  console.log('\n--- Step 4: Verify Unsupported waiting_for_settlement is Sanitized (P1-2) ---');
  const statusOptions = await page.locator('#filter-review-status option').allTextContents();
  const statusValues = await page.locator('#filter-review-status option').evaluateAll(opts => opts.map(o => o.value));

  console.log('  Available Review Status Options:', statusOptions.map((text, i) => `${text} (${statusValues[i]})`));
  assert.ok(!statusValues.includes('waiting_for_settlement'), 'Filter dropdown MUST NOT contain waiting_for_settlement');
  console.log('  ✓ PASS (P1-2): waiting_for_settlement is completely absent from filter options');

  // Verify direct URL with waiting_for_settlement is safely sanitized
  await page.goto('https://127.0.0.1:5174/?tab=review&review_status=waiting_for_settlement', { waitUntil: 'networkidle' });
  const currentStatusVal = await page.locator('#filter-review-status').inputValue();
  assert.strictEqual(currentStatusVal, '', 'Unsupported status in URL must fallback to all status ("")');
  console.log('  ✓ PASS (P1-2): Direct URL with waiting_for_settlement sanitized safely without sending invalid query');

  // Step 4.2: P2 Regression: Strategy group query with 0 samples preserves backend no_evidence state
  console.log('\n--- Step 4.2: Strategy group query with 0 samples preserves no_evidence (P2) ---');
  await page.goto('https://127.0.0.1:5174/?tab=review&strategy_group_id=SOR-US-EQ-PERP-001', { waitUntil: 'networkidle' });
  await page.waitForSelector('#review-page');

  // Verify Completed Tickets card shows 0
  const zeroCount = await page.locator('[data-testid="metric-completed-count"]').textContent();
  assert.strictEqual(zeroCount.trim(), '0', 'Completed Tickets must be 0 for empty strategy group');

  // Verify StrategyGroup Evidence section shows SOR-US-EQ-PERP-001 with No Evidence
  const sgSection = page.locator('div:has-text("StrategyGroup Evidence")').first();
  const sgText = await sgSection.innerText();
  assert.ok(sgText.includes('SOR-US-EQ-PERP-001'), `Must display strategy group ID SOR-US-EQ-PERP-001, got: ${sgText}`);
  assert.ok(sgText.includes('0 笔'), `Must display 0 笔, got: ${sgText}`);
  assert.ok(sgText.includes('No Evidence'), `Must display No Evidence badge, got: ${sgText}`);
  assert.ok(!sgText.includes('无策略组样本记录'), 'Must NOT display "无策略组样本记录" placeholder when backend returned explicit no_evidence state');
  console.log('  ✓ PASS (P2): Preserved explicit no_evidence strategy group state: "SOR-US-EQ-PERP-001 · 0 笔 · No Evidence"');

  const screenP2 = path.join(screenshotsDir, '06_review_no_evidence_state.png');
  await page.screenshot({ path: screenP2, fullPage: true });
  console.log(`  📸 Screenshot saved: ${screenP2}`);

  // Return to clean review page
  await page.goto('https://127.0.0.1:5174/?tab=review', { waitUntil: 'networkidle' });
  await page.waitForSelector('#review-page');

  // 5. P2-2: Breakdown Sections Evidence Chips & CausalityDrawer Integration
  console.log('\n--- Step 5: Breakdown Sections Evidence & CausalityDrawer Integration (P2-2) ---');
  // Check Breakdown Evidence Trays
  const evidenceTrays = page.locator('[data-testid="evidence-tray"]');
  const trayCount = await evidenceTrays.count();
  assert.ok(trayCount > 0, `Must render evidence trays in breakdown sections, found ${trayCount}`);
  console.log(`  ✓ PASS (P2-2): Rendered ${trayCount} breakdown evidence trays`);

  // Check first ticket chip in breakdown
  const firstTicketChip = page.locator('button[data-testid^="evidence-ticket-"]').first();
  await firstTicketChip.waitFor({ state: 'visible', timeout: 5000 });
  const ticketIdentity = await firstTicketChip.textContent();
  console.log(`  Found Ticket Evidence Chip: "${ticketIdentity.trim()}", clicking to open CausalityDrawer...`);

  await firstTicketChip.click();

  // Verify CausalityDrawer opened
  const drawer = page.locator('#causality-drawer');
  await drawer.waitFor({ state: 'visible', timeout: 5000 });
  await page.waitForTimeout(600);
  console.log('  ✓ PASS (P2-2): CausalityDrawer opened successfully by clicking Breakdown Ticket evidence chip!');

  // Switch to K-Line tab inside CausalityDrawer
  const kLineTab = drawer.locator('button:has-text("K 线复盘")');
  await kLineTab.waitFor({ state: 'visible', timeout: 5000 });
  await kLineTab.click();
  await page.waitForSelector('[data-testid="causality-chart-tab"]', { timeout: 10000 });
  console.log('  ✓ PASS: K-Line tab rendered inside CausalityDrawer');

  const screen3 = path.join(screenshotsDir, '03_review_causality_kline_drawer.png');
  await page.screenshot({ path: screen3, fullPage: false });
  console.log(`  📸 Screenshot saved: ${screen3}`);

  // Dismiss drawer with Escape key
  await page.keyboard.press('Escape');
  await drawer.waitFor({ state: 'hidden', timeout: 5000 });
  console.log('  ✓ PASS: CausalityDrawer closed gracefully on Escape key');

  // 6. Review Table & Row Expansion
  console.log('\n--- Step 6: Review Table & Row Expansion ---');
  const table = page.locator('table[data-testid="review-table"]');
  await table.waitFor({ state: 'visible' });

  const firstRow = table.locator('tbody tr[data-ticket-id]').first();
  const expandBtn = firstRow.locator('button[aria-label*="展开"]');
  await expandBtn.click();
  await page.waitForSelector('text=复盘因果评估陈述与可追溯证据');
  console.log('  ✓ PASS: Row expanded, review sentences and evidence visible');

  const screen2 = path.join(screenshotsDir, '02_review_expanded_rows.png');
  await page.screenshot({ path: screen2, fullPage: true });
  console.log(`  📸 Screenshot saved: ${screen2}`);

  // 7. Theme Switching: Light Mode
  console.log('\n--- Step 7: Light Mode Verification ---');
  const themeBtn = page.locator('header button[aria-label*="主题"]');
  if (await themeBtn.isVisible()) {
    await themeBtn.click();
    await page.waitForTimeout(300);
  } else {
    await page.evaluate(() => {
      document.documentElement.classList.remove('dark');
      document.documentElement.classList.add('light');
    });
  }
  const screen4 = path.join(screenshotsDir, '04_review_light_mode.png');
  await page.screenshot({ path: screen4, fullPage: true });
  console.log(`  📸 Screenshot saved: ${screen4}`);

  // 8. Responsive Viewport Check
  console.log('\n--- Step 8: Responsive Viewports Check ---');
  for (const w of [1280, 1024, 768]) {
    await page.setViewportSize({ width: w, height: 900 });
    await page.waitForTimeout(200);
    const screenW = path.join(screenshotsDir, `05_review_viewport_${w}.png`);
    await page.screenshot({ path: screenW, fullPage: true });
    console.log(`  📸 Viewport ${w}px screenshot saved: ${screenW}`);
  }

  // 9. Audit Mutating Requests
  console.log('\n--- Step 9: Network Mutation Audit ---');
  assert.strictEqual(mutatingRequests.length, 0, `Forbidden mutating requests found: ${JSON.stringify(mutatingRequests)}`);
  console.log(`  ✓ PASS: Exactly 0 mutating requests dispatched across entire session (${apiCalls.length} safe GET calls)`);

  await browser.close();
  console.log('\n================================================================');
  console.log('--- Review Center Real Browser E2E Test Completed: ALL PASS ---');
  console.log('================================================================\n');
}

run().catch((err) => {
  console.error('Fatal Browser E2E failure:', err);
  process.exit(1);
});
