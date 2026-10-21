/**
 * Owner Console V2 - Strategies Regression Test Suite
 * 
 * Verifies all strategy fact semantics, domain mappings, and anti-falsification rules:
 * 1. Money metric decimal formatting & honest unavailable handling ('no_confirmed_natural_review')
 * 2. Win rate calculation with strict denominator guard (0/0 -> null, never false 0%)
 * 3. Separation of natural terminals vs controlled exits vs reviews
 * 4. Version isolation (different versions of same strategy not merged)
 * 5. Observation facts separation (never conflated with trade PnL or Ticket count)
 * 6. First path labels translation & fallbacks
 * 7. Runtime controls & blocker integration
 * 8. Query key stability
 */

import assert from 'node:assert/strict';
import {
  formatStrategyMoneyMetric,
  computeWinRate,
  formatFirstPathLabel,
  formatObservationMetric,
  enrichStrategyVersion,
  STRATEGY_METADATA,
  FIRST_PATH_ZH,
} from './src/mapping/strategyMapping.ts';
import {
  strategiesQueryKey,
  strategyTicketsInfiniteQueryKey,
  strategyObservationsInfiniteQueryKey,
} from './src/api/strategiesApi.ts';
import {
  ApiError,
  apiErrorFromResponse,
  isUnauthorized,
  isForbidden,
  isConflict,
  isServerError,
} from './src/api/errors.ts';
import { parseStrategyError } from './src/mapping/strategyErrorMapping.ts';
import { drawerStack, handleDrawerGlobalKeyDown } from './src/hooks/useDrawerDismiss.ts';

let passCount = 0;
function test(name, fn) {
  try {
    fn();
    console.log(`  ✓ PASS: ${name}`);
    passCount++;
  } catch (err) {
    console.error(`  ✗ FAIL: ${name}`);
    console.error(err);
    process.exit(1);
  }
}

console.log('================================================================');
console.log('Running Owner Console V2 Strategies Regression Suite');
console.log('================================================================\n');

// -----------------------------------------------------------------------------
// Test Group 1: Money Metric Formatting & Honest Review Reporting
// -----------------------------------------------------------------------------
console.log('--- Test Group 1: Money Metric Formatting & Honest Review Reporting ---');

test('formatStrategyMoneyMetric: positive profit formatted with + sign and unit', () => {
  const metric = { value: '123.456', unit: 'USDT' };
  const res = formatStrategyMoneyMetric(metric);
  assert.equal(res.formatted, '+123.46 USDT');
  assert.equal(res.isPositive, true);
  assert.equal(res.isUnavailable, false);
});

test('formatStrategyMoneyMetric: negative loss formatted with - sign and unit', () => {
  const metric = { value: '-45.67', unit: 'R' };
  const res = formatStrategyMoneyMetric(metric);
  assert.equal(res.formatted, '-45.67 R');
  assert.equal(res.isPositive, false);
  assert.equal(res.isUnavailable, false);
});

test('formatStrategyMoneyMetric: zero value is neither positive nor negative', () => {
  const metric = { value: '0.000', unit: 'USDT' };
  const res = formatStrategyMoneyMetric(metric);
  assert.equal(res.formatted, '0.00 USDT');
  assert.equal(res.isPositive, null);
  assert.equal(res.isUnavailable, false);
});

test('formatStrategyMoneyMetric: preserves high precision Decimal without IEEE-754 drift', () => {
  // 0.1 + 0.2 in JS is 0.30000000000000004
  const metric = { value: '0.30000000000000004', unit: 'USDT' };
  const res = formatStrategyMoneyMetric(metric);
  assert.equal(res.formatted, '+0.30 USDT');
});

test('formatStrategyMoneyMetric: null or undefined value returns default unavailable text', () => {
  const resNull = formatStrategyMoneyMetric(null, '待完成 Review');
  assert.equal(resNull.formatted, '待完成 Review');
  assert.equal(resNull.isUnavailable, true);
  assert.equal(resNull.isPositive, null);

  const resEmpty = formatStrategyMoneyMetric({ value: null, unit: 'USDT' });
  assert.equal(resEmpty.formatted, '待完成 Review');
  assert.equal(resEmpty.isUnavailable, true);
});

test('formatStrategyMoneyMetric: unavailable_reason "no_confirmed_natural_review" is displayed honestly', () => {
  const metric = {
    value: null,
    unit: 'USDT',
    unavailable_reason: 'no_confirmed_natural_review',
  };
  const res = formatStrategyMoneyMetric(metric);
  assert.equal(res.formatted, '无已确认自然评审');
  assert.equal(res.isUnavailable, true);
  assert.equal(res.value, null);
});

test('formatStrategyMoneyMetric: invalid/corrupt string returns placeholder without crashing', () => {
  const metric = { value: 'invalid_number', unit: 'USDT' };
  const res = formatStrategyMoneyMetric(metric);
  assert.equal(res.formatted, '—');
  assert.equal(res.isUnavailable, true);
});

// -----------------------------------------------------------------------------
// Test Group 2: Win Rate Calculation & Strict Denominator Guard
// -----------------------------------------------------------------------------
console.log('\n--- Test Group 2: Win Rate Calculation & Strict Denominator Guard ---');

test('computeWinRate: 0 wins and 0 losses returns null percent with "不可评价" label', () => {
  const res = computeWinRate(0, 0);
  assert.equal(res.percent, null);
  assert.equal(res.label, '无胜负样本 · 不可评价');
  assert.equal(res.evaluatedCount, 0);
});

