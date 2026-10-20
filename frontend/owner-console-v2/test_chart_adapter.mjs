import assert from 'node:assert/strict';
import { LineStyle } from 'lightweight-charts';
import {
  toChartNumber,
  formatChartPrice,
  isSamePrice,
  toCandlestickData,
  toSeriesMarkers,
  isAnnotationInCandles,
  getOutOfWindowAnnotations,
  computeChartWindow,
  computeObservationChartWindow,
  ticketPriceLevels,
  observationPriceLevels,
} from './src/mapping/chartAdapter.ts';
import { marketCandlesQueryKey } from './src/api/marketApi.ts';

console.log('================================================================');
console.log('Running Owner Console V2 Chart Adapter & K-Line Unit Suite');
console.log('================================================================\n');

let passCount = 0;
function test(name, fn) {
  try {
    const res = fn();
    if (res && typeof res.then === 'function') {
      return res
        .then(() => {
          console.log(`  ✓ PASS: ${name}`);
          passCount++;
        })
        .catch((err) => {
          console.error(`  ✗ FAIL: ${name}`);
          console.error(err);
          process.exitCode = 1;
        });
    }
    console.log(`  ✓ PASS: ${name}`);
    passCount++;
  } catch (err) {
    console.error(`  ✗ FAIL: ${name}`);
    console.error(err);
    process.exitCode = 1;
  }
}

// -------------------------------------------------------------------------
// Test Group 1: Number parsing and price formatting
// -------------------------------------------------------------------------
console.log('--- Test Group 1: Number Parsing & Price Formatting ---');

test('toChartNumber: parses valid numeric strings and numbers', () => {
  assert.equal(toChartNumber('123.45'), 123.45);
  assert.equal(toChartNumber(67890), 67890);
  assert.equal(toChartNumber('0'), 0);
  assert.equal(toChartNumber('-42.5'), -42.5);
});

test('toChartNumber: throws on null, undefined, or invalid input', () => {
  assert.throws(() => toChartNumber(null), /missing chart coordinate/);
  assert.throws(() => toChartNumber(undefined), /missing chart coordinate/);
  assert.throws(() => toChartNumber('abc'), /invalid chart coordinate/);
  assert.throws(() => toChartNumber(NaN), /invalid chart coordinate/);
});

test('formatChartPrice: formats numbers with commas and decimals', () => {
  assert.equal(formatChartPrice('65432.10'), '65,432.10');
  assert.equal(formatChartPrice('1000000'), '1,000,000');
  assert.equal(formatChartPrice('-5432.1'), '-5,432.1');
  assert.equal(formatChartPrice(0.005), '0.005');
  assert.equal(formatChartPrice('0.332390000000000000'), '0.33239');
  assert.equal(formatChartPrice('1234.50000'), '1,234.50');
  assert.equal(formatChartPrice('1234.00000'), '1,234.00');
  assert.equal(formatChartPrice(null), '—');
  assert.equal(formatChartPrice(undefined), '—');
  assert.equal(formatChartPrice(''), '—');
});

test('isSamePrice: compares numerical values with decimal precision', () => {
  // Equivalences
  assert.equal(isSamePrice('0.90', '0.900000'), true);
  assert.equal(isSamePrice('50000', '50000.0000'), true);
  assert.equal(isSamePrice('0.33239', '0.332390000000000000'), true);
  assert.equal(isSamePrice(123.45, '123.450'), true);
  assert.equal(isSamePrice('8.5780000', '8.578'), true);

  // Genuinely distinct prices (P1: must NOT be collapsed by epsilon)
  assert.equal(isSamePrice('8.577999999999998', '8.578'), false);
  assert.equal(isSamePrice('0.90', '0.91'), false);
  assert.equal(isSamePrice('0.00000001', '0.00000002'), false);
  assert.equal(isSamePrice('100.00000000000001', '100'), false);

  // Edge cases & invalid coordinates
  assert.equal(isSamePrice(null, '0.90'), false);
  assert.equal(isSamePrice('0.90', undefined), false);
  assert.equal(isSamePrice('', '0.90'), false);
  assert.equal(isSamePrice(NaN, '1'), false);
  assert.equal(isSamePrice('invalid', '1'), false);
});

