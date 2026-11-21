import React, { useState } from 'react';
import { useReviewData } from '../../hooks/useReviewData.ts';
import { useReviewFilterState } from '../../hooks/useUrlSearchParams.ts';
import { ReviewFilterBar } from './ReviewFilterBar.tsx';
import { IncomeSummary, IncomeScopeBar } from '../common/IncomeSummary';
import { ReviewTable } from './ReviewTable.tsx';
import { ReviewBreakdownSections } from './ReviewBreakdownSections.tsx';
import { CausalityDrawer } from '../overview/CausalityDrawer.tsx';
import { formatReviewFreshness } from '../../mapping/reviewMapping.ts';
import {
  RefreshCw,
  AlertCircle,
  FileSearch,
  ShieldAlert,
} from 'lucide-react';

export const ReviewPage: React.FC = () => {
  const { filters, setFilters, resetFilters } = useReviewFilterState();

  const {
    isLoading,
    isFetching,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
    isError,
    paginationError,
    refreshError,
    error,
    freshness,
    generatedAt,
    items,
    summary,
    performance,performanceError,
    refetch,
  } = useReviewData(filters);

  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);
  const freshnessMeta = formatReviewFreshness(freshness);

  const handleManualRefresh = async () => {
    await refetch();
  };

  return (
    <div id="review-page" className="space-y-4">
      {/* 1. Header Ribbon */}
      <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4 shadow-xs sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-base font-bold tracking-tight text-text-primary flex items-center gap-2">
              <FileSearch className="h-5 w-5 text-brand" />
              <span>复盘评估</span>
            </h1>
            <span
              data-testid="review-freshness-badge"
              className={`rounded px-1.5 py-0.5 text-[10px] font-semibold border ${
                freshnessMeta.tone === 'success'
                  ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20'
                  : freshnessMeta.tone === 'attention'
                  ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20'
                  : freshnessMeta.tone === 'danger'
                  ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20'
                  : 'bg-surface-subtle text-text-secondary border-border'
              }`}
            >
              {freshnessMeta.label}
            </span>
          </div>
          <p className="mt-1 text-xs text-text-secondary leading-relaxed">
            逐笔核对退出原因、收益核算与执行证据，未知事实明确标注
          </p>
        </div>

        {/* Right side: Refresh Button */}
        <div className="flex items-center gap-2">
          {generatedAt && (
            <span className="font-mono text-[11px] text-text-muted hidden sm:inline">
              快照: {new Date(generatedAt).toLocaleTimeString('zh-CN', { hour12: false })}
            </span>
          )}
          <button
            type="button"
            onClick={handleManualRefresh}
            disabled={isFetching}
            className="inline-flex items-center gap-1.5 rounded border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text-primary hover:bg-surface-elevated transition-colors shadow-2xs disabled:opacity-60 cursor-pointer"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 text-text-muted ${isFetching ? 'animate-spin text-brand' : ''}`}
            />
            <span>{isFetching ? '刷新中...' : '刷新复盘'}</span>
          </button>
        </div>
      </div>

      {performanceError && <IncomeSummary summary={null} error={performanceError} onRefresh={handleManualRefresh} />}
      {/* 2. Refresh Error Banner */}
      {refreshError && (
        <div
          role="status"
          className="flex items-center justify-between rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-300 shadow-2xs"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-amber-500 flex-none" />
            <div>
              <strong className="font-semibold">数据刷新失败：</strong>
              <span>
                继续显示上一次成功快照。
                {refreshError instanceof Error ? ` (${refreshError.message})` : ''}
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={handleManualRefresh}
            className="rounded border border-amber-500/40 bg-surface px-2.5 py-1 text-[11px] font-semibold text-amber-700 dark:text-amber-300 hover:bg-amber-500/20 transition-colors"
          >
            重试刷新
          </button>
        </div>
      )}

      {/* 3. Filter Bar */}
      <ReviewFilterBar
        filters={filters}
        onChange={setFilters}
        onReset={resetFilters}
        disabled={isLoading}
      >
        <IncomeScopeBar view={filters.view} scope={filters.exit_scope} onChange={setFilters} />
      </ReviewFilterBar>

      {/* 4. Initial Loading State */}
      {isLoading && (
        <div className="py-20 text-center space-y-3">
          <div className="inline-block h-6 w-6 border-2 border-brand/30 border-t-brand rounded-full animate-spin" />
          <p className="text-xs text-text-secondary">正在加载复盘记录与收益统计...</p>
        </div>
      )}

      {/* 5. Complete Failure State */}
      {isError && (
        <div className="rounded-xl border border-rose-500/30 bg-surface p-8 text-center max-w-lg mx-auto my-8 shadow-sm space-y-3">
          <div className="inline-flex items-center justify-center h-12 w-12 rounded-full bg-rose-500/10 text-rose-500">
            <ShieldAlert className="h-6 w-6" />
          </div>
          <h3 className="text-base font-bold text-text-primary">复盘数据暂时不可用</h3>
          <p className="text-xs text-text-secondary leading-relaxed">
            {error instanceof Error ? error.message : '未能成功获取真实复盘事实。'}
          </p>
          <div className="pt-2">
            <button
              type="button"
              onClick={handleManualRefresh}
              className="inline-flex items-center gap-1.5 rounded bg-brand px-4 py-2 text-xs font-semibold text-white hover:bg-brand/90 transition-colors cursor-pointer"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              <span>重新加载</span>
            </button>
          </div>
        </div>
      )}

      {/* 6. Normal Content when data is present */}
      {!isLoading && !isError && (
        <>
          {/* Summary Deck */}
          <IncomeSummary summary={performance} error={performanceError} onRefresh={handleManualRefresh} onSelectTicket={setSelectedTicketId} />

          {/* Records Table */}
          <ReviewTable
            items={items}
            onSelectTicket={(ticketId) => setSelectedTicketId(ticketId)}
            isLoading={false}
          />

          {/* Cursor Pagination & Failure Retry */}
          {paginationError && (
            <div className="flex items-center justify-between rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-700 dark:text-rose-300">
              <div className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4 text-rose-500 flex-none" />
                <span>加载下一页失败，已加载 {items.length} 条记录已保留。</span>
              </div>
              <button
                type="button"
                onClick={() => fetchNextPage()}
                className="rounded border border-rose-500/40 bg-surface px-2.5 py-1 text-[11px] font-semibold text-rose-700 dark:text-rose-300 hover:bg-rose-500/20 transition-colors cursor-pointer"
              >
                重试加载
              </button>
            </div>
          )}

          {hasNextPage && !paginationError && (
            <div className="flex justify-center pt-2">
              <button
                type="button"
                onClick={() => fetchNextPage()}
                disabled={isFetchingNextPage}
                className="inline-flex items-center gap-2 rounded-lg border border-border bg-surface px-6 py-2.5 text-xs font-semibold text-text-primary hover:bg-surface-elevated transition-colors shadow-2xs disabled:opacity-60 cursor-pointer"
              >
                {isFetchingNextPage ? (
                  <>
                    <div className="h-3.5 w-3.5 border-2 border-brand/30 border-t-brand rounded-full animate-spin" />
                    <span>正在加载更多复盘记录...</span>
                  </>
                ) : (
                  <>
                    <span>加载更多复盘记录</span>
                    <span className="font-mono text-[10px] text-text-muted">已载入 {items.length} 笔</span>
                  </>
                )}
              </button>
            </div>
          )}

          <p className="text-[11px] text-text-muted">以下证据分布仅对应已加载的 {items.length} 笔明细；顶部收益覆盖完整窗口。</p>
          {/* Breakdown Sections */}
          <ReviewBreakdownSections
            summary={summary}
            onSelectTicket={(ticketId) => setSelectedTicketId(ticketId)}
          />
        </>
      )}

      {/* 7. Causality Drawer (Timeline, Candlestick Chart, Evidence, Commands) */}
      <CausalityDrawer
        ticketId={selectedTicketId}
        isOpen={Boolean(selectedTicketId)}
        onClose={() => setSelectedTicketId(null)}
      />
    </div>
  );
};