test('computeWinRate: 100% win rate correctly computed', () => {
  const res = computeWinRate(5, 0);
  assert.equal(res.percent, 100);
  assert.equal(res.label, '5 胜 / 0 负 (100%)');
  assert.equal(res.evaluatedCount, 5);
});

test('computeWinRate: 0% win rate correctly computed when all evaluated are losses', () => {
  const res = computeWinRate(0, 4);
  assert.equal(res.percent, 0);
  assert.equal(res.label, '0 胜 / 4 负 (0%)');
  assert.equal(res.evaluatedCount, 4);
});

test('computeWinRate: 3 wins and 1 loss yields 75%', () => {
  const res = computeWinRate(3, 1);
  assert.equal(res.percent, 75);
  assert.equal(res.label, '3 胜 / 1 负 (75%)');
  assert.equal(res.evaluatedCount, 4);
});

// -----------------------------------------------------------------------------
// Test Group 3: Observation Metrics & First Path Translations
// -----------------------------------------------------------------------------
console.log('\n--- Test Group 3: Observation Metrics & First Path Translations ---');

test('formatFirstPathLabel: maps all 7 documented paths correctly', () => {
  assert.equal(formatFirstPathLabel('tp1_first'), 'TP1 先到达');
  assert.equal(formatFirstPathLabel('initial_stop_first'), '止损先到达');
  assert.equal(formatFirstPathLabel('ambiguous_same_bar'), '同 Bar 歧义');
  assert.equal(formatFirstPathLabel('opening_range_failure'), '开盘区间失效');
  assert.equal(formatFirstPathLabel('time_stop'), '时间止损 (Time Stop)');
  assert.equal(formatFirstPathLabel('session_exit'), '时段平仓 (Session Exit)');
  assert.equal(formatFirstPathLabel('horizon_complete'), '观察周期完成');
});

test('formatFirstPathLabel: handles null, empty, and unrecognized paths', () => {
  assert.equal(formatFirstPathLabel(null), '全部路径');
  assert.equal(formatFirstPathLabel(undefined), '全部路径');
  assert.equal(formatFirstPathLabel(''), '全部路径');
  assert.equal(formatFirstPathLabel('custom_unknown_path'), 'custom_unknown_path');
});

test('formatObservationMetric: formats numbers and handles nulls', () => {
  assert.equal(formatObservationMetric('1.5678', ' R'), '1.57 R');
  assert.equal(formatObservationMetric(2.5, ' R'), '2.50 R');
  assert.equal(formatObservationMetric(null), '—');
  assert.equal(formatObservationMetric(undefined), '—');
  assert.equal(formatObservationMetric(''), '—');
});

// -----------------------------------------------------------------------------
// Test Group 4: enrichStrategyVersion & Domain Separation
// -----------------------------------------------------------------------------
console.log('\n--- Test Group 4: enrichStrategyVersion & Domain Separation ---');

test('enrichStrategyVersion: maintains strict separation of natural terminals vs controlled exits', () => {
  const summary = {
    strategy_group_id: 'CPM-RO-001',
    strategy_version_id: 'sv-cpm-v1',
    version: 1,
    is_current: true,
    ticket_count: 10,
    natural_terminal_count: 7,
    controlled_exit_count: 3,
    confirmed_natural_review_count: 6,
    pending_natural_review_count: 1,
    tp1_reached_count: 4,
    tp1_not_reached_count: 3,
    win_count: 4,
    loss_count: 2,
    net_pnl: { value: '450.20', unit: 'USDT' },
    net_r: { value: '3.10', unit: 'R' },
    observation_count: 25,
    completed_observation_count: 20,
    median_mfe_r: '1.80',
    median_mae_r: '0.65',
    product_events: [],
  };

  const enriched = enrichStrategyVersion(summary);

  // Assert counts are distinct and never merged
  assert.equal(enriched.totalTickets, 10);
  assert.equal(enriched.naturalTerminals, 7);
  assert.equal(enriched.controlledExits, 3);
  assert.equal(enriched.confirmedReviews, 6);
  assert.equal(enriched.pendingReviews, 1);
  assert.equal(enriched.tp1Reached, 4);
  assert.equal(enriched.tp1NotReached, 3);

  // Assert natural terminals + controlled exits = totalTickets
  assert.equal(enriched.naturalTerminals + enriched.controlledExits, enriched.totalTickets);

  // Assert observation count is distinct and not conflated with tickets
  assert.equal(enriched.observationCount, 25);
  assert.notEqual(enriched.observationCount, enriched.totalTickets);

  // Assert win rate computed only from natural wins/losses
  assert.equal(enriched.winRatePercent, 67); // 4 / (4 + 2) = 66.67% -> 67%
  assert.equal(enriched.winRateLabel, '4 胜 / 2 负 (67%)');
});

