// ============================================================================
// Unit Tests: Owner Console V2 Unified Time Range Utilities
// ============================================================================

import assert from 'node:assert/strict';
import {
  getBeijingDayStartMs,
  calculatePresetWindow,
  validateTimeWindow,
  toShanghaiInputValue,
  parseShanghaiInputValue,
  formatShanghaiRangeDisplay,
  SHANGHAI_OFFSET_MS,
  DAY_MS,
  MAX_WINDOW_MS,
} from './src/utils/timeRange.ts';

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
console.log('Running Time Range Utilities Unit Suite');
console.log('================================================================\n');

// Group 1: Beijing Day Start & Presets
console.log('--- Test Group 1: Beijing Calendar Boundary & Presets ---');

test('getBeijingDayStartMs: aligns strictly with 00:00:00.000 Asia/Shanghai', () => {
  // 2026-10-20 11:30:00 Beijing time
  // UTC = 2026-10-20 03:30:00 UTC
  const testUtcMs = Date.UTC(2026, 9, 20, 3, 30, 0);
  const beijingDayStart = getBeijingDayStartMs(testUtcMs);

  // Expected Beijing midnight: 2026-10-20 00:00:00 Beijing = 2026-10-19 16:00:00 UTC
  const expectedUtcMidnight = Date.UTC(2026, 9, 19, 16, 0, 0);
  assert.equal(beijingDayStart, expectedUtcMidnight);

  // Formatted in Shanghai should be 2026-10-20T00:00
  assert.equal(toShanghaiInputValue(beijingDayStart), '2026-10-20T00:00');
});

test('calculatePresetWindow: "today" starts at Beijing 00:00:00 and ends at now', () => {
  const nowMs = Date.UTC(2026, 9, 20, 3, 30, 0); // 11:30:00 Beijing
  const window = calculatePresetWindow('today', nowMs);

  assert.equal(window.from_ms, Date.UTC(2026, 9, 19, 16, 0, 0));
  assert.equal(window.to_ms, nowMs);
  assert.ok(window.to_ms > window.from_ms);
});

test('calculatePresetWindow: "24h" is rolling 24h, distinct from "today"', () => {
  const nowMs = Date.UTC(2026, 9, 20, 3, 30, 0);
  const window24h = calculatePresetWindow('24h', nowMs);
  const windowToday = calculatePresetWindow('today', nowMs);

  assert.equal(window24h.from_ms, nowMs - DAY_MS);
  assert.equal(window24h.to_ms, nowMs);

  // At 11:30 Beijing time, "today" started 11.5 hours ago, while "24h" started 24 hours ago
  assert.notEqual(window24h.from_ms, windowToday.from_ms);
  assert.ok(window24h.from_ms < windowToday.from_ms);
});

test('calculatePresetWindow: "7d" and "30d" compute exact rolling days', () => {
  const nowMs = 1700000000000;
  const win7d = calculatePresetWindow('7d', nowMs);
  assert.equal(win7d.from_ms, nowMs - 7 * DAY_MS);
  assert.equal(win7d.to_ms, nowMs);

  const win30d = calculatePresetWindow('30d', nowMs);
  assert.equal(win30d.from_ms, nowMs - 30 * DAY_MS);
  assert.equal(win30d.to_ms, nowMs);
});

// Group 2: Window Validation & Backend 90-Day Limit
console.log('\n--- Test Group 2: Window Validation & 90-Day Limit ---');

test('validateTimeWindow: accepts valid increasing window <= 90 days', () => {
  const now = 1700000000000;
  const result = validateTimeWindow(now - 30 * DAY_MS, now);
  assert.equal(result.valid, true);
  assert.equal(result.error, undefined);
});

test('validateTimeWindow: rejects when to_ms <= from_ms', () => {
  const now = 1700000000000;
  const equalResult = validateTimeWindow(now, now);
  assert.equal(equalResult.valid, false);
  assert.equal(equalResult.error, '结束时间必须晚于开始时间');

  const invertedResult = validateTimeWindow(now, now - 1000);
  assert.equal(invertedResult.valid, false);
  assert.equal(invertedResult.error, '结束时间必须晚于开始时间');
});

test('validateTimeWindow: rejects window exceeding 90 days backend limit', () => {
  const now = 1700000000000;
  const tooLargeResult = validateTimeWindow(now - (90 * DAY_MS + 1000), now);
  assert.equal(tooLargeResult.valid, false);
  assert.ok(tooLargeResult.error.includes('90 天'));

  // Exactly 90 days is accepted
  const exact90Result = validateTimeWindow(now - 90 * DAY_MS, now);
  assert.equal(exact90Result.valid, true);
});

test('validateTimeWindow: rejects null or NaN inputs', () => {
  assert.equal(validateTimeWindow(null, 1000).valid, false);
  assert.equal(validateTimeWindow(1000, null).valid, false);
  assert.equal(validateTimeWindow(NaN, 1000).valid, false);
  assert.equal(validateTimeWindow(1000, NaN).valid, false);
});

// Group 3: Shanghai ISO String Formatting & Parsing
console.log('\n--- Test Group 3: Asia/Shanghai Datetime-Local Formatting & Parsing ---');

test('toShanghaiInputValue: formats exact Asia/Shanghai YYYY-MM-DDTHH:mm string', () => {
  // 2026-10-20 03:45:00 UTC = 2026-10-20 11:45:00 Shanghai
  const utcMs = Date.UTC(2026, 9, 20, 3, 45, 0);
  const formatted = toShanghaiInputValue(utcMs);
  assert.equal(formatted, '2026-10-20T11:45');
});

test('parseShanghaiInputValue: parses Shanghai string into exact UTC millisecond timestamp', () => {
  const parsedMs = parseShanghaiInputValue('2026-10-20T11:45');
  const expectedUtcMs = Date.UTC(2026, 9, 20, 3, 45, 0);
  assert.equal(parsedMs, expectedUtcMs);
});

test('Roundtrip formatting & parsing is completely lossless', () => {
  const originalStr = '2026-10-15T09:30';
  const parsedMs = parseShanghaiInputValue(originalStr);
  const formattedAgain = toShanghaiInputValue(parsedMs);
  assert.equal(formattedAgain, originalStr);
});

test('formatShanghaiRangeDisplay: produces human readable string', () => {
  const fromMs = Date.UTC(2026, 9, 1, 0, 0, 0); // 08:00 Shanghai
  const toMs = Date.UTC(2026, 9, 20, 4, 0, 0); // 12:00 Shanghai
  const display = formatShanghaiRangeDisplay(fromMs, toMs);
  assert.equal(display, '2026-10-01 08:00 ~ 2026-10-20 12:00 (上海时间)');
});

console.log('\n================================================================');
console.log(`Time Range Utilities Summary: ${passCount} Passed, 0 Failed`);
console.log('================================================================\n');
