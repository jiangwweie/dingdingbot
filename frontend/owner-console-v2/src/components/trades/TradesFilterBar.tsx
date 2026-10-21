import React from 'react';
import { TimeRangeFilter } from '../common/TimeRangeFilter.tsx';
import type { TradesFilterParams } from '../../utils/urlParams.ts';
import { RotateCcw } from 'lucide-react';

export interface TradesFilterBarProps {
  filters: TradesFilterParams;
  onChange: (patch: Partial<TradesFilterParams>) => void;
  onReset: () => void;
  disabled?: boolean;
}

const COMMON_STRATEGY_GROUPS = [
  'CPM-RO-001',
  'MPG-001',
  'MI-001',
  'BRF2-001',
];

const COMMON_STATUSES = [
  { value: '', label: '全部状态 (All)' },
  { value: 'terminal', label: '生命周期终态 (terminal)' },
  { value: 'position_protected', label: '持仓保护 (position_protected)' },
  { value: 'runner_protected', label: 'Runner 保护 (runner_protected)' },
  { value: 'entry_rejected', label: '开仓拒绝 (entry_rejected)' },
  { value: 'entry_vacuum_cancelled', label: '超时撤单 (entry_vacuum_cancelled)' },
  { value: 'partial_fill_incident', label: '部分成交异常 (partial_fill_incident)' },
];

export const TradesFilterBar: React.FC<TradesFilterBarProps> = ({
  filters,
  onChange,
  onReset,
  disabled = false,
}) => {
  const hasActiveFilters = Boolean(
    filters.strategy_group_id ||
      filters.exchange_instrument_id ||
      filters.position_side ||
      filters.aggregate_status ||
      filters.range !== '30d'
  );

  return (
    <div
      data-testid="trades-filter-bar"
      className="rounded-lg border border-border bg-surface p-4 shadow-xs space-y-3 font-sans text-xs"
    >
      {/* 1. Time Range Section */}
      <div className="pb-3 border-b border-border">
        <TimeRangeFilter
          preset={filters.range}
          from_ms={filters.from_ms}
          to_ms={filters.to_ms}
          disabled={disabled}
          onChange={({ preset, from_ms, to_ms }) =>
            onChange({ range: preset, from_ms, to_ms })
          }
        />
      </div>

      {/* 2. Business Field Filters */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 items-end">
        {/* Strategy Group */}
        <div className="space-y-1">
          <label htmlFor="filter-strategy-group" className="text-[11px] font-semibold text-text-secondary">
            策略组 (Strategy Group)
          </label>
          <div className="relative">
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
        </div>

        {/* Instrument / Symbol */}
        <div className="space-y-1">
          <label htmlFor="filter-exchange-instrument" className="text-[11px] font-semibold text-text-secondary">
            标的 / 交易对 (Instrument)
          </label>
          <input
            id="filter-exchange-instrument"
            type="text"
            disabled={disabled}
            value={filters.exchange_instrument_id ?? ''}
            placeholder="如 binance-usdm:ETHUSDT:perpetual"
            onChange={(e) =>
              onChange({ exchange_instrument_id: e.target.value.trim() || undefined })
            }
            className="h-8 w-full rounded border border-border bg-surface-subtle px-2.5 text-xs font-mono text-text-primary placeholder:text-text-muted focus:border-brand focus:bg-surface focus:outline-none focus:ring-1 focus:ring-brand/30"
          />
        </div>

        {/* Position Side */}
        <div className="space-y-1">
          <label htmlFor="filter-position-side" className="text-[11px] font-semibold text-text-secondary">
            多空方向 (Side)
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
            <option value="">全部方向 (All)</option>
            <option value="long">做多 (LONG)</option>
            <option value="short">做空 (SHORT)</option>
          </select>
        </div>

        {/* Aggregate Status */}
        <div className="space-y-1">
          <label htmlFor="filter-aggregate-status" className="text-[11px] font-semibold text-text-secondary">
            状态 (Aggregate Status)
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

      {/* 3. Action Bar / Active Badges */}
      {hasActiveFilters && (
        <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-border/60 text-[11px]">
          <div className="flex flex-wrap items-center gap-1.5 text-text-secondary">
            <span className="font-semibold text-text-muted">已生效筛选:</span>
            {filters.range !== '30d' && (
              <span className="rounded bg-brand/10 text-brand px-2 py-0.5 font-mono text-[10px] font-bold">
                {filters.range === 'today'
                  ? '今日'
                  : filters.range === '24h'
                  ? '近 24h'
                  : filters.range === '7d'
                  ? '近 7 天'
                  : '自定义时间'}
              </span>
            )}
            {filters.strategy_group_id && (
              <span className="rounded bg-surface-subtle border border-border px-2 py-0.5 font-mono text-[10px]">
                策略: {filters.strategy_group_id}
              </span>
            )}
            {filters.exchange_instrument_id && (
              <span className="rounded bg-surface-subtle border border-border px-2 py-0.5 font-mono text-[10px]">
                标的: {filters.exchange_instrument_id}
              </span>
            )}
            {filters.position_side && (
              <span className="rounded bg-surface-subtle border border-border px-2 py-0.5 font-mono text-[10px]">
                方向: {filters.position_side.toUpperCase()}
              </span>
            )}
            {filters.aggregate_status && (
              <span className="rounded bg-surface-subtle border border-border px-2 py-0.5 font-mono text-[10px]">
                状态: {filters.aggregate_status}
              </span>
            )}
          </div>

          <button
            type="button"
            disabled={disabled}
            onClick={onReset}
            className="inline-flex items-center gap-1 rounded border border-border bg-surface px-2.5 py-1 text-[11px] font-medium text-text-muted hover:text-text-primary hover:bg-surface-elevated transition-colors cursor-pointer"
          >
            <RotateCcw className="h-3 w-3" />
            <span>清除全部条件 (Reset)</span>
          </button>
        </div>
      )}
    </div>
  );
};