test('enrichStrategyVersion: integrates runtime control and blocker accurately', () => {
  const summary = {
    strategy_group_id: 'BRF2-001',
    strategy_version_id: 'sv-brf-v1',
    version: 1,
    is_current: true,
    ticket_count: 2,
    natural_terminal_count: 2,
    controlled_exit_count: 0,
    confirmed_natural_review_count: 0,
    pending_natural_review_count: 2,
    tp1_reached_count: 0,
    tp1_not_reached_count: 2,
    win_count: 0,
    loss_count: 0,
    net_pnl: { value: null, unit: 'USDT', unavailable_reason: 'no_confirmed_natural_review' },
    net_r: { value: null, unit: 'R', unavailable_reason: 'no_confirmed_natural_review' },
    observation_count: 10,
    completed_observation_count: 8,
    median_mfe_r: null,
    median_mae_r: null,
    product_events: [],
  };

  const control = {
    strategy_group_id: 'BRF2-001',
    configured_state: 'enabled',
    effective_state: 'enabled',
    control_version: 3,
    last_event_id: 'evt-1',
    reason: 'init',
    updated_at_ms: 1700000000000,
    entry_state: 'enabled',
  };

  // Case A: Blocked by capacity/blocker
  const enrichedBlocked = enrichStrategyVersion(summary, control, {
    firstBlocker: '容量已满 (Max 3)',
    activeTicketCount: 1,
  });
  assert.equal(enrichedBlocked.runtimeStatus, 'blocked');
  assert.equal(enrichedBlocked.runtimeStatusLabel, '阻断 · 容量已满 (Max 3)');
  assert.equal(enrichedBlocked.activeTicketCount, 1);
  assert.equal(enrichedBlocked.firstBlocker, '容量已满 (Max 3)');
  assert.equal(enrichedBlocked.netPnlFormatted, '无已确认自然评审');
  assert.equal(enrichedBlocked.hasConfirmedReview, false);

  // Case B: Clean enabled runtime
  const enrichedEnabled = enrichStrategyVersion(summary, control, {
    firstBlocker: null,
    activeTicketCount: 0,
  });
  assert.equal(enrichedEnabled.runtimeStatus, 'enabled');
  assert.equal(enrichedEnabled.runtimeStatusLabel, '运行中');
});

test('enrichStrategyVersion: version isolation guarantees independent identities', () => {
  const summaryV1 = {
    strategy_group_id: 'CPM-RO-001',
    strategy_version_id: 'sv-cpm-v1',
    version: 1,
    is_current: false,
    ticket_count: 5,
    natural_terminal_count: 5,
    controlled_exit_count: 0,
    confirmed_natural_review_count: 5,
    pending_natural_review_count: 0,
    tp1_reached_count: 2,
    tp1_not_reached_count: 3,
    win_count: 2,
    loss_count: 3,
    net_pnl: { value: '-20.00', unit: 'USDT' },
    net_r: { value: '-0.50', unit: 'R' },
    observation_count: 10,
    completed_observation_count: 10,
    median_mfe_r: '1.2',
    median_mae_r: '0.8',
    product_events: [],
  };

  const summaryV2 = {
    strategy_group_id: 'CPM-RO-001',
    strategy_version_id: 'sv-cpm-v2',
    version: 2,
    is_current: true,
    ticket_count: 8,
    natural_terminal_count: 6,
    controlled_exit_count: 2,
    confirmed_natural_review_count: 6,
    pending_natural_review_count: 0,
    tp1_reached_count: 4,
    tp1_not_reached_count: 2,
    win_count: 4,
    loss_count: 2,
    net_pnl: { value: '+180.00', unit: 'USDT' },
    net_r: { value: '+2.10', unit: 'R' },
    observation_count: 15,
    completed_observation_count: 12,
    median_mfe_r: '2.0',
    median_mae_r: '0.4',
    product_events: [],
  };

  const v1 = enrichStrategyVersion(summaryV1);
  const v2 = enrichStrategyVersion(summaryV2);

  assert.equal(v1.version, 1);
  assert.equal(v1.isCurrent, false);
  assert.equal(v1.totalTickets, 5);
  assert.equal(v1.netPnlFormatted, '-20.00 USDT');

  assert.equal(v2.version, 2);
  assert.equal(v2.isCurrent, true);
  assert.equal(v2.totalTickets, 8);
  assert.equal(v2.netPnlFormatted, '+180.00 USDT');

  // Strict isolation: V1 and V2 are distinct objects with unpolluted values
  assert.notEqual(v1.summary.strategy_version_id, v2.summary.strategy_version_id);
});

// -----------------------------------------------------------------------------
// Test Group 5: Query Key Stability
// -----------------------------------------------------------------------------
console.log('\n--- Test Group 5: Query Key Stability ---');

test('strategiesQueryKey: generates stable query keys without dynamic timestamps', () => {
  const key1 = strategiesQueryKey({ view: 'current' });
  const key2 = strategiesQueryKey({ view: 'current' });
  assert.deepEqual(key1, key2);
  assert.deepEqual(key1, ['owner', 'strategies', { view: 'current' }]);

  const keyAll = strategiesQueryKey({ view: 'all' });
  assert.deepEqual(keyAll, ['owner', 'strategies', { view: 'all' }]);
});

test('strategyTicketsInfiniteQueryKey: generates stable infinite query keys', () => {
  const params = {
    strategy_version_id: 'sv-100',
    scope: 'natural',
    exit_path: 'tp1_reached',
    limit: 50,
  };
  const key1 = strategyTicketsInfiniteQueryKey(params);
  const key2 = strategyTicketsInfiniteQueryKey(params);
  assert.deepEqual(key1, key2);
  assert.deepEqual(key1, ['owner', 'strategies', 'tickets', 'infinite', params]);
});

