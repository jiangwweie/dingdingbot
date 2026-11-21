import React from 'react';
import { TimeRangeFilter } from '../common/TimeRangeFilter.tsx';
import type { TradesFilterParams } from '../../utils/urlParams.ts';
import { cleanSymbol } from '../../utils/symbol.ts';
import { RotateCcw, SlidersHorizontal } from 'lucide-react';

export interface TradesFilterBarProps {
  filters: TradesFilterParams;
  onChange: (patch: Partial<TradesFilterParams>) => void;
  onReset: () => void;
  disabled?: boolean;
  instrumentSuggestions?: string[];
  children?: React.ReactNode;
}

const COMMON_STRATEGY_GROUPS = [
  'CPM-RO-001',
  'MPG-001',
  'MI-001',
  'BRF2-001',
  'SOR-1H-001',
  'SOR-1H-LONG-001',
  'SOR-1H-SHORT-001',
];

const COMMON_STATUSES = [
  { value: '', label: '全部状态' },
  { value: 'terminal', label: '生命周期终态' },
  { value: 'position_protected', label: '持仓保护' },
  { value: 'runner_protected', label: 'Runner 保护' },
  { value: 'entry_rejected', label: '开仓拒绝' },
  { value: 'entry_vacuum_cancelled', label: '超时撤单' },
  { value: 'partial_fill_incident', label: '部分成交异常' },
];

