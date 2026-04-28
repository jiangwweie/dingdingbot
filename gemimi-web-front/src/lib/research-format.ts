import { BadgeVariant, DASH, fmtDateTime } from '@/src/lib/console-utils';
import type { ResearchJobStatus, ResearchPositionResult, ResearchRunResult, ResearchCloseEvent } from '@/src/types';

export function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function fmtMoney(value: unknown, digits = 2): string {
  const n = toNumber(value);
  if (n === null) return DASH;
  return n.toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function fmtRatio(value: unknown, digits = 1): string {
  const n = toNumber(value);
  if (n === null) return DASH;
  return `${(n * 100).toFixed(digits)}%`;
}

export function fmtMetric(value: unknown, digits = 2): string {
  const n = toNumber(value);
  if (n === null) return DASH;
  return n.toFixed(digits);
}

export function fmtUtcMs(value: unknown): string {
  if (value === null || value === undefined || value === '') return DASH;
  if (typeof value === 'number') {
    return fmtDateTime(new Date(value).toISOString());
  }
  if (typeof value === 'string') {
    if (/^\d+$/.test(value)) {
      return fmtDateTime(new Date(Number(value)).toISOString());
    }
    return fmtDateTime(value);
  }
  return DASH;
}

export function researchJobStatusLabel(status: ResearchJobStatus | string | null | undefined): string {
  switch (status) {
    case 'PENDING': return '等待中';
    case 'RUNNING': return '运行中';
    case 'SUCCEEDED': return '已完成';
    case 'FAILED': return '失败';
    case 'CANCELED': return '已取消';
    default: return status || DASH;
  }
}

export function researchJobStatusVariant(status: ResearchJobStatus | string | null | undefined): BadgeVariant {
  switch (status) {
    case 'SUCCEEDED': return 'outline';
    case 'RUNNING': return 'info';
    case 'FAILED': return 'danger';
    case 'PENDING': return 'warning';
    case 'CANCELED': return 'default';
    default: return 'default';
  }
}

export function signedMoneyClass(value: unknown): string {
  const n = toNumber(value);
  if (n === null || n === 0) return 'text-zinc-700 dark:text-zinc-300';
  return n > 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400';
}

export function shortResearchName(value: string | null | undefined): string {
  if (!value) return DASH;
  return value
    .replace(/^optuna_candidate_?/, '')
    .replace(/^candidate-/, '')
    .replace(/^rr_/, '结果 ')
    .slice(0, 36);
}

export function warningLabel(value: string): string {
  switch (value) {
    case 'sortino_missing_or_suspect': return '索提诺比率异常';
    case 'parameter_near_boundary': return '参数触及边界';
    case 'low_trade_count': return '交易次数偏少';
    case 'drawdown_too_high': return '回撤偏高';
    case 'insufficient_oos': return '样本外验证不足';
    default: return value.replaceAll('_', ' ');
  }
}

export function reviewLabel(value: string | null | undefined): string {
  switch (value) {
    case 'PASS_STRICT': return '严格通过';
    case 'PASS_STRICT_WITH_WARNINGS': return '通过但有警告';
    case 'PASS_LOOSE': return '初步达标';
    case 'REJECT': return '不建议';
    case 'PENDING': return '待评审';
    default: return value || DASH;
  }
}

export function getRunMetric(run: ResearchRunResult | undefined | null, key: string): unknown {
  return run?.summary_metrics?.[key];
}

export function getResolvedRuntime(run: ResearchRunResult | null | undefined): Record<string, unknown> {
  const spec = run?.spec_snapshot;
  if (!spec || typeof spec !== 'object') return {};
  const resolved = (spec as Record<string, unknown>).resolved_runtime_overrides;
  return resolved && typeof resolved === 'object' ? resolved as Record<string, unknown> : {};
}

export function getResolvedOrderStrategy(run: ResearchRunResult | null | undefined): Record<string, unknown> {
  const spec = run?.spec_snapshot;
  if (!spec || typeof spec !== 'object') return {};
  const resolved = (spec as Record<string, unknown>).resolved_order_strategy;
  return resolved && typeof resolved === 'object' ? resolved as Record<string, unknown> : {};
}

export function getSpecCosts(runOrSpec: ResearchRunResult | Record<string, unknown> | null | undefined): Record<string, unknown> {
  const spec = 'spec_snapshot' in (runOrSpec || {}) ? (runOrSpec as ResearchRunResult).spec_snapshot : runOrSpec;
  if (!spec || typeof spec !== 'object') return {};
  const costs = (spec as Record<string, unknown>).costs;
  return costs && typeof costs === 'object' ? costs as Record<string, unknown> : {};
}

export function arrayText(value: unknown): string {
  if (Array.isArray(value)) return value.join(', ');
  if (value === null || value === undefined || value === '') return DASH;
  return String(value);
}

export function describeRunParameters(run: ResearchRunResult | undefined | null): string {
  const runtime = getResolvedRuntime(run);
  const order = getResolvedOrderStrategy(run);
  const direction = arrayText(runtime.allowed_directions);
  const ema = runtime.ema_period ? `EMA${runtime.ema_period}` : 'EMA--';
  const tpTargets = arrayText(order.tp_targets || runtime.tp_targets);
  return `${ema} · ${direction} · TP ${tpTargets}`;
}

/** Compute Profit Factor from positions */
export function computeProfitFactor(positions: ResearchPositionResult[]): number | string | null {
  const values = positions.map(p => toNumber(p.realized_pnl)).filter((v): v is number => v !== null);
  const grossProfit = values.filter(v => v > 0).reduce((sum, v) => sum + v, 0);
  const grossLoss = Math.abs(values.filter(v => v < 0).reduce((sum, v) => sum + v, 0));
  if (grossProfit === 0 && grossLoss === 0) return null;
  if (grossLoss === 0) return '∞';
  return grossProfit / grossLoss;
}

/** Compute max consecutive losses from positions */
export function computeMaxConsecutiveLosses(positions: ResearchPositionResult[]): number | null {
  const pnls = positions.map(p => toNumber(p.realized_pnl)).filter((v): v is number => v !== null);
  if (pnls.length === 0) return null;
  let maxStreak = 0;
  let currentStreak = 0;
  for (const pnl of pnls) {
    if (pnl < 0) {
      currentStreak++;
      if (currentStreak > maxStreak) maxStreak = currentStreak;
    } else {
      currentStreak = 0;
    }
  }
  return maxStreak;
}

/** Compute annualized return rate given total return and time span in ms */
export function computeAnnualizedReturn(totalReturn: number | null, startMs: number | null, endMs: number | null): number | null {
  if (totalReturn === null || startMs === null || endMs === null) return null;
  if (endMs <= startMs) return null;
  const days = (endMs - startMs) / (86400000);
  if (days < 30) return null; // too short for meaningful annualization
  const years = days / 365.25;
  return Math.pow(1 + totalReturn, 1 / years) - 1;
}

/** Compute PnL ratio (realized_pnl / entry_price * quantity) for a position */
export function pnlRatioClass(pnl: unknown): string {
  const n = toNumber(pnl);
  if (n === null) return 'text-zinc-700 dark:text-zinc-300';
  if (n > 0) return 'text-emerald-600 dark:text-emerald-400';
  if (n < 0) return 'text-rose-600 dark:text-rose-400';
  return 'text-zinc-700 dark:text-zinc-300';
}

/** Direction badge color */
export function directionLabel(dir: string | null | undefined): string {
  switch (dir) {
    case 'LONG': return '多';
    case 'SHORT': return '空';
    default: return dir || DASH;
  }
}

export function directionVariant(dir: string | null | undefined): BadgeVariant {
  switch (dir) {
    case 'LONG': return 'success';
    case 'SHORT': return 'danger';
    default: return 'default';
  }
}

export function closeEventLabel(event: ResearchCloseEvent | null | undefined): string {
  if (!event) return '退出';
  const val = String(event.event_type || event.exit_reason || event.event_category || '').toUpperCase();
  if (val.includes('TAKE_PROFIT_1') || val.includes('TP1')) return '止盈1';
  if (val.includes('TAKE_PROFIT_2') || val.includes('TP2')) return '止盈2';
  if (val.includes('TAKE_PROFIT') || val.includes('TP')) return '止盈';
  if (val.includes('STOP_LOSS') || val.includes('SL')) return '止损';
  if (val.includes('TRAILING')) return '追踪退出';
  if (val.includes('MANUAL') || val.includes('CLOSE')) return '手动退出';
  const fallback = event.event_type || event.exit_reason || event.event_category;
  return fallback || '退出';
}

export function closeEventVariant(event: ResearchCloseEvent | null | undefined): BadgeVariant {
  if (!event) return 'default';
  const val = String(event.event_type || event.exit_reason || event.event_category || '').toUpperCase();
  if (val.includes('TAKE_PROFIT') || val.includes('TP')) return 'success';
  if (val.includes('STOP_LOSS') || val.includes('SL')) return 'danger';
  return 'default';
}