/**
 * Runtime 交易驾驶舱格式化工具
 * — 状态中文化、风险进度条、环境标识、滑点计算
 */

import { DASH } from '@/src/lib/console-utils';

// ─── 信号状态 ───────────────────────────────────────────

export const SIGNAL_STATUS_LABELS: Record<string, string> = {
  pending: '等待执行',
  active: '已进入执行链',
  executed: '已执行',
  blocked: '被风控拦截',
  blocked_by_risk: '被风控拦截',
  expired: '已过期',
  cancelled: '已撤销',
  canceled: '已撤销',
  superseded: '已被替代',
  failed: '执行失败',
  skipped: '已跳过',
  closed: '已平仓',
};

export function signalStatusLabel(status: string | null | undefined): string {
  if (!status) return DASH;
  return SIGNAL_STATUS_LABELS[status.toLowerCase()] ?? status;
}

// ─── 执行意图状态 ───────────────────────────────────────

export const INTENT_STATUS_LABELS: Record<string, string> = {
  pending: '待审批',
  approved: '已批准',
  rejected: '已拒绝',
  submitted: '已提交',
  open: '已挂单',
  filled: '已成交',
  partially_filled: '部分成交',
  protecting: '保护单处理中',
  partially_protected: '部分保护',
  completed: '已完成',
  blocked: '已阻断',
  failed: '失败',
  cancelled: '已撤销',
  canceled: '已撤销',
  expired: '已过期',
  executing: '执行中',
};

export function intentStatusLabel(status: string): string {
  return INTENT_STATUS_LABELS[status.toLowerCase()] ?? status;
}

// ─── 订单状态 ───────────────────────────────────────────

export const ORDER_STATUS_LABELS: Record<string, string> = {
  created: '已创建',
  pending: '待提交',
  submitted: '已提交',
  open: '已挂单',
  new: '已挂单',
  filled: '已成交',
  partially_filled: '部分成交',
  cancelled: '已撤销',
  canceled: '已撤销',
  rejected: '被拒绝',
  failed: '失败',
  expired: '已过期',
};

export function orderStatusLabel(status: string): string {
  return ORDER_STATUS_LABELS[status.toLowerCase()] ?? status;
}

// ─── 方向 ───────────────────────────────────────────────

export const DIRECTION_LABELS: Record<string, string> = {
  long: '做多',
  short: '做空',
  LONG: '做多',
  SHORT: '做空',
  buy: '做多',
  sell: '做空',
};

export function directionLabel(dir: string | undefined | null): string {
  if (!dir) return DASH;
  return DIRECTION_LABELS[dir] ?? dir;
}

export function directionColor(dir: string | undefined | null): string {
  if (!dir) return 'text-gray-400';
  const lower = dir.toLowerCase();
  return lower === 'long' || lower === 'buy' ? 'text-green-400' : 'text-red-400';
}

// ─── 风险进度条 ─────────────────────────────────────────

export type RiskLevel = 'low' | 'medium' | 'high';

export function riskLevel(usagePercent: number): RiskLevel {
  if (usagePercent < 50) return 'low';
  if (usagePercent < 80) return 'medium';
  return 'high';
}

export function riskBarColor(level: RiskLevel): string {
  switch (level) {
    case 'low': return 'bg-green-500';
    case 'medium': return 'bg-yellow-500';
    case 'high': return 'bg-red-500';
  }
}

export function riskTextColor(level: RiskLevel): string {
  switch (level) {
    case 'low': return 'text-green-400';
    case 'medium': return 'text-yellow-400';
    case 'high': return 'text-red-400';
  }
}

// ─── 环境标识 ───────────────────────────────────────────

export type EnvironmentMode = 'SIM' | 'LIVE' | 'UNKNOWN';

export function environmentModeLabel(mode: string | undefined | null): EnvironmentMode {
  if (!mode) return 'UNKNOWN';
  const upper = mode.toUpperCase();
  if (upper === 'LIVE' || upper === 'PRODUCTION' || upper === 'REAL') return 'LIVE';
  if (upper === 'SIM' || upper.startsWith('SIM-') || upper === 'SIMULATION' || upper === 'PAPER' || upper === 'TEST' || upper === 'TESTNET') return 'SIM';
  return 'UNKNOWN';
}

