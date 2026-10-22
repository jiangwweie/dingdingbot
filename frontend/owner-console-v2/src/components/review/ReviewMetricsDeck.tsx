import React from 'react';
import type { ReviewCenterSummary } from '../../types/review.ts';
import { formatReviewMoneyMetric } from '../../mapping/reviewMapping.ts';
import { formatShanghaiRangeDisplay } from '../../utils/timeRange.ts';
import {
  TrendingUp,
  Target,
  Receipt,
  Coins,
  CheckCircle2,
  AlertTriangle,
  Layers,
  HelpCircle,
  Info,
} from 'lucide-react';

interface ReviewMetricsDeckProps {
  summary: ReviewCenterSummary | null;
  totalAttentionCount: number;
  isLoading?: boolean;
  onSelectTicket?: (ticketId: string) => void;
}

export const ReviewMetricsDeck: React.FC<ReviewMetricsDeckProps> = ({
  summary,
  totalAttentionCount,
  isLoading = false,
  onSelectTicket,
}) => {
  if (isLoading || !summary) {
    return (
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4 xl:grid-cols-8">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="flex flex-col justify-between rounded-lg border border-border bg-surface p-3 shadow-xs animate-pulse min-h-[78px]"
          >
            <div className="h-3 w-16 bg-surface-subtle rounded" />
            <div className="h-5 w-20 bg-surface-subtle rounded mt-2" />
          </div>
        ))}
      </div>
    );
  }

  const totals = summary.verified_totals ?? summary;
  const pnl = formatReviewMoneyMetric(totals.net_pnl, { sign: true });
  const r = formatReviewMoneyMetric(totals.net_r, { sign: true, fractionDigits: 4 });
  const fees = formatReviewMoneyMetric(totals.fees);
  const funding = formatReviewMoneyMetric(totals.funding);

  const coverageNote = (name: string) => {
    const coverage = summary.metric_coverage?.[name];
    if (!coverage) return <span className="text-[10px] text-text-muted">覆盖范围未提供</span>;
    const missing = coverage.missing_ticket_ids ?? [];
    return <div className="mt-1 text-[10px] text-text-muted" data-testid={`coverage-${name}`}>
      {coverage.available_count < coverage.total_count ? '已核实部分合计 · ' : '已核实合计 · '}覆盖 {coverage.available_count}/{coverage.total_count} 笔
      {missing.length > 0 && <details className="mt-1"><summary className="cursor-pointer text-amber-600">查看 {missing.length} 笔缺项交易</summary>
        {missing.map(id => <button key={id} type="button" className="block break-all text-left text-brand underline" onClick={() => onSelectTicket?.(id)}>{id}</button>)}
      </details>}
    </div>;
  };

  const rangeDisplay = formatShanghaiRangeDisplay(summary.from_ms, summary.to_ms);

  return (
    <div data-testid="review-metrics-deck" className="space-y-2">
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4 xl:grid-cols-8">
        {/* 1. Completed Tickets */}
        <div data-testid="card-completed-tickets" className="flex flex-col justify-between rounded-lg border border-border bg-surface p-3 shadow-xs min-h-[78px]">
          <div className="flex items-center justify-between text-[11px] font-medium text-text-secondary">
            <span>Completed Tickets</span>
            <Layers className="h-3.5 w-3.5 text-text-muted" />
          </div>
          <div className="mt-1 flex items-baseline gap-1">
            <span data-testid="metric-completed-count" className="font-mono text-lg font-bold tracking-tight text-text-primary tabular-number">
              {summary.sample_count}
            </span>
            <span className="text-[10px] text-text-muted">笔终态</span>
          </div>
        </div>

        {/* 2. Net PnL */}
        <div data-testid="card-net-pnl" className="flex flex-col justify-between rounded-lg border border-border bg-surface p-3 shadow-xs min-h-[78px]">
          <div className="flex items-center justify-between text-[11px] font-medium text-text-secondary">
            <span>Net PnL (净盈亏)</span>
            <TrendingUp className="h-3.5 w-3.5 text-text-muted" />
          </div>
          <div className="mt-1 flex flex-col">
            <span
              data-testid="metric-net-pnl"
              className={`font-mono text-lg font-bold tracking-tight tabular-number ${
                pnl.isUnavailable
                  ? 'text-text-muted'
                  : pnl.isPositive === null
                  ? 'text-text-secondary'
                  : pnl.isPositive
                  ? 'text-emerald-600 dark:text-emerald-400'
                  : 'text-rose-600 dark:text-rose-400'
              }`}
              title={pnl.formatted}
            >
              {pnl.formatted}
            </span>
            {coverageNote('net_pnl')}
          </div>
        </div>

        {/* 3. Net R */}
        <div data-testid="card-net-r" className="flex flex-col justify-between rounded-lg border border-border bg-surface p-3 shadow-xs min-h-[78px]">
          <div className="flex items-center justify-between text-[11px] font-medium text-text-secondary">
            <span>Net R (净 R)</span>
            <Target className="h-3.5 w-3.5 text-brand" />
          </div>
          <div className="mt-1 flex flex-col">
            <span
              data-testid="metric-net-r"
              className={`font-mono text-lg font-bold tracking-tight tabular-number ${
                r.isUnavailable
                  ? 'text-text-muted'
                  : r.isPositive === null
                  ? 'text-text-secondary'
                  : r.isPositive
                  ? 'text-emerald-600 dark:text-emerald-400'
                  : 'text-rose-600 dark:text-rose-400'
              }`}
              title={r.formatted}
            >
              {r.formatted}
            </span>
            {coverageNote('net_r')}
          </div>
        </div>

        {/* 4. Fees */}
        <div data-testid="card-fees" className="flex flex-col justify-between rounded-lg border border-border bg-surface p-3 shadow-xs min-h-[78px]">
          <div className="flex items-center justify-between text-[11px] font-medium text-text-secondary">
            <span>Fees (手续费)</span>
            <Receipt className="h-3.5 w-3.5 text-text-muted" />
          </div>
          <div className="mt-1 flex flex-col">
            <span data-testid="metric-fees" className="font-mono text-lg font-bold tracking-tight text-text-primary tabular-number truncate" title={fees.formatted}>
              {fees.formatted}
            </span>
            {coverageNote('fees')}
          </div>
        </div>

        {/* 5. Funding */}
        <div data-testid="card-funding" className="flex flex-col justify-between rounded-lg border border-border bg-surface p-3 shadow-xs min-h-[78px]">
          <div className="flex items-center justify-between text-[11px] font-medium text-text-secondary">
            <span>Funding (资金费)</span>
            <Coins className="h-3.5 w-3.5 text-text-muted" />
          </div>
          <div className="mt-1 flex flex-col">
            <span data-testid="metric-funding" className="font-mono text-lg font-bold tracking-tight text-text-primary tabular-number truncate" title={funding.formatted}>
              {funding.formatted}
            </span>
            {coverageNote('funding')}
          </div>
        </div>

        {/* 6. 完整 Review */}
        <div data-testid="card-complete-review" className="flex flex-col justify-between rounded-lg border border-border bg-surface p-3 shadow-xs min-h-[78px]">
          <div className="flex items-center justify-between text-[11px] font-medium text-text-secondary">
            <span>Review 完整</span>
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
          </div>
          <div className="mt-1 flex items-baseline gap-1">
            <span data-testid="metric-complete-count" className="font-mono text-lg font-bold tracking-tight text-emerald-600 dark:text-emerald-400 tabular-number">
              {summary.complete_review_count}
            </span>
            <span className="text-[10px] text-text-muted">笔完整</span>
          </div>
        </div>

        {/* 7. 不完整 Review */}
        <div data-testid="card-incomplete-review" className="flex flex-col justify-between rounded-lg border border-border bg-surface p-3 shadow-xs min-h-[78px]">
          <div className="flex items-center justify-between text-[11px] font-medium text-text-secondary">
            <span>复盘有待核实项</span>
            <HelpCircle className="h-3.5 w-3.5 text-amber-500" />
          </div>
          <div className="mt-1 flex items-baseline gap-1">
            <span data-testid="metric-incomplete-count" className={`font-mono text-lg font-bold tracking-tight tabular-number ${summary.incomplete_review_count > 0 ? 'text-amber-600 dark:text-amber-400' : 'text-text-muted'}`}>
              {summary.incomplete_review_count}
            </span>
            <span className="text-[10px] text-text-muted">待核实</span>
          </div>
        </div>

        {/* 8. Attention 数 */}
        <div data-testid="card-attention" className="flex flex-col justify-between rounded-lg border border-border bg-surface p-3 shadow-xs min-h-[78px]">
          <div className="flex items-center justify-between text-[11px] font-medium text-text-secondary">
            <span>Attention 关注</span>
            <AlertTriangle className="h-3.5 w-3.5 text-rose-500" />
          </div>
          <div className="mt-1 flex items-baseline gap-1">
            <span data-testid="metric-attention-count" className={`font-mono text-lg font-bold tracking-tight tabular-number ${totalAttentionCount > 0 ? 'text-rose-600 dark:text-rose-400' : 'text-text-muted'}`}>
              {totalAttentionCount}
            </span>
            <span className="text-[10px] text-text-muted">项待核对</span>
          </div>
        </div>
      </div>

      {/* Scope disclosure note */}
      <div className="flex items-center gap-1.5 px-1 text-[11px] text-text-muted">
        <Info className="h-3.5 w-3.5 flex-none" />
        <span data-testid="review-scope-note">
          统计口径：仅已加载终态记录统计（共 {summary.sample_count} 笔），基于查询窗口 {rangeDisplay}。各项金额独立列明覆盖笔数；部分合计不代表整个筛选范围的总收益，缺失事实不按 0 计算。
          {summary.next_cursor ? ' 尚有后续分页，加载更多后更新覆盖范围。' : ''}
        </span>
      </div>
    </div>
  );
};
