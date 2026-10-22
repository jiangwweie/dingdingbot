/**
 * Owner Console V2 — Review Center Contracts & Integration Suite
 *
 * Verifies:
 * 1. Review Query Key stability, cursor isolation, and filter change invalidation.
 * 2. URL search parameters: 30d default, presets, custom ranges, review_status, strategy_group_id, roundtrip,
 *    and P1-2 verification: unsupported waiting_for_settlement is safely sanitized to undefined.
 * 3. Exact MoneyMetric formatting: Decimal precision, sign handling, non-fabrication of missing/null values.
 * 4. Execution classification, review status, exit reasons, and sentence template mappings.
 * 5. P1-1 verification: computeReviewSummary accurately aggregates cross-page loaded records (e.g. 50 + 16 = 66),
 *    deduplicates tickets, recomputes complete/incomplete review counts, Decimal sums economics, and handles breakdowns.
 * 6. P2-1 verification: Asia/Shanghai datetime and range formatting independence.
 * 7. P2-2 verification: EvidenceRef deduplication, preservation of ticket vs non-ticket evidence in breakdowns.
 */

import assert from 'node:assert';
import {
  reviewQueryKey,
  reviewInfiniteQueryKey,
} from './src/api/reviewApi.ts';
import { reviewPaginationOptions } from './src/api/reviewPagination.ts';
import {
  parseReviewSearchParams,
  serializeReviewSearchParams,
} from './src/utils/urlParams.ts';
import {
  formatReviewMoneyMetric,
  formatExecutionClassification,
  formatReviewStatus,
  formatReviewExitReason,
  formatReviewSentenceTemplate,
} from './src/mapping/reviewMapping.ts';
import {
  calculatePresetWindow,
  formatShanghaiDateTime,
  formatShanghaiRangeDisplay,
} from './src/utils/timeRange.ts';
import {
  computeReviewSummary,
  computeReviewEconomics,
  deduplicateEvidence,
} from './src/mapping/reviewSummary.ts';

console.log('================================================================');
console.log('Running Review Center Contracts & Integration Suite');
console.log('================================================================\n');

let passCount = 0;
let failCount = 0;

function it(name, fn) {
  try {
    fn();
    console.log(`  ✓ PASS: ${name}`);
    passCount++;
  } catch (err) {
    console.error(`  ✗ FAIL: ${name}`);
    console.error(err);
    failCount++;
  }
}

// -----------------------------------------------------------------------------
// Group 1: Review Query Key Stability & Invalidation
// -----------------------------------------------------------------------------
console.log('--- Test Group 1: Review Query Key Stability & Cursor Isolation ---');

it('Default query keys for Review are identical and stable', () => {
  const k1 = reviewQueryKey();
  const k2 = reviewQueryKey();
  assert.deepStrictEqual(k1, k2);
  assert.strictEqual(k1[0], 'owner');
  assert.strictEqual(k1[1], 'review');
});

it('Applying filters generates distinct, deterministic query key', () => {
  const kDefault = reviewQueryKey();
  const kFiltered = reviewQueryKey({
    from_ms: 1_700_000_000_000,
    to_ms: 1_700_100_000_000,
    review_status: 'complete',
    strategy_group_id: 'CPM-RO-001',
  });

  assert.notDeepStrictEqual(kDefault, kFiltered);
  assert.strictEqual(kFiltered[2].review_status, 'complete');
  assert.strictEqual(kFiltered[2].strategy_group_id, 'CPM-RO-001');
  assert.strictEqual(kFiltered[2].from_ms, 1_700_000_000_000);
});

it('Review infinite query key isolates params without embedding page cursor', () => {
  const options = reviewPaginationOptions({
    limit: 50,
    review_status: 'complete',
  });
  assert.strictEqual(options.queryKey[0], 'owner');
  assert.strictEqual(options.queryKey[1], 'review');
  assert.strictEqual(options.queryKey[2], 'infinite');
  assert.strictEqual(options.initialPageParam, null);

  const nextPage = options.getNextPageParam({
    data: { next_cursor: 'cursor_token_123' },
  });
  assert.strictEqual(nextPage, 'cursor_token_123');

  const finalPage = options.getNextPageParam({
    data: { next_cursor: null },
  });
  assert.strictEqual(finalPage, null);
});