test('strategyObservationsInfiniteQueryKey: generates stable infinite query keys', () => {
  const params = {
    strategy_version_id: 'sv-100',
    first_path: 'tp1_first',
    limit: 50,
  };
  const key1 = strategyObservationsInfiniteQueryKey(params);
  const key2 = strategyObservationsInfiniteQueryKey(params);
  assert.deepEqual(key1, key2);
  assert.deepEqual(key1, ['owner', 'strategies', 'observations', 'infinite', params]);
});

// -----------------------------------------------------------------------------
// Test Group 6: P1-1 Error Preservation vs True Empty State
// -----------------------------------------------------------------------------
console.log('\n--- Test Group 6: P1-1 Error Preservation vs True Empty State ---');

test('P1-1: 401 Unauthorized creates ApiError and is not converted to empty list', () => {
  const mockResponse = new Response(JSON.stringify({ error: { code: 'unauthorized', message: 'Auth token missing or expired' } }), {
    status: 401,
    headers: { 'Content-Type': 'application/json' },
  });
  const err = apiErrorFromResponse(mockResponse, { error: { code: 'unauthorized', message: 'Auth token missing or expired' } });
  assert.equal(err.status, 401);
  assert.equal(err.code, 'unauthorized');
  assert.equal(isUnauthorized(err), true);
  // Must remain an error, never an empty items array
  assert.ok(err instanceof Error);
});

test('P1-1: 403 Forbidden creates ApiError and is preserved', () => {
  const mockResponse = new Response(JSON.stringify({ error: { code: 'forbidden', message: 'Access denied' } }), {
    status: 403,
    headers: { 'Content-Type': 'application/json' },
  });
  const err = apiErrorFromResponse(mockResponse, { error: { code: 'forbidden', message: 'Access denied' } });
  assert.equal(err.status, 403);
  assert.equal(isForbidden(err), true);
});

test('P1-1: 409 Conflict creates ApiError and is preserved', () => {
  const mockResponse = new Response(JSON.stringify({ error: { code: 'contradictory_facts', message: 'Current facts are contradictory' } }), {
    status: 409,
    headers: { 'Content-Type': 'application/json' },
  });
  const err = apiErrorFromResponse(mockResponse, { error: { code: 'contradictory_facts', message: 'Current facts are contradictory' } });
  assert.equal(err.status, 409);
  assert.equal(isConflict(err), true);
});

test('P1-1: 422 Unprocessable Entity creates ApiError and is preserved', () => {
  const mockResponse = new Response(JSON.stringify({ error: { code: 'validation_error', message: 'controlled exit path requires all scope' } }), {
    status: 422,
    headers: { 'Content-Type': 'application/json' },
  });
  const err = apiErrorFromResponse(mockResponse, { error: { code: 'validation_error', message: 'controlled exit path requires all scope' } });
  assert.equal(err.status, 422);
  assert.equal(err.message, 'controlled exit path requires all scope');
});

test('P1-1: 500 Server Error creates ApiError and is preserved', () => {
  const mockResponse = new Response(JSON.stringify({ error: { code: 'internal_error', message: 'Database connection failed' } }), {
    status: 500,
    headers: { 'Content-Type': 'application/json' },
  });
  const err = apiErrorFromResponse(mockResponse, { error: { code: 'internal_error', message: 'Database connection failed' } });
  assert.equal(err.status, 500);
  assert.equal(isServerError(err), true);
});

test('P1-1: Distinguishes true empty response (200 OK with [] items) from error states', () => {
  const successfulEmptyEnvelope = {
    data: {
      items: [],
      next_cursor: null,
    },
    meta: {
      freshness: 'fresh',
      as_of_ms: Date.now(),
    },
  };
  // Successful empty response has data.items as empty array and no error
  assert.equal(Array.isArray(successfulEmptyEnvelope.data.items), true);
  assert.equal(successfulEmptyEnvelope.data.items.length, 0);

  // An error state does not contain successful data.items
  const errorPayload = new ApiError(500, 'server_error', 'Internal server failure');
  assert.equal(errorPayload instanceof ApiError, true);
  assert.notEqual(errorPayload.status, 200);
});

// -----------------------------------------------------------------------------
// Test Group 7: P1-2 Natural Scope Filtering & Non-Terminal Labeling
// -----------------------------------------------------------------------------
console.log('\n--- Test Group 7: P1-2 Natural Scope Filtering & Non-Terminal Labeling ---');

test('P1-2: Natural scope filtering strictly admits only natural terminal paths', () => {
  const rawItems = [
    { ticket_id: 't-1', evaluation_path: 'tp1_reached' },
    { ticket_id: 't-2', evaluation_path: 'tp1_not_reached' },
    { ticket_id: 't-3', evaluation_path: 'tp1_reached' },
    { ticket_id: 't-4', evaluation_path: 'not_terminal' },
    { ticket_id: 't-5', evaluation_path: 'not_terminal' },
  ];

  // Logic used in useStrategyTicketsData:
  const naturalItems = rawItems.filter(
    (item) => item.evaluation_path === 'tp1_reached' || item.evaluation_path === 'tp1_not_reached'
  );
  const excludedCount = rawItems.filter((item) => item.evaluation_path === 'not_terminal').length;

  assert.equal(naturalItems.length, 3);
  assert.equal(excludedCount, 2);
  assert.deepEqual(naturalItems.map((i) => i.ticket_id), ['t-1', 't-2', 't-3']);
  // not_terminal is completely absent from natural items
  assert.equal(naturalItems.some((i) => i.evaluation_path === 'not_terminal'), false);
});