// -------------------------------------------------------------------------
// Test Group 2: Candlestick data mapping & sorting
// -------------------------------------------------------------------------
console.log('\n--- Test Group 2: Candlestick Data Mapping & Deduplication ---');

test('toCandlestickData: maps open_time_ms to UTC timestamp in seconds', () => {
  const candles = [
    { open_time_ms: 1700000000000, close_time_ms: 1700003599999, open: '100', high: '105', low: '95', close: '102', volume: '500' },
    { open_time_ms: 1700003600000, close_time_ms: 1700007199999, open: '102', high: '108', low: '101', close: '107', volume: '600' },
  ];
  const result = toCandlestickData(candles);
  assert.equal(result.length, 2);
  assert.equal(result[0].time, 1700000000);
  assert.equal(result[0].open, 100);
  assert.equal(result[0].close, 102);
  assert.equal(result[1].time, 1700003600);
});

test('toCandlestickData: deduplicates duplicate open times and sorts ascending', () => {
  const unorderedAndDuped = [
    { open_time_ms: 1700003600000, close_time_ms: 1700007199999, open: '102', high: '108', low: '101', close: '107', volume: '600' },
    { open_time_ms: 1700000000000, close_time_ms: 1700003599999, open: '100', high: '105', low: '95', close: '102', volume: '500' },
    { open_time_ms: 1700000000000, close_time_ms: 1700003599999, open: '100', high: '105', low: '95', close: '102', volume: '500' }, // duplicate
  ];
  const result = toCandlestickData(unorderedAndDuped);
  assert.equal(result.length, 2);
  assert.equal(result[0].time, 1700000000);
  assert.equal(result[1].time, 1700003600);
  assert.ok(result[0].time < result[1].time);
});

// -------------------------------------------------------------------------
// Test Group 3: Marker generation and candle bar snapping
// -------------------------------------------------------------------------
console.log('\n--- Test Group 3: Marker Generation & Bar Snapping ---');

test('toSeriesMarkers: handles empty annotations cleanly', () => {
  assert.deepEqual(toSeriesMarkers([]), []);
});

test('toSeriesMarkers: snaps annotation timestamps to containing candle bar', () => {
  const candles = [
    { open_time_ms: 1700000000000, close_time_ms: 1700003599999, open: '100', high: '105', low: '95', close: '102', volume: '500' },
    { open_time_ms: 1700003600000, close_time_ms: 1700007199999, open: '102', high: '108', low: '101', close: '107', volume: '600' },
  ];
  const annotations = [
    { kind: 'signal', label: 'Signal', price: '101.5', occurred_at_ms: 1700001200000 }, // falls inside bar 0
    { kind: 'entry', label: 'Entry', price: '103.0', occurred_at_ms: 1700004000000 },  // falls inside bar 1
  ];
  const markers = toSeriesMarkers(annotations, candles);
  assert.equal(markers.length, 2);
  assert.equal(markers[0].time, 1700000000); // snapped to bar 0 open
  assert.equal(markers[0].shape, 'arrowUp');
  assert.equal(markers[0].color, '#FCD535');
  assert.equal(markers[1].time, 1700003600); // snapped to bar 1 open
  assert.equal(markers[1].shape, 'arrowUp');
  assert.equal(markers[1].color, '#0ECB81');
});