// -----------------------------------------------------------------------------
// Group 2: URL Search Params & Deep Linking
// -----------------------------------------------------------------------------
console.log('\n--- Test Group 2: URL Search Params & Deep Linking ---');

it('Default Review search params resolve to 30d window with no status filter', () => {
  const sp = new URLSearchParams('tab=review');
  const parsed = parseReviewSearchParams(sp);
  assert.strictEqual(parsed.range, '30d');
  assert.ok(parsed.from_ms > 0);
  assert.ok(parsed.to_ms > parsed.from_ms);
  assert.strictEqual(parsed.review_status, undefined);
  assert.strictEqual(parsed.strategy_group_id, undefined);
});

it('Parses valid review_status enums correctly and discards unsupported/invalid ones (P1-2)', () => {
  const validStatuses = [
    'in_progress',
    'waiting_for_review',
    'complete',
    'incomplete_evidence',
  ];
  for (const st of validStatuses) {
    const sp = new URLSearchParams(`tab=review&review_status=${st}`);
    const parsed = parseReviewSearchParams(sp);
    assert.strictEqual(parsed.review_status, st);
  }

  // P1-2 regression: waiting_for_settlement is unsupported by backend matches_review_status and MUST be sanitized
  const unsupportedSp = new URLSearchParams('tab=review&review_status=waiting_for_settlement');
  const unsupportedParsed = parseReviewSearchParams(unsupportedSp);
  assert.strictEqual(unsupportedParsed.review_status, undefined, 'waiting_for_settlement must be sanitized to undefined');

  const invalidSp = new URLSearchParams('tab=review&review_status=fabricated_status');
  const invalidParsed = parseReviewSearchParams(invalidSp);
  assert.strictEqual(invalidParsed.review_status, undefined);
});

it('Serializes Review search params with tab=review and roundtrips with full fidelity', () => {
  const original = {
    range: '7d',
    from_ms: 1_700_000_000_000,
    to_ms: 1_700_604_800_000,
    review_status: 'complete',
    strategy_group_id: 'CPM-RO-001',
  };
  const serialized = serializeReviewSearchParams(original);
  assert.ok(serialized.includes('tab=review'));
  assert.ok(serialized.includes('range=7d'));
  assert.ok(serialized.includes('review_status=complete'));
  assert.ok(serialized.includes('strategy_group_id=CPM-RO-001'));

  const parsed = parseReviewSearchParams(new URLSearchParams(serialized));
  assert.strictEqual(parsed.range, original.range);
  assert.strictEqual(parsed.from_ms, original.from_ms);
  assert.strictEqual(parsed.to_ms, original.to_ms);
  assert.strictEqual(parsed.review_status, original.review_status);
  assert.strictEqual(parsed.strategy_group_id, original.strategy_group_id);
});

it('Rejects invalid date window where to_ms <= from_ms and falls back to preset', () => {
  const sp = new URLSearchParams('tab=review&from_ms=100000&to_ms=50000');
  const parsed = parseReviewSearchParams(sp);
  assert.ok(parsed.to_ms > parsed.from_ms);
});

// -----------------------------------------------------------------------------
// Group 3: Decimal Precision & MoneyMetric Formatting
// -----------------------------------------------------------------------------
console.log('\n--- Test Group 3: Decimal Precision & MoneyMetric Non-Fabrication ---');

it('Positive profit formatted with + sign and unit', () => {
  const metric = { value: '124.50', unit: 'USDT', unavailable_reason: null };
  const res = formatReviewMoneyMetric(metric, { sign: true });
  assert.strictEqual(res.formatted, '+124.50 USDT');
  assert.strictEqual(res.isPositive, true);
  assert.strictEqual(res.isUnavailable, false);
});

