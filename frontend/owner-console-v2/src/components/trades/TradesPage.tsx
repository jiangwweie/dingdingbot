import { IncomeSummary, IncomeScopeBar } from '../common/IncomeSummary';
import React, { useState } from 'react';
import { useTradesData } from '../../hooks/useTradesData';
import { useTradesFilterState } from '../../hooks/useUrlSearchParams';
import { TradesFilterBar } from './TradesFilterBar';
import { ActiveTradeCard } from './ActiveTradeCard';
import { CompletedTradeTable } from './CompletedTradeTable';
import { CausalityDrawer } from '../overview/CausalityDrawer';
import type { TradeEpisode } from '../../types/trades';
import {
  RefreshCw,
  AlertCircle,
  Layers,
  ShieldCheck,
  TrendingUp,
  Activity,
  CheckCircle2,
} from 'lucide-react';

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
    metrics,performance,performanceError,
    refetch,
  } = useTradesData(filters);

  const filterMode = filters.filter_mode;
  const setFilterMode = (mode: 'all' | 'active' | 'completed') => {
    setFilters({ filter_mode: mode });
  };

  const [selectedEpisode, setSelectedEpisode] = useState<TradeEpisode | null>(null);

  const handleManualRefresh = async () => {
    await refetch();
  };

  return (
    <div id="trades-page" className="space-y-5">
      {/* 1. Header & Live Indicator Ribbon */}
      <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-5 shadow-xs sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-base font-bold tracking-tight text-text-primary">
              交易因果与生命周期 (Trades)
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
            以 <strong className="text-text-primary">Trade Episode</strong> 为核心业务对象 · 贯穿 8 阶段生命周期因果与审计证据
          </p>
        </div>

        {/* Filter Switcher & Refresh */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Tabs: All / Active / Completed */}
          <div className="flex items-center rounded-lg border border-border bg-surface-subtle p-1 text-xs">
            <button
              type="button"
              onClick={() => setFilterMode('all')}
              className={`rounded px-3 py-1 font-mono text-xs font-medium transition-colors ${
                filterMode === 'all'
                  ? 'bg-surface text-brand font-bold shadow-xs border border-border'
                  : 'text-text-muted hover:text-text-primary'
              }`}
            >
              已加载 ({metrics.totalCount})
            </button>
            <button
              type="button"
              onClick={() => setFilterMode('active')}
              className={`rounded px-3 py-1 font-mono text-xs font-medium transition-colors ${
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
              className={`rounded px-3 py-1 font-mono text-xs font-medium transition-colors ${
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
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text-secondary hover:bg-surface-elevated hover:text-text-primary transition-colors shadow-xs"
            title="手动刷新 Ticket 账本"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin text-brand' : ''}`} />
            <span>刷新</span>
          </button>
        </div>
      </div>

      {/* 2. Unified Historical Filter Bar */}
      <TradesFilterBar
        filters={filters}
        onChange={setFilters}
        onReset={resetFilters}
        disabled={isFetching}
      />

      {/* 3. Live Active Coverage Ribbon */}
      <div role="status" className="rounded border border-border bg-surface p-3 text-xs text-text-secondary" data-testid="active-coverage">
        实时在管身份核验：已加载 {activeTrades.length} 笔；Overview 报告 {liveActiveTicketCount ?? '未知'} 笔。
        历史筛选不影响此区域，实时在管交易不受历史日期、策略、标的、方向或状态条件限制。
        {coverage.complete ? ' 本次只读快照身份一致。' : ` 覆盖尚未确认，已知未覆盖 ${coverage.missing.length} 笔。`}
        {liveError && <span role="alert" className="block text-danger">实时身份读取或刷新失败，已加载数据可能为旧快照：{liveError instanceof Error ? liveError.message : '请求失败'}</span>}
        {isLiveLoading && <span className="block">正在核验实时在管身份...</span>}
      </div>
      {refreshError && (
        <div role="alert" data-testid="trades-refresh-error" className="rounded border border-danger/30 p-3 text-xs text-danger">
          刷新失败，当前显示旧快照：{refreshError instanceof Error ? refreshError.message : '请求失败'}
          <button type="button" onClick={handleManualRefresh} className="ml-3 underline">重试刷新</button>
        </div>
      )}
      {isLoading && <div role="status" className="p-4 text-xs">正在读取历史筛选范围...</div>}
      {isError && <div role="alert" className="p-4 text-xs text-danger">
        无法连接 Tickets API：{error instanceof Error ? error.message : '请求失败'}
        <button type="button" onClick={handleManualRefresh} className="ml-3 underline">重试</button>
      </div>}
      <IncomeScopeBar view={filters.view} scope={filters.exit_scope} onChange={setFilters} />
      <IncomeSummary summary={performance} error={performanceError} onRefresh={handleManualRefresh} onSelectTicket={(id)=>setSelectedEpisode(allTrades.find(t=>t.ticket_id===id)??null)} />
      {/* 2. Top Summary Metrics Deck (L1 Owner Summary) */}
      {!isLoading && !isError && <div data-testid="trades-metrics-ribbon" className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <div data-testid="metric-total-trades" className="rounded-lg border border-border bg-surface p-3.5 shadow-xs">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-text-muted">
            <Activity className="h-3.5 w-3.5 text-brand" />
            <span>已加载明细数</span>
          </div>
          <div data-testid="metric-value" className="mt-1 font-mono text-lg font-bold text-text-primary">
            {metrics.totalCount}
          </div>
          <div data-testid="metric-subtext" className="text-[10px] text-text-muted mt-0.5 truncate" title={metrics.scopeLabel}>
            {metrics.scopeLabel}
          </div>
        </div>

        <div data-testid="metric-active-trades" className="rounded-lg border border-border bg-surface p-3.5 shadow-xs">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-text-muted">
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />
            <span>筛选范围内在管记录</span>
          </div>
          <div data-testid="metric-value" className="mt-1 font-mono text-lg font-bold text-brand">
            {metrics.activeCount}
          </div>
          <div data-testid="metric-subtext" className="text-[10px] text-text-muted mt-0.5">
            生命周期在管中 · 依阶段保护或退出
          </div>
        </div>

        <div data-testid="metric-completed-trades" className="rounded-lg border border-border bg-surface p-3.5 shadow-xs">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-text-muted">
            <CheckCircle2 className="h-3.5 w-3.5 text-text-secondary" />
            <span>全窗口已结束持仓 / 净胜率</span>
          </div>
          <div data-testid="metric-value" className="mt-1 font-mono text-lg font-bold text-text-primary">
            {metrics.completedCount}{' '}
            <span data-testid="metric-win-rate" className="text-xs font-normal text-text-muted">
              ({metrics.winRatePercent != null ? `${metrics.winRatePercent}%` : '—'})
            </span>
          </div>
          <div data-testid="metric-subtext" className="text-[10px] text-text-muted mt-0.5 truncate" title={metrics.winRateDenominatorText}>
            {metrics.winRateDenominatorText}
          </div>
        </div>

        <div data-testid="metric-total-pnl" className="rounded-lg border border-border bg-surface p-3.5 shadow-xs">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-text-muted">
            <TrendingUp className="h-3.5 w-3.5 text-brand" />
            <span>{metrics.hasPnlGaps ? '已记录已结收益' : '累计已结收益'}</span>
          </div>
          <div data-testid="metric-value" className="mt-1 font-mono text-lg font-bold text-text-primary">
            {metrics.totalNetPnlFormatted}
          </div>
          <div data-testid="metric-subtext" className="text-[10px] text-text-muted mt-0.5 truncate" title={metrics.pnlCoverageText}>
            {metrics.pnlCoverageText}
          </div>
        </div>

        <div data-testid="metric-total-r" className="rounded-lg border border-border bg-surface p-3.5 shadow-xs">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-text-muted">
            <Layers className="h-3.5 w-3.5 text-brand" />
            <span>{metrics.hasRGaps ? '已记录风险回报' : '累计单笔净 R'}</span>
          </div>
          <div data-testid="metric-value" className="mt-1 font-mono text-lg font-bold text-text-primary">
            {metrics.totalNetRFormatted}
          </div>
          <div data-testid="metric-subtext" className="text-[10px] text-text-muted mt-0.5 truncate" title={metrics.rCoverageText}>
            {metrics.rCoverageText}
          </div>
        </div>
      </div>}

      {/* 3. Section 1: Active Trade Episodes (Only when filter is 'all' or 'active') */}
      {(filterMode === 'all' || filterMode === 'active') && (
        <section id="active-trade-episodes" data-testid="active-trade-episodes" className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="text-xs font-bold uppercase tracking-wider text-text-primary">
                当前在管交易 (Active Trade Episodes)
              </h2>
              <span className="rounded-full bg-brand/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-brand">
                {activeTrades.length} 笔在管
              </span>
            </div>
            <span className="text-[11px] text-text-muted">实时账户身份 · 不受历史筛选影响</span>
          </div>

          {activeTrades.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {activeTrades.map((ep) => (
                <ActiveTradeCard
                  key={ep.ticket_id}
                  episode={ep}
                  onSelectEpisode={(selected) => setSelectedEpisode(selected)}
                />
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-border bg-surface p-6 text-center text-xs text-text-muted">
              <AlertCircle className="mx-auto h-7 w-7 text-amber-500 mb-1.5" />
              <p className="font-semibold text-text-primary">{isLiveLoading ? '正在读取实时在管交易' : coverage.complete ? '当前无在管交易' : '实时在管覆盖尚未确认'}</p>
              {!coverage.complete && <p className="mt-1">不能据此判断账户空仓，请查看身份核验及错误提示。</p>}
            </div>
          )}
        </section>
      )}

      {/* 4. Section 2: Trade History (Only when filter is 'all' or 'completed') */}
      {!isLoading && !isError && (filterMode === 'all' || filterMode === 'completed') && (
        <section id="completed-trade-episodes" data-testid="completed-trade-episodes" className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="text-xs font-bold uppercase tracking-wider text-text-primary">
                已结束交易记录 (Completed Trade Episodes)
              </h2>
              <span className="rounded-full bg-surface-subtle px-2 py-0.5 font-mono text-[11px] font-semibold text-text-secondary border border-border">
                {completedTrades.length} 笔已结束
              </span>
            </div>
            <span className="text-[11px] text-text-muted">
              终态不等于已成交或已结算，详见每笔结果
            </span>
          </div>

          <CompletedTradeTable
            episodes={completedTrades}
            onSelectEpisode={(selected) => setSelectedEpisode(selected)}
          />

          {paginationError && (
            <p role="alert" data-testid="pagination-error" className="text-xs text-danger">
              更早记录加载失败，已加载数据保留。请点击加载更多重试。
            </p>
          )}
          {/* Pagination Controls & Status */}
          {hasNextPage ? (
            <div
              data-testid="trades-pagination-bar"
              className="flex flex-col sm:flex-row items-center justify-between gap-3 rounded-lg border border-border bg-surface p-4 shadow-xs"
            >
              <div className="text-xs text-text-secondary">
                <span className="font-semibold text-text-primary">当前已加载前 {allTrades.length} 笔交易</span>
                <span className="text-text-muted ml-1.5">(首屏统计基于已加载范围，尚有更早历史记录)</span>
              </div>
              <button
                type="button"
                data-testid="load-more-btn"
                onClick={() => fetchNextPage()}
                disabled={isFetchingNextPage}
                className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface-subtle px-4 py-2 text-xs font-semibold text-text-primary hover:bg-surface-elevated hover:border-brand/40 transition-colors shadow-xs disabled:opacity-50"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${isFetchingNextPage ? 'animate-spin text-brand' : ''}`} />
                <span>{isFetchingNextPage ? '正在加载更早记录...' : '加载更多历史交易 (Load More)'}</span>
              </button>
            </div>
          ) : (
            <div data-testid="trades-pagination-status" className="py-2 text-center text-[11px] text-text-muted">
              已加载当前筛选范围全部账本记录 (共 {allTrades.length} 笔) · 该范围无更多数据
            </div>
          )}
        </section>
      )}

      {/* 5. Level 3 & Level 4: Causality Drawer */}
      <CausalityDrawer
        episode={selectedEpisode}
        onClose={() => setSelectedEpisode(null)}
      />
    </div>
  );
};
