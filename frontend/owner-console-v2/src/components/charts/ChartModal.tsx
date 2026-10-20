import React, { useMemo } from 'react';
import { X, AlertTriangle } from 'lucide-react';
import { CausalityChart } from './CausalityChart';
import { useDrawerDismiss } from '../../hooks/useDrawerDismiss';
import {
  getOutOfWindowAnnotations,
  type CandleView,
  type ChartAnnotation,
  type ChartPriceLevel,
} from '../../mapping/chartAdapter';

export interface ChartModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  candles: CandleView[];
  annotations?: ChartAnnotation[];
  priceLevels?: ChartPriceLevel[];
  drawerId?: string;
}

export const ChartModal: React.FC<ChartModalProps> = ({
  isOpen,
  onClose,
  title,
  subtitle,
  candles,
  annotations = [],
  priceLevels = [],
  drawerId = 'chart-fullscreen-modal',
}) => {
  useDrawerDismiss({
    isOpen,
    onClose,
    drawerId,
  });

  const outOfWindowAnnotations = useMemo(
    () => getOutOfWindowAnnotations(annotations, candles),
    [annotations, candles]
  );

  if (!isOpen) return null;

  return (
    <div
      data-testid="chart-fullscreen-modal"
      className="fixed inset-0 z-[80] overflow-hidden bg-black/80 backdrop-blur-sm flex items-center justify-center p-3 md:p-6 animate-in fade-in duration-200"
      role="dialog"
      aria-modal="true"
      aria-labelledby="chart-modal-title"
    >
      <div
        className="w-full h-full max-h-[calc(100vh-24px)] md:max-h-[calc(100vh-48px)] max-w-7xl rounded-xl border border-border bg-surface shadow-2xl flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex min-h-12 items-center justify-between gap-3 border-b border-border bg-surface-subtle px-5 py-3">
          <div className="min-w-0">
            <h2 id="chart-modal-title" className="text-sm font-bold text-text-primary truncate">
              {title}
            </h2>
            {subtitle && (
              <p className="text-[11px] text-text-muted truncate mt-0.5 font-mono">
                {subtitle}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1.5 text-text-muted hover:bg-surface-elevated hover:text-text-primary transition-colors cursor-pointer flex-none"
            aria-label="关闭全屏图表"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Out-of-window warning in fullscreen modal */}
        {outOfWindowAnnotations.length > 0 && (
          <div
            data-testid="chart-modal-out-of-window-banner"
            className="flex items-center gap-2 border-b border-amber-500/30 bg-amber-500/10 px-5 py-2 text-xs text-amber-700 dark:text-amber-300 font-sans"
          >
            <AlertTriangle className="h-4 w-4 shrink-0 text-amber-500" />
            <span>
              提示: {outOfWindowAnnotations.length} 个事件标注发生时间超出当前 K 线窗口范围（已在图表中隐藏，但完整保留在因果时间线与审计中）
            </span>
          </div>
        )}

        {/* Chart Body */}
        <div className="flex-1 min-h-0 p-4 bg-background">
          <CausalityChart
            candles={candles}
            annotations={annotations}
            priceLevels={priceLevels}
            fullscreen
          />
        </div>
      </div>
    </div>
  );
};