it('Negative loss formatted with - sign and unit', () => {
  const metric = { value: '-42.10', unit: 'USDT', unavailable_reason: null };
  const res = formatReviewMoneyMetric(metric, { sign: true });
  assert.strictEqual(res.formatted, '-42.10 USDT');
  assert.strictEqual(res.isPositive, false);
  assert.strictEqual(res.isUnavailable, false);
});

it('Zero value has no + sign and is not marked as positive or negative', () => {
  const metric = { value: '0.00', unit: 'USDT', unavailable_reason: null };
  const res = formatReviewMoneyMetric(metric, { sign: true });
  assert.strictEqual(res.formatted, '0.00 USDT');
  assert.strictEqual(res.isPositive, null);
  assert.strictEqual(res.isUnavailable, false);
});

it('Preserves high-precision Decimal without IEEE-754 binary floating drift', () => {
  const metric = { value: '0.000000123456789', unit: 'USDT', unavailable_reason: null };
  const res = formatReviewMoneyMetric(metric, { fractionDigits: 8 });
  assert.strictEqual(res.formatted, '0.00000012 USDT');
});

it('R metric supports 4 fraction digits', () => {
  const metric = { value: '1.2543', unit: 'R', unavailable_reason: null };
  const res = formatReviewMoneyMetric(metric, { sign: true, fractionDigits: 4 });
  assert.strictEqual(res.formatted, '+1.2543 R');
});

it('Missing or null value NEVER converts to 0.00 and honors honest unavailable reason', () => {
  const missingEconomics = { value: null, unit: 'USDT', unavailable_reason: 'incomplete_review_economics' };
  const res1 = formatReviewMoneyMetric(missingEconomics);
  assert.strictEqual(res1.formatted, '净额尚未完整核实');
  assert.strictEqual(res1.isUnavailable, true);
  assert.strictEqual(res1.value, null);

  const nullMetric = null;
  const res2 = formatReviewMoneyMetric(nullMetric);
  assert.strictEqual(res2.formatted, '—');
  assert.strictEqual(res2.isUnavailable, true);
});

// -----------------------------------------------------------------------------
// Group 4: Review Classifications, Status, Exit Reasons & Sentence Templates
// -----------------------------------------------------------------------------
console.log('\n--- Test Group 4: Statuses, Classifications & Exit Reasons Mapping ---');

it('Execution classification mapping is strictly bounded and accurate', () => {
  assert.deepStrictEqual(formatExecutionClassification('complete'), { label: '链路已核实', tone: 'success' });
  assert.deepStrictEqual(formatExecutionClassification('recovered_incident'), { label: '异常已恢复', tone: 'attention' });
  assert.deepStrictEqual(formatExecutionClassification('evidence_incomplete'), { label: '存在待核实项', tone: 'attention' });
  assert.deepStrictEqual(formatExecutionClassification('waiting_review'), { label: '等待复盘', tone: 'neutral' });
  assert.deepStrictEqual(formatExecutionClassification('in_progress'), { label: '进行中', tone: 'neutral' });
});

it('Review status mapping preserves all server states and legacy fallback', () => {
  assert.deepStrictEqual(formatReviewStatus('complete'), { label: '完整', tone: 'success' });
  assert.deepStrictEqual(formatReviewStatus('incomplete_evidence'), { label: '存在待核实项', tone: 'attention' });
  assert.deepStrictEqual(formatReviewStatus('waiting_review'), { label: '等待复盘', tone: 'neutral' });
  assert.deepStrictEqual(formatReviewStatus('waiting_for_review'), { label: '等待复盘', tone: 'neutral' });
  assert.deepStrictEqual(formatReviewStatus('waiting_for_settlement'), { label: '等待结算', tone: 'neutral' });
  assert.deepStrictEqual(formatReviewStatus('in_progress'), { label: '进行中', tone: 'neutral' });
});