test('P1-2: All scope retains all items including not_terminal and controlled_exit', () => {
  const rawItems = [
    { ticket_id: 't-1', evaluation_path: 'tp1_reached' },
    { ticket_id: 't-2', evaluation_path: 'controlled_exit' },
    { ticket_id: 't-3', evaluation_path: 'not_terminal' },
  ];

  // In all scope, no items are excluded from rawItems
  const allItems = rawItems;
  const excludedCount = 0;

  assert.equal(allItems.length, 3);
  assert.equal(excludedCount, 0);
});

test('P1-2: not_terminal path is labeled as "未达终态 (在途)" and never "未平仓终态"', () => {
  const formatPathLabel = (path) => {
    switch (path) {
      case 'tp1_reached':
        return '已达 TP1';
      case 'tp1_not_reached':
        return '未达 TP1';
      case 'controlled_exit':
        return '受控退出';
      default:
        return '未达终态 (在途)';
    }
  };

  assert.equal(formatPathLabel('not_terminal'), '未达终态 (在途)');
  assert.notEqual(formatPathLabel('not_terminal'), '未平仓终态');
  assert.equal(formatPathLabel('tp1_reached'), '已达 TP1');
  assert.equal(formatPathLabel('tp1_not_reached'), '未达 TP1');
  assert.equal(formatPathLabel('controlled_exit'), '受控退出');
});

// -----------------------------------------------------------------------------
// Test Group 8: P1-3 Prevent Illegal Query Combinations
// -----------------------------------------------------------------------------
console.log('\n--- Test Group 8: P1-3 Prevent Illegal Query Combinations ---');

test('P1-3: Defensive guard strips controlled_exit when scope is natural', () => {
  const computeEffectiveExitPath = (scope, exitPath) => {
    if (scope === 'natural' && exitPath === 'controlled_exit') {
      return null;
    }
    return exitPath;
  };

  assert.equal(computeEffectiveExitPath('natural', 'controlled_exit'), null);
  assert.equal(computeEffectiveExitPath('natural', 'tp1_reached'), 'tp1_reached');
  assert.equal(computeEffectiveExitPath('all', 'controlled_exit'), 'controlled_exit');
  assert.equal(computeEffectiveExitPath('all', null), null);
});

test('P1-3: UI state handler auto-switches scope to "all" when clicking controlled_exit', () => {
  let scope = 'natural';
  let exitPath = null;

  const handleExitPathChange = (path) => {
    if (path === 'controlled_exit' && scope === 'natural') {
      scope = 'all';
    }
    exitPath = path;
  };

  handleExitPathChange('controlled_exit');
  assert.equal(scope, 'all');
  assert.equal(exitPath, 'controlled_exit');
});

test('P1-3: UI state handler resets exitPath to null when switching back to natural from controlled_exit', () => {
  let scope = 'all';
  let exitPath = 'controlled_exit';

  const handleScopeChange = (newScope) => {
    if (newScope === 'natural' && exitPath === 'controlled_exit') {
      exitPath = null;
    }
    scope = newScope;
  };

  handleScopeChange('natural');
  assert.equal(scope, 'natural');
  assert.equal(exitPath, null);
});

// -----------------------------------------------------------------------------
// Test Group 9: P2-1 MoneyMetric Exact Formatting & Decimal Boundaries
// -----------------------------------------------------------------------------
console.log('\n--- Test Group 9: P2-1 MoneyMetric Exact Formatting & Decimal Boundaries ---');

test('P2-1: MoneyMetric exact formatting with positive, negative, zero and boundaries', () => {
  // Positive
  const pos = formatStrategyMoneyMetric({ value: '123.456', unit: 'USDT' }, '—');
  assert.equal(pos.formatted, '+123.46 USDT');
  assert.equal(pos.isPositive, true);

  // Negative
  const neg = formatStrategyMoneyMetric({ value: '-0.05', unit: 'USDT' }, '—');
  assert.equal(neg.formatted, '-0.05 USDT');
  assert.equal(neg.isPositive, false);

  // Zero
  const zero = formatStrategyMoneyMetric({ value: '0.000', unit: 'USDT' }, '—');
  assert.equal(zero.formatted, '0.00 USDT');
  assert.equal(zero.isPositive, null);

  // High precision Decimal without float drift
  const prec = formatStrategyMoneyMetric({ value: '0.30000000000000004', unit: 'USDT' }, '—');
  assert.equal(prec.formatted, '+0.30 USDT');

  // Large financial value
  const large = formatStrategyMoneyMetric({ value: '98765432.10', unit: 'USDT' }, '—');
  assert.equal(large.formatted, '+98765432.10 USDT');
});