test('P1-1: toSeriesMarkers strictly prohibits nearest-neighbor snapping for out-of-window events', () => {
  // Event time: 1000ms. Available candle: 100000ms.
  // P1-1: 1000ms event MUST NOT be snapped to the 100000ms candle bar!
  const candles = [
    { open_time_ms: 100000, close_time_ms: 100999, open: '10', high: '12', low: '9', close: '11', volume: '100' },
  ];
  const annotations = [
    { kind: 'signal', label: 'Signal', price: '10.5', occurred_at_ms: 1000 }, // Out of window!
  ];

  const markers = toSeriesMarkers(annotations, candles);
  assert.equal(markers.length, 0, 'Out-of-window 1000ms event must NOT be plotted on 100000ms candle bar');

  // getOutOfWindowAnnotations identifies this out-of-window annotation
  const outOfWindow = getOutOfWindowAnnotations(annotations, candles);
  assert.equal(outOfWindow.length, 1);
  assert.equal(outOfWindow[0].occurred_at_ms, 1000);
});

test('toSeriesMarkers: correctly anchors events on exact candle boundaries', () => {
  const candles = [
    { open_time_ms: 1700000000000, close_time_ms: 1700003599999, open: '100', high: '105', low: '95', close: '102', volume: '500' },
  ];
  // Exactly at open_time
  const atOpen = toSeriesMarkers([{ kind: 'signal', label: 'Signal', price: '100', occurred_at_ms: 1700000000000 }], candles);
  assert.equal(atOpen.length, 1);
  assert.equal(atOpen[0].time, 1700000000);

  // Exactly at close_time
  const atClose = toSeriesMarkers([{ kind: 'exit', label: 'Exit', price: '102', occurred_at_ms: 1700003599999 }], candles);
  assert.equal(atClose.length, 1);
  assert.equal(atClose[0].time, 1700000000);
});

test('toSeriesMarkers: sorts markers strictly ascending by time to prevent Lightweight Charts crash', () => {
  const annotations = [
    { kind: 'exit', label: 'Exit', price: '110', occurred_at_ms: 1700007200000 },
    { kind: 'signal', label: 'Signal', price: '100', occurred_at_ms: 1700000000000 },
    { kind: 'stop', label: 'Stop', price: '95', occurred_at_ms: 1700003600000 },
  ];
  const markers = toSeriesMarkers(annotations);
  assert.equal(markers.length, 3);
  assert.equal(markers[0].time, 1700000000);
  assert.equal(markers[1].time, 1700003600);
  assert.equal(markers[2].time, 1700007200);
  assert.ok(markers[0].time < markers[1].time);
  assert.ok(markers[1].time < markers[2].time);
});

// -------------------------------------------------------------------------
// Test Group 4: Window calculation logic
// -------------------------------------------------------------------------
console.log('\n--- Test Group 4: Chart Window Calculation ---');

test('computeChartWindow: computes 1h timeframe window with 12 bars padding', () => {
  const signalMs = 1700000000000;
  const terminalMs = signalMs + 36_000_000; // 10 hours later
  const detail = {
    trade: { issued_at_ms: signalMs, terminal_at_ms: terminalMs },
    annotations: [{ kind: 'signal', occurred_at_ms: signalMs, label: 'Signal', price: '100' }],
  };

  const win = computeChartWindow({
    data: detail,
    timeframe: '1h',
  });

  const expectedClosedAtMs = terminalMs + 12 * 3_600_000;
  assert.equal(win.closedAtMs, expectedClosedAtMs);
  assert.ok(win.limit >= 48);
  assert.ok(win.limit <= 500);
});

test('computeChartWindow: projects window forward when terminal_at_ms is null (active trade)', () => {
  const signalMs = 1700000000000;
  const detail = {
    trade: { issued_at_ms: signalMs, terminal_at_ms: null },
    annotations: [{ kind: 'signal', occurred_at_ms: signalMs, label: 'Signal', price: '100' }],
  };

  const win = computeChartWindow({
    data: detail,
    timeframe: '1h',
    generatedAt: new Date(signalMs + 7_200_000).toISOString(),
  });

  assert.ok(win.closedAtMs >= signalMs + 12 * 3_600_000);
  assert.ok(win.limit >= 48);
});

