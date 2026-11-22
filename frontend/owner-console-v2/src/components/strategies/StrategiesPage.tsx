import { ExitConfigurationPanel } from './ExitConfigurationPanel';
import { IncomeSummary, IncomeScopeBar } from '../common/IncomeSummary';
import React, { useState, useMemo } from 'react';
import { useStrategiesData } from '../../hooks/useStrategiesData.ts';
import { useStrategiesFilterState } from '../../hooks/useUrlSearchParams.ts';
import { TimeRangeFilter } from '../common/TimeRangeFilter.tsx';
import { StrategyMatrixTable } from './StrategyMatrixTable.tsx';
import { StrategyDetailDrawer } from './StrategyDetailDrawer.tsx';
import { CausalityDrawer } from '../overview/CausalityDrawer.tsx';
import { mapTradeListItemToEpisode } from '../../mapping/tradeEpisodeMapping.ts';
import { parseStrategyError } from '../../mapping/strategyErrorMapping.ts';
import type { EnrichedStrategyVersion, StrategyTicketListItem } from '../../types/strategies.ts';
import type { TradeEpisode } from '../../types/trades.ts';
import { cleanSymbol } from '../../utils/symbol.ts';
import { RefreshCw, AlertCircle, RotateCcw, SlidersHorizontal } from 'lucide-react';