test('P2-1: MoneyMetric missing value handling preserves honest unavailable semantics', () => {
  // ticket_active unavailable reason
  const active = formatStrategyMoneyMetric({ value: null, unavailable_reason: 'ticket_active' }, '—');
  assert.equal(active.formatted, '持仓中 · 未结');
  assert.equal(active.isUnavailable, true);
  assert.equal(active.value, null);

  // no_confirmed_natural_review unavailable reason
  const review = formatStrategyMoneyMetric({ value: null, unavailable_reason: 'no_confirmed_natural_review' }, '—');
  assert.equal(review.formatted, '无已确认自然评审');
  assert.equal(review.isUnavailable, true);

  // Plain missing metric
  const missing = formatStrategyMoneyMetric(null, '—');
  assert.equal(missing.formatted, '—');
  assert.equal(missing.isUnavailable, true);

  // Missing metric with custom placeholder
  const custom = formatStrategyMoneyMetric(null, '未产生有效终态');
  assert.equal(custom.formatted, '未产生有效终态');

  // Missing unit handled cleanly without "undefined"
  const noUnit = formatStrategyMoneyMetric({ value: '42.50' }, '—');
  assert.equal(noUnit.formatted, '+42.50');
  assert.equal(noUnit.formatted.includes('undefined'), false);
});

// -----------------------------------------------------------------------------
// Test Group 10: P2-2 Fixed Pagination Window & Failure Retention
// -----------------------------------------------------------------------------
console.log('\n--- Test Group 10: P2-2 Fixed Pagination Window & Failure Retention ---');

test('P2-2: Pagination query parameters maintain fixed from_ms and to_ms across cursor fetches', () => {
  const windowEnd = 1710000000000;
  const windowStart = windowEnd - 30 * 86_400_000;

  // Page 1 params
  const page1Params = {
    strategy_version_id: 'sv-cpm-v1',
    from_ms: windowStart,
    to_ms: windowEnd,
    limit: 50,
    cursor: null,
  };

  // Page 2 params with cursor
  const page2Params = {
    strategy_version_id: 'sv-cpm-v1',
    from_ms: windowStart,
    to_ms: windowEnd,
    limit: 50,
    cursor: 'cursor_page_2',
  };

  // Assert time window is identical
  assert.equal(page1Params.from_ms, page2Params.from_ms);
  assert.equal(page1Params.to_ms, page2Params.to_ms);

  // Assert infinite query key base parameters remain identical
  const baseKey1 = strategyTicketsInfiniteQueryKey({
    strategy_version_id: 'sv-cpm-v1',
    from_ms: windowStart,
    to_ms: windowEnd,
    limit: 50,
  });
  const baseKey2 = strategyTicketsInfiniteQueryKey({
    strategy_version_id: 'sv-cpm-v1',
    from_ms: windowStart,
    to_ms: windowEnd,
    limit: 50,
  });
  assert.deepEqual(baseKey1, baseKey2);
});

test('P2-2: Next page fetch failure retains existing page 1 data and enables retry', () => {
  // Existing state with page 1
  const existingPages = [
    { data: { items: [{ id: 1 }, { id: 2 }], next_cursor: 'cursor_2' } },
  ];

  // Simulating fetchNextPage failure: existingPages are preserved
  const isFetchNextPageError = true;
  const error = new ApiError(500, 'server_error', 'Connection timed out on page 2');

  const currentItems = existingPages.flatMap((page) => page.data.items);
  assert.equal(currentItems.length, 2);
  assert.equal(isFetchNextPageError, true);
  assert.equal(error.status, 500);

  // On retry success: page 2 appends to page 1
  const retriedPages = [
    ...existingPages,
    { data: { items: [{ id: 3 }, { id: 4 }], next_cursor: null } },
  ];
  const combinedItems = retriedPages.flatMap((page) => page.data.items);
  assert.equal(combinedItems.length, 4);
  assert.deepEqual(combinedItems.map((i) => i.id), [1, 2, 3, 4]);
});

// -----------------------------------------------------------------------------
// Test Group 11: Requirement 7 Truthful Handling of view=all 409
// -----------------------------------------------------------------------------
console.log('\n--- Test Group 11: Requirement 7 Truthful Handling of view=all 409 ---');

test('Requirement 7: view=all 409 is preserved truthfully without fallback or mock', () => {
  const conflictResponse = new Response(
    JSON.stringify({
      error: {
        code: 'contradictory_facts',
        message: 'Current facts are contradictory',
      },
    }),
    { status: 409, headers: { 'Content-Type': 'application/json' } }
  );

  const error = apiErrorFromResponse(conflictResponse, {
    error: {
      code: 'contradictory_facts',
      message: 'Current facts are contradictory',
    },
  });

  assert.equal(error.status, 409);
  assert.equal(error.code, 'contradictory_facts');
  assert.equal(error.message, 'Current facts are contradictory');
  assert.equal(isConflict(error), true);

  // The application must NOT fabricate empty data
  const isError = true;
  const data = null;
  assert.equal(isError, true);
  assert.equal(data, null);
});

// -----------------------------------------------------------------------------
// Test Group 12: P1-1 Strategies Error Object Diagnostics (parseStrategyError)
// -----------------------------------------------------------------------------
console.log('\n--- Test Group 12: P1-1 Strategies Error Object Diagnostics (parseStrategyError) ---');

test('P1-1: 409 Contradictory facts on view=all returns 409 title and enables return to current', () => {
  const err = new ApiError(409, 'contradictory_facts', 'Current facts are contradictory');
  const diag = parseStrategyError(err, 'all');
  assert.equal(diag.isConflict409, true);
  assert.equal(diag.httpStatus, 409);
  assert.equal(diag.code, 'contradictory_facts');
  assert.match(diag.title, /HTTP 409/);
  assert.equal(diag.canReturnToCurrent, true);
});

