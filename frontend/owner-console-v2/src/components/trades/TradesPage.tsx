import React, { useState } from 'react';
import { useTradesData } from '../../hooks/useTradesData';
import { ActiveTradeCard } from './ActiveTradeCard';
import { CompletedTradeTable } from './CompletedTradeTable';
import { CausalityDrawer } from '../overview/CausalityDrawer';
import type { TradeEpisode, TradeFilterMode } from '../../types/trades';
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
  const {
    isLoading,
    isFetching,
    isError,
    error,
    freshness,
    activeTrades,
    completedTrades,
    metrics,
    refetch,
  } = useTradesData();

  const [filterMode, setFilterMode] = useState<TradeFilterMode>('all');
  const [selectedEpisode, setSelectedEpisode] = useState<TradeEpisode | null>(null);

  const handleManualRefresh = async () => {
    await refetch();
  };

  if (isLoading) {
    return (
      <div id="trades-page" className="py-24 text-center">
        <div className="inline-block h-7 w-7 border-2 border-brand/30 border-t-brand rounded-full animate-spin mb-3" />
        <h3 className="text-sm font-semibold text-text-primary">
          正在从生产 API 加载交易账本事实...
        </h3>
        <p className="mt-1 text-xs text-text-muted">
          读取 /api/owner/v1/tickets · 严格杜绝任何 Mock 假数据
        </p>
      </div>
    );
  }

  if (isError) {
    return (
      <div id="trades-page" className="rounded-xl border border-danger/30 bg-surface p-8 text-center max-w-lg mx-auto my-12 shadow-sm">
        <div className="inline-flex items-center justify-center h-12 w-12 rounded-full bg-danger/10 text-danger mb-4">
          <AlertCircle className="h-6 w-6" />
        </div>
        <h3 className="text-base font-bold text-text-primary">
          无法连接 Tickets API
        </h3>
        <p className="mt-1.5 text-xs text-text-secondary leading-relaxed">
          {error instanceof Error ? error.message : '请检查生产网络连接或认证状态。严格拒绝任何静默伪造。'}
        </p>
        <div className="mt-5">
          <button
            type="button"
            onClick={handleManualRefresh}
            className="inline-flex items-center gap-1.5 rounded bg-brand px-4 py-2 text-xs font-semibold text-white hover:bg-brand/90 transition-colors shadow-xs"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>重新加载 (Retry)</span>
          </button>
        </div>
      </div>
    );
  }

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
              全部 ({metrics.totalCount})
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
              在管 ({metrics.activeCount})
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
              已平仓 ({metrics.completedCount})
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

      {/* 2. Top Summary Metrics Deck (L1 Owner Summary) */}
      <div data-testid="trades-metrics-ribbon" className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <div className="rounded-lg border border-border bg-surface p-3.5 shadow-xs">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-text-muted">
            <Activity className="h-3.5 w-3.5 text-brand" />
            <span>总交易数</span>
          </div>
          <div className="mt-1 font-mono text-lg font-bold text-text-primary">
            {metrics.totalCount}
          </div>
          <div className="text-[10px] text-text-muted mt-0.5">30 天滚动窗口账本</div>
        </div>

        <div className="rounded-lg border border-border bg-surface p-3.5 shadow-xs">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-text-muted">
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />
            <span>当前在管交易</span>
          </div>
          <div className="mt-1 font-mono text-lg font-bold text-brand">
            {metrics.activeCount}
          </div>
          <div className="text-[10px] text-text-muted mt-0.5">严格受保护在途</div>
        </div>

        <div className="rounded-lg border border-border bg-surface p-3.5 shadow-xs">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-text-muted">
            <CheckCircle2 className="h-3.5 w-3.5 text-text-secondary" />
            <span>历史平仓 / 胜率</span>
          </div>
          <div className="mt-1 font-mono text-lg font-bold text-text-primary">
            {metrics.completedCount}{' '}
            <span className="text-xs font-normal text-text-muted">
              ({metrics.winRatePercent != null ? `${metrics.winRatePercent}%` : '—'})
            </span>
          </div>
          <div className="text-[10px] text-text-muted mt-0.5">
            {metrics.winCount} 胜 / {metrics.lossCount} 负
          </div>
        </div>

        <div className="rounded-lg border border-border bg-surface p-3.5 shadow-xs">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-text-muted">
            <TrendingUp className="h-3.5 w-3.5 text-brand" />
            <span>累计已结收益</span>
          </div>
          <div className="mt-1 font-mono text-lg font-bold text-text-primary">
            {metrics.totalNetPnlFormatted}
          </div>
          <div className="text-[10px] text-text-muted mt-0.5">扣除手续费与滑点</div>
        </div>

        <div className="rounded-lg border border-border bg-surface p-3.5 shadow-xs">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-text-muted">
            <Layers className="h-3.5 w-3.5 text-brand" />
            <span>累计风险回报</span>
          </div>
          <div className="mt-1 font-mono text-lg font-bold text-text-primary">
            {metrics.totalNetRFormatted}
          </div>
          <div className="text-[10px] text-text-muted mt-0.5">单位风险倍数 (R)</div>
        </div>
      </div>

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
            <span className="text-[11px] text-text-muted">
              独立 Netting Domain · 终态前持续监控保护与退出条件
            </span>
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
              <CheckCircle2 className="mx-auto h-7 w-7 text-status-green mb-1.5" />
              <p className="font-semibold text-text-primary">当前无在管交易</p>
              <p className="mt-0.5 text-[11px] text-text-secondary">所有持仓均已安全平仓并完成账本结清。</p>
            </div>
          )}
        </section>
      )}

      {/* 4. Section 2: Trade History (Only when filter is 'all' or 'completed') */}
      {(filterMode === 'all' || filterMode === 'completed') && (
        <section id="completed-trade-episodes" data-testid="completed-trade-episodes" className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="text-xs font-bold uppercase tracking-wider text-text-primary">
                历史平仓记录 (Completed Trade Episodes)
              </h2>
              <span className="rounded-full bg-surface-subtle px-2 py-0.5 font-mono text-[11px] font-semibold text-text-secondary border border-border">
                {completedTrades.length} 笔已结清
              </span>
            </div>
            <span className="text-[11px] text-text-muted">
              完整经由 Reconciliation 与 Review 审计归档
            </span>
          </div>

          <CompletedTradeTable
            episodes={completedTrades}
            onSelectEpisode={(selected) => setSelectedEpisode(selected)}
          />
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
