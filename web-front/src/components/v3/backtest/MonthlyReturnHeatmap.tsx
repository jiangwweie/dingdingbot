import { useMemo } from 'react';
import { Calendar, TrendingUp, TrendingDown } from 'lucide-react';
import { cn } from '../../../lib/utils';
import type { PMSBacktestReport, PositionSummary } from '../../../lib/api';

interface MonthlyReturnHeatmapProps {
  report: PMSBacktestReport | null;
  className?: string;
  title?: string;
}

/**
 * 月度收益热力图组件
 * 展示每个月的盈亏情况（正绿负红）
 */
export function MonthlyReturnHeatmap({ report, className, title }: MonthlyReturnHeatmapProps) {
  // Build monthly return data from positions
  const { monthlyData, yearRange } = useMemo(() => {
    if (!report || !report.positions || report.positions.length === 0) {
      return { monthlyData: [], yearRange: null };
    }

    // Group positions by year-month
    const monthlyPnl: Record<string, number> = {};
    const monthlyTrades: Record<string, number> = {};

    report.positions.forEach(position => {
      if (position.exit_time) {
        const date = new Date(position.exit_time);
        const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
        const pnl = parseFloat(position.realized_pnl || '0');

        if (!monthlyPnl[key]) {
          monthlyPnl[key] = 0;
          monthlyTrades[key] = 0;
        }

        monthlyPnl[key] += pnl;
        monthlyTrades[key] += 1;
      }
    });

    // Convert to array and sort by date
    const monthlyData = Object.entries(monthlyPnl)
      .map(([date, pnl]) => ({
        date,
        year: parseInt(date.split('-')[0]),
        month: parseInt(date.split('-')[1]),
        pnl,
        trades: monthlyTrades[date] || 0,
      }))
      .sort((a, b) => {
        if (a.year !== b.year) return a.year - b.year;
        return a.month - b.month;
      });

    // Calculate year range for display
    const years = [...new Set(monthlyData.map(d => d.year))];
    const yearRange = years.length > 0
      ? { min: Math.min(...years), max: Math.max(...years) }
      : null;

    return { monthlyData, yearRange };
  }, [report]);

  if (!report || monthlyData.length === 0) {
    return (
      <div className={cn('bg-white rounded-xl border border-gray-200 p-6', className)}>
        <div className="flex items-center gap-2 mb-4">
          <Calendar className="w-5 h-5 text-gray-400" />
          <h3 className="text-sm font-semibold text-gray-700">
            {title || '月度收益热力图'}
          </h3>
        </div>
        <div className="h-[200px] flex items-center justify-center text-gray-400 text-sm">
          暂无回测数据
        </div>
      </div>
    );
  }

  // Get min and max PnL for color scaling
  const pnlValues = monthlyData.map(d => d.pnl);
  const minPnl = Math.min(...pnlValues);
  const maxPnl = Math.max(...pnlValues);
  const maxAbs = Math.max(Math.abs(minPnl), Math.abs(maxPnl));

  return (
    <div className={cn('bg-white rounded-xl border border-gray-200 p-6', className)}>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Calendar className="w-5 h-5 text-gray-600" />
          <h3 className="text-sm font-semibold text-gray-700">
            {title || '月度收益热力图'}
          </h3>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <div className="flex items-center gap-1">
            <div className="w-3 h-3 bg-apple-green rounded" />
            <span className="text-gray-600">盈利</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-3 h-3 bg-apple-red rounded" />
            <span className="text-gray-600">亏损</span>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        {yearRange && (
          <YearRows
            monthlyData={monthlyData}
            yearRange={yearRange}
            maxAbs={maxAbs}
          />
        )}
      </div>

      {/* Color scale legend */}
      <div className="mt-4 flex items-center justify-center gap-2 text-xs text-gray-500">
        <span>${(-maxAbs).toFixed(0)}</span>
        <div className="w-32 h-2 rounded bg-gradient-to-r from-apple-red via-gray-200 to-apple-green" />
        <span>${maxAbs.toFixed(0)}</span>
      </div>
    </div>
  );
}

interface YearRowsProps {
  monthlyData: Array<{
    date: string;
    year: number;
    month: number;
    pnl: number;
    trades: number;
  }>;
  yearRange: { min: number; max: number };
  maxAbs: number;
}

function YearRows({ monthlyData, yearRange, maxAbs }: YearRowsProps) {
  const months = ['1 月', '2 月', '3 月', '4 月', '5 月', '6 月', '7 月', '8 月', '9 月', '10 月', '11 月', '12 月'];

  // Group data by year
  const dataByYear = monthlyData.reduce((acc, d) => {
    if (!acc[d.year]) {
      acc[d.year] = [];
    }
    acc[d.year].push(d);
    return acc;
  }, {} as Record<number, typeof monthlyData>);

  return (
    <div className="space-y-2">
      {Object.entries(dataByYear)
        .sort(([a], [b]) => parseInt(a) - parseInt(b))
        .map(([year, yearData]) => (
          <div key={year} className="flex items-center gap-2">
            <div className="w-12 text-xs text-gray-500 text-right">{year}</div>
            <div className="flex gap-1">
              {months.map((monthLabel, monthIndex) => {
                const monthData = yearData.find(d => d.month === monthIndex + 1);

                if (!monthData) {
                  return (
                    <div
                      key={monthLabel}
                      className="w-8 h-8 bg-gray-100 rounded flex items-center justify-center"
                      title={`${year}年${monthLabel}: 无数据`}
                    >
                      <span className="text-[8px] text-gray-400">{monthIndex + 1}</span>
                    </div>
                  );
                }

                const pnlPercent = (monthData.pnl / maxAbs) * 100;
                const colorIntensity = Math.abs(pnlPercent);

                return (
                  <div
                    key={monthLabel}
                    className={cn(
                      'w-8 h-8 rounded flex flex-col items-center justify-center transition-colors',
                      monthData.pnl >= 0
                        ? 'text-white'
                        : 'text-white'
                    )}
                    style={{
                      backgroundColor: monthData.pnl >= 0
                        ? `rgba(34, 197, 94, ${0.3 + colorIntensity / 200})`
                        : `rgba(239, 68, 68, ${0.3 + colorIntensity / 200})`,
                    }}
                    title={`${year}年${monthLabel}: ${monthData.pnl >= 0 ? '+' : ''}$${monthData.pnl.toFixed(2)} (${monthData.trades}场交易)`}
                  >
                    <span className="text-[9px] font-medium">
                      {monthData.pnl >= 0 ? '+' : ''}{monthData.pnl.toFixed(0)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
    </div>
  );
}
