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

console.log('\n================================================================');
console.log(`Strategies Regression Summary: ${passCount} Passed, 0 Failed`);
console.log('================================================================\n');
