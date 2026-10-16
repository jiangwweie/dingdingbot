/**
 * Time utility functions for Owner Console V2.
 * Adheres strictly to Kernel UTC boundaries and avoids fabricating ages/deadlines.
 */

/**
 * Return exact UTC day boundary (00:00:00.000 UTC) for a given millisecond timestamp.
 * Matches backend `utc_day_start_ms` in `_shared.py`.
 */
export function getUtcDayStartMs(timestampMs: number = Date.now()): number {
  const date = new Date(timestampMs);
  return Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
}

/**
 * Format timestamp into exact UTC date and time string.
 * Example: "2026-10-16 14:08:00 UTC"
 */
export function formatUtcDateTime(timestampMs: number | null | undefined): string {
  if (!timestampMs || timestampMs <= 0 || isNaN(timestampMs)) {
    return '—';
  }
  const d = new Date(timestampMs);
  const year = d.getUTCFullYear();
  const month = String(d.getUTCMonth() + 1).padStart(2, '0');
  const day = String(d.getUTCDate()).padStart(2, '0');
  const hours = String(d.getUTCHours()).padStart(2, '0');
  const minutes = String(d.getUTCMinutes()).padStart(2, '0');
  const seconds = String(d.getUTCSeconds()).padStart(2, '0');
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds} UTC`;
}

/**
 * Format remaining or elapsed duration relative to now.
 * Pure local computation, never triggers network refetch.
 */
export function formatRelativeCountdown(
  targetMs: number | null | undefined,
  nowMs: number = Date.now()
): string {
  if (!targetMs || targetMs <= 0) {
    return '未知';
  }
  const diffMs = targetMs - nowMs;
  if (diffMs > 0) {
    const totalSeconds = Math.floor(diffMs / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    if (hours > 24) {
      const days = Math.floor(hours / 24);
      const remHours = hours % 24;
      return `剩余 ${days}天 ${remHours}小时`;
    }
    return `剩余 ${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  } else {
    const elapsedSeconds = Math.floor(Math.abs(diffMs) / 1000);
    if (elapsedSeconds < 60) {
      return `已过期 ${elapsedSeconds}s 前`;
    }
    const elapsedMinutes = Math.floor(elapsedSeconds / 60);
    if (elapsedMinutes < 60) {
      return `已过期 ${elapsedMinutes}m 前`;
    }
    const elapsedHours = Math.floor(elapsedMinutes / 60);
    return `已过期 ${elapsedHours}h 前`;
  }
}

/**
 * Format age in seconds/hours.
 */
export function formatAgeFromTimestamp(
  timestampMs: number | null | undefined,
  nowMs: number = Date.now()
): { seconds: string; labelZh: string } {
  if (!timestampMs || timestampMs <= 0) {
    return { seconds: '未知', labelZh: '未知' };
  }
  const ageMs = Math.max(0, nowMs - timestampMs);
  const totalSeconds = Math.floor(ageMs / 1000);
  if (totalSeconds < 60) {
    return { seconds: `${totalSeconds}s`, labelZh: `${totalSeconds}秒前` };
  }
  const minutes = Math.floor(totalSeconds / 60);
  if (minutes < 60) {
    return { seconds: `${totalSeconds}s`, labelZh: `${minutes}分钟前` };
  }
  const hours = (ageMs / 3_600_000).toFixed(1);
  return { seconds: `${totalSeconds}s`, labelZh: `${hours}小时前` };
}

/**
 * Format duration in milliseconds into human-readable Chinese string.
 * Example: 7200000 -> "2小时", 8640000 -> "2小时24分", 45000 -> "45秒"
 */
export function formatDuration(durationMs: number | null | undefined): string {
  if (durationMs == null || durationMs < 0 || isNaN(durationMs)) {
    return '—';
  }
  const totalSeconds = Math.floor(durationMs / 1000);
  if (totalSeconds < 60) {
    return `${totalSeconds}秒`;
  }
  const totalMinutes = Math.floor(totalSeconds / 60);
  if (totalMinutes < 60) {
    const sec = totalSeconds % 60;
    return sec > 0 ? `${totalMinutes}分${sec}秒` : `${totalMinutes}分钟`;
  }
  const hours = Math.floor(totalMinutes / 60);
  const remMinutes = totalMinutes % 60;
  if (hours < 24) {
    return remMinutes > 0 ? `${hours}小时${remMinutes}分` : `${hours}小时`;
  }
  const days = Math.floor(hours / 24);
  const remHours = hours % 24;
  return remHours > 0 ? `${days}天${remHours}小时` : `${days}天`;
}