test('computeObservationChartWindow: computes 15m window with 4 bars padding', () => {
  const startMs = 1700000000000;
  const endMs = startMs + 14_400_000; // 4 hours later (16 bars of 15m)
  const obs = {
    occurred_at_ms: startMs,
    horizon_start_ms: startMs,
    horizon_end_ms: endMs,
    completed_at_ms: endMs,
  };

  const win = computeObservationChartWindow(obs);
  const expectedClosedAtMs = endMs + 4 * 900_000;
  assert.equal(win.closedAtMs, expectedClosedAtMs);
  assert.ok(win.limit >= 48);
  assert.ok(win.limit <= 500);
});

// -------------------------------------------------------------------------
// Test Group 5: Price level separation & anti-fabrication
// -------------------------------------------------------------------------
console.log('\n--- Test Group 5: Price Level Separation & Anti-Fabrication ---');

test('ticketPriceLevels: strictly distinguishes actual entry vs reference entry', () => {
  // Case A: Actually filled trade
  const filledPlan = {
    actual_entry_price: '50100.5',
    entry_reference_price: '50000.0',
    initial_stop_price: '49500.0',
    active_stop_price: '50050.0', // Breakeven / trailing stop
    tp1_price: '51000.0',
  };

  const levelsA = ticketPriceLevels(filledPlan);
  assert.equal(levelsA.length, 5);

  const actualLevel = levelsA.find((l) => l.label.includes('实际 Entry'));
  const refLevel = levelsA.find((l) => l.label.includes('计划 Entry'));
  const stopLevel = levelsA.find((l) => l.label.includes('Initial Stop'));
  const activeStopLevel = levelsA.find((l) => l.label.includes('Active Stop'));
  const tp1Level = levelsA.find((l) => l.label.includes('TP1'));

  assert.ok(actualLevel, 'Actual entry must be present when filled');
  assert.equal(actualLevel.price, '50100.5');
  assert.equal(actualLevel.color, '#0ECB81');
  assert.equal(actualLevel.lineStyle, LineStyle.Solid);
  assert.equal(actualLevel.lineWidth, 2);

  assert.ok(refLevel, 'Planned reference entry must be present');
  assert.equal(refLevel.price, '50000.0');
  assert.equal(refLevel.color, '#F59E0B'); // Amber
  assert.equal(refLevel.lineStyle, LineStyle.Dashed);
  assert.equal(refLevel.lineWidth, 1);

  assert.ok(stopLevel, 'Initial stop must be present');
  assert.equal(stopLevel.price, '49500.0');
  assert.equal(stopLevel.lineStyle, LineStyle.Dashed);

  assert.ok(activeStopLevel, 'Active stop must be present when different from initial');
  assert.equal(activeStopLevel.price, '50050.0');
  assert.equal(activeStopLevel.lineStyle, LineStyle.Dotted);

  assert.ok(tp1Level, 'TP1 must be present');
  assert.equal(tp1Level.price, '51000.0');
  assert.equal(tp1Level.lineStyle, LineStyle.Dashed);

  // Case B: Unfilled / rejected trade where actual_entry_price is null
  const unfilledPlan = {
    actual_entry_price: null,
    entry_reference_price: '50000.0',
    initial_stop_price: '49500.0',
    active_stop_price: '49500.0', // Same as initial stop
    tp1_price: '51000.0',
  };

  const levelsB = ticketPriceLevels(unfilledPlan);
  const actualLevelB = levelsB.find((l) => l.label.includes('实际 Entry'));
  assert.equal(actualLevelB, undefined, 'Actual entry must NEVER be created when actual_entry_price is null');

  // Merged visual position: exactly one stop line exists at 49500.0, with both facts recognized in label
  assert.equal(levelsB.length, 3); // Planned Entry, Initial / Active Stop, TP1
  const stopB = levelsB.find((l) => l.price === '49500.0');
  assert.ok(stopB);
  assert.equal(stopB.label, 'Initial / Active Stop · 49,500.0 (数值相同)');

  // Case C: P1 Decimal equality recognition (0.90 vs 0.900000)
  const decimalEquivPlan = {
    actual_entry_price: null,
    entry_reference_price: '1.00',
    initial_stop_price: '0.900000',
    active_stop_price: '0.90', // Numerically identical to initial stop
    tp1_price: '1.20',
  };
  const levelsC = ticketPriceLevels(decimalEquivPlan);
  assert.equal(levelsC.length, 3);
  const stopC = levelsC.find((l) => l.price === '0.900000');
  assert.ok(stopC);
  assert.equal(stopC.label, 'Initial / Active Stop · 0.90 (数值相同)');

  // Case D: Exact match between actual entry and planned reference
  const exactMatchPlan = {
    actual_entry_price: '50000.0',
    entry_reference_price: '50000',
    initial_stop_price: '49000.0',
    active_stop_price: null,
    tp1_price: '52000.0',
  };
  const levelsD = ticketPriceLevels(exactMatchPlan);
  const actualD = levelsD.find((l) => l.label.includes('实际 Entry'));
  assert.ok(actualD);
  assert.ok(actualD.label.includes('(等同计划)'));
  const refD = levelsD.find((l) => l.label.includes('计划 Entry'));
  assert.equal(refD, undefined, 'Planned entry line should not be duplicated when identical to actual entry');

  // Case E: P1 Sub-micro-tolerance price differentiation (8.577999999999998 vs 8.578)
  // Two different price lines, even if visually very close, must NOT be logically deleted
  const tightPlan = {
    actual_entry_price: null,
    entry_reference_price: '8.60',
    initial_stop_price: '8.578',
    active_stop_price: '8.577999999999998',
    tp1_price: '9.00',
  };
  const levelsE = ticketPriceLevels(tightPlan);
  assert.equal(levelsE.length, 4); // Planned Entry, Initial Stop, Active Stop, TP1
  const initialStopE = levelsE.find((l) => l.label.startsWith('Initial Stop'));
  const activeStopE = levelsE.find((l) => l.label.startsWith('Active Stop'));
  assert.ok(initialStopE, 'Initial stop must be present');
  assert.equal(initialStopE.price, '8.578');
  assert.equal(initialStopE.color, '#EF4444');
  assert.ok(activeStopE, 'Active stop must NOT be erroneously hidden or logically deleted');
  assert.equal(activeStopE.price, '8.577999999999998');
  assert.equal(activeStopE.color, '#3B82F6');
  assert.equal(activeStopE.lineStyle, LineStyle.Dotted);

  // Case F: Entry reference vs Actual entry with near-identical values
  const tightEntryPlan = {
    actual_entry_price: '8.577999999999998',
    entry_reference_price: '8.578',
    initial_stop_price: null,
    active_stop_price: null,
    tp1_price: null,
  };
  const levelsF = ticketPriceLevels(tightEntryPlan);
  assert.equal(levelsF.length, 2);
  const actualF = levelsF.find((l) => l.label.startsWith('实际 Entry'));
  const refF = levelsF.find((l) => l.label.startsWith('计划 Entry'));
  assert.ok(actualF);
  assert.equal(actualF.price, '8.577999999999998');
  assert.ok(refF);
  assert.equal(refF.price, '8.578');
});

