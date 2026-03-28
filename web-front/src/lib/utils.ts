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
