import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * 获取快捷日期范围
 * @param type 快捷类型：today | 3days | 7days | 14days | 30days
 * @returns { start: number, end: number } UNIX 毫秒戳
 */
export function getQuickDateRange(type: string): { start: number; end: number } {
  const now = Date.now();
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  switch (type) {
    case 'today':
      return { start: today.getTime(), end: now };
    case '3days':
      return {
        start: new Date(now - 3 * 24 * 60 * 60 * 1000).setHours(0, 0, 0, 0),
        end: now
      };
    case '7days':
      return {
        start: new Date(now - 7 * 24 * 60 * 60 * 1000).setHours(0, 0, 0, 0),
        end: now
      };
    case '14days':
      return {
        start: new Date(now - 14 * 24 * 60 * 60 * 1000).setHours(0, 0, 0, 0),
        end: now
      };
    case '30days':
      return {
        start: new Date(now - 30 * 24 * 60 * 60 * 1000).setHours(0, 0, 0, 0),
        end: now
      };
    default:
      return { start: today.getTime(), end: now };
  }
}

/**
 * 格式化时间戳为 YYYY-MM-DD HH:mm 格式
 */
export function formatTimestamp(ts: number | null): string {
  if (!ts) return '-';
  const date = new Date(ts);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return `${year}-${month}-${day} ${hours}:${minutes}`;
}

/**
 * 将时间戳转换为 datetime-local 输入格式
 */
export function timestampToDateTimeLocal(ts: number | null): string {
  if (!ts) return '';
  const date = new Date(ts);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

/**
 * 格式化时间戳为北京时间 (UTC+8)
 * 用于统一信号触发时间显示，解决时区混乱问题
 * 强制使用 UTC+8，与币安 App（中国大陆）显示一致
 * @param ts 毫秒时间戳（UTC）或 ISO 字符串
 * @param format 格式：'full' | 'short' | 'date' | 'time'
 * @returns 北京时间字符串，如 '03-30 18:15 (CST)' 或 '2026-03-30 18:15:00 (CST)'
 */
export function formatBeijingTime(
  ts: number | string | null | undefined,
  format: 'full' | 'short' | 'date' | 'time' = 'short'
): string {
  if (!ts) return '-';

  // 处理字符串 ISO 时间戳
  const timestamp = typeof ts === 'string' ? new Date(ts).getTime() : ts;

  // 转换为北京时间 (UTC+8)
  // 方法：将 UTC 时间戳加上 8 小时的偏移量
  const BEIJING_TZ_OFFSET_MS = 8 * 60 * 60 * 1000;  // 8 小时 = 28800000 毫秒
  const beijingTime = new Date(timestamp + BEIJING_TZ_OFFSET_MS);

  const year = beijingTime.getUTCFullYear();
  const month = String(beijingTime.getUTCMonth() + 1).padStart(2, '0');
  const day = String(beijingTime.getUTCDate()).padStart(2, '0');
  const hours = String(beijingTime.getUTCHours()).padStart(2, '0');
  const minutes = String(beijingTime.getUTCMinutes()).padStart(2, '0');
  const seconds = String(beijingTime.getUTCSeconds()).padStart(2, '0');

  switch (format) {
    case 'full':
      return `${year}-${month}-${day} ${hours}:${minutes}:${seconds} (CST)`;
    case 'short':
      return `${month}-${day} ${hours}:${minutes} (CST)`;
    case 'date':
      return `${year}-${month}-${day}`;
    case 'time':
      return `${hours}:${minutes}:${seconds} (CST)`;
    default:
      return `${month}-${day} ${hours}:${minutes} (CST)`;
  }
}

/**
 * 格式化时间戳为北京时间 (UTC+8)
 * 用于统一信号触发时间显示，解决时区混乱问题
 * @param ts 毫秒时间戳（UTC）
 * @param format 格式：'full' | 'short' | 'date' | 'time'
 * @returns 北京时间字符串，如 '03-30 18:15:00 (CST)' 或 '2026-03-30 18:15:00 (CST)'
 */
export function formatBeijingTime(
  ts: number | string | null | undefined,
  format: 'full' | 'short' | 'date' | 'time' = 'short'
): string {
  if (!ts) return '-';

  // 处理字符串 ISO 时间戳
  const timestamp = typeof ts === 'string' ? new Date(ts).getTime() : ts;
  const date = new Date(timestamp);

  // 获取 UTC 时间
  const utcYear = date.getUTCFullYear();
  const utcMonth = date.getUTCMonth();
  const utcDate = date.getUTCDate();
  const utcHours = date.getUTCHours();
  const utcMinutes = date.getUTCMinutes();
  const utcSeconds = date.getUTCSeconds();

  // 转换为北京时间 (UTC+8)
  const beijingDate = new Date(Date.UTC(utcYear, utcMonth, utcDate, utcHours + 8, utcMinutes, utcSeconds));

  const year = beijingDate.getUTCFullYear();
  const month = String(beijingDate.getUTCMonth() + 1).padStart(2, '0');
  const day = String(beijingDate.getUTCDate()).padStart(2, '0');
  const hours = String(beijingDate.getUTCHours()).padStart(2, '0');
  const minutes = String(beijingDate.getUTCMinutes()).padStart(2, '0');
  const seconds = String(beijingDate.getUTCSeconds()).padStart(2, '0');

  switch (format) {
    case 'full':
      return `${year}-${month}-${day} ${hours}:${minutes}:${seconds} (CST)`;
    case 'short':
      return `${month}-${day} ${hours}:${minutes}:${seconds} (CST)`;
    case 'date':
      return `${year}-${month}-${day}`;
    case 'time':
      return `${hours}:${minutes}:${seconds} (CST)`;
    default:
      return `${month}-${day} ${hours}:${minutes}:${seconds} (CST)`;
  }
}