it('Exit reason mapping renders human-readable labels without losing raw context', () => {
  assert.strictEqual(formatReviewExitReason('TP1 + Runner Exit').label, 'TP1 后 Runner 退出');
  assert.strictEqual(formatReviewExitReason('initial_stop_triggered').label, '初始止损触发');
  assert.strictEqual(formatReviewExitReason('owner_flatten_all:manual:1').label, 'Owner 全部持仓受控平仓');
  assert.strictEqual(formatReviewExitReason('deployment_drain').label, '部署前安全退出');
  assert.strictEqual(formatReviewExitReason(null).label, '退出原因未确认');
});

it('Review sentence templates map accurately', () => {
  assert.strictEqual(formatReviewSentenceTemplate('execution_complete').label, '链路已核实');
  assert.strictEqual(formatReviewSentenceTemplate('execution_recovered').label, '异常已恢复');
  assert.strictEqual(formatReviewSentenceTemplate('economics_complete').label, '经济结算完整');
  assert.strictEqual(formatReviewSentenceTemplate('economics_incomplete').label, '经济结算不完整');
  assert.strictEqual(formatReviewSentenceTemplate('review_waiting').label, '等待复盘');
  assert.strictEqual(formatReviewSentenceTemplate('ticket_in_progress').label, '持仓进行中');
});

// -----------------------------------------------------------------------------
// Group 5: Review Summary & Pagination Scope Integrity (P1-1 Regression)
// -----------------------------------------------------------------------------
console.log('\n--- Test Group 5: Review Summary & Pagination Scope Integrity (P1-1) ---');

function createDummyItem(id, options = {}) {
  const {
    strategy_group_id = 'MPG-001',
    review_status = 'complete',
    execution_classification = 'complete',
    exit_reason = 'TP1 + Runner Exit',
    net_pnl = '10.50',
    net_r = '1.2000',
    fees = '0.50',
    funding = '0.10',
    attention_items = [],
    evidence = [{ kind: 'ticket', identity: `t-${id}`, occurred_at_ms: 1_700_000_000_000 + id }],
  } = options;

  return {
    ticket_id: `t-${id}`,
    strategy_group_id,
    exchange_instrument_id: 'BINANCE:BTC-USDT-PERP',
    position_side: 'long',
    terminal_at_ms: 1_700_000_000_000 + id,
    review: {
      ticket_id: `t-${id}`,
      review_status,
      execution_classification,
      exit_reason,
      economic_summary: {
        net_pnl: { value: net_pnl, unit: 'USDT', unavailable_reason: null },
        net_r: { value: net_r, unit: 'R', unavailable_reason: null },
        fees: { value: fees, unit: 'USDT', unavailable_reason: null },
        funding: { value: funding, unit: 'USDT', unavailable_reason: null },
        gross_pnl: { value: net_pnl, unit: 'USDT', unavailable_reason: null },
      },
      sentences: [],
      attention_items,
      evidence,
    },
  };
}

it('computeReviewSummary accurately aggregates Page 1 (50 items) + Page 2 (16 items) into 66 total', () => {
  const page1Items = Array.from({ length: 50 }, (_, i) =>
    createDummyItem(i + 1, {
      review_status: i < 10 ? 'complete' : 'incomplete_evidence',
      execution_classification: i < 10 ? 'complete' : 'evidence_incomplete',
      attention_items: i < 40 ? ['actual_stop_risk_above_frozen_plan'] : [],
      net_pnl: '10.00',
      net_r: '1.0000',
      fees: '1.00',
      funding: '0.10',
    })
  );

  const page2Items = Array.from({ length: 16 }, (_, i) =>
    createDummyItem(i + 51, {
      review_status: i < 5 ? 'complete' : 'incomplete_evidence',
      execution_classification: i < 5 ? 'complete' : 'evidence_incomplete',
      attention_items: ['open_incident:inc-1'],
      net_pnl: '20.00',
      net_r: '2.0000',
      fees: '2.00',
      funding: '0.20',
    })
  );

  const allItems = [...page1Items, ...page2Items];
  assert.strictEqual(allItems.length, 66);

  const baseSummary = {
    from_ms: 1_700_000_000_000,
    to_ms: 1_700_900_000_000,
    sample_count: 50,
    next_cursor: 'cursor_page_2',
    items: page1Items,
    complete_review_count: 10,
    incomplete_review_count: 40,
    net_pnl: { value: '500.00', unit: 'USDT', unavailable_reason: null },
    net_r: { value: '50.0000', unit: 'R', unavailable_reason: null },
    fees: { value: '50.00', unit: 'USDT', unavailable_reason: null },
    funding: { value: '5.00', unit: 'USDT', unavailable_reason: null },
    strategy_group_samples: [],
    execution_quality_breakdown: [],
    exit_reason_breakdown: [],
    evidence: [],
  };

  const recomputed = computeReviewSummary(allItems, baseSummary, null);

  // Completed Tickets updated from 50 to 66
  assert.strictEqual(recomputed.sample_count, 66, 'sample_count must be 66');

  // Review Complete count: 10 (page 1) + 5 (page 2) = 15
  assert.strictEqual(recomputed.complete_review_count, 15, 'complete_review_count must be 15');
  // Review Incomplete count: 40 (page 1) + 11 (page 2) = 51
  assert.strictEqual(recomputed.incomplete_review_count, 51, 'incomplete_review_count must be 51');

  // Economics: 50 * 10 + 16 * 20 = 500 + 320 = 820.00
  assert.strictEqual(recomputed.net_pnl.value, '820');
  // Net R: 50 * 1 + 16 * 2 = 82.0000
  assert.strictEqual(recomputed.net_r.value, '82');
  // Fees: 50 * 1 + 16 * 2 = 82.00
  assert.strictEqual(recomputed.fees.value, '82');
  // Funding: 50 * 0.1 + 16 * 0.2 = 5 + 3.2 = 8.2
  assert.strictEqual(recomputed.funding.value, '8.2');

  // Execution breakdown sums to 66
  const qualityTotal = recomputed.execution_quality_breakdown.reduce((sum, b) => sum + b.ticket_count, 0);
  assert.strictEqual(qualityTotal, 66);

  // Next cursor reflects latest page param
  assert.strictEqual(recomputed.next_cursor, null);
});

it('Cross-page duplicates are deduplicated prior to aggregation and never double counted', () => {
  const item1 = createDummyItem(1, { net_pnl: '100.00' });
  const item2 = createDummyItem(2, { net_pnl: '200.00' });
  const item2Duplicate = createDummyItem(2, { net_pnl: '200.00' });
  const item3 = createDummyItem(3, { net_pnl: '300.00' });

  // Deduplication map as performed in useReviewData
  const unique = new Map();
  for (const item of [item1, item2, item2Duplicate, item3]) {
    if (!unique.has(item.ticket_id)) unique.set(item.ticket_id, item);
  }
  const deduplicated = [...unique.values()];
  assert.strictEqual(deduplicated.length, 3);

  const baseSummary = {
    from_ms: 1_700_000_000_000,
    to_ms: 1_700_900_000_000,
    sample_count: 2,
    next_cursor: null,
    items: [],
    complete_review_count: 0,
    incomplete_review_count: 0,
    net_pnl: { value: null, unit: 'USDT' },
    net_r: { value: null, unit: 'R' },
    fees: { value: null, unit: 'USDT' },
    funding: { value: null, unit: 'USDT' },
    strategy_group_samples: [],
    execution_quality_breakdown: [],
    exit_reason_breakdown: [],
    evidence: [],
  };

  const recomputed = computeReviewSummary(deduplicated, baseSummary);
  assert.strictEqual(recomputed.sample_count, 3);
  assert.strictEqual(recomputed.net_pnl.value, '600');
});

it('Each metric retains independent totals and verified partial coverage', () => {
  const economics = computeReviewEconomics([createDummyItem(1, { net_pnl: '100.00' }), createDummyItem(2, { net_pnl: null })]);
  assert.strictEqual(economics.net_pnl.value, null);
  assert.strictEqual(economics.net_pnl.unavailable_reason, 'incomplete_review_economics');
  assert.strictEqual(economics.verified_totals.net_pnl.value, '100');
  assert.deepStrictEqual(economics.metric_coverage.net_pnl, { available_count: 1, total_count: 2, missing_ticket_ids: ['t-2'] });
  assert.strictEqual(economics.net_r.value, '2.4');
  assert.notStrictEqual(economics.fees.value, null);
  assert.notStrictEqual(economics.funding.value, null);
});

