import React, { useState, useEffect, useId } from 'react';
import {
  type TimeRangePreset,
  calculatePresetWindow,
  validateTimeWindow,
  toShanghaiInputValue,
  parseShanghaiInputValue,
} from '../../utils/timeRange.ts';
import { Calendar, AlertCircle, RotateCcw } from 'lucide-react';

export interface TimeRangeFilterProps {
  preset: TimeRangePreset;
  from_ms: number;
  to_ms: number;
  onChange: (next: { preset: TimeRangePreset; from_ms: number; to_ms: number }) => void;
  disabled?: boolean;
}

export const TimeRangeFilter: React.FC<TimeRangeFilterProps> = ({
  preset,
  from_ms,
  to_ms,
  onChange,
  disabled = false,
}) => {
  const [showCustomInputs, setShowCustomInputs] = useState(preset === 'custom');
  const [customError, setCustomError] = useState<string | null>(null);
  const [draftFrom, setDraftFrom] = useState(() => toShanghaiInputValue(from_ms));
  const [draftTo, setDraftTo] = useState(() => toShanghaiInputValue(to_ms));
  const inputId = useId();
  useEffect(() => {
    setDraftFrom(toShanghaiInputValue(from_ms));
    setDraftTo(toShanghaiInputValue(to_ms));
    setCustomError(null);
    setShowCustomInputs(preset === 'custom');
  }, [from_ms, to_ms, preset]);

  const presets: { id: TimeRangePreset; label: string }[] = [
    { id: 'today', label: '今日' },
    { id: '24h', label: '近 24h' },
    { id: '7d', label: '近 7 天' },
    { id: '30d', label: '近 30 天' },
  ];

  const handleSelectPreset = (p: TimeRangePreset) => {
    if (disabled) return;
    setCustomError(null);
    setShowCustomInputs(false);
    const window = calculatePresetWindow(p);
    onChange({
      preset: p,
      from_ms: window.from_ms,
      to_ms: window.to_ms,
    });
  };

  const handleToggleCustom = () => {
    if (disabled) return;
    setShowCustomInputs(true);
    setCustomError(null);
  };

  const handleApplyCustom = () => {
    const nextFrom = parseShanghaiInputValue(draftFrom);
    const nextTo = parseShanghaiInputValue(draftTo);
    const validation = validateTimeWindow(nextFrom, nextTo);
    if (!validation.valid || nextFrom === null || nextTo === null) {
      setCustomError(validation.error ?? '无效时间范围');
      return;
    }
    setCustomError(null);
    onChange({ preset: 'custom', from_ms: nextFrom, to_ms: nextTo });
  };

  const handleReset = () => {
    if (disabled) return;
    handleSelectPreset('30d');
  };

  const isCustomActive = preset === 'custom' || showCustomInputs;

  return (
    <div className="flex flex-col gap-2 text-xs font-sans">
      {/* Preset Buttons & Custom Trigger */}
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="flex items-center gap-1 text-[11px] font-semibold text-text-secondary mr-1">
          <Calendar className="h-3.5 w-3.5 text-text-muted" />
          <span>时间范围:</span>
        </span>

        {presets.map((p) => {
          const isActive = preset === p.id && !showCustomInputs;
          return (
            <button
              key={p.id}
              type="button"
              disabled={disabled}
              onClick={() => handleSelectPreset(p.id)}
              className={`rounded px-2.5 py-1 text-xs font-medium transition-colors cursor-pointer ${
                isActive
                  ? 'bg-brand/10 text-brand font-bold border border-brand/30 shadow-xs'
                  : 'border border-border bg-surface text-text-secondary hover:text-text-primary hover:bg-surface-elevated'
              } disabled:opacity-50 disabled:cursor-not-allowed`}
            >
              {p.label}
            </button>
          );
        })}

        <button
          type="button"
          disabled={disabled}
          onClick={handleToggleCustom}
          className={`rounded px-2.5 py-1 text-xs font-medium transition-colors cursor-pointer ${
            isCustomActive
              ? 'bg-brand/10 text-brand font-bold border border-brand/30 shadow-xs'
              : 'border border-border bg-surface text-text-secondary hover:text-text-primary hover:bg-surface-elevated'
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          自定义
        </button>

        {(preset !== '30d' || isCustomActive) && (
          <button
            type="button"
            disabled={disabled}
            onClick={handleReset}
            className="inline-flex items-center gap-1 text-[11px] text-text-muted hover:text-brand px-1.5 py-0.5 transition-colors cursor-pointer ml-1"
            title="恢复默认近 30 天"
          >
            <RotateCcw className="h-3 w-3" />
            <span>重置</span>
          </button>
        )}
      </div>

      {/* Custom Inputs Panel (when active) */}
      {isCustomActive && (
        <div className="flex flex-wrap items-center gap-2 p-2 rounded border border-border bg-surface-subtle animate-in fade-in-50 duration-150">
          <div className="flex items-center gap-1.5">
            <label htmlFor={`${inputId}-start`} className="text-[11px] text-text-secondary font-medium">
              开始:
            </label>
            <input
              id={`${inputId}-start`}
              aria-label="自定义开始时间"
              type="datetime-local"
              disabled={disabled}
              value={draftFrom}
              onChange={(e) => { setDraftFrom(e.target.value); setCustomError(null); }}
              className="h-7 rounded border border-border bg-surface px-2 text-xs font-mono text-text-primary outline-none focus:border-brand focus:ring-1 focus:ring-brand/30"
            />
          </div>

          <div className="flex items-center gap-1.5">
            <label htmlFor={`${inputId}-end`} className="text-[11px] text-text-secondary font-medium">
              结束:
            </label>
            <input
              id={`${inputId}-end`}
              aria-label="自定义结束时间"
              type="datetime-local"
              disabled={disabled}
              value={draftTo}
              onChange={(e) => { setDraftTo(e.target.value); setCustomError(null); }}
              className="h-7 rounded border border-border bg-surface px-2 text-xs font-mono text-text-primary outline-none focus:border-brand focus:ring-1 focus:ring-brand/30"
            />
          </div>

          <button type="button" disabled={disabled} onClick={handleApplyCustom}
            className="rounded border border-brand/30 bg-brand/10 px-3 py-1 font-semibold text-brand disabled:opacity-50">
            应用时间范围
          </button>
          <span className="text-[10px] text-text-muted hidden md:inline">
            · 按北京时间 (Asia/Shanghai) 查看 · 最大 90 天
          </span>

          {customError && (
            <div role="alert" className="flex items-center gap-1 text-[11px] text-danger font-medium w-full mt-1">
              <AlertCircle className="h-3.5 w-3.5 flex-none" />
              <span>{customError}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
