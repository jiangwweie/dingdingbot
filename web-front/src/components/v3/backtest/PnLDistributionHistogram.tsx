import { useMemo } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { BarChart3, TrendingUp, TrendingDown } from 'lucide-react';
import { cn } from '../../../lib/utils';
import type { PMSBacktestReport } from '../../../lib/api';

interface PnLDistributionHistogramProps {
  report: PMSBacktestReport | null;
  className?: string;
  title?: string;
  bucketCount?: number; // Number of bins for histogram
}

/**
 * 盈亏分布直方图组件
 * 展示交易盈亏的分布情况
 */
export function PnLDistributionHistogram({
  report,
  className,
  title,
  bucketCount = 10,
}: PnLDistributionHistogramProps) {
  // Build histogram data from positions
  const { histogramData, stats } = useMemo(() => {
    if (!report || !report.positions || report.positions.length === 0) {
      return { histogramData: [], stats: null };
    }

    // Extract PnL values from positions
    const pnlValues = report.positions
      .map(p => parseFloat(p.realized_pnl || '0'))
      .filter(pnl => pnl !== 0);

    if (pnlValues.length === 0) {
      return { histogramData: [], stats: null };
    }

    // Calculate statistics
    const minPnl = Math.min(...pnlValues);
    const maxPnl = Math.max(...pnlValues);
    const avgPnl = pnlValues.reduce((a, b) => a + b, 0) / pnlValues.length;

    // Create buckets for histogram
    const range = maxPnl - minPnl;
    const bucketSize = range / bucketCount || 1;

    const buckets: Array<{
      range: string;
      count: number;
      min: number;
      max: number;
    }> = [];

    for (let i = 0; i < bucketCount; i++) {
      const bucketMin = minPnl + i * bucketSize;
      const bucketMax = minPnl + (i + 1) * bucketSize;

      buckets.push({
        range: formatRange(bucketMin, bucketMax),
        count: 0,
        min: bucketMin,
        max: bucketMax,
      });
    }

    // Count PnL values in each bucket
    pnlValues.forEach(pnl => {
      const bucketIndex = Math.min(
        Math.floor((pnl - minPnl) / bucketSize),
        bucketCount - 1
      );
      if (bucketIndex >= 0 && bucketIndex < bucketCount) {
        buckets[bucketIndex].count++;
      }
    });

    // Build chart data
    const histogramData = buckets.map(bucket => ({
      range: bucket.range,
      count: bucket.count,
      min: bucket.min,
      max: bucket.max,
      isPositive: bucket.max > 0,
    }));

    const stats = {
      totalTrades: pnlValues.length,
      minPnl,
      maxPnl,
      avgPnl,
      winningTrades: pnlValues.filter(p => p > 0).length,
      losingTrades: pnlValues.filter(p => p <= 0).length,
    };

    return { histogramData, stats };
  }, [report, bucketCount]);

  if (!report || histogramData.length === 0) {
    return (
      <div className={cn('bg-white rounded-xl border border-gray-200 p-6', className)}>
        <div className="flex items-center gap-2 mb-4">
          <BarChart3 className="w-5 h-5 text-gray-400" />
          <h3 className="text-sm font-semibold text-gray-700">
            {title || '盈亏分布'}
          </h3>
        </div>
        <div className="h-[250px] flex items-center justify-center text-gray-400 text-sm">
          暂无回测数据
        </div>
      </div>
    );
  }

  return (
    <div className={cn('bg-white rounded-xl border border-gray-200 p-6', className)}>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-gray-600" />
          <h3 className="text-sm font-semibold text-gray-700">
            {title || '盈亏分布'}
          </h3>
        </div>
        {stats && (
          <div className="flex items-center gap-4 text-xs text-gray-600">
            <div className="flex items-center gap-1">
              <TrendingUp className="w-3 h-3 text-green-600" />
              <span>盈利：{stats.winningTrades} 场</span>
            </div>
            <div className="flex items-center gap-1">
              <TrendingDown className="w-3 h-3 text-red-600" />
              <span>亏损：{stats.losingTrades} 场</span>
            </div>
          </div>
        )}
      </div>

      <div className="h-[250px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={histogramData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis
              dataKey="range"
              tick={{ fontSize: 10, fill: '#6b7280' }}
              angle={-45}
              textAnchor="end"
              height={60}
            />
            <YAxis
              tick={{ fontSize: 12, fill: '#6b7280' }}
              allowDecimals={false}
            />
            <Tooltip content={<PnLTooltip />} />
            <Bar dataKey="count" radius={[4, 4, 0, 0]}>
              {histogramData.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={entry.count > 0 ? (entry.isPositive ? '#22c55e' : '#ef4444') : '#e5e7eb'}
                  opacity={entry.count > 0 ? 0.8 : 0.3}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {stats && (
        <div className="mt-4 grid grid-cols-3 gap-4 text-xs">
          <div className="text-center">
            <p className="text-gray-500">最小盈亏</p>
            <p className={cn(
              'font-bold',
              stats.minPnl >= 0 ? 'text-green-600' : 'text-red-600'
            )}>
              ${stats.minPnl.toFixed(2)}
            </p>
          </div>
          <div className="text-center">
            <p className="text-gray-500">平均盈亏</p>
            <p className={cn(
              'font-bold',
              stats.avgPnl >= 0 ? 'text-green-600' : 'text-red-600'
            )}>
              ${stats.avgPnl.toFixed(2)}
            </p>
          </div>
          <div className="text-center">
            <p className="text-gray-500">最大盈亏</p>
            <p className={cn(
              'font-bold',
              stats.maxPnl >= 0 ? 'text-green-600' : 'text-red-600'
            )}>
              ${stats.maxPnl.toFixed(2)}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Custom tooltip for PnL histogram
 */
function PnLTooltip({ active, payload }: any) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;

    return (
      <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-3 text-xs">
        <p className="font-medium text-gray-700 mb-1">
          盈亏范围：{data.range}
        </p>
        <p className="text-gray-600">
          交易次数：<span className="font-medium">{data.count} 场</span>
        </p>
      </div>
    );
  }
  return null;
}

/**
 * Format range string
 */
function formatRange(min: number, max: number): string {
  const minFormatted = min >= 0 ? `+$${min.toFixed(0)}` : `-$${Math.abs(min).toFixed(0)}`;
  const maxFormatted = max >= 0 ? `+$${max.toFixed(0)}` : `-$${Math.abs(max).toFixed(0)}`;
  return `${minFormatted}~${maxFormatted}`;
}
