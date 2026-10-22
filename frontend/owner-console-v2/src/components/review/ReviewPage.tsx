import React, { useState } from 'react';
import { useReviewData } from '../../hooks/useReviewData.ts';
import { useReviewFilterState } from '../../hooks/useUrlSearchParams.ts';
import { ReviewFilterBar } from './ReviewFilterBar.tsx';
import { ReviewMetricsDeck } from './ReviewMetricsDeck.tsx';
import { ReviewTable } from './ReviewTable.tsx';
import { ReviewBreakdownSections } from './ReviewBreakdownSections.tsx';
import { CausalityDrawer } from '../overview/CausalityDrawer.tsx';
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
    totalAttentionCount,
    refetch,
  } = useReviewData(filters);

  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);

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
              <span>复盘评估工作台 (Review)</span>
            </h1>
            <span className="inline-flex items-center gap-1 rounded bg-emerald-500/10 px-2 py-0.5 font-mono text-[10px] font-bold text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              REAL API · PROD
            </span>
            <span
              className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase ${
                freshness === 'fresh'
                  ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                  : 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
              }`}
            >
              {freshness}
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
            <span>{isFetching ? '正在读取真实 facts...' : '刷新复盘'}</span>
          </button>
        </div>
      </div>

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
      />

      {/* 4. Initial Loading State */}
      {isLoading && (
        <div className="py-20 text-center space-y-3">
          <div className="inline-block h-6 w-6 border-2 border-brand/30 border-t-brand rounded-full animate-spin" />
          <p className="text-xs text-text-secondary">正在读取复盘中心事实快照 (GET /api/owner/v1/review)...</p>
        </div>
      )}

      {/* 5. Complete Failure State */}
      {isError && (
        <div className="rounded-xl border border-rose-500/30 bg-surface p-8 text-center max-w-lg mx-auto my-8 shadow-sm space-y-3">
          <div className="inline-flex items-center justify-center h-12 w-12 rounded-full bg-rose-500/10 text-rose-500">
            <ShieldAlert className="h-6 w-6" />
          </div>
          <h3 className="text-base font-bold text-text-primary">Review API 暂时不可用</h3>
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
          <ReviewMetricsDeck
            summary={summary}
            totalAttentionCount={totalAttentionCount}
            onSelectTicket={setSelectedTicketId}
            isLoading={false}
          />

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
                    <span>加载更多复盘记录 (Cursor 分页)</span>
                    <span className="font-mono text-[10px] text-text-muted">已载入 {items.length} 笔</span>
                  </>
                )}
              </button>
            </div>
          )}

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
