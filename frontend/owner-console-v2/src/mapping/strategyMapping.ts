import Decimal from 'decimal.js';
import type {
  StrategyVersionSummary,
  StrategyControlView,
  EnrichedStrategyVersion,
  MoneyMetric,
} from '../types/strategies.ts';
import type { StrategyAdmissionHealth } from '../types/controls.ts';
import { MoneyDecimal } from './tradeTruth.ts';

export const STRATEGY_METADATA: Record<string, { nameZh: string; timeframe: string }> = {
  'CPM-RO-001': { nameZh: '均线回踩做多', timeframe: '1h close' },
  'BRF2-001': { nameZh: '假反弹衰竭做空', timeframe: '1h close' },
  'MI-001': { nameZh: '相对强弱冲量', timeframe: '1h close' },
  'MPG-001': { nameZh: '趋势动量持续', timeframe: '1h close' },
  'SOR-1H-001': { nameZh: '单边突破 (1h/15m)', timeframe: '1h close' },
  'SOR-US-EQ-PERP-001': { nameZh: '美股 Perp 突破', timeframe: '1h close' },
  'SOR-001': { nameZh: '旧单边突破策略', timeframe: '已退役' },
};

export const FIRST_PATH_ZH: Record<string, string> = {
  tp1_first: 'TP1 先到达',
  initial_stop_first: '止损先到达',
  ambiguous_same_bar: '同 Bar 歧义',
  opening_range_failure: '开盘区间失效',
  time_stop: '时间止损 (Time Stop)',
  session_exit: '时段平仓 (Session Exit)',
  horizon_complete: '观察周期完成',
};

export function formatFirstPathLabel(path: string | null | undefined): string {
  if (!path) return '全部路径';
  return FIRST_PATH_ZH[path] ?? path;
}

export function formatStrategyMoneyMetric(
  metric: MoneyMetric | null | undefined,
  defaultUnavailableText: string = '待完成 Review'
): { formatted: string; value: string | null; isPositive: boolean | null; isUnavailable: boolean } {
  if (!metric || metric.value === null || metric.value === undefined || metric.unavailable_reason) {
    if (metric?.unavailable_reason === 'no_confirmed_natural_review') {
      return { formatted: '无已确认自然评审', value: null, isPositive: null, isUnavailable: true };
    }
    if (metric?.unavailable_reason === 'ticket_active') {
      return { formatted: '持仓中 · 未结', value: null, isPositive: null, isUnavailable: true };
    }
    return { formatted: defaultUnavailableText, value: null, isPositive: null, isUnavailable: true };
  }

  let num: Decimal;
  try {
    num = new MoneyDecimal(metric.value);
  } catch {
    return { formatted: '—', value: null, isPositive: null, isUnavailable: true };
  }

  if (!num.isFinite()) {
    return { formatted: '—', value: null, isPositive: null, isUnavailable: true };
  }

  const sign = num.isPositive() && !num.isZero() ? '+' : '';
  const unitStr = metric.unit ? ` ${metric.unit}` : '';
  const formatted = `${sign}${num.toFixed(2)}${unitStr}`.trim();
  const isPositive = num.isZero() ? null : num.isPositive();

  return {
    formatted,
    value: num.toString(),
    isPositive,
    isUnavailable: false,
  };
}

export function computeWinRate(
  winCount: number,
  lossCount: number
): { percent: number | null; label: string; evaluatedCount: number } {
  const evaluatedCount = winCount + lossCount;
  if (evaluatedCount === 0) {
    return { percent: null, label: '无胜负样本 · 不可评价', evaluatedCount: 0 };
  }

  const percent = Math.round((winCount / evaluatedCount) * 100);
  return {
    percent,
    label: `${winCount} 胜 / ${lossCount} 负 (${percent}%)`,
    evaluatedCount,
  };
}

export function formatObservationMetric(value: string | number | null | undefined, suffix: string = ''): string {
  if (value === null || value === undefined || value === '') return '—';
  const num = Number(value);
  if (isNaN(num)) return `${value}${suffix}`;
  return `${num.toFixed(2)}${suffix}`;
}

export interface StrategyRuntimeExtra {
  admissionHealth?: StrategyAdmissionHealth;
  activeTicketCount?: number;
  firstBlocker?: string | null;
}

export function enrichStrategyVersion(
  summary: StrategyVersionSummary,
  control?: StrategyControlView,
  runtimeExtra?: StrategyRuntimeExtra
): EnrichedStrategyVersion {
  const meta = STRATEGY_METADATA[summary.strategy_group_id] ?? {
    nameZh: summary.strategy_group_display_name || summary.strategy_group_id,
    timeframe: '1h close',
  };

  const pnl = formatStrategyMoneyMetric(summary.net_pnl);
  const r = formatStrategyMoneyMetric(summary.net_r);
  const winRate = computeWinRate(summary.win_count, summary.loss_count);

  let runtimeStatus: EnrichedStrategyVersion['runtimeStatus'] = 'unknown';
  let runtimeStatusLabel = '状态未知';

  if (control) {
    if (runtimeExtra?.firstBlocker) {
      runtimeStatus = 'blocked';
      runtimeStatusLabel = `阻断 · ${runtimeExtra.firstBlocker}`;
    } else if (control.effective_state === 'paused' || control.effective_state === 'paused_by_global') {
      runtimeStatus = 'paused';
      runtimeStatusLabel = control.effective_state === 'paused_by_global' ? '全局暂停' : '已暂停';
    } else if (control.effective_state === 'enabled') {
      runtimeStatus = 'enabled';
      runtimeStatusLabel = '运行中';
    }
  }

  return {
    summary,
    control,
    admissionHealth: runtimeExtra?.admissionHealth,
    displayNameZh: meta.nameZh,
    timeframe: meta.timeframe,
    isCurrent: summary.is_current,
    version: summary.version,
    netPnlFormatted: pnl.formatted,
    netPnlIsPositive: pnl.isPositive,
    netRFormatted: r.formatted,
    netRIsPositive: r.isPositive,
    hasConfirmedReview: !pnl.isUnavailable,
    winRatePercent: winRate.percent,
    winRateLabel: winRate.label,
    totalTickets: summary.ticket_count,
    naturalTerminals: summary.natural_terminal_count,
    controlledExits: summary.controlled_exit_count,
    confirmedReviews: summary.confirmed_review_count ?? summary.confirmed_natural_review_count,
    pendingReviews: summary.selected_terminal_count != null ? summary.selected_terminal_count - (summary.confirmed_review_count ?? 0) : summary.pending_natural_review_count,
    tp1Reached: summary.tp1_reached_count,
    tp1NotReached: summary.tp1_not_reached_count,
    runtimeStatus,
    runtimeStatusLabel,
    activeTicketCount: runtimeExtra?.activeTicketCount ?? 0,
    firstBlocker: runtimeExtra?.firstBlocker ?? null,
    observationCount: summary.observation_count,
    completedObservationCount: summary.completed_observation_count,
    medianMfeR: formatObservationMetric(summary.median_mfe_r, ' R'),
    medianMaeR: formatObservationMetric(summary.median_mae_r, ' R'),
  };
}