it('Zero items: economics returns no_review_evidence without fabricating zero values', () => {
  const economics = computeReviewEconomics([]);
  assert.strictEqual(economics.net_pnl.value, null);
  assert.strictEqual(economics.net_pnl.unavailable_reason, 'no_review_evidence');
});

it('Decimal high-precision summation preserves exact strings without floating-point drift', () => {
  const item1 = createDummyItem(1, { net_pnl: '0.10000000000000000001' });
  const item2 = createDummyItem(2, { net_pnl: '0.20000000000000000002' });

  const economics = computeReviewEconomics([item1, item2]);
  assert.strictEqual(economics.net_pnl.value, '0.30000000000000000003');
});

it('P1 Regression: MoneyDecimal 80-digit precision correctly computes big number cancellation with small remainder', () => {
  // In default 20-digit Decimal, 100000000000000000000 + 0.01 truncates to 100000000000000000000,
  // then subtracting 100000000000000000000 erroneously produces 0 instead of 0.01.
  const item1 = createDummyItem(1, { net_pnl: '100000000000000000000' });
  const item2 = createDummyItem(2, { net_pnl: '0.01' });
  const item3 = createDummyItem(3, { net_pnl: '-100000000000000000000' });

  const economics = computeReviewEconomics([item1, item2, item3]);
  assert.strictEqual(economics.net_pnl.value, '0.01', 'Must preserve 0.01 without rounding drift in big number cancellation');
});

it('P1 Regression: Supports extreme 50-digit precision without truncation to zero', () => {
  const large = '1234567890123456789012345678901234567890.0000000001';
  const negLarge = '-1234567890123456789012345678901234567890';
  const item1 = createDummyItem(1, { net_pnl: large });
  const item2 = createDummyItem(2, { net_pnl: negLarge });

  const economics = computeReviewEconomics([item1, item2]);
  assert.strictEqual(economics.net_pnl.value, '0.0000000001', 'Must preserve 50-digit precision');
});

// -----------------------------------------------------------------------------
// Group 6: Asia/Shanghai Timezone Formatting (P2-1 Regression)
// -----------------------------------------------------------------------------
console.log('\n--- Test Group 6: Asia/Shanghai Timezone Formatting (P2-1) ---');

it('formatShanghaiDateTime renders strictly in East-8 (+08:00)', () => {
  // 2026-10-01 00:00:00 UTC = 2026-10-01 08:00:00 Asia/Shanghai
  const utcMs = Date.UTC(2026, 9, 1, 0, 0, 0);
  const formatted = formatShanghaiDateTime(utcMs);
  assert.ok(formatted.includes('2026-10-01 08:00'), `Expected 2026-10-01 08:00, got ${formatted}`);
});

it('formatShanghaiRangeDisplay renders both from_ms and to_ms with (上海时间) marker', () => {
  const fromMs = Date.UTC(2026, 9, 1, 0, 0, 0); // 08:00
  const toMs = Date.UTC(2026, 9, 2, 0, 0, 0);   // 08:00 next day
  const rangeStr = formatShanghaiRangeDisplay(fromMs, toMs);

  assert.ok(rangeStr.includes('2026-10-01 08:00'));
  assert.ok(rangeStr.includes('2026-10-02 08:00'));
  assert.ok(rangeStr.includes('(上海时间)'));
});

// -----------------------------------------------------------------------------
// Group 7: Evidence Aggregation & Linking (P2-2 Regression)
// -----------------------------------------------------------------------------
console.log('\n--- Test Group 7: Evidence Aggregation & Breakdown Linking (P2-2) ---');

