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
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
      {/* 1. 今日净收益 (Net PnL) */}
      <div data-testid="net-pnl-card" className="rounded-lg border border-border bg-surface p-4 shadow-sm">
        <div className="flex items-center justify-between text-xs text-text-secondary">
          <span className="font-medium">今日净收益 (Net PnL)</span>
          <TrendingUp className="h-4 w-4 text-emerald-500" />
        </div>
        <div className="mt-2 flex items-baseline gap-2">
          <span data-testid="metric-value"
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
        <p className="mt-1 text-[11px] text-text-muted">
          {pnlIsUnavailable
            ? metrics.pnl_unavailable_reason || '今日暂无已完结交易结算事实'
            : '扣除全部交易手续费与执行滑点损耗'}
        </p>
      </div>

      {/* 2. 今日净 R (Net R) */}
      <div data-testid="net-r-card" className="rounded-lg border border-border bg-surface p-4 shadow-sm">
        <div className="flex items-center justify-between text-xs text-text-secondary">
          <span className="font-medium">今日累计收益 (Net R)</span>
          <Target className="h-4 w-4 text-brand" />
        </div>
        <div className="mt-2 flex items-baseline gap-2">
          <span data-testid="metric-value"
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
        <p className="mt-1 text-[11px] text-text-muted">
          以单笔初始风险单位 (R) 度量不对称右尾回报
        </p>
      </div>

      {/* 3. 今日信号与准入 (Today Signals & Admission) */}
      <div className="rounded-lg border border-border bg-surface p-4 shadow-sm">
        <div className="flex items-center justify-between text-xs text-text-secondary">
          <span className="font-medium">今日信号扫描与准入</span>
          <Radio className="h-4 w-4 text-text-muted" />
        </div>
        <div className="mt-2 flex items-baseline gap-2">
          <span className="font-mono text-2xl font-bold tracking-tight text-text-primary">
            {metrics.today_signal_count}
          </span>
          <span className="text-xs font-medium text-text-secondary">个信号</span>
          <span className="text-xs text-text-muted">·</span>
          <span className="font-mono text-xs text-emerald-600 dark:text-emerald-400 font-medium">
            准入 {metrics.admitted_signal_count}
          </span>
          <span className="text-xs text-text-muted">·</span>
          <span className="font-mono text-xs text-text-muted font-medium">
            拒绝 {metrics.rejected_signal_count}
          </span>
        </div>
        <p className="mt-1 text-[11px] text-text-muted">
          严格遵循门禁与容量规则 · 未决执行异常: {metrics.execution_incident_count} 笔
        </p>
      </div>
    </div>
  );
};
