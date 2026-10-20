import React from 'react';
import { TimeRangeFilter } from '../common/TimeRangeFilter.tsx';
import type { ReviewFilterParams, ReviewStatusQuery } from '../../types/review.ts';
import { RotateCcw } from 'lucide-react';

export interface ReviewFilterBarProps {
  filters: ReviewFilterParams;
  onChange: (patch: Partial<ReviewFilterParams>) => void;
  onReset: () => void;
  disabled?: boolean;
}

const COMMON_STRATEGY_GROUPS = [
  'MPG-001',
  'CPM-RO-001',
  'MI-001',
  'BRF2-001',
];

const REVIEW_STATUS_OPTIONS: { value: ReviewStatusQuery | ''; label: string }[] = [
  { value: '', label: '全部状态 (All)' },
  { value: 'complete', label: '复盘完整 (complete)' },
  { value: 'incomplete_evidence', label: '证据不完整 (incomplete_evidence)' },
  { value: 'waiting_for_review', label: '等待复盘 (waiting_for_review)' },
  { value: 'in_progress', label: '进行中 (in_progress)' },
];

export const ReviewFilterBar: React.FC<ReviewFilterBarProps> = ({
  filters,
  onChange,
  onReset,
  disabled = false,
}) => {
  const hasActiveFilters = Boolean(
    filters.strategy_group_id ||
      filters.review_status ||
      filters.range !== '30d'
  );

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
            策略组 (Strategy Group)
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
            复盘状态 (Review Status)
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
              <span>重置条件</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