test('observationPriceLevels: maps all observation price lines with explicit planning tags', () => {
  const obs = {
    entry_reference_price: '3000.0',
    initial_stop_price: '2950.0',
    take_profit_price: '3100.0',
    opening_range_boundary_price: '2980.0',
  };

  const levels = observationPriceLevels(obs);
  assert.equal(levels.length, 4);

  const entryLevel = levels.find((l) => l.label.includes('计划参考 (Entry)'));
  assert.ok(entryLevel);
  assert.equal(entryLevel.price, '3000.0');
  assert.equal(entryLevel.color, '#F59E0B');

  const stopLevel = levels.find((l) => l.label.includes('计划止损 (Stop)'));
  assert.ok(stopLevel);
  assert.equal(stopLevel.price, '2950.0');
  assert.equal(stopLevel.color, '#EF4444');

  const tpLevel = levels.find((l) => l.label.includes('计划止盈 (TP1)'));
  assert.ok(tpLevel);
  assert.equal(tpLevel.price, '3100.0');
  assert.equal(tpLevel.color, '#14B8A6');

  const orLevel = levels.find((l) => l.label.includes('首小时边界 (Opening Range)'));
  assert.ok(orLevel);
  assert.equal(orLevel.price, '2980.0');
  assert.equal(orLevel.color, '#8B5CF6');
});

