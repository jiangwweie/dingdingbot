import React from 'react';
import { TimeRangeFilter } from '../common/TimeRangeFilter.tsx';
import type { ReviewFilterParams, ReviewStatusQuery } from '../../types/review.ts';
import { cleanSymbol } from '../../utils/symbol.ts';
import { RotateCcw } from 'lucide-react';

export interface ReviewFilterBarProps {
  filters: ReviewFilterParams;
  onChange: (patch: Partial<ReviewFilterParams>) => void;
  onReset: () => void;
  disabled?: boolean;
  children?: React.ReactNode;
}

const COMMON_STRATEGY_GROUPS = [
  'MPG-001',
  'CPM-RO-001',
  'MI-001',
  'BRF2-001',
];

const REVIEW_STATUS_OPTIONS: { value: ReviewStatusQuery | ''; label: string }[] = [
  { value: '', label: '全部状态' },
  { value: 'complete', label: '复盘完整' },
  { value: 'incomplete_evidence', label: '存在待核实项' },
  { value: 'waiting_for_review', label: '等待复盘' },
  { value: 'in_progress', label: '进行中' },
];

const EXIT_SCOPE_LABELS: Record<string, string> = {
  strategy: '策略自身退出',
  owner: 'Owner 平仓',
  safety: '安全恢复退出',
  unknown: '退出原因未知',
};

const RANGE_LABELS: Record<string, string> = {
  today: '今日',
  '24h': '近 24h',
  '7d': '近 7 天',
  '30d': '近 30 天',
};

export const ReviewFilterBar: React.FC<ReviewFilterBarProps> = ({
  filters,
  onChange,
  onReset,
  disabled = false,
  children,
}) => {
  const hasActiveFilters = Boolean(
    filters.strategy_group_id ||
      filters.strategy_version_id ||
      filters.exchange_instrument_id ||
      filters.position_side ||
      filters.review_status ||
      (filters.exit_scope && filters.exit_scope !== 'all') ||
      filters.view === 'current' ||
      filters.range !== '30d'
  );

  const statusLabel = REVIEW_STATUS_OPTIONS.find((o) => o.value === filters.review_status)?.label;

  return (
    <div
      data-testid="review-filter-bar"
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
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 items-end">
        {/* Strategy Group */}
        <div className="space-y-1">
          <label
            htmlFor="filter-review-strategy-group"
            className="text-[11px] font-semibold text-text-secondary"
          >
            策略组
          </label>
          <div className="relative">
            <input
              id="filter-review-strategy-group"
              type="text"
              list="review-strategy-group-suggestions"
              disabled={disabled}
              value={filters.strategy_group_id ?? ''}
              placeholder="如 MPG-001"
              onChange={(e) =>
                onChange({ strategy_group_id: e.target.value.trim() || undefined })
              }
              className="h-8 w-full rounded border border-border bg-surface-subtle px-2.5 text-xs font-mono text-text-primary placeholder:text-text-muted focus:border-brand focus:bg-surface focus:outline-none focus:ring-1 focus:ring-brand/30"
            />
            <datalist id="review-strategy-group-suggestions">
              {COMMON_STRATEGY_GROUPS.map((sg) => (
                <option key={sg} value={sg} />
              ))}
            </datalist>
          </div>
        </div>

        {/* Review Status */}
        <div className="space-y-1">
          <label
            htmlFor="filter-review-status"
            className="text-[11px] font-semibold text-text-secondary"
          >
            复盘状态
          </label>
          <select
            id="filter-review-status"
            disabled={disabled}
            value={filters.review_status ?? ''}
            onChange={(e) =>
              onChange({
                review_status: e.target.value ? (e.target.value as ReviewStatusQuery) : undefined,
              })
            }
            className="h-8 w-full rounded border border-border bg-surface-subtle px-2.5 text-xs text-text-primary focus:border-brand focus:bg-surface focus:outline-none focus:ring-1 focus:ring-brand/30"
          >
            {REVIEW_STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* Action: Reset */}
        <div className="flex items-center gap-2">
          {hasActiveFilters && (
            <button
              type="button"
              disabled={disabled}
              onClick={onReset}
              className="inline-flex h-8 items-center gap-1.5 rounded border border-border bg-surface px-3 text-xs font-medium text-text-secondary hover:bg-surface-elevated hover:text-text-primary transition-colors cursor-pointer"
            >
              <RotateCcw className="h-3 w-3 text-text-muted" />
              <span>清除筛选</span>
            </button>
          )}
        </div>
      </div>

      {/* 3. Always-visible Active Filter Summary */}
      <div className="flex flex-wrap items-center gap-1.5 pt-2 border-t border-border/60 text-[11px] text-text-secondary">
        <span className="font-semibold text-text-muted">生效筛选:</span>
        <span className="rounded bg-brand/10 text-brand px-2 py-0.5 font-mono text-[10px] font-bold">
          {RANGE_LABELS[filters.range] ?? '自定义时间'}
        </span>
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
          <span className="rounded bg-surface-subtle border border-border px-2 py-0.5 text-[10px]">
            方向: {filters.position_side === 'long' ? '多头' : '空头'}
          </span>
        )}
        {statusLabel && (
          <span className="rounded bg-surface-subtle border border-border px-2 py-0.5 text-[10px]">
            复盘状态: {statusLabel}
          </span>
        )}
        {filters.exit_scope && filters.exit_scope !== 'all' && (
          <span className="rounded bg-surface-subtle border border-border px-2 py-0.5 text-[10px]">
            退出范围: {EXIT_SCOPE_LABELS[filters.exit_scope] ?? filters.exit_scope}
          </span>
        )}
        {filters.view === 'current' && (
          <span className="rounded bg-surface-subtle border border-border px-2 py-0.5 text-[10px]">
            仅当前版本
          </span>
        )}
      </div>

      {/* 4. Optional Embedded Scope Controls */}
      {children && (
        <div className="pt-2 border-t border-border/60">
          {children}
        </div>
      )}
    </div>
  );
};