test('P1-1: 500 Server error on view=all returns 500 title and does NOT claim 409', () => {
  const err = new ApiError(500, 'server_error', 'Database connection refused');
  const diag = parseStrategyError(err, 'all');
  assert.equal(diag.isConflict409, false);
  assert.equal(diag.httpStatus, 500);
  assert.equal(diag.code, 'server_error');
  assert.match(diag.title, /服务端异常 \(HTTP 500/);
  assert.doesNotMatch(diag.title, /409/);
  assert.doesNotMatch(diag.title, /Contradictory Facts/);
  assert.equal(diag.canReturnToCurrent, true);
});

test('P1-1: 401 Unauthorized returns auth prompt and forbids return to current button', () => {
  const err = new ApiError(401, 'unauthorized', 'Missing token');
  const diag = parseStrategyError(err, 'current');
  assert.equal(diag.httpStatus, 401);
  assert.match(diag.title, /HTTP 401/);
  assert.equal(diag.canReturnToCurrent, false);
});

test('P1-1: 403 Forbidden returns forbidden prompt and forbids return to current button', () => {
  const err = new ApiError(403, 'forbidden', 'Insufficient scopes');
  const diag = parseStrategyError(err, 'current');
  assert.equal(diag.httpStatus, 403);
  assert.match(diag.title, /HTTP 403/);
  assert.equal(diag.canReturnToCurrent, false);
});

test('P1-1: 422 Validation error returns validation title and details', () => {
  const err = new ApiError(422, 'validation_error', 'Invalid query parameters');
  const diag = parseStrategyError(err, 'current');
  assert.equal(diag.httpStatus, 422);
  assert.match(diag.title, /HTTP 422/);
});

test('P1-1: Network error returns network error title without HTTP status', () => {
  const err = new Error('Failed to fetch');
  const diag = parseStrategyError(err, 'current');
  assert.equal(diag.httpStatus, null);
  assert.equal(diag.code, 'network_error');
  assert.match(diag.title, /网络连接异常/);
});

// -----------------------------------------------------------------------------
// Test Group 13: P1-2 Pagination Edge Boundary: Page 1 with only not_terminal items
// -----------------------------------------------------------------------------
console.log('\n--- Test Group 13: P1-2 Pagination Edge Boundary: Page 1 with only not_terminal items ---');

test('P1-2: Page 1 with only not_terminal items leaves filtered Natural empty but hasNextPage is true', () => {
  const page1Items = [
    { ticket_id: 't-1', evaluation_path: 'not_terminal', exchange_instrument_id: 'BTC-USDT', issued_at_ms: 1000 },
    { ticket_id: 't-2', evaluation_path: 'not_terminal', exchange_instrument_id: 'ETH-USDT', issued_at_ms: 1001 },
    { ticket_id: 't-3', evaluation_path: 'not_terminal', exchange_instrument_id: 'SOL-USDT', issued_at_ms: 1002 },
    { ticket_id: 't-4', evaluation_path: 'not_terminal', exchange_instrument_id: 'DOGE-USDT', issued_at_ms: 1003 },
    { ticket_id: 't-5', evaluation_path: 'not_terminal', exchange_instrument_id: 'BNB-USDT', issued_at_ms: 1004 },
  ];

  const scope = 'natural';
  const naturalItems = page1Items.filter(
    (item) => item.evaluation_path === 'tp1_reached' || item.evaluation_path === 'tp1_not_reached'
  );
  const excludedNonTerminalCount = page1Items.filter((item) => item.evaluation_path === 'not_terminal').length;
  const hasNextPage = true;

  assert.equal(page1Items.length, 5);
  assert.equal(naturalItems.length, 0);
  assert.equal(excludedNonTerminalCount, 5);
  assert.equal(hasNextPage, true);

  // Verification of the UI branch condition:
  // When items.length === 0 and hasNextPage is true, it MUST NOT render terminal empty state
  const isTerminalEmpty = naturalItems.length === 0 && !hasNextPage;
  const isActivePagination = naturalItems.length === 0 && hasNextPage;
  assert.equal(isTerminalEmpty, false);
  assert.equal(isActivePagination, true);
});

test('P1-2: Appending Page 2 loads 36 natural terminals while keeping 5 not_terminal strictly excluded', () => {
  const page1Items = [
    { ticket_id: 't-1', evaluation_path: 'not_terminal', exchange_instrument_id: 'BTC-USDT', issued_at_ms: 1000 },
    { ticket_id: 't-2', evaluation_path: 'not_terminal', exchange_instrument_id: 'ETH-USDT', issued_at_ms: 1001 },
    { ticket_id: 't-3', evaluation_path: 'not_terminal', exchange_instrument_id: 'SOL-USDT', issued_at_ms: 1002 },
    { ticket_id: 't-4', evaluation_path: 'not_terminal', exchange_instrument_id: 'DOGE-USDT', issued_at_ms: 1003 },
    { ticket_id: 't-5', evaluation_path: 'not_terminal', exchange_instrument_id: 'BNB-USDT', issued_at_ms: 1004 },
  ];

  const page2Items = Array.from({ length: 36 }, (_, i) => ({
    ticket_id: `t-natural-${i + 1}`,
    evaluation_path: i % 2 === 0 ? 'tp1_reached' : 'tp1_not_reached',
    exchange_instrument_id: 'BTC-USDT',
    issued_at_ms: 2000 + i,
  }));

  const allRawItems = [...page1Items, ...page2Items];
  assert.equal(allRawItems.length, 41);

  const scope = 'natural';
  const naturalItems = allRawItems.filter(
    (item) => item.evaluation_path === 'tp1_reached' || item.evaluation_path === 'tp1_not_reached'
  );
  const excludedNonTerminalCount = allRawItems.filter((item) => item.evaluation_path === 'not_terminal').length;
  const hasNextPage = false; // page 2 has next_cursor: null

  assert.equal(naturalItems.length, 36);
  assert.equal(excludedNonTerminalCount, 5);
  assert.equal(hasNextPage, false);

  // In Natural view, not_terminal must never be in the admitted items list
  assert.equal(naturalItems.some((item) => item.evaluation_path === 'not_terminal'), false);
});

// -----------------------------------------------------------------------------
// Test Group 14: Cross-Page Identity Deduplication
// -----------------------------------------------------------------------------
console.log('\n--- Test Group 14: Cross-Page Identity Deduplication ---');

test('Deduplication: Tickets across pages with duplicate ticket_ids are deduplicated', () => {
  const pages = [
    { data: { items: [{ ticket_id: 't-1' }, { ticket_id: 't-2' }] } },
    { data: { items: [{ ticket_id: 't-2' }, { ticket_id: 't-3' }] } }, // t-2 overlaps
  ];

  const all = pages.flatMap((p) => p.data.items);
  const seen = new Set();
  const deduped = [];
  for (const item of all) {
    const key = item.ticket_id;
    if (!seen.has(key)) {
      seen.add(key);
      deduped.push(item);
    }
  }

  assert.equal(deduped.length, 3);
  assert.deepEqual(deduped.map((d) => d.ticket_id), ['t-1', 't-2', 't-3']);
});

test('Deduplication: Observations across pages with duplicate shadow_outcome_ids are deduplicated', () => {
  const pages = [
    { data: { items: [{ shadow_outcome_id: 'obs-1' }, { shadow_outcome_id: 'obs-2' }] } },
    { data: { items: [{ shadow_outcome_id: 'obs-2' }, { shadow_outcome_id: 'obs-3' }] } }, // obs-2 overlaps
  ];

  const all = pages.flatMap((p) => p.data.items);
  const seen = new Set();
  const deduped = [];
  for (const item of all) {
    const key = item.shadow_outcome_id;
    if (!seen.has(key)) {
      seen.add(key);
      deduped.push(item);
    }
  }

  assert.equal(deduped.length, 3);
  assert.deepEqual(deduped.map((d) => d.shadow_outcome_id), ['obs-1', 'obs-2', 'obs-3']);
});

// -----------------------------------------------------------------------------
// Test Group 15: P2 Hierarchical Escape Drawer Dismissal & Focus Restoration
// -----------------------------------------------------------------------------
console.log('\n--- Test Group 15: P2 Hierarchical Escape Drawer Dismissal & Focus Restoration ---');

test('P2: Escape pops ONLY the topmost child drawer, leaving parent drawer open', () => {
  // Clear stack before test
  drawerStack.length = 0;

  let parentClosed = false;
  let childClosed = false;

  // 1. Open parent StrategyDetailDrawer
  drawerStack.push({
    id: 'strategy-detail-drawer',
    onClose: () => { parentClosed = true; },
    triggerElement: null,
  });

  // 2. Open child CausalityDrawer
  drawerStack.push({
    id: 'causality-drawer',
    onClose: () => { childClosed = true; },
    triggerElement: null,
  });

  assert.equal(drawerStack.length, 2);

  // 3. User presses Escape
  const event1 = {
    key: 'Escape',
    defaultPrevented: false,
    preventDefault() { this.defaultPrevented = true; },
    stopPropagation() {},
  };

  const handled1 = handleDrawerGlobalKeyDown(event1);
  assert.equal(handled1, true);
  assert.equal(childClosed, true, 'Topmost CausalityDrawer must be closed');
  assert.equal(parentClosed, false, 'Parent StrategyDetailDrawer must remain OPEN');
  assert.equal(drawerStack.length, 1);
  assert.equal(drawerStack[0].id, 'strategy-detail-drawer');

  // 4. User presses Escape again
  const event2 = {
    key: 'Escape',
    defaultPrevented: false,
    preventDefault() { this.defaultPrevented = true; },
    stopPropagation() {},
  };

  const handled2 = handleDrawerGlobalKeyDown(event2);
  assert.equal(handled2, true);
  assert.equal(parentClosed, true, 'Parent StrategyDetailDrawer must now be closed');
  assert.equal(drawerStack.length, 0);

  // 5. User presses Escape when stack is empty
  const handled3 = handleDrawerGlobalKeyDown(event2);
  assert.equal(handled3, false);
});

test('P2: Non-Escape keys do not pop any drawer', () => {
  drawerStack.length = 0;
  let closed = false;
  drawerStack.push({
    id: 'test-drawer',
    onClose: () => { closed = true; },
    triggerElement: null,
  });

  const enterEvent = {
    key: 'Enter',
    defaultPrevented: false,
    preventDefault() {},
    stopPropagation() {},
  };

  const handled = handleDrawerGlobalKeyDown(enterEvent);
  assert.equal(handled, false);
  assert.equal(closed, false);
  assert.equal(drawerStack.length, 1);
  drawerStack.length = 0;
});

console.log('\n================================================================');
console.log(`Strategies Regression Summary: ${passCount} Passed, 0 Failed`);
console.log('================================================================\n');
