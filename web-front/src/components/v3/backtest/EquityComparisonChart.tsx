import { useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine } from 'recharts';
import { TrendingUp, Activity } from 'lucide-react';
import { cn } from '../../../lib/utils';
import type { PMSBacktestReport, PositionSummary } from '../../../lib/api';

interface EquityComparisonChartProps {
  report: PMSBacktestReport | null;
  className?: string;
  title?: string;
}

/**
 * 权益曲线对比图组件
 * 展示策略净值曲线与基准（初始资金）的对比
 */
export function EquityComparisonChart({ report, className, title }: EquityComparisonChartProps) {
  // Transform position data into equity curve data points
  const chartData = useMemo(() => {
    if (!report || !report.positions || report.positions.length === 0) {
      return [];
    }

    const initialBalance = parseFloat(report.initial_balance || '10000');

    // Sort positions by entry time
    const sortedPositions = [...report.positions].sort(
      (a, b) => a.entry_time - b.entry_time
    );

    // Build equity curve data points
    const dataPoints: Array<{
      timestamp: number;
      date: string;
      strategyEquity: number;
      benchmark: number;
    }> = [];

    // Starting point
    dataPoints.push({
      timestamp: report.backtest_start,
      date: formatDate(report.backtest_start),
      strategyEquity: initialBalance,
      benchmark: initialBalance,
    });

    // Add data point for each closed position
    let runningPnl = 0;
    sortedPositions.forEach((position, index) => {
      if (position.exit_time) {
        const pnl = parseFloat(position.realized_pnl || '0');
        runningPnl += pnl;

        dataPoints.push({
          timestamp: position.exit_time,
          date: formatDate(position.exit_time),
          strategyEquity: initialBalance + runningPnl,
          benchmark: initialBalance,
        });
      }
    });

    // End point: total_pnl is now net PnL (includes all costs), so equity = initial + net_pnl = final_balance
    const netPnl = parseFloat(report.total_pnl || '0');
    dataPoints.push({
      timestamp: report.backtest_end,
      date: formatDate(report.backtest_end),
      strategyEquity: initialBalance + netPnl,
      benchmark: initialBalance,
    });

    return dataPoints;
  }, [report]);

  if (!report || chartData.length === 0) {
    return (
      <div className={cn('bg-white rounded-xl border border-gray-200 p-6', className)}>
        <div className="flex items-center gap-2 mb-4">
          <Activity className="w-5 h-5 text-gray-400" />
          <h3 className="text-sm font-semibold text-gray-700">
            {title || '权益曲线对比'}
          </h3>
        </div>
        <div className="h-[300px] flex items-center justify-center text-gray-400 text-sm">
          暂无回测数据
        </div>
      </div>
    );
  }

  const initialBalance = parseFloat(report.initial_balance || '10000');
  const finalBalance = parseFloat(report.final_balance || initialBalance);
  const totalReturn = (finalBalance - initialBalance) / initialBalance;

  return (
    <div className={cn('bg-white rounded-xl border border-gray-200 p-6', className)}>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-gray-600" />
          <h3 className="text-sm font-semibold text-gray-700">
            {title || '权益曲线对比'}
          </h3>
        </div>
        <div className="text-sm text-gray-600">
          初始：${initialBalance.toFixed(2)} → 最终：${finalBalance.toFixed(2)}
          <span className={cn(
            'ml-2 font-medium',
            totalReturn >= 0 ? 'text-green-600' : 'text-red-600'
          )}>
            ({totalReturn >= 0 ? '+' : ''}{(totalReturn * 100).toFixed(2)}%)
          </span>
        </div>
      </div>

      <div className="h-[300px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 12, fill: '#6b7280' }}
              tickFormatter={formatXAxisTick}
            />
            <YAxis
              tick={{ fontSize: 12, fill: '#6b7280' }}
              tickFormatter={(value) => `$${value.toFixed(0)}`}
              domain={['auto', 'auto']}
            />
            <Tooltip
              content={<EquityTooltip />}
              labelFormatter={(label) => `时间：${label}`}
            />
            <Legend />
            <ReferenceLine
              y={initialBalance}
              stroke="#9ca3af"
              strokeDasharray="3 3"
              label="初始资金"
            />
            <Line
              type="monotone"
              dataKey="strategyEquity"
              name="策略净值"
              stroke="#000000"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 6, fill: '#000000' }}
            />
            <Line
              type="monotone"
              dataKey="benchmark"
              name="基准"
              stroke="#9ca3af"
              strokeWidth={2}
              strokeDasharray="5 5"
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/**
 * Custom tooltip for equity chart
 */
function EquityTooltip({ active, payload, label }: any) {
  if (active && payload && payload.length) {
    const strategyEquity = payload[0]?.value;
    const benchmark = payload[1]?.value;
    const excess = strategyEquity - benchmark;

    return (
      <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-3 text-xs">
        <p className="font-medium text-gray-700 mb-2">{label}</p>
        <div className="space-y-1">
          <div className="flex items-center justify-between gap-4">
            <span className="text-gray-600">策略净值:</span>
            <span className="font-medium text-black">${strategyEquity.toFixed(2)}</span>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span className="text-gray-600">基准:</span>
            <span className="font-medium text-gray-500">${benchmark.toFixed(2)}</span>
          </div>
          <div className="flex items-center justify-between gap-4 pt-1 border-t border-gray-100">
            <span className="text-gray-600">超额收益:</span>
            <span className={cn(
              'font-medium',
              excess >= 0 ? 'text-green-600' : 'text-red-600'
            )}>
              {excess >= 0 ? '+' : ''}${excess.toFixed(2)}
            </span>
          </div>
        </div>
      </div>
    );
  }
  return null;
}

/**
 * Format date for X-axis tick
 */
function formatXAxisTick(date: string): string {
  const dateObj = new Date(date);
  const month = dateObj.getMonth() + 1;
  const day = dateObj.getDate();
  return `${month}/${day}`;
}

/**
 * Format timestamp to date string
 */
function formatDate(timestamp: number | string): string {
  const ts = typeof timestamp === 'string' ? parseInt(timestamp) : timestamp;
  return new Date(ts).toISOString();
}
