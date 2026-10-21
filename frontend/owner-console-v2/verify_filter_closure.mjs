// Isolated UI regression tests. All API responses are injected fixtures, never production evidence.
import assert from 'node:assert/strict';
import playwright from '../owner-console/node_modules/@playwright/test/index.js';
const { chromium } = playwright;
const metric = value => ({ value, unit: 'USDT', unavailable_reason: value === null ? 'ticket_active' : null });
const active = {
  ticket_id: 'ticket:qa-active', strategy_group_id: 'BRF2-001', event_spec_id: 'event_spec:qa',
  exchange_instrument_id: 'binance-usdm:ETHUSDT:perpetual', position_side: 'short',
  ticket_status: 'issued', aggregate_status: 'position_protected', lifecycle_stage: 'protection',
  issued_at_ms: 1792400000000, terminal_at_ms: null, completed_stage_count: 3, total_stage_count: 8,
  review_id: null, review_revision: null, economics_completeness: null, exit_reason: null,
  exit_reason_unavailable_reason: 'ticket_active', gross_pnl: metric(null), fees: metric(null),
  funding: metric(null), net_pnl: metric(null), net_r: {...metric(null), unit: 'R'},
  attention_items: [], evidence: [],
};
const terminal = [1,2].map(i => ({...active,ticket_id:`ticket:qa-terminal-${i}`,ticket_status:'terminal',
  aggregate_status:'terminal',lifecycle_stage:'review',terminal_at_ms:1792410000000,
  exit_reason:'stop',exit_reason_unavailable_reason:null,net_pnl:metric('2.00'),net_r:{...metric('1'),unit:'R'}}));
const summary = {
  strategy_group_id:'BRF2-001',strategy_group_display_name:'QA bear rally failure',
  strategy_version_id:'sgv:BRF2-001:v3',version:3,strategy_version_status:'active',is_current:true,
  ticket_count:2,natural_terminal_count:2,confirmed_natural_review_count:2,pending_natural_review_count:0,
  controlled_exit_count:0,tp1_reached_count:2,tp1_not_reached_count:0,win_count:2,loss_count:0,
  net_pnl:metric('4'),net_r:{...metric('2'),unit:'R'},observation_count:0,completed_observation_count:0,
  unavailable_observation_count:0,tp1_first_count:0,initial_stop_first_count:0,ambiguous_observation_count:0,
  opening_range_failure_count:0,time_stop_count:0,session_exit_count:0,median_mfe_r:null,median_mae_r:null,
  median_spread_bps:null,evidence:[],product_events:[],
};
const facts = {overview:{active_ticket_count:1,active_ticket_ids:[active.ticket_id]},
  tickets:{items:[active,...terminal],next_cursor:null},strategies:{items:[summary]},
  causality:{trade:active,price_plan:{},current_stage:'protection',stages:[],annotations:[],raw_events:[],raw_commands:[],evidence:[]}};
