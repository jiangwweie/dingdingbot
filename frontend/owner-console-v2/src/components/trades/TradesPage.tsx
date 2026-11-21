import { IncomeSummary, IncomeScopeBar } from '../common/IncomeSummary';
import React, { useState, useMemo } from 'react';
import { useTradesData } from '../../hooks/useTradesData';
import { useTradesFilterState } from '../../hooks/useUrlSearchParams';
import { TradesFilterBar } from './TradesFilterBar';
import { ActiveTradeCard } from './ActiveTradeCard';
import { CompletedTradeTable } from './CompletedTradeTable';
import { CausalityDrawer } from '../overview/CausalityDrawer';
import type { TradeEpisode } from '../../types/trades';
import { RefreshCw, AlertCircle, CheckCircle2 } from 'lucide-react';

export const TradesPage: React.FC = () => {
  const { filters, setFilters, resetFilters } = useTradesFilterState();

  const {
    isLoading,
    isFetching,
    isFetchingNextPage,
    hasNextPage,
    paginationError,
    refreshError,
    liveError,
    isLiveLoading,
    fetchNextPage,
    isError,
    error,
    freshness,
    allTrades,
    activeTrades,
    coverage,
    liveActiveTicketCount,
    completedTrades,
    metrics,
    performance,
    performanceError,
    refetch,
  } = useTradesData(filters);

  const filterMode = filters.filter_mode;
  const setFilterMode = (mode: 'all' | 'active' | 'completed') => {
    setFilters({ filter_mode: mode });
  };

  const [selectedEpisode, setSelectedEpisode] = useState<TradeEpisode | null>(null);
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);

  const openByEpisode = (ep: TradeEpisode) => {
    setSelectedTicketId(null);
    setSelectedEpisode(ep);
  };

  const openByTicketId = (ticketId: string) => {
    const matched = allTrades.find((t) => t.ticket_id === ticketId) ?? null;
    setSelectedEpisode(matched);
    setSelectedTicketId(ticketId);
  };

  const closeDrawer = () => {
    setSelectedEpisode(null);
    setSelectedTicketId(null);
  };

  const instrumentSuggestions = useMemo(() => {
    const set = new Set<string>();
    for (const t of activeTrades) {
      if (t.raw_item?.exchange_instrument_id) set.add(t.raw_item.exchange_instrument_id);
    }
    for (const t of allTrades) {
      if (t.raw_item?.exchange_instrument_id) set.add(t.raw_item.exchange_instrument_id);
    }
    return Array.from(set);
  }, [activeTrades, allTrades]);

  const handleManualRefresh = async () => {
    await refetch();
  };

  const hasCoverageAlert = Boolean(liveError) || (!isLiveLoading && !coverage.complete);

  return (
    <div id="trades-page" className="space-y-4">
      {/* 1. Compact Header & Mode Switcher */}
      <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface px-4 py-3.5 shadow-xs sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2.5">
          <h1 className="text-base font-bold tracking-tight text-text-primary">
            交易因果
          </h1>
          <span
            className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase ${
              freshness === 'fresh'
                ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                : 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
            }`}
          >
            {freshness}
          </span>
          <span className="text-xs text-text-muted font-mono">
            已加载 {metrics.totalCount} 笔
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center rounded-lg border border-border bg-surface-subtle p-1 text-xs">
            <button
              type="button"
              onClick={() => setFilterMode('all')}
              className={`rounded px-3 py-1 font-mono text-xs font-medium transition-colors cursor-pointer ${
                filterMode === 'all'
                  ? 'bg-surface text-brand font-bold shadow-xs border border-border'
                  : 'text-text-muted hover:text-text-primary'
              }`}
            >
              全部 ({metrics.totalCount})
            </button>
            <button
              type="button"
              onClick={() => setFilterMode('active')}
              className={`rounded px-3 py-1 font-mono text-xs font-medium transition-colors cursor-pointer ${
                filterMode === 'active'
                  ? 'bg-surface text-brand font-bold shadow-xs border border-border'
                  : 'text-text-muted hover:text-text-primary'
              }`}
            >
              在管 ({liveActiveTicketCount ?? '未知'})
            </button>
            <button
              type="button"
              onClick={() => setFilterMode('completed')}
              className={`rounded px-3 py-1 font-mono text-xs font-medium transition-colors cursor-pointer ${
                filterMode === 'completed'
                  ? 'bg-surface text-brand font-bold shadow-xs border border-border'
                  : 'text-text-muted hover:text-text-primary'
              }`}
            >
              已结束 ({metrics.completedCount})
            </button>
          </div>

          <button
            type="button"
            onClick={handleManualRefresh}
            disabled={isFetching}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text-secondary hover:bg-surface-elevated hover:text-text-primary transition-colors shadow-xs cursor-pointer"
            title="手动刷新 Ticket 账本"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin text-brand' : ''}`} />
            <span>刷新</span>
          </button>
        </div>
      </div>

      {/* 2. Filter Summary & Collapsible Advanced Filters */}
      <TradesFilterBar
        filters={filters}
        onChange={setFilters}
        onReset={resetFilters}
        disabled={isFetching}
        instrumentSuggestions={instrumentSuggestions}
      >
        <IncomeScopeBar view={filters.view} scope={filters.exit_scope} onChange={setFilters} />
      </TradesFilterBar>

      {/* 3. Single Authoritative Full-Window Income Summary */}
      <IncomeSummary
        summary={performance}
        error={performanceError}
        onRefresh={handleManualRefresh}
        onSelectTicket={openByTicketId}
      />

      {/* Always-visible Active Identity Verification Strip (never hidden even in 'completed' mode) */}
      <div
        role="status"
        data-testid="active-coverage"
        className={`rounded-lg border px-3.5 py-2 text-xs flex flex-wrap items-center justify-between gap-2 ${
          hasCoverageAlert
            ? 'border-amber-500/40 bg-amber-500/5 text-amber-700 dark:text-amber-300'
            : 'border-border bg-surface text-text-secondary'
        }`}
      >
        <div className="flex flex-wrap items-center gap-2">
          {hasCoverageAlert ? (
            <AlertCircle className="h-3.5 w-3.5 text-amber-500 flex-none" />
          ) : (
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 flex-none" />
          )}
          <span>
            实时在管身份：已加载 {activeTrades.length} 笔 / Overview 报告 {liveActiveTicketCount ?? '未知'} 笔 ·{' '}
            {isLiveLoading
              ? '正在核验实时在管身份...'
              : coverage.complete
              ? '本次快照身份一致'
              : `覆盖尚未确认，已知未覆盖 ${coverage.missing.length} 笔`}
          </span>
        </div>
        <span className="text-[11px] text-text-muted">
          实时在管不受历史筛选影响
        </span>
        {liveError && (
          <span role="alert" className="w-full text-danger font-medium">
            实时身份读取或刷新失败，已加载数据可能为旧快照：{liveError instanceof Error ? liveError.message : '请求失败'}
          </span>
        )}
      </div>

      {refreshError && (
        <div role="alert" data-testid="trades-refresh-error" className="rounded-lg border border-danger/30 bg-danger/5 p-3 text-xs text-danger">
          刷新失败，当前显示旧快照：{refreshError instanceof Error ? refreshError.message : '请求失败'}
          <button type="button" onClick={handleManualRefresh} className="ml-3 underline font-semibold cursor-pointer">
            重试刷新
          </button>
        </div>
      )}

      {isLoading && (
        <div role="status" className="p-4 text-xs text-text-muted">
          正在读取历史筛选范围...
        </div>
      )}

      {isError && (
        <div role="alert" className="rounded-lg border border-danger/30 bg-danger/5 p-4 text-xs text-danger">
          无法连接 Tickets API：{error instanceof Error ? error.message : '请求失败'}
          <button type="button" onClick={handleManualRefresh} className="ml-3 underline font-semibold cursor-pointer">
            重试
          </button>
        </div>
      )}

      {/* 4. Section 1: Active Trade Episodes */}
      {(filterMode === 'all' || filterMode === 'active') && (
        <section id="active-trade-episodes" data-testid="active-trade-episodes" className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="text-xs font-bold uppercase tracking-wider text-text-primary">
                当前在管交易
              </h2>
              <span className="rounded-full bg-brand/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-brand">
                {activeTrades.length} 笔在管
              </span>
            </div>
            <span className="text-[11px] text-text-muted">不受历史筛选影响</span>
          </div>

          {activeTrades.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {activeTrades.map((ep) => (
                <ActiveTradeCard
                  key={ep.ticket_id}
                  episode={ep}
                  onSelectEpisode={openByEpisode}
                />
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-border bg-surface p-5 text-center text-xs text-text-muted">
              <p className="font-semibold text-text-primary">
                {isLiveLoading ? '正在读取实时在管交易' : coverage.complete ? '当前无在管交易' : '实时在管覆盖尚未确认'}
              </p>
              {!coverage.complete && (
                <p className="mt-1">不能据此判断账户空仓，请查看身份核验及错误提示。</p>
              )}
            </div>
          )}
        </section>
      )}

      {/* 5. Section 2: Completed Trade Episodes */}
      {!isLoading && !isError && (filterMode === 'all' || filterMode === 'completed') && (
        <section id="completed-trade-episodes" data-testid="completed-trade-episodes" className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <h2 className="text-xs font-bold uppercase tracking-wider text-text-primary">
                已结束交易记录
              </h2>
              <span className="rounded-full bg-surface-subtle px-2 py-0.5 font-mono text-[11px] font-semibold text-text-secondary border border-border">
                已加载 {completedTrades.length} 笔
              </span>
            </div>
            <span className="text-[11px] text-text-muted">
              终态不等于已成交或已结算，详见每笔结果
            </span>
          </div>

          <CompletedTradeTable
            episodes={completedTrades}
            onSelectEpisode={openByEpisode}
          />

          {paginationError && (
            <p role="alert" data-testid="pagination-error" className="text-xs text-danger">
              更早记录加载失败，已加载数据保留。请点击加载更多重试。
            </p>
          )}

          {hasNextPage ? (
            <div
              data-testid="trades-pagination-bar"
              className="flex flex-col sm:flex-row items-center justify-between gap-3 rounded-lg border border-border bg-surface p-4 shadow-xs"
            >
              <div className="text-xs text-text-secondary">
                <span className="font-semibold text-text-primary">当前已加载前 {allTrades.length} 笔明细</span>
                <span className="text-text-muted ml-1.5">(尚有更早历史记录)</span>
              </div>
              <button
                type="button"
                data-testid="load-more-btn"
                onClick={() => fetchNextPage()}
                disabled={isFetchingNextPage}
                className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface-subtle px-4 py-2 text-xs font-semibold text-text-primary hover:bg-surface-elevated hover:border-brand/40 transition-colors shadow-xs disabled:opacity-50 cursor-pointer"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${isFetchingNextPage ? 'animate-spin text-brand' : ''}`} />
                <span>{isFetchingNextPage ? '正在加载更早记录...' : '加载更多历史交易'}</span>
              </button>
            </div>
          ) : (
            <div data-testid="trades-pagination-status" className="py-2 text-center text-[11px] text-text-muted">
              已加载当前筛选范围全部账本记录 (共 {allTrades.length} 笔)
            </div>
          )}
        </section>
      )}

      {/* 6. Causality Drawer (supports both loaded episodes and direct ticketId lookup) */}
      <CausalityDrawer
        episode={selectedEpisode}
        ticketId={selectedTicketId}
        onClose={closeDrawer}
      />
    </div>
  );
};
