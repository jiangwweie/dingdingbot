import React, { useState } from 'react';
import { useStrategiesData } from '../../hooks/useStrategiesData.ts';
import { StrategyMatrixTable } from './StrategyMatrixTable.tsx';
import { StrategyDetailDrawer } from './StrategyDetailDrawer.tsx';
import { CausalityDrawer } from '../overview/CausalityDrawer.tsx';
import { mapTradeListItemToEpisode } from '../../mapping/tradeEpisodeMapping.ts';
import type { EnrichedStrategyVersion, StrategyTicketListItem } from '../../types/strategies.ts';
import type { TradeEpisode } from '../../types/trades.ts';
import {
  Layers,
  RefreshCw,
  Activity,
  ShieldCheck,
  AlertCircle,
  Clock,
} from 'lucide-react';

export const StrategiesPage: React.FC = () => {
  const {
    strategies,
    view,
    setView,
    isLoading,
    isFetching,
    isError,
    error,
    freshness,
    refetch,
  } = useStrategiesData();

  const [selectedStrategy, setSelectedStrategy] = useState<EnrichedStrategyVersion | null>(null);
  const [selectedTicketForCausality, setSelectedTicketForCausality] = useState<TradeEpisode | null>(null);

  const activeStrategiesCount = strategies.filter((s) => s.runtimeStatus === 'enabled').length;
  const totalActiveTickets = strategies.reduce((acc, s) => acc + s.activeTicketCount, 0);

  const handleSelectTicket = (ticket: StrategyTicketListItem) => {
    setSelectedTicketForCausality(mapTradeListItemToEpisode(ticket));
  };

  if (isLoading) {
    return (
      <div id="strategies-page" className="py-24 text-center">
        <div className="inline-block h-8 w-8 border-2 border-brand/30 border-t-brand rounded-full animate-spin mb-3" />
        <p className="text-xs font-semibold text-text-primary">正在读取策略表现与控制状态...</p>
        <span className="text-[11px] text-text-muted mt-1 font-mono">
          GET /api/owner/v1/strategies?view={view}
        </span>
      </div>
    );
  }

  if (isError) {
    return (
      <div id="strategies-page" className="rounded-xl border border-danger/30 bg-surface p-8 text-center max-w-lg mx-auto my-12 shadow-sm">
        <div className="inline-flex items-center justify-center h-12 w-12 rounded-full bg-danger/10 text-danger mb-4">
          <AlertCircle className="h-6 w-6" />
        </div>
        <h3 className="text-base font-bold text-text-primary">策略评估数据暂时不可用</h3>
        <p className="mt-1.5 text-xs text-text-secondary leading-relaxed">
          {error instanceof Error ? error.message : '未能成功获取真实策略统计或控制状态。'}
        </p>
        <div className="mt-5">
          <button
            type="button"
            onClick={() => refetch()}
            className="inline-flex items-center gap-1.5 rounded bg-brand px-4 py-2 text-xs font-semibold text-white hover:bg-brand/90 transition-colors shadow-xs cursor-pointer"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>重新加载</span>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div id="strategies-page" className="space-y-6 animate-in fade-in-50 duration-200">
      {/* 1. Header Bar */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-border pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-bold text-text-primary">策略评估与动态选币</h1>
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
            按 <strong className="text-text-primary">StrategyVersion</strong> 隔离实盘 Ticket 损益与 Observation 假设检验证据 · 物理区分自然退出与受控干预
          </p>
        </div>

        {/* View Switcher & Refresh */}
        <div className="flex items-center gap-2">
          {/* View Filter: Current active vs All versions */}
          <div className="flex items-center rounded-lg border border-border bg-surface-subtle p-1 text-xs">
            <button
              type="button"
              onClick={() => setView('current')}
              className={`rounded px-3 py-1 font-mono text-xs font-medium transition-colors ${
                view === 'current'
                  ? 'bg-surface text-brand font-bold shadow-xs border border-border'
                  : 'text-text-muted hover:text-text-primary'
              }`}
            >
              当前活跃版本 (current)
            </button>
            <button
              type="button"
              onClick={() => setView('all')}
              className={`rounded px-3 py-1 font-mono text-xs font-medium transition-colors ${
                view === 'all'
                  ? 'bg-surface text-brand font-bold shadow-xs border border-border'
                  : 'text-text-muted hover:text-text-primary'
              }`}
            >
              全部版本 (all)
            </button>
          </div>

          <button
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text-secondary hover:bg-surface-elevated hover:text-text-primary transition-colors shadow-xs"
            title="手动刷新策略评估事实"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin text-brand' : ''}`} />
            <span>刷新</span>
          </button>
        </div>
      </div>

      {/* 2. Top Summary Ribbon */}
      <div data-testid="strategies-metrics-ribbon" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {/* Metric 1: Total Strategy Versions */}
        <div data-testid="metric-total-strategies" className="rounded-lg border border-border bg-surface p-3.5 shadow-xs">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-text-muted">
            <Layers className="h-3.5 w-3.5 text-brand" />
            <span>评估策略版本数</span>
          </div>
          <div data-testid="metric-value" className="mt-1 font-mono text-lg font-bold text-text-primary">
            {strategies.length}
          </div>
          <div data-testid="metric-subtext" className="text-[10px] text-text-muted mt-0.5 truncate">
            {view === 'current' ? '当前有效活跃策略' : '包含历史归档版本'}
          </div>
        </div>

        {/* Metric 2: Active Strategies */}
        <div data-testid="metric-active-strategies" className="rounded-lg border border-border bg-surface p-3.5 shadow-xs">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-text-muted">
            <Activity className="h-3.5 w-3.5 text-emerald-500" />
            <span>正常运行中</span>
          </div>
          <div data-testid="metric-value" className="mt-1 font-mono text-lg font-bold text-emerald-600 dark:text-emerald-400">
            {activeStrategiesCount}
          </div>
          <div data-testid="metric-subtext" className="text-[10px] text-text-muted mt-0.5">
            有效准入开仓状态正常
          </div>
        </div>

        {/* Metric 3: Active Tickets Across Strategies */}
        <div data-testid="metric-active-tickets" className="rounded-lg border border-border bg-surface p-3.5 shadow-xs">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-text-muted">
            <ShieldCheck className="h-3.5 w-3.5 text-brand" />
            <span>当前在管持仓</span>
          </div>
          <div data-testid="metric-value" className="mt-1 font-mono text-lg font-bold text-brand">
            {totalActiveTickets}
          </div>
          <div data-testid="metric-subtext" className="text-[10px] text-text-muted mt-0.5">
            占用全局 Ticket 槽位
          </div>
        </div>

        {/* Metric 4: Observation Samples */}
        <div data-testid="metric-total-observations" className="rounded-lg border border-border bg-surface p-3.5 shadow-xs">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-text-muted">
            <Clock className="h-3.5 w-3.5 text-text-secondary" />
            <span>研究观察样本总数</span>
          </div>
          <div data-testid="metric-value" className="mt-1 font-mono text-lg font-bold text-text-primary">
            {strategies.reduce((acc, s) => acc + s.observationCount, 0)}
          </div>
          <div data-testid="metric-subtext" className="text-[10px] text-text-muted mt-0.5">
            非实盘交易 · 信号影子轨迹
          </div>
        </div>
      </div>

      {/* 3. Strategy Matrix Table */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h2 className="text-xs font-bold uppercase tracking-wider text-text-primary">
              策略表现矩阵 (Strategy Performance Matrix)
            </h2>
            <span className="rounded-full bg-surface-subtle px-2 py-0.5 font-mono text-[11px] font-semibold text-text-secondary border border-border">
              {strategies.length} 个版本
            </span>
          </div>
          <span className="text-[11px] text-text-muted">
            点击任意策略查看深度表现、控制准入、动态选币及双轨证据
          </span>
        </div>

        <StrategyMatrixTable
          strategies={strategies}
          onSelectStrategy={(st) => setSelectedStrategy(st)}
        />
      </section>

      {/* 4. Strategy Detail Drawer (L2) */}
      {selectedStrategy && (
        <StrategyDetailDrawer
          strategy={selectedStrategy}
          onClose={() => setSelectedStrategy(null)}
          onSelectTicket={handleSelectTicket}
        />
      )}

      {/* 5. Ticket Causality Drawer (L3 & L4) */}
      <CausalityDrawer
        episode={selectedTicketForCausality}
        onClose={() => setSelectedTicketForCausality(null)}
      />
    </div>
  );
};