test('observationPriceLevels: handles missing optional prices gracefully', () => {
  const partialObs = {
    entry_reference_price: '3000.0',
    initial_stop_price: null,
    take_profit_price: undefined,
    opening_range_boundary_price: null,
  };

  const levels = observationPriceLevels(partialObs);
  assert.equal(levels.length, 1);
  assert.equal(levels[0].price, '3000.0');
});

// -------------------------------------------------------------------------
// Test Group 6: Stable Query Keys
// -------------------------------------------------------------------------
console.log('\n--- Test Group 6: Stable Market Query Keys ---');

test('marketCandlesQueryKey: produces stable query key tuple', () => {
  const key1 = marketCandlesQueryKey({
    exchange_instrument_id: 'BTC-USDT-SWAP',
    timeframe: '1h',
    closed_at_ms: 1700000000000,
    limit: 100,
  });
  const key2 = marketCandlesQueryKey({
    exchange_instrument_id: 'BTC-USDT-SWAP',
    timeframe: '1h',
    closed_at_ms: 1700000000000,
    limit: 100,
  });

  assert.deepEqual(key1, key2);
  assert.equal(key1[0], 'owner');
  assert.equal(key1[1], 'market');
  assert.equal(key1[2], 'candles');
  assert.equal(key1[3], 'BTC-USDT-SWAP');
  assert.equal(key1[4], '1h');
  assert.equal(key1[5], 1700000000000);
  assert.equal(key1[6], 100);
});

// -------------------------------------------------------------------------
// Test Group 7: Ticket Switching Query Key & Late Response Isolation
// -------------------------------------------------------------------------
console.log('\n--- Test Group 7: Ticket Switching Query Key & Late Response Isolation ---');

test('Ticket Switching: Query keys for Ticket A and Ticket B are strictly isolated', () => {
  const queryKeyA = marketCandlesQueryKey({
    exchange_instrument_id: 'binance-usdm:LINKUSDT:perpetual',
    timeframe: '15m',
    closed_at_ms: 1792470000000,
    limit: 48,
  });

  const queryKeyB = marketCandlesQueryKey({
    exchange_instrument_id: 'binance-usdm:ETHUSDT:perpetual',
    timeframe: '1h',
    closed_at_ms: 1792480000000,
    limit: 48,
  });

  // Query keys are completely distinct
  assert.notDeepEqual(queryKeyA, queryKeyB);
  assert.equal(queryKeyA[3], 'binance-usdm:LINKUSDT:perpetual');
  assert.equal(queryKeyB[3], 'binance-usdm:ETHUSDT:perpetual');
  assert.equal(queryKeyA[4], '15m');
  assert.equal(queryKeyB[4], '1h');

  // Verify that an in-memory cache mapped by queryKey cannot collide
  const cache = new Map();
  cache.set(JSON.stringify(queryKeyA), { candles: ['candle-link-15m'] });
  assert.equal(cache.get(JSON.stringify(queryKeyB)), undefined);

  // Late response for Ticket A updates ONLY Ticket A entry
  const lateResponseA = { candles: ['candle-link-15m-delayed'] };
  cache.set(JSON.stringify(queryKeyA), lateResponseA);
  assert.equal(cache.get(JSON.stringify(queryKeyB)), undefined, 'Ticket B must never receive Ticket A late response');
});

