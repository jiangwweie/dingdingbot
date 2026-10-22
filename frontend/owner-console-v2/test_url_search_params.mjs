// ============================================================================
// Unit Tests: Owner Console V2 URL Search Params Parsing & Serialization
// ============================================================================

import assert from 'node:assert/strict';
import {
  parseTradesSearchParams,
  serializeTradesSearchParams,
  parseStrategiesSearchParams,
  serializeStrategiesSearchParams,
} from './src/utils/urlParams.ts';
import { DAY_MS } from './src/utils/timeRange.ts';

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
console.log('Running URL Search Params Unit Suite');
console.log('================================================================\n');

// Group 1: Trades URL Params
console.log('--- Test Group 1: Trades URL Params ---');

test('parseTradesSearchParams: default empty query initializes default 30d and all mode', () => {
  const nowMs = 1700000000000;
  const q = new URLSearchParams('');
  const parsed = parseTradesSearchParams(q, nowMs);

  assert.equal(parsed.range, '30d');
  assert.equal(parsed.from_ms, nowMs - 30 * DAY_MS);
  assert.equal(parsed.to_ms, nowMs);
  assert.equal(parsed.filter_mode, 'all');
  assert.equal(parsed.strategy_group_id, undefined);
  assert.equal(parsed.exchange_instrument_id, undefined);
  assert.equal(parsed.position_side, undefined);
  assert.equal(parsed.aggregate_status, undefined);
});

test('parseTradesSearchParams: parses full valid query parameters', () => {
  const q = new URLSearchParams(
    'range=7d&from_ms=1690000000000&to_ms=1690500000000&strategy_group_id=CPM-RO-001&exchange_instrument_id=binance-usdm:TRXUSDT:perpetual&position_side=short&aggregate_status=position_protected&filter_mode=active'
  );
  const parsed = parseTradesSearchParams(q);

  assert.equal(parsed.range, '7d');
  assert.equal(parsed.from_ms, 1690000000000);
  assert.equal(parsed.to_ms, 1690500000000);
  assert.equal(parsed.strategy_group_id, 'CPM-RO-001');
  assert.equal(parsed.exchange_instrument_id, 'binance-usdm:TRXUSDT:perpetual');
  assert.equal(parsed.position_side, 'short');
  assert.equal(parsed.aggregate_status, 'position_protected');
  assert.equal(parsed.filter_mode, 'active');
});

test('parseTradesSearchParams: invalid dates fallback cleanly to preset window', () => {
  const nowMs = 1700000000000;
  // to_ms <= from_ms (inverted)
  const q = new URLSearchParams('range=24h&from_ms=2000&to_ms=1000');
  const parsed = parseTradesSearchParams(q, nowMs);

  assert.equal(parsed.range, '24h');
  assert.equal(parsed.from_ms, nowMs - DAY_MS);
  assert.equal(parsed.to_ms, nowMs);
});

test('serializeTradesSearchParams: roundtrips correctly', () => {
  const params = {
    range: '7d',
    from_ms: 1690000000000,
    to_ms: 1690500000000,
    strategy_group_id: 'BRF2-001',
    exchange_instrument_id: 'binance-usdm:ETHUSDT:perpetual',
    position_side: 'long',
    aggregate_status: 'completed',
    filter_mode: 'completed',
  };
  const serialized = serializeTradesSearchParams(params);
  const reParsed = parseTradesSearchParams(new URLSearchParams(serialized));

  assert.deepEqual(reParsed, {view:'all',exit_scope:'all',strategy_version_id:undefined,...params});
});

// Group 2: Strategies URL Params
console.log('\n--- Test Group 2: Strategies URL Params ---');

test('parseStrategiesSearchParams: default empty query initializes current view and 30d window', () => {
  const nowMs = 1700000000000;
  const q = new URLSearchParams('');
  const parsed = parseStrategiesSearchParams(q, nowMs);

  assert.equal(parsed.view, 'all');
  assert.equal(parsed.range, '30d');
  assert.equal(parsed.from_ms, nowMs - 30 * DAY_MS);
  assert.equal(parsed.to_ms, nowMs);
  assert.equal(parsed.scope, 'all');
  assert.equal(parsed.strategy_version_id, undefined);
  assert.equal(parsed.drawer_tab, undefined);
  assert.equal(parsed.exit_path, undefined);
  assert.equal(parsed.first_path, undefined);
});

test('parseStrategiesSearchParams: parses all view, drawer context, and sub-filters', () => {
  const q = new URLSearchParams(
    'view=all&range=today&from_ms=1690000000000&to_ms=1690100000000&strategy_version_id=sv_12345&drawer_tab=tickets&scope=all&exit_path=controlled_exit'
  );
  const parsed = parseStrategiesSearchParams(q);

  assert.equal(parsed.view, 'all');
  assert.equal(parsed.range, 'today');
  assert.equal(parsed.from_ms, 1690000000000);
  assert.equal(parsed.to_ms, 1690100000000);
  assert.equal(parsed.strategy_version_id, 'sv_12345');
  assert.equal(parsed.drawer_tab, 'tickets');
  assert.equal(parsed.scope, 'all');
  assert.equal(parsed.exit_path, 'controlled_exit');
});

test('parseStrategiesSearchParams: defensive guard strips controlled_exit when scope is natural', () => {
  const q = new URLSearchParams('scope=natural&exit_path=controlled_exit');
  const parsed = parseStrategiesSearchParams(q);

  assert.equal(parsed.scope, 'natural');
  assert.equal(parsed.exit_path, undefined, 'controlled_exit must be stripped in natural scope');
});

test('serializeStrategiesSearchParams: roundtrips correctly', () => {
  const params = {
    view: 'all',
    range: 'today',
    from_ms: 1690000000000,
    to_ms: 1690100000000,
    strategy_version_id: 'sv_test_999',
    drawer_tab: 'observations',
    scope: 'natural',
    exit_path: 'tp1_reached',
    first_path: 'tp1_first',
  };
  const serialized = serializeStrategiesSearchParams(params);
  const reParsed = parseStrategiesSearchParams(new URLSearchParams(serialized));

  assert.deepEqual(reParsed, {exit_scope:'all',strategy_group_id:undefined,exchange_instrument_id:undefined,position_side:undefined,...params});
});

console.log('\n================================================================');
console.log(`URL Search Params Summary: ${passCount} Passed, 0 Failed`);
console.log('================================================================\n');
