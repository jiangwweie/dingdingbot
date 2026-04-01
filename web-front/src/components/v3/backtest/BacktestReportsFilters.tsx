/**
 * Backtest Reports Filters Component
 *
 * 回测报告筛选表单组件
 */
import { useState, useCallback, useEffect } from 'react';
import { Filter, X } from 'lucide-react';
import { cn } from '../../../lib/utils';
import QuickDateRangePicker from '../../QuickDateRangePicker';

interface BacktestReportsFiltersProps {
  onSubmit: (filters: FilterValues) => void;
  onReset: () => void;
  defaultFilters?: FilterValues;
  className?: string;
}

export interface FilterValues {
  strategyId?: string;
  symbol?: string;
  startDate?: number;
  endDate?: number;
}

// Symbol options
const SYMBOL_OPTIONS = [
  'BTC/USDT:USDT',
  'ETH/USDT:USDT',
  'SOL/USDT:USDT',
  'BNB/USDT:USDT',
  'XRP/USDT:USDT',
  'ADA/USDT:USDT',
  'DOGE/USDT:USDT',
  'MATIC/USDT:USDT',
];

/**
 * 回测报告筛选表单组件
 */
export function BacktestReportsFilters({
  onSubmit,
  onReset,
  defaultFilters,
  className,
}: BacktestReportsFiltersProps) {
  const [strategyId, setStrategyId] = useState('');
  const [symbol, setSymbol] = useState('');
  const [startTime, setStartTime] = useState<number | null>(null);
  const [endTime, setEndTime] = useState<number | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);

  // Load default filters
  useEffect(() => {
    if (defaultFilters) {
      setStrategyId(defaultFilters.strategyId || '');
      setSymbol(defaultFilters.symbol || '');
      setStartTime(defaultFilters.startDate ? new Date(defaultFilters.startDate).getTime() : null);
      setEndTime(defaultFilters.endDate ? new Date(defaultFilters.endDate).getTime() : null);
    }
  }, [defaultFilters]);

  // Check if there are active filters
  const hasActiveFilters = strategyId || symbol || startTime || endTime;

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      strategyId: strategyId || undefined,
      symbol: symbol || undefined,
      startDate: startTime || undefined,
      endDate: endTime || undefined,
    });
  }, [strategyId, symbol, startTime, endTime, onSubmit]);

  const handleReset = useCallback(() => {
    setStrategyId('');
    setSymbol('');
    setStartTime(null);
    setEndTime(null);
    onReset();
  }, [onReset]);

  return (
    <div className={cn('bg-white rounded-xl border border-gray-200', className)}>
      {/* Filter Header */}
      <div className="p-4 border-b border-gray-200 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-gray-500" />
          <h3 className="text-sm font-medium text-gray-700">筛选条件</h3>
          {hasActiveFilters && (
            <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs font-medium rounded-full">
              {hasActiveFilters} 个筛选生效中
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {hasActiveFilters && (
            <button
              onClick={handleReset}
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 transition-colors"
            >
              <X className="w-3 h-3" />
              重置
            </button>
          )}
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-gray-400 hover:text-gray-600 transition-colors"
          >
            <svg
              className={cn('w-5 h-5 transition-transform', isExpanded && 'rotate-180')}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        </div>
      </div>

      {/* Filter Form */}
      {isExpanded && (
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Strategy ID Filter */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                策略 ID
              </label>
              <input
                type="text"
                value={strategyId}
                onChange={(e) => setStrategyId(e.target.value)}
                placeholder="输入策略 ID"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-black transition-colors"
              />
            </div>

            {/* Symbol Filter */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                交易对
              </label>
              <select
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-black transition-colors"
              >
                <option value="">全部交易对</option>
                {SYMBOL_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Date Range Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              回测时间范围
            </label>
            <QuickDateRangePicker
              startTime={startTime}
              endTime={endTime}
              onStartChange={setStartTime}
              onEndChange={setEndTime}
            />
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-2 pt-2 border-t border-gray-200">
            <button
              type="button"
              onClick={handleReset}
              className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
            >
              重置
            </button>
            <button
              type="submit"
              className="px-4 py-2 text-sm bg-black text-white hover:bg-gray-800 rounded-lg transition-colors"
            >
              应用筛选
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