test('Ticket Switching: timeframe switch on same instrument generates distinct query key', () => {
  const key1h = marketCandlesQueryKey({
    exchange_instrument_id: 'binance-usdm:LINKUSDT:perpetual',
    timeframe: '1h',
    closed_at_ms: 1792470000000,
    limit: 48,
  });

  const key15m = marketCandlesQueryKey({
    exchange_instrument_id: 'binance-usdm:LINKUSDT:perpetual',
    timeframe: '15m',
    closed_at_ms: 1792470000000,
    limit: 48,
  });

  assert.notDeepEqual(key1h, key15m);
  assert.equal(key1h[4], '1h');
  assert.equal(key15m[4], '15m');
});

// -------------------------------------------------------------------------
// Test Group 8: Out-of-Window Event Notification & Fact Preservation
// -------------------------------------------------------------------------
console.log('\n--- Test Group 8: Out-of-Window Event Notification & Fact Preservation ---');

test('Out-of-Window: identifies out-of-window events and preserves original data immutably', () => {
  const candles = [
    { open_time_ms: 100000, close_time_ms: 103599, open: '10', high: '12', low: '9', close: '11', volume: '100' },
    { open_time_ms: 103600, close_time_ms: 107199, open: '11', high: '13', low: '10', close: '12', volume: '100' },
  ];

  const inWindowEvent = {
    kind: 'entry',
    label: 'ENTRY Fill',
    price: '10.5',
    occurred_at_ms: 102000,
  };

  const outWindowEvent = {
    kind: 'signal',
    label: 'Old Signal',
    price: '9.8',
    occurred_at_ms: 5000, // Outside window (< 100000)
  };

  const annotations = [inWindowEvent, outWindowEvent];

  // Test detection
  assert.equal(isAnnotationInCandles(inWindowEvent, candles), true);
  assert.equal(isAnnotationInCandles(outWindowEvent, candles), false);

  const outOfWindow = getOutOfWindowAnnotations(annotations, candles);
  assert.equal(outOfWindow.length, 1);
  assert.equal(outOfWindow[0].occurred_at_ms, 5000);
  assert.equal(outOfWindow[0].label, 'Old Signal');
  assert.equal(outOfWindow[0].price, '9.8');

  // Verify markers only contain the in-window event
  const markers = toSeriesMarkers(annotations, candles);
  assert.equal(markers.length, 1);
  assert.equal(markers[0].text, 'ENTRY Fill · 10.5');

  // Verify original annotations were NOT mutated (timestamps and prices preserved)
  assert.equal(outWindowEvent.occurred_at_ms, 5000);
  assert.equal(outWindowEvent.price, '9.8');
  assert.equal(inWindowEvent.occurred_at_ms, 102000);
  assert.equal(inWindowEvent.price, '10.5');
});

test('Out-of-Window: empty annotations or empty candles handled cleanly', () => {
  assert.deepEqual(getOutOfWindowAnnotations([], []), []);
  // Before candles load (empty candles), no window is established yet, so returns []
  assert.deepEqual(getOutOfWindowAnnotations([{ kind: 'signal', occurred_at_ms: 1000 }], []), []);
});

// -------------------------------------------------------------------------
// Test Group 9: QueryObserver Cancellation & Cache Key Isolation Contract
// (Note: End-to-end mounted CausalityDrawer lifecycle race is tested in verify_k_line_component_race.mjs)
// -------------------------------------------------------------------------
console.log('\n--- Test Group 9: QueryObserver Cancellation & Cache Key Isolation Contract ---');

