/**
 * Unified Time Range utilities for Owner Console V2 (Trades + Strategies).
 *
 * Strict Semantics:
 * 1. Asia/Shanghai (UTC+8) calendar timezone boundaries.
 * 2. "今日 (today)": Beijing 00:00:00.000 to now.
 * 3. "近 24 小时 (24h)": Rolling 24h (now - 86,400,000 to now), distinct from "今日".
 * 4. "近 7 天 (7d)": Rolling 7 days (now - 7 * 86,400,000 to now).
 * 5. "近 30 天 (30d)": Rolling 30 days (now - 30 * 86,400,000 to now). Default.
 * 6. "自定义 (custom)": User-specified from_ms and to_ms.
 * 7. Backend maximum window: 90 days (7,776,000,000 ms).
 * 8. Validation: to_ms > from_ms and to_ms - from_ms <= 90 days.
 */

export const SHANGHAI_OFFSET_MS = 8 * 3600 * 1000; // +8 hours
export const DAY_MS = 86_400_000;
export const MAX_WINDOW_MS = 90 * DAY_MS;

export type TimeRangePreset = 'today' | '24h' | '7d' | '30d' | 'custom';

export interface TimeWindow {
  from_ms: number;
  to_ms: number;
}

export interface TimeRangeState extends TimeWindow {
  preset: TimeRangePreset;
}

/**
 * Compute the exact Beijing midnight (00:00:00.000 Asia/Shanghai) timestamp for any given timestamp.
 */
export function getBeijingDayStartMs(timestampMs: number = Date.now()): number {
  const shanghaiMs = timestampMs + SHANGHAI_OFFSET_MS;
  const d = new Date(shanghaiMs);
  const beijingDayStartUtc = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
  return beijingDayStartUtc - SHANGHAI_OFFSET_MS;
}

/**
 * Calculate the millisecond window for a preset at a given point in time.
 * Pure function: does not mutate state.
 */
export function calculatePresetWindow(
  preset: TimeRangePreset,
  nowMs: number = Date.now()
): TimeWindow {
  switch (preset) {
    case 'today': {
      const from_ms = getBeijingDayStartMs(nowMs);
      // Ensure to_ms is strictly greater than from_ms even at exact 00:00:00.000
      const to_ms = Math.max(from_ms + 1000, nowMs);
      return { from_ms, to_ms };
    }
    case '24h':
      return {
        from_ms: nowMs - DAY_MS,
        to_ms: nowMs,
      };
    case '7d':
      return {
        from_ms: nowMs - 7 * DAY_MS,
        to_ms: nowMs,
      };
    case '30d':
    default:
      return {
        from_ms: nowMs - 30 * DAY_MS,
        to_ms: nowMs,
      };
  }
}

/**
 * Validate a time window against backend contracts:
 * 1. Both from_ms and to_ms must be valid numbers.
 * 2. to_ms must be strictly greater than from_ms.
 * 3. to_ms - from_ms must not exceed 90 days (7,776,000,000 ms).
 */
export function validateTimeWindow(
  from_ms?: number | null,
  to_ms?: number | null
): { valid: boolean; error?: string } {
  if (from_ms == null || !Number.isFinite(from_ms) || from_ms <= 0) {
    return { valid: false, error: '开始时间无效或缺失' };
  }
  if (to_ms == null || !Number.isFinite(to_ms) || to_ms <= 0) {
    return { valid: false, error: '结束时间无效或缺失' };
  }
  if (to_ms <= from_ms) {
    return { valid: false, error: '结束时间必须晚于开始时间' };
  }
  if (to_ms - from_ms > MAX_WINDOW_MS) {
    return { valid: false, error: '时间窗口不能超过 90 天（后端最大约束）' };
  }
  return { valid: true };
}

/**
 * Format a timestamp into Asia/Shanghai datetime-local input string: "YYYY-MM-DDTHH:mm".
 * Strictly renders Asia/Shanghai (+08:00) regardless of the browser host timezone.
 */
export function toShanghaiInputValue(timestampMs: number | null | undefined): string {
  if (timestampMs == null || isNaN(timestampMs) || timestampMs <= 0) {
    return '';
  }
  const d = new Date(timestampMs + SHANGHAI_OFFSET_MS);
  const year = d.getUTCFullYear();
  const month = String(d.getUTCMonth() + 1).padStart(2, '0');
  const day = String(d.getUTCDate()).padStart(2, '0');
  const hours = String(d.getUTCHours()).padStart(2, '0');
  const minutes = String(d.getUTCMinutes()).padStart(2, '0');
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

/**
 * Parse an Asia/Shanghai "YYYY-MM-DDTHH:mm" datetime-local input value into UTC epoch milliseconds.
 * Strictly interprets the input string as Asia/Shanghai (+08:00).
 */
export function parseShanghaiInputValue(inputValue: string): number | null {
  if (!inputValue || typeof inputValue !== 'string') return null;
  const trimmed = inputValue.trim();
  const match = trimmed.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/);
  if (!match) return null;

  const [, year, month, day, hours, minutes, seconds = '0'] = match;
  const utcMs = Date.UTC(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hours),
    Number(minutes),
    Number(seconds)
  );

  return utcMs - SHANGHAI_OFFSET_MS;
}

/**
 * Format a timestamp range in Asia/Shanghai for human display: "2026-10-01 12:00 ~ 2026-10-20 18:00 (上海时间)"
 */
export function formatShanghaiRangeDisplay(from_ms: number, to_ms: number): string {
  const fromStr = toShanghaiInputValue(from_ms).replace('T', ' ');
  const toStr = toShanghaiInputValue(to_ms).replace('T', ' ');
  return `${fromStr} ~ ${toStr} (上海时间)`;
}