it('deduplicateEvidence deduplicates by (kind, identity, occurred_at_ms)', () => {
  const refs = [
    { kind: 'ticket', identity: 't-1', occurred_at_ms: 1000 },
    { kind: 'ticket', identity: 't-1', occurred_at_ms: 1000 }, // dup
    { kind: 'fact', identity: 'f-1', occurred_at_ms: 1000 },
    { kind: 'ticket', identity: 't-2', occurred_at_ms: 2000 },
  ];
  const deduped = deduplicateEvidence(refs);
  assert.strictEqual(deduped.length, 3);
  assert.strictEqual(deduped[0].identity, 't-1');
  assert.strictEqual(deduped[1].identity, 'f-1');
  assert.strictEqual(deduped[2].identity, 't-2');
});

it('computeReviewSummary preserves evidence for each breakdown category', () => {
  const item1 = createDummyItem(1, {
    strategy_group_id: 'MPG-001',
    execution_classification: 'complete',
    evidence: [{ kind: 'ticket', identity: 't-1', occurred_at_ms: 1000 }],
  });
  const item2 = createDummyItem(2, {
    strategy_group_id: 'CPM-RO-001',
    execution_classification: 'complete',
    evidence: [{ kind: 'ticket', identity: 't-2', occurred_at_ms: 2000 }],
  });

  const baseSummary = {
    from_ms: 1000,
    to_ms: 2000,
    sample_count: 2,
    next_cursor: null,
    items: [],
    complete_review_count: 2,
    incomplete_review_count: 0,
    net_pnl: { value: '0', unit: 'USDT' },
    net_r: { value: '0', unit: 'R' },
    fees: { value: '0', unit: 'USDT' },
    funding: { value: '0', unit: 'USDT' },
    strategy_group_samples: [],
    execution_quality_breakdown: [],
    exit_reason_breakdown: [],
    evidence: [],
  };

  const recomputed = computeReviewSummary([item1, item2], baseSummary);

  // Strategy group breakdown has evidence
  const mpg = recomputed.strategy_group_samples.find(s => s.strategy_group_id === 'MPG-001');
  assert.ok(mpg);
  assert.strictEqual(mpg.sample_count, 1);
  assert.strictEqual(mpg.evidence.length, 1);
  assert.strictEqual(mpg.evidence[0].identity, 't-1');

  // Quality breakdown has evidence
  const completeQuality = recomputed.execution_quality_breakdown.find(q => q.label === 'complete');
  assert.ok(completeQuality);
  assert.strictEqual(completeQuality.ticket_count, 2);
  assert.strictEqual(completeQuality.evidence.length, 2);
});

it('P2 Regression: Preserves backend explicit no_evidence strategy group state when items is empty', () => {
  const baseSummary = {
    from_ms: 1000,
    to_ms: 2000,
    sample_count: 0,
    next_cursor: null,
    items: [],
    complete_review_count: 0,
    incomplete_review_count: 0,
    net_pnl: { value: null, unit: 'USDT', unavailable_reason: 'no_review_evidence' },
    net_r: { value: null, unit: 'R', unavailable_reason: 'no_review_evidence' },
    fees: { value: null, unit: 'USDT', unavailable_reason: 'no_review_evidence' },
    funding: { value: null, unit: 'USDT', unavailable_reason: 'no_review_evidence' },
    strategy_group_samples: [
      {
        strategy_group_id: 'SOR-US-EQ-PERP-001',
        sample_count: 0,
        evidence_state: 'no_evidence',
        evidence: [],
      },
    ],
    execution_quality_breakdown: [],
    exit_reason_breakdown: [],
    evidence: [],
  };

  const recomputed = computeReviewSummary([], baseSummary);
  assert.strictEqual(recomputed.strategy_group_samples.length, 1);
  assert.strictEqual(recomputed.strategy_group_samples[0].strategy_group_id, 'SOR-US-EQ-PERP-001');
  assert.strictEqual(recomputed.strategy_group_samples[0].sample_count, 0);
  assert.strictEqual(recomputed.strategy_group_samples[0].evidence_state, 'no_evidence');
});

console.log('\n================================================================');
console.log(`Review Contracts Suite Summary: ${passCount} Passed, ${failCount} Failed`);
console.log('================================================================\n');

if (failCount > 0) {
  process.exit(1);
}