const controls = {
  generated_at_ms:1792400000000,
  global_entry:{configured_state:'enabled',effective_state:'enabled',policy_version:1,active_ticket_count:1,first_blocker:null},
  runtime_entry_authority:{effective_status:'ready',exchange_commands_enabled:false,first_blocker:null,runtime_profile_ids:[]},
  account_capacity:{active_ticket_count:1,max_concurrent_tickets:3,remaining_ticket_slots:2,
    max_same_strategy_side:2,strategy_side_active_counts:{'BRF2-001:short':1},family_active_counts:{},family_limits:{}},
  strategies:[{strategy_group_id:'BRF2-001',entry_state:'enabled',configured_state:'enabled',effective_state:'enabled',
    control_version:1,reason:'qa',updated_at_ms:1792400000000,last_event_id:'qa'}],recent_operations:[],current_operation:null,
};
const envelope = data => ({ data, freshness: 'fresh', generated_at: new Date().toISOString() });
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
let failures = 0;
let total = 0;
async function scenario(name, test, overrides = {}) {
  total++;
  const context = await browser.newContext({ ignoreHTTPSErrors: true, timezoneId: 'UTC' });
  const page = await context.newPage();
  page.setDefaultTimeout(3500);
  const calls = [];
  const state = { failRefresh: false, failPage: false };
  await context.route('**/api/owner/v1/**', async route => {
    const url = new URL(route.request().url());
    assert.equal(route.request().method(), 'GET', 'Tests must perform zero writes');
    calls.push(url);
    const reply = (data, status = 200) => route.fulfill({status, contentType:'application/json', body:JSON.stringify(data)});
    if (url.pathname.endsWith('/auth/session')) return reply({ authenticated: true });
    if (url.pathname.endsWith('/overview')) return reply(envelope({ ...facts.overview, active_ticket_ids: [active.ticket_id], active_ticket_count: 1 }));
    if (url.pathname.endsWith('/controls')) return reply({ ...controls, account_capacity: { ...controls.account_capacity, active_ticket_count: 1 } });
    if (url.pathname.endsWith('/causality')) {
      if (overrides.causalityFailure) return reply({error:{code:'qa_identity',message:'Injected identity failure'}},500);
      const id = decodeURIComponent(url.pathname.split('/').at(-2));
      return reply(envelope({ ...facts.causality, trade: { ...active, ticket_id: id } }));
    }
    if (overrides.route && await overrides.route(url, reply, state)) return;
    if (url.pathname.endsWith('/tickets') && !url.pathname.includes('/strategies/')) {
      if (state.failRefresh) return reply({error:{code:'qa_refresh',message:'Injected refresh failure'}},500);
      return reply(envelope(url.searchParams.get('range') === 'empty' ? {items:[],next_cursor:null} : facts.tickets));
    }
    if (url.pathname.endsWith('/strategies')) return reply(envelope(facts.strategies));
    if (url.pathname.endsWith('/selection')) return reply({error:{code:'unsupported',message:'No selection fixture'}},422);
    return reply(envelope({ items: [], next_cursor: null }));
  });
  try {
    await test(page, calls, state);
    console.log('PASS', name);
  } catch (error) { failures++; console.error('FAIL', name, error.message); }
  finally { await context.close(); }
}
const goto = async (page, query = 'tab=trades') => {
  await page.goto(`https://127.0.0.1:5174/?${query}`);
  await page.locator(query.includes('tab=trades') ? '[data-testid=trades-filter-bar]' : '[data-testid=strategies-time-range-bar]').waitFor();
};
try {
  console.log('[MOCKED UI INTEGRATION] Full historical filter closure');
  await scenario('custom dates use a draft and atomically apply a distant valid window', async page => {
    await goto(page);
    await page.getByRole('button', {name:'自定义',exact:true}).click();
    await page.getByLabel('自定义开始时间').fill('2026-06-01T00:00');
    assert.equal(await page.getByLabel('自定义开始时间').inputValue(), '2026-06-01T00:00');
    await page.getByLabel('自定义结束时间').fill('2026-06-02T00:00');
    await page.getByRole('button', {name:'应用时间范围',exact:true}).click();
    await page.waitForURL(u => u.searchParams.get('range') === 'custom');
    assert.equal(Number(new URL(page.url()).searchParams.get('from_ms')), Date.parse('2026-06-01T00:00:00+08:00'));
    await page.getByLabel('自定义结束时间').fill('2026-10-01T00:00');
    await page.getByRole('button', {name:'应用时间范围',exact:true}).click();
    assert.match(await page.getByRole('alert').innerText(), /90 天/);
    assert.equal(Number(new URL(page.url()).searchParams.get('to_ms')), Date.parse('2026-06-02T00:00:00+08:00'));
  });
  await scenario('refresh failure preserves data but exposes error and stale status', async (page, calls, state) => {
    await goto(page);
    const before = await page.locator('[data-testid=metric-total-trades] [data-testid=metric-value]').innerText();
    state.failRefresh = true;
    await page.getByRole('button', {name:'刷新',exact:true}).click();
    await page.getByText(/刷新失败.*旧快照/).waitFor({timeout:3000});
    assert.equal(await page.locator('[data-testid=metric-total-trades] [data-testid=metric-value]').innerText(), before);
    assert.ok(!(await page.locator('#trades-page').innerText()).includes('\nFRESH\n'));
  });
  await scenario('history window cannot hide current active identities', async page => {
    await goto(page, 'tab=trades&range=custom&from_ms=1780243200000&to_ms=1780329600000');
    await page.locator(`[data-testid=active-trade-episodes] [data-ticket-id="${active.ticket_id}"]`).waitFor({timeout:3000});
    assert.match(await page.locator('[data-testid=active-coverage]').innerText(), /不受历史/);
    assert.equal(await page.locator('[data-testid=metric-total-trades] [data-testid=metric-value]').innerText(), '0');
  }, {route: async (url, reply) => {
    if (url.pathname === '/api/owner/v1/tickets') { await reply(envelope({items:[],next_cursor:null})); return true; }
  }});
  await scenario('history first-page error does not hide live cards', async page => {
    await goto(page);
    await page.locator(`[data-testid=active-trade-episodes] [data-ticket-id="${active.ticket_id}"]`).waitFor();
    assert.match(await page.getByRole('alert').innerText(), /无法连接 Tickets API/);
    assert.equal(await page.locator('[data-testid=trades-metrics-ribbon]').count(), 0);
  }, {route: async (url, reply) => {
    if (url.pathname !== '/api/owner/v1/tickets') return false;
    await reply({error:{code:'qa_history',message:'Injected history failure'}},500); return true;
  }});
  await scenario('failed live identity cannot be presented as an empty account', async page => {
    await goto(page);
    await page.getByText(/实时身份读取或刷新失败/).waitFor();
    assert.match(await page.locator('[data-testid=active-trade-episodes]').innerText(), /覆盖尚未确认/);
    assert.equal(await page.getByText('当前无在管交易', {exact:true}).count(), 0);
  }, {causalityFailure:true});
  await scenario('overlapping pages dedupe, preserve failed page and reset cursor', async (page, calls, state) => {
    await goto(page, 'tab=trades&from_ms=1780243200000&to_ms=1780329600000');
    state.failPage = true;
    await page.locator('[data-testid=load-more-btn]').click();
    await page.locator('[data-testid=pagination-error]').waitFor();
    assert.equal(await page.locator('[data-testid=metric-total-trades] [data-testid=metric-value]').innerText(), '1');
    state.failPage = false;
    await page.locator('[data-testid=load-more-btn]').click();
    await page.locator('[data-testid=trades-pagination-status]').waitFor();
    assert.equal(await page.locator('[data-testid=metric-total-trades] [data-testid=metric-value]').innerText(), '2');
    await page.locator('#filter-position-side').selectOption('short');
    await page.waitForResponse(r => r.url().includes('position_side=short'));
    const relevant = calls.filter(u => u.pathname === '/api/owner/v1/tickets' && u.searchParams.has('from_ms'));
    assert.ok(relevant.every(u => u.searchParams.get('from_ms') === '1780243200000' && u.searchParams.get('to_ms') === '1780329600000'));
    assert.equal(relevant.at(-1).searchParams.get('cursor'), null);
  }, {route: async (url, reply, state) => {
    if (url.pathname !== '/api/owner/v1/tickets') return false;
    if (url.searchParams.has('cursor') && state.failPage) await reply({error:{code:'qa_page',message:'Injected page failure'}},500);
    else await reply(envelope({items:url.searchParams.has('cursor') ? terminal.slice(0,2) : terminal.slice(0,1),next_cursor:url.searchParams.has('cursor')?null:'next'}));
    return true;
  }});
  await scenario('historical versions do not multiply account current capacity; Shanghai labels fixed', async page => {
    await goto(page, 'tab=strategies&view=all&range=7d&from_ms=1791874800000&to_ms=1792479600000');
    await page.locator('tr[data-strategy-version-id]').first().waitFor();
    assert.equal(await page.locator('[data-testid=strategies-active-count]').innerText(), '1');
    assert.equal(await page.getByRole('columnheader', {name:'30天自然净盈亏',exact:true}).count(), 0);
    assert.match(await page.locator('[data-testid=strategies-time-range-bar]').innerText(), /15:00/);
    const old = page.locator('tr[data-strategy-version-id="sgv:BRF2-001:v2"]');
    assert.match(await old.innerText(), /历史版本.*不归属当前/);
  }, {route: async (url, reply) => {
    if (url.pathname !== '/api/owner/v1/strategies') return false;
    const current = facts.strategies.items.find(s => s.strategy_group_id === 'BRF2-001');
    await reply(envelope({...facts.strategies,items:[current,{...current,is_current:false,version:2,strategy_version_id:'sgv:BRF2-001:v2'}]})); return true;
  }});
  await scenario('Natural filtered-empty page failure retries the failed cursor', async (page, calls, state) => {
    state.failPage = true;
    await goto(page, 'tab=strategies&strategy_version_id=sgv%3ABRF2-001%3Av3&drawer_tab=tickets');
    await page.getByRole('button', {name:'加载更多 Ticket (Next Cursor)',exact:true}).click();
    await page.getByText(/加载下一页失败/).waitFor({timeout:3000});
    state.failPage = false;
    await page.getByRole('button', {name:'重试',exact:true}).click();
    await page.getByText('QA retry terminal', {exact:true}).waitFor({timeout:3000});
    assert.equal(calls.filter(u=>u.pathname.endsWith('/tickets')&&u.pathname.includes('/strategies/')).at(-1).searchParams.get('cursor'), 'next');
  }, {route: async (url, reply, state) => {
    if (!url.pathname.includes('/strategies/') || !url.pathname.endsWith('/tickets')) return false;
    if (url.searchParams.has('cursor') && state.failPage) await reply({error:{code:'qa_page',message:'Injected page failure'}},500);
    else await reply(envelope({items:[url.searchParams.has('cursor')?{...terminal[0],evaluation_path:'tp1_reached',exit_reason:'QA retry terminal'}:{...active,evaluation_path:'not_terminal'}],next_cursor:url.searchParams.has('cursor')?null:'next'}));
    return true;
  }});
} finally { await browser.close(); }
if (failures) process.exitCode = 1;
console.log(`Closure scenarios: ${total-failures} passed, ${failures} failed`);
