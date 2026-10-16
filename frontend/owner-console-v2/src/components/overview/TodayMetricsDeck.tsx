import React from 'react';
import type { TodayPerformanceMetrics } from '../../types/overview';
import { TrendingUp, Target, CheckCircle2 } from 'lucide-react';

interface TodayMetricsDeckProps {
  metrics: TodayPerformanceMetrics;
}

export const TodayMetricsDeck: React.FC<TodayMetricsDeckProps> = ({ metrics }) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
      {/* 1. 今日净收益 (Net PnL) */}
      <div className="rounded-lg border border-border bg-surface p-4 shadow-sm">
        <div className="flex items-center justify-between text-xs text-text-secondary">
          <span className="font-medium">今日净收益 (Net PnL)</span>
          <TrendingUp className="h-4 w-4 text-emerald-500" />
        </div>
        <div className="mt-2 flex items-baseline gap-2">
          <span className="font-mono text-2xl font-bold tracking-tight text-emerald-600 dark:text-emerald-400">
            {metrics.net_pnl_usd >= 0 ? `+${metrics.net_pnl_usd.toFixed(2)}` : metrics.net_pnl_usd.toFixed(2)}
          </span>
          <span className="font-mono text-xs font-semibold text-text-muted">USDT</span>
        </div>
        <p className="mt-1 text-[11px] text-text-muted">
          扣除全部交易手续费与执行滑点损耗
        </p>
      </div>

      {/* 2. 今日净 R (Net R) */}
      <div className="rounded-lg border border-border bg-surface p-4 shadow-sm">
        <div className="flex items-center justify-between text-xs text-text-secondary">
          <span className="font-medium">今日累计收益 (Net R)</span>
          <Target className="h-4 w-4 text-brand" />
        </div>
        <div className="mt-2 flex items-baseline gap-2">
          <span className="font-mono text-2xl font-bold tracking-tight text-emerald-600 dark:text-emerald-400">
            {metrics.net_r >= 0 ? `+${metrics.net_r.toFixed(2)}` : metrics.net_r.toFixed(2)} R
          </span>
          <span className="inline-flex items-center rounded bg-brand/10 px-1.5 py-0.5 text-[10px] font-mono font-medium text-brand">
            盈亏比 {metrics.profit_factor}x
          </span>
        </div>
        <p className="mt-1 text-[11px] text-text-muted">
          以单笔风险单位 (R) 度量不对称右尾回报
        </p>
      </div>

      {/* 3. 已完成交易 (Completed Trades) */}
      <div className="rounded-lg border border-border bg-surface p-4 shadow-sm">
        <div className="flex items-center justify-between text-xs text-text-secondary">
          <span className="font-medium">今日已完结交易</span>
          <CheckCircle2 className="h-4 w-4 text-text-muted" />
        </div>
        <div className="mt-2 flex items-baseline gap-2">
          <span className="font-mono text-2xl font-bold tracking-tight text-text-primary">
            {metrics.completed_trades_count}
          </span>
          <span className="text-xs font-medium text-text-secondary">笔</span>
          <span className="text-xs text-text-muted">·</span>
          <span className="font-mono text-xs text-emerald-600 dark:text-emerald-400 font-medium">
            {metrics.win_trades_count} 胜 {metrics.loss_trades_count} 负 ({metrics.win_rate_percent}%)
          </span>
        </div>
        <p className="mt-1 text-[11px] text-text-muted">
          全链路严格执行，0 笔异常强平或非受控退出
        </p>
      </div>
    </div>
  );
};