export const StrategiesPage: React.FC = () => {
  const { filters, setFilters, resetFilters } = useStrategiesFilterState();

  const {
    strategies,performance,
    liveActiveTicketCount,
    view,
    setView,
    isLoading,
    isFetching,
    isError,
    error,
    freshness,
    refetch,
  } = useStrategiesData({
    view: filters.view,exit_scope:filters.exit_scope,strategy_group_id:filters.strategy_group_id,strategy_version_id:filters.strategy_version_id,exchange_instrument_id:filters.exchange_instrument_id,position_side:filters.position_side,
    from_ms: filters.from_ms,
    to_ms: filters.to_ms,
  });


  const [selectedTicketForCausality, setSelectedTicketForCausality] = useState<TradeEpisode | null>(null);
  const [selectedTicketIdForCausality, setSelectedTicketIdForCausality] = useState<string | null>(null);

  // Derive selected strategy strictly from current query results to prevent stale metrics retention
  const selectedStrategyId = filters.strategy_version_id;
  const selectedStrategy = useMemo(() => {
    if (!selectedStrategyId || strategies.length === 0) return null;
    return (
      strategies.find(
        (s) => s.summary.strategy_version_id === selectedStrategyId
      ) ?? null
    );
  }, [selectedStrategyId, strategies]);

  const enabledStrategiesCount = strategies.filter(
    (s) => s.isCurrent && s.control?.configured_state === 'enabled'
  ).length;
  const configuredButBlockedCount = strategies.filter(
    (s) =>
      s.isCurrent &&
      s.control?.configured_state === 'enabled' &&
      (s.runtimeStatus === 'blocked' || s.runtimeStatus === 'paused')
  ).length;
  const controlUnknownCount = strategies.filter((s) => s.isCurrent && s.control == null).length;
  const uniqueGroupCount = new Set(strategies.map((s) => s.summary.strategy_group_id)).size;
  const totalObservations = strategies.reduce((acc, s) => acc + s.observationCount, 0);
  const totalActiveTickets = liveActiveTicketCount;

  const advancedScopeCount = [
    filters.exit_scope && filters.exit_scope !== 'all' ? filters.exit_scope : undefined,
    filters.view === 'current' ? 'current' : undefined,
    filters.strategy_group_id,
    filters.strategy_version_id,
    filters.exchange_instrument_id,
    filters.position_side,
  ].filter(Boolean).length;

  const hasAnyActiveFilter =
    advancedScopeCount > 0 ||
    filters.range !== '30d' ||
    Boolean(filters.drawer_tab || filters.exit_path || filters.first_path || (filters.scope && filters.scope !== 'all'));

  const handleSelectStrategy = (st: EnrichedStrategyVersion) => {
    setFilters({ strategy_version_id: st.summary.strategy_version_id });
  };

  const handleCloseStrategyDrawer = () => {
    setFilters({
      strategy_version_id: undefined,
      drawer_tab: undefined,
      scope: undefined,
      exit_path: undefined,
      first_path: undefined,
    });
  };

  const handleSelectTicket = (ticket: StrategyTicketListItem) => {
    setSelectedTicketForCausality(mapTradeListItemToEpisode(ticket));
    setSelectedTicketIdForCausality(ticket.ticket_id);
  };

  const handleSelectTicketId = (ticketId: string) => {
    // P1-2: Strictly prohibit constructing fake TradeEpisode with default side: 'long' or empty symbols.
    // Instead, pass the raw ticketId and let CausalityDrawer verify authentic server facts.
    setSelectedTicketForCausality(null);
    setSelectedTicketIdForCausality(ticketId);
  };

  return (
    <div id="strategies-page" className="space-y-4 animate-in fade-in-50 duration-200">
      {/* 1. Compact Header Bar */}
      <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface px-4 py-3.5 shadow-xs sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2.5">
          <h1 className="text-base font-bold tracking-tight text-text-primary">策略与选币</h1>
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

        {/* View Switcher & Refresh */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center rounded-lg border border-border bg-surface-subtle p-1 text-xs">
            <button
              type="button"
              onClick={() => {
                setView('current');
                setFilters({ view: 'current' });
              }}
              className={`rounded px-3 py-1 font-mono text-xs font-medium transition-colors cursor-pointer ${
                view === 'current'
                  ? 'bg-surface text-brand font-bold shadow-xs border border-border'
                  : 'text-text-muted hover:text-text-primary'
              }`}
            >
              当前版本
            </button>
            <button
              type="button"
              onClick={() => {
                setView('all');
                setFilters({ view: 'all' });
              }}
              className={`rounded px-3 py-1 font-mono text-xs font-medium transition-colors cursor-pointer ${
                view === 'all'
                  ? 'bg-surface text-brand font-bold shadow-xs border border-border'
                  : 'text-text-muted hover:text-text-primary'
              }`}
            >
              全部版本
            </button>
          </div>

          <button
            type="button"
            onClick={() => { refetch(); }}
            disabled={isFetching}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text-secondary hover:bg-surface-elevated hover:text-text-primary transition-colors shadow-xs cursor-pointer"
            title="手动刷新策略评估事实"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin text-brand' : ''}`} />
            <span>刷新</span>
          </button>
        </div>
      </div>

      {/* 2. Unified Filter Summary & Collapsible Scope Bar */}
      <div
        data-testid="strategies-time-range-bar"
        className="rounded-lg border border-border bg-surface p-3.5 shadow-xs space-y-2.5 font-sans text-xs"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <TimeRangeFilter
            preset={filters.range}
            from_ms={filters.from_ms}
            to_ms={filters.to_ms}
            disabled={isFetching}
            onChange={({ preset, from_ms, to_ms }) =>
              setFilters({ range: preset, from_ms, to_ms })
            }
          />
          <span className="text-[11px] text-text-muted">
            交易按终态时间 · 研究观察按信号时间 · 账户当前在管独立于历史窗口
          </span>
        </div>

        {/* Always-Visible Active Filter Badges + Full Reset */}
        <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-border/60 text-[11px]">
          <div className="flex flex-wrap items-center gap-1.5 text-text-secondary">
            <span className="font-semibold text-text-muted">生效筛选:</span>
            <span className="rounded bg-brand/10 text-brand px-2 py-0.5 font-mono text-[10px] font-bold">
              {filters.range === 'today'
                ? '今日'
                : filters.range === '24h'
                ? '近 24h'
                : filters.range === '7d'
                ? '近 7 天'
                : filters.range === '30d'
                ? '近 30 天'
                : '自定义时间'}
            </span>
            <span className="rounded bg-surface-subtle border border-border px-2 py-0.5 font-mono text-[10px]">
              {new Date(filters.from_ms).toLocaleString('zh-CN', { hour12: false, timeZone: 'Asia/Shanghai' })} ~{' '}
              {new Date(filters.to_ms).toLocaleString('zh-CN', { hour12: false, timeZone: 'Asia/Shanghai' })}
            </span>
            {filters.view === 'current' && (
              <span className="rounded bg-surface-subtle border border-border px-2 py-0.5 font-mono text-[10px]">
                仅当前版本
              </span>
            )}
            {filters.exit_scope && filters.exit_scope !== 'all' && (
              <span className="rounded bg-surface-subtle border border-border px-2 py-0.5 font-mono text-[10px]">
                退出范围: {filters.exit_scope}
              </span>
            )}
            {filters.strategy_group_id && (
              <span className="rounded bg-surface-subtle border border-border px-2 py-0.5 font-mono text-[10px]">
                策略组: {filters.strategy_group_id}
              </span>
            )}
            {filters.strategy_version_id && (
              <span className="rounded bg-surface-subtle border border-border px-2 py-0.5 font-mono text-[10px]">
                版本: {filters.strategy_version_id}
              </span>
            )}
            {filters.exchange_instrument_id && (
              <span className="rounded bg-surface-subtle border border-border px-2 py-0.5 font-mono text-[10px]">
                标的: {cleanSymbol(filters.exchange_instrument_id)}
              </span>
            )}
            {filters.position_side && (
              <span className="rounded bg-surface-subtle border border-border px-2 py-0.5 font-mono text-[10px]">
                方向: {filters.position_side === 'long' ? '做多' : '做空'}
              </span>
            )}
          </div>

          {hasAnyActiveFilter && (
            <button
              type="button"
              disabled={isFetching}
              onClick={resetFilters}
              className="inline-flex items-center gap-1 rounded border border-border bg-surface px-2 py-1 text-[11px] font-medium text-text-muted hover:text-text-primary hover:bg-surface-elevated transition-colors cursor-pointer shrink-0"
            >
              <RotateCcw className="h-3 w-3" />
              <span>清除筛选</span>
            </button>
          )}
        </div>

        {/* Collapsible Scope Controls */}
        <details className="group pt-1">
          <summary className="cursor-pointer select-none inline-flex items-center gap-1.5 text-[11px] font-semibold text-brand hover:underline focus-visible:outline-2 focus-visible:outline-brand rounded px-1">
            <SlidersHorizontal className="h-3 w-3" />
            <span>
              收益与版本口径{advancedScopeCount > 0 ? ` (${advancedScopeCount})` : ''} ›
            </span>
          </summary>
          <div className="mt-2.5 pt-2.5 border-t border-border/60">
            <IncomeScopeBar view={filters.view} scope={filters.exit_scope} onChange={setFilters} />
          </div>
        </details>
      </div>

      {/* 3. Single Authoritative Full-Window Income Summary */}
      <IncomeSummary summary={performance} error={isError ? error : null} onRefresh={() => { refetch(); }} onSelectTicket={handleSelectTicketId} />
      <details className="rounded-lg border border-border bg-surface px-4 py-3 text-xs" aria-label="退出参数设置">
        <summary className="cursor-pointer font-semibold text-brand">TP1 与 MA50 参数</summary>
        <div className="mt-3"><ExitConfigurationPanel /></div>
      </details>

      {/* 4. Main Content Area */}
      {isLoading ? (
        <div className="py-20 text-center">
          <div className="inline-block h-7 w-7 border-2 border-brand/30 border-t-brand rounded-full animate-spin mb-3" />
          <p className="text-xs font-semibold text-text-primary">正在读取策略表现与控制状态...</p>
        </div>
      ) : isError ? (
        (() => {
          const errDiag = parseStrategyError(error, view);
          const isWarning = errDiag.isConflict409;
          return (
            <div
              data-testid="strategies-error-card"
              className={`rounded-xl border ${
                isWarning ? 'border-amber-500/30' : 'border-danger/30'
              } bg-surface p-8 text-center max-w-xl mx-auto my-8 shadow-sm`}
            >
              <div
                className={`inline-flex items-center justify-center h-12 w-12 rounded-full ${
                  isWarning
                    ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
                    : 'bg-danger/10 text-danger'
                } mb-4`}
              >
                <AlertCircle className="h-6 w-6" />
              </div>
              <h3 className="text-base font-bold text-text-primary" data-testid="strategies-error-title">
                {errDiag.title}
              </h3>
              <p className="mt-2 text-xs text-text-secondary leading-relaxed">
                {errDiag.explanation}
              </p>
              {errDiag.message && errDiag.message !== errDiag.explanation && (
                <div className="mt-3">
                  <code className="font-mono text-[11px] bg-surface-subtle px-2 py-1 rounded border border-border text-text-muted break-all inline-block">
                    {errDiag.code ? `[${errDiag.code}] ` : ''}{errDiag.message}
                  </code>
                </div>
              )}
              <div className="mt-6 flex items-center justify-center gap-3">
                {errDiag.canReturnToCurrent && (
                  <button
                    type="button"
                    onClick={() => {
                      setView('current');
                      setFilters({ view: 'current' });
                    }}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-brand px-4 py-2 text-xs font-semibold text-white hover:bg-brand/90 transition-colors shadow-xs cursor-pointer"
                  >
                    <span>返回当前活跃版本 (current)</span>
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => refetch()}
                  className={`inline-flex items-center gap-1.5 rounded-lg ${
                    errDiag.canReturnToCurrent
                      ? 'border border-border bg-surface px-4 py-2 text-xs font-semibold text-text-secondary hover:bg-surface-elevated hover:text-text-primary transition-colors shadow-xs'
                      : 'bg-brand px-4 py-2 text-xs font-semibold text-white hover:bg-brand/90 transition-colors shadow-xs'
                  } cursor-pointer`}
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  <span>重试请求</span>
                </button>
              </div>
            </div>
          );
        })()
      ) : (
        <>
          {/* 5. Strategy Matrix Table (Visible immediately above the fold, no redundant 4-card ribbon) */}
          <section className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <h2 className="text-xs font-bold uppercase tracking-wider text-text-primary">
                  策略表现矩阵
                </h2>
                <span className="rounded-full bg-surface-subtle px-2 py-0.5 font-mono text-[11px] font-semibold text-text-secondary border border-border">
                  策略组 {uniqueGroupCount} · 版本 {strategies.length}
                </span>
                <span className="rounded-full bg-surface-subtle px-2 py-0.5 font-mono text-[11px] text-text-secondary border border-border">
                  已启用 {enabledStrategiesCount}
                  {configuredButBlockedCount > 0 ? ` · 生效受阻 ${configuredButBlockedCount}` : ''}
                  {controlUnknownCount > 0 ? ` · 控制未知 ${controlUnknownCount}` : ''}
                </span>
                <span className="rounded-full bg-brand/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-brand border border-brand/20">
                  账户当前在管 <span data-testid="strategies-active-count">{totalActiveTickets ?? '未知'}</span> 笔
                </span>
                <span className="rounded-full bg-surface-subtle px-2 py-0.5 font-mono text-[11px] text-text-muted border border-border">
                  研究观察 {totalObservations} 条 (非实盘成交)
                </span>
              </div>
              <span className="text-[11px] text-text-muted">
                点击行查看详情、控制与双轨证据
              </span>
            </div>

            <StrategyMatrixTable
              strategies={strategies}
              onSelectStrategy={handleSelectStrategy}
            />
          </section>
        </>
      )}

      {/* 4. Strategy Detail Drawer (L2) */}
      {selectedStrategy && (
        <StrategyDetailDrawer
          strategy={selectedStrategy}
          onClose={handleCloseStrategyDrawer}
          onSelectTicket={handleSelectTicket}
          onSelectTicketId={handleSelectTicketId}
          from_ms={filters.from_ms}
          to_ms={filters.to_ms}
          activeDrawerTab={filters.drawer_tab}
          onTabChange={(tab) => setFilters({ drawer_tab: tab })}
          scope={filters.scope} exit_scope={filters.exit_scope}
          exit_path={filters.exit_path ?? null}
          first_path={filters.first_path ?? null}
          onScopeChange={(scope) => setFilters({ scope })}
          onExitPathChange={(exit_path) =>
            setFilters({ exit_path: exit_path ?? undefined })
          }
          onFirstPathChange={(first_path) =>
            setFilters({ first_path: first_path ?? undefined })
          }
          onTicketFiltersChange={({ scope, exit_path }) => {
            setFilters((prev) => ({
              ...prev,
              ...(scope ? { scope } : {}),
              exit_path: exit_path ?? undefined,
            }));
          }}
          isStrategiesFetching={isFetching}
        />
      )}

      <CausalityDrawer
        episode={selectedTicketForCausality}
        ticketId={selectedTicketIdForCausality}
        onClose={() => {
          setSelectedTicketForCausality(null);
          setSelectedTicketIdForCausality(null);
        }}
      />
    </div>
  );
};
