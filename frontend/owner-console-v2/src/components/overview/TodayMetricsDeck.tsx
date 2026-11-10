import React from 'react';
import type { TodayPerformanceMetrics } from '../../types/overview';
import { TrendingUp, Target, Radio } from 'lucide-react';

interface TodayMetricsDeckProps {
  metrics: TodayPerformanceMetrics;
}

export const TodayMetricsDeck: React.FC<TodayMetricsDeckProps> = ({ metrics }) => {
  const pnlIsUnavailable = metrics.net_pnl_formatted === '--';
  const rIsUnavailable = metrics.net_r_formatted === '--';

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {/* 1. 今日已核实净收益 */}
      <div data-testid="net-pnl-card" className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-xs transition-all">
        <div className="flex items-center justify-between text-xs text-text-secondary">
          <span className="font-semibold tracking-wide">今日已核实净收益</span>
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
            <TrendingUp className="h-4 w-4" />
          </div>
        </div>
        <div className="mt-3 flex items-baseline gap-2.5 flex-wrap">
          <span
            data-testid="metric-value"
            className={`font-mono text-2xl sm:text-3xl font-bold tracking-tight ${
              pnlIsUnavailable
                ? 'text-text-muted'
                : metrics.net_pnl_is_positive
                ? 'text-emerald-600 dark:text-emerald-400'
                : 'text-rose-600 dark:text-rose-400'
            }`}
          >
            {metrics.net_pnl_formatted}
          </span>
          {metrics.income_coverage && (
            <span className="text-[11px] text-text-muted font-medium break-words">
              {metrics.income_coverage}
            </span>
          )}
        </div>
        <p className="mt-2 text-xs text-text-muted leading-relaxed">
          {pnlIsUnavailable
            ? metrics.pnl_unavailable_reason || '今日暂无已完结交易结算事实'
            : '按后端已核实成交、手续费与资金费核算'}
        </p>
      </div>

      {/* 2. 今日净 R (Net R) */}
      <div data-testid="net-r-card" className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-xs transition-all">
        <div className="flex items-center justify-between text-xs text-text-secondary">
          <span className="font-semibold tracking-wide">今日累计单笔净 R</span>
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-brand/10 text-brand">
            <Target className="h-4 w-4" />
          </div>
        </div>
        <div className="mt-3 flex items-baseline gap-2.5">
          <span
            data-testid="metric-value"
            className={`font-mono text-2xl sm:text-3xl font-bold tracking-tight ${
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
        <p className="mt-2 text-xs text-text-muted leading-relaxed">
          上海今日终态交易 · 单笔净 R 合计，不代表账户收益率
        </p>
      </div>

      {/* 3. 今日信号与准入 */}
      <div className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-xs transition-all">
        <div className="flex items-center justify-between text-xs text-text-secondary">
          <span className="font-semibold tracking-wide">今日信号扫描与准入</span>
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-surface-subtle text-text-muted border border-border">
            <Radio className="h-4 w-4" />
          </div>
        </div>
        <div className="mt-3 flex items-baseline gap-2 flex-wrap">
          <span className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-text-primary">
            {metrics.today_signal_count}
          </span>
          <span className="text-xs font-medium text-text-secondary">个信号</span>
          <span className="text-xs text-text-muted">·</span>
          <span className="font-mono text-xs text-emerald-600 dark:text-emerald-400 font-semibold">
            准入 {metrics.admitted_signal_count}
          </span>
          <span className="text-xs text-text-muted">·</span>
          <span className="font-mono text-xs text-text-muted font-semibold">
            拒绝 {metrics.rejected_signal_count}
          </span>
        </div>
        <p className="mt-2 text-xs text-text-muted leading-relaxed">
          严格遵循门禁与容量规则 · 未决执行异常: {metrics.execution_incident_count} 笔
        </p>
      </div>
    </div>
  );
};