export function environmentBadgeStyle(mode: EnvironmentMode): string {
  switch (mode) {
    case 'SIM': return 'bg-blue-900/60 text-blue-300 border-blue-700';
    case 'LIVE': return 'bg-red-900/60 text-red-300 border-red-700 animate-pulse';
    case 'UNKNOWN': return 'bg-gray-800 text-gray-400 border-gray-600';
  }
}

// ─── 时间与时长 ─────────────────────────────────────────

export function formatDuration(ms: number): string {
  if (ms < 0) return DASH;
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}秒`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}分钟`;
  const hours = Math.floor(minutes / 60);
  const remainMin = minutes % 60;
  if (hours < 24) return `${hours}小时${remainMin > 0 ? ` ${remainMin}分` : ''}`;
  const days = Math.floor(hours / 24);
  const remainHours = hours % 24;
  return `${days}天${remainHours > 0 ? ` ${remainHours}小时` : ''}`;
}

export function holdingDuration(openedAt: string | undefined | null): string {
  if (!openedAt) return '暂无数据';
  const start = new Date(openedAt).getTime();
  const now = Date.now();
  if (isNaN(start)) return '暂无数据';
  return formatDuration(now - start);
}

// ─── 滑点计算 ───────────────────────────────────────────

export function slippageBps(suggestedPrice: number | undefined | null, fillPrice: number | undefined | null): string {
  if (!suggestedPrice || !fillPrice || suggestedPrice === 0) return '暂不可计算';
  const bps = ((fillPrice - suggestedPrice) / suggestedPrice) * 10000;
  const sign = bps >= 0 ? '+' : '';
  return `${sign}${bps.toFixed(1)} bps`;
}

export function slippageColor(suggestedPrice: number | undefined | null, fillPrice: number | undefined | null): string {
  if (!suggestedPrice || !fillPrice || suggestedPrice === 0) return 'text-gray-500';
  const bps = Math.abs(((fillPrice - suggestedPrice) / suggestedPrice) * 10000);
  if (bps < 5) return 'text-green-400';
  if (bps < 20) return 'text-yellow-400';
  return 'text-red-400';
}

// ─── 健康状态 ───────────────────────────────────────────

export type HealthStatus = 'healthy' | 'degraded' | 'down' | 'unknown';

export function healthFromComponents(
  components: Record<string, { status?: string; healthy?: boolean }>
): HealthStatus {
  const values = Object.values(components);
  if (values.length === 0) return 'unknown';
  const anyDown = values.some(c => c.healthy === false || c.status === 'down' || c.status === 'error');
  if (anyDown) return 'down';
  const anyDegraded = values.some(c => c.status === 'degraded' || c.status === 'warning');
  if (anyDegraded) return 'degraded';
  return 'healthy';
}

export function healthLabel(status: HealthStatus): string {
  switch (status) {
    case 'healthy': return '正常运行';
    case 'degraded': return '性能降级';
    case 'down': return '服务中断';
    case 'unknown': return '状态未知';
  }
}

export function healthDotColor(status: HealthStatus): string {
  switch (status) {
    case 'healthy': return 'bg-green-500';
    case 'degraded': return 'bg-yellow-500';
    case 'down': return 'bg-red-500';
    case 'unknown': return 'bg-gray-500';
  }
}

// ─── 百分比格式 ─────────────────────────────────────────

export function formatPercent(value: number | undefined | null, decimals = 2): string {
  if (value == null || isNaN(value)) return DASH;
  return `${value.toFixed(decimals)}%`;
}

export function pnlColor(value: number | undefined | null): string {
  if (value == null || isNaN(value)) return 'text-gray-400';
  if (value > 0) return 'text-green-400';
  if (value < 0) return 'text-red-400';
  return 'text-gray-400';
}

// ─── ID 截断 ────────────────────────────────────────────

export function truncateId(id: string | undefined | null, head = 6, tail = 4): string {
  if (!id) return DASH;
  if (id.length <= head + tail + 3) return id;
  return `${id.slice(0, head)}…${id.slice(-tail)}`;
}
