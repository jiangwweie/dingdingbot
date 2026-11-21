import React from 'react';
import type { TodayPerformanceMetrics } from '../../types/overview';
import { ArrowRight } from 'lucide-react';

interface TodayMetricsDeckProps {
  metrics: TodayPerformanceMetrics;
  onNavigateToReview?: () => void;
  onNavigateToTrades?: () => void;
}

export const TodayMetricsDeck: React.FC<TodayMetricsDeckProps> = ({
  metrics,
  onNavigateToReview,
  onNavigateToTrades,
}) => {
  const pnlIsUnavailable = metrics.net_pnl_formatted === '--';
  const rIsUnavailable = metrics.net_r_formatted === '--';
  const pnlIsPartial = Boolean(metrics.pnl_is_partial || metrics.income_coverage?.includes('部分合计'));
  const rIsPartial = Boolean(metrics.r_is_partial || metrics.income_coverage?.includes('部分合计'));
  const pnlBadgeText = metrics.pnl_coverage ?? metrics.income_coverage ?? (pnlIsUnavailable ? '未知 / 暂无结算' : '已核实');
  const rBadgeText = metrics.r_coverage ?? metrics.income_coverage ?? (rIsUnavailable ? '未知 / 暂无结算' : '已核实');
  const incidentCount = metrics.execution_incident_count ?? 0;

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {/* 1. 今日净收益 */}
      <div data-testid="net-pnl-card" className="rounded-xl border border-border bg-surface p-4 shadow-xs transition-all flex flex-col justify-between">
        <div className="flex items-center justify-between text-xs text-text-secondary gap-2">
          <span className="font-semibold tracking-wide">今日净收益</span>
          {onNavigateToReview && (
            <button
              type="button"
              onClick={onNavigateToReview}
              className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px] font-semibold text-brand hover:bg-brand/10 transition-colors cursor-pointer"
            >
              <span>复盘明细</span>
              <ArrowRight className="h-3 w-3" />
            </button>
          )}
        </div>

        <div className="mt-2.5 flex items-baseline justify-between gap-2 flex-wrap">
          <span
            data-testid="metric-value"
            className={`font-mono text-2xl font-bold tracking-tight ${
              pnlIsUnavailable
                ? 'text-text-muted'
                : metrics.net_pnl_is_positive
                ? 'text-emerald-600 dark:text-emerald-400'
                : 'text-rose-600 dark:text-rose-400'
            }`}
          >
            {metrics.net_pnl_formatted}
          </span>
        </div>

        <details className="mt-2 text-[11px]">
          <summary
            className={`cursor-pointer select-none inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-medium border focus-visible:outline-2 focus-visible:outline-brand ${
              pnlIsPartial || pnlIsUnavailable
                ? 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/30 font-semibold'
                : 'bg-surface-subtle text-text-secondary border-border'
            }`}
          >
            <span>{pnlBadgeText} ›</span>
          </summary>
          <div className="mt-1.5 text-text-muted leading-relaxed break-words">
            {pnlIsUnavailable
              ? metrics.pnl_unavailable_reason || '今日暂无已完结交易结算事实'
              : '上海今日终态交易 · 已结算终态净额（含手续费与资金费）'}
          </div>
        </details>
      </div>

      {/* 2. 今日单笔净 R 合计 */}
      <div data-testid="net-r-card" className="rounded-xl border border-border bg-surface p-4 shadow-xs transition-all flex flex-col justify-between">
        <div className="flex items-center justify-between text-xs text-text-secondary gap-2">
          <span className="font-semibold tracking-wide">今日单笔净 R 合计</span>
          {onNavigateToReview && (
            <button
              type="button"
              onClick={onNavigateToReview}
              className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px] font-semibold text-brand hover:bg-brand/10 transition-colors cursor-pointer"
            >
              <span>复盘明细</span>
              <ArrowRight className="h-3 w-3" />
            </button>
          )}
        </div>

        <div className="mt-2.5 flex items-baseline justify-between gap-2 flex-wrap">
          <span
            data-testid="metric-value"
            className={`font-mono text-2xl font-bold tracking-tight ${
              rIsUnavailable
                ? 'text-text-muted'
                : metrics.net_r_is_positive
                ? 'text-emerald-600 dark:text-emerald-400'
                : 'text-rose-600 dark:text-rose-400'
            }`}
          >
            {metrics.net_r_formatted}
          </span>
        </div>

        <details className="mt-2 text-[11px]">
          <summary
            className={`cursor-pointer select-none inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-medium border focus-visible:outline-2 focus-visible:outline-brand ${
              rIsPartial || rIsUnavailable
                ? 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/30 font-semibold'
                : 'bg-surface-subtle text-text-secondary border-border'
            }`}
          >
            <span>{rBadgeText} ›</span>
          </summary>
          <div className="mt-1.5 text-text-muted leading-relaxed break-words">
            上海今日终态交易 · 单笔净 R 合计，不代表账户收益率
          </div>
        </details>
      </div>

      {/* 3. 今日信号与准入 */}
      <div className="rounded-xl border border-border bg-surface p-4 shadow-xs transition-all flex flex-col justify-between">
        <div className="flex items-center justify-between text-xs text-text-secondary gap-2">
          <span className="font-semibold tracking-wide">今日信号与准入</span>
          {onNavigateToTrades && (
            <button
              type="button"
              onClick={onNavigateToTrades}
              className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px] font-semibold text-brand hover:bg-brand/10 transition-colors cursor-pointer"
            >
              <span>交易因果</span>
              <ArrowRight className="h-3 w-3" />
            </button>
          )}
        </div>

        <div className="mt-2.5 flex items-baseline gap-2 flex-wrap">
          <span className="font-mono text-2xl font-bold tracking-tight text-text-primary">
            {metrics.today_signal_count}
          </span>
          <span className="text-xs font-medium text-text-secondary">个信号</span>
        </div>

        <div className="mt-2 flex items-center justify-between gap-2 flex-wrap text-[11px]">
          <div className="inline-flex items-center gap-2 font-mono">
            <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
              准入 {metrics.admitted_signal_count}
            </span>
            <span className="text-text-muted">·</span>
            <span className="text-text-muted font-medium">
              拒绝 {metrics.rejected_signal_count}
            </span>
          </div>

          {incidentCount > 0 && (
            <span className="rounded bg-rose-500/10 px-1.5 py-0.5 font-mono text-[11px] font-bold text-rose-600 dark:text-rose-400 border border-rose-500/20">
              未决执行异常 {incidentCount} 笔
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