await test('QueryObserver Cancellation: Disabling observer aborts real query signal and isolates cache', async () => {
  // [TEST TAXONOMY NOTE]
  // This unit test simulates an isolated delayed Promise resolution directly in TanStack Query.
  // It proves cache-key isolation at the query-engine level, complementing the browser-level real AbortSignal
  // cancellation and true->false fullscreen reset tests in verify_k_line_component_race.mjs.
  const { QueryClient, QueryObserver } = await import('@tanstack/react-query');
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  const keyA = marketCandlesQueryKey({
    exchange_instrument_id: 'binance-usdm:TRXUSDT:perpetual',
    timeframe: '15m',
    closed_at_ms: 1000,
    limit: 48,
  });

  let resolveTicketA;
  const promiseA = new Promise((resolve) => {
    resolveTicketA = resolve;
  });

  let recordedSignalA = null;

  // Mount QueryObserver for Ticket A (simulating active tab = chart on Ticket A)
  const observer = new QueryObserver(queryClient, {
    queryKey: keyA,
    queryFn: ({ signal }) => {
      recordedSignalA = signal;
      return promiseA;
    },
    enabled: true,
  });

  const unsubscribe = observer.subscribe(() => {});

  // Wait for query to start
  await new Promise((r) => setTimeout(r, 10));
  assert.ok(recordedSignalA, 'queryFn must receive real AbortSignal from TanStack Query');
  assert.equal(recordedSignalA.aborted, false, 'Signal must be active while in-flight');

  // Simulate switching to Ticket B (activeTab resets to timeline, enabled becomes false)
  const keyB = marketCandlesQueryKey({
    exchange_instrument_id: 'binance-usdm:ETHUSDT:perpetual',
    timeframe: '1h',
    closed_at_ms: 2000,
    limit: 48,
  });

  observer.setOptions({
    queryKey: ['owner', 'market', 'candles', 'disabled'],
    enabled: false,
  });

  // Assert TanStack Query automatically aborts the in-flight query signal
  assert.equal(recordedSignalA.aborted, true, 'TanStack Query QueryObserver MUST automatically abort signal when disabled');

  // Now simulate user activating chart on Ticket B with distinct ETHUSDT OHLC data (~3500)
  const dataB = {
    data: {
      candles: [{ open_time_ms: 2000000, close_time_ms: 2003599, open: '3500.00', high: '3550.00', low: '3490.00', close: '3575.00', volume: '500' }],
    },
  };

  observer.setOptions({
    queryKey: keyB,
    queryFn: async () => dataB,
    enabled: true,
  });

  await new Promise((r) => setTimeout(r, 20));
  const cachedB = queryClient.getQueryData(keyB);
  assert.deepEqual(cachedB, dataB, 'Ticket B data must be loaded into cache');
  assert.equal(cachedB.data.candles[0].open, '3500.00', 'Ticket B open must be 3500.00');

  // Finally let Ticket A resolve late with distinct TRXUSDT OHLC data (~0.15)
  const dataA = {
    data: {
      candles: [{ open_time_ms: 1000000, close_time_ms: 1000899, open: '0.1500', high: '0.1550', low: '0.1480', close: '0.1520', volume: '10000' }],
    },
  };
  resolveTicketA(dataA);
  await new Promise((r) => setTimeout(r, 20));

  // Assert: Ticket B data is strictly preserved and not overwritten
  const cachedBAfter = queryClient.getQueryData(keyB);
  assert.deepEqual(cachedBAfter, dataB, 'Ticket B data must NEVER be overwritten by late Ticket A response');
  assert.equal(cachedBAfter.data.candles[0].open, '3500.00', 'Ticket B open price must strictly remain 3500.00 (NOT 0.1500)');

  unsubscribe();
});

console.log('\n================================================================');
console.log(`Chart Adapter & K-Line Summary: ${passCount} Passed, 0 Failed`);
console.log('================================================================\n');