export const TradesFilterBar: React.FC<TradesFilterBarProps> = ({
  filters,
  onChange,
  onReset,
  disabled = false,
  instrumentSuggestions = [],
  children,
}) => {
  const advancedFilterCount = [
    filters.strategy_group_id,
    filters.strategy_version_id,
    filters.exchange_instrument_id,
    filters.position_side,
    filters.aggregate_status,
    filters.exit_scope && filters.exit_scope !== 'all' ? filters.exit_scope : undefined,
    filters.view === 'current' ? 'current' : undefined,
  ].filter(Boolean).length;

  const hasActiveFilters = advancedFilterCount > 0 || filters.range !== '30d';

  return (
    <div
      data-testid="trades-filter-bar"
      className="rounded-lg border border-border bg-surface p-3.5 shadow-xs space-y-2.5 font-sans text-xs"
    >
      {/* 1. Always Visible: Time Range + Scope Clarification + Advanced Toggle */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <TimeRangeFilter
          preset={filters.range}
          from_ms={filters.from_ms}
          to_ms={filters.to_ms}
          disabled={disabled}
          onChange={({ preset, from_ms, to_ms }) =>
            onChange({ range: preset, from_ms, to_ms })
          }
        />
        <span className="text-[11px] text-text-muted">
          仅筛选历史记录，不影响实时在管持仓
        </span>
      </div>

      {/* 2. Always Visible Active Filter Badges + Advanced Filter Trigger */}
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
          {filters.strategy_group_id && (
            <span className="rounded bg-surface-subtle border border-border px-2 py-0.5 font-mono text-[10px]">
              策略: {filters.strategy_group_id}
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
          {filters.aggregate_status && (
            <span className="rounded bg-surface-subtle border border-border px-2 py-0.5 font-mono text-[10px]">
              状态: {filters.aggregate_status}
            </span>
          )}
          {filters.exit_scope && filters.exit_scope !== 'all' && (
            <span className="rounded bg-surface-subtle border border-border px-2 py-0.5 font-mono text-[10px]">
              归属: {filters.exit_scope}
            </span>
          )}
          {filters.view === 'current' && (
            <span className="rounded bg-surface-subtle border border-border px-2 py-0.5 font-mono text-[10px]">
              仅当前版本
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {hasActiveFilters && (
            <button
              type="button"
              disabled={disabled}
              onClick={onReset}
              className="inline-flex items-center gap-1 rounded border border-border bg-surface px-2 py-1 text-[11px] font-medium text-text-muted hover:text-text-primary hover:bg-surface-elevated transition-colors cursor-pointer"
            >
              <RotateCcw className="h-3 w-3" />
              <span>清除筛选</span>
            </button>
          )}
        </div>
      </div>

      {/* 3. Collapsible Advanced Filters (Strategy, Instrument, Side, Status, Income Scope) */}
      <details className="group pt-1">
        <summary className="cursor-pointer select-none inline-flex items-center gap-1.5 text-[11px] font-semibold text-brand hover:underline focus-visible:outline-2 focus-visible:outline-brand rounded px-1">
          <SlidersHorizontal className="h-3 w-3" />
          <span>
            高级筛选{advancedFilterCount > 0 ? ` (${advancedFilterCount})` : ''} ›
          </span>
        </summary>

        <div className="mt-3 pt-3 border-t border-border/60 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 items-end">
            {/* Strategy Group */}
            <div className="space-y-1">
              <label htmlFor="filter-strategy-group" className="text-[11px] font-semibold text-text-secondary">
                策略组
              </label>
              <input
                id="filter-strategy-group"
                type="text"
                list="strategy-group-suggestions"
                disabled={disabled}
                value={filters.strategy_group_id ?? ''}
                placeholder="如 CPM-RO-001"
                onChange={(e) =>
                  onChange({ strategy_group_id: e.target.value.trim() || undefined })
                }
                className="h-8 w-full rounded border border-border bg-surface-subtle px-2.5 text-xs font-mono text-text-primary placeholder:text-text-muted focus:border-brand focus:bg-surface focus:outline-none focus:ring-1 focus:ring-brand/30"
              />
              <datalist id="strategy-group-suggestions">
                {COMMON_STRATEGY_GROUPS.map((sg) => (
                  <option key={sg} value={sg} />
                ))}
              </datalist>
            </div>

            {/* Instrument / Symbol */}
            <div className="space-y-1">
              <label htmlFor="filter-exchange-instrument" className="text-[11px] font-semibold text-text-secondary">
                交易标的 <span className="font-normal text-text-muted">(已加载建议)</span>
              </label>
              <input
                id="filter-exchange-instrument"
                type="text"
                list="instrument-suggestions"
                disabled={disabled}
                value={filters.exchange_instrument_id ?? ''}
                placeholder="输入完整合约 ID"
                onChange={(e) =>
                  onChange({ exchange_instrument_id: e.target.value.trim() || undefined })
                }
                className="h-8 w-full rounded border border-border bg-surface-subtle px-2.5 text-xs font-mono text-text-primary placeholder:text-text-muted focus:border-brand focus:bg-surface focus:outline-none focus:ring-1 focus:ring-brand/30"
              />
              <datalist id="instrument-suggestions">
                {instrumentSuggestions.map((fullId) => (
                  <option key={fullId} value={fullId}>
                    {cleanSymbol(fullId)}
                  </option>
                ))}
              </datalist>
            </div>

            {/* Position Side */}
            <div className="space-y-1">
              <label htmlFor="filter-position-side" className="text-[11px] font-semibold text-text-secondary">
                多空方向
              </label>
              <select
                id="filter-position-side"
                disabled={disabled}
                value={filters.position_side ?? ''}
                onChange={(e) =>
                  onChange({
                    position_side: (e.target.value as 'long' | 'short') || undefined,
                  })
                }
                className="h-8 w-full rounded border border-border bg-surface-subtle px-2 text-xs font-sans text-text-primary focus:border-brand focus:bg-surface focus:outline-none focus:ring-1 focus:ring-brand/30"
              >
                <option value="">全部方向</option>
                <option value="long">做多</option>
                <option value="short">做空</option>
              </select>
            </div>

            {/* Aggregate Status */}
            <div className="space-y-1">
              <label htmlFor="filter-aggregate-status" className="text-[11px] font-semibold text-text-secondary">
                生命周期状态
              </label>
              <select
                id="filter-aggregate-status"
                disabled={disabled}
                value={filters.aggregate_status ?? ''}
                onChange={(e) =>
                  onChange({ aggregate_status: e.target.value.trim() || undefined })
                }
                className="h-8 w-full rounded border border-border bg-surface-subtle px-2 text-xs font-sans text-text-primary focus:border-brand focus:bg-surface focus:outline-none focus:ring-1 focus:ring-brand/30"
              >
                {COMMON_STATUSES.map((st) => (
                  <option key={st.value} value={st.value}>
                    {st.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {children && (
            <div className="pt-2 border-t border-border/60">
              {children}
            </div>
          )}
        </div>
      </details>
    </div>
  );
};
