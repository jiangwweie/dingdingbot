import { useMemo } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { cn } from '../../lib/utils';

export type DateRangeType = '7days' | '30days' | '90days';

interface EquityDataPoint {
  date: string;
  equity: number;
}

interface EquityCurveChartProps {
  snapshots?: Array<{
    timestamp: number;
    total_equity: string;
  }>;
  dateRange: DateRangeType;
  isLoading?: boolean;
  className?: string;
}

/**
 * 净值曲线图表组件
 * 使用 Recharts 绘制 7 天/30 天/90 天净值变化曲线
 */
export function EquityCurveChart({
  snapshots,
  dateRange,
  isLoading,
  className,
}: EquityCurveChartProps) {
  // Process snapshots into chart data
  const chartData: EquityDataPoint[] = useMemo(() => {
    if (!snapshots || snapshots.length === 0) {
      return [];
    }

    // Sort by timestamp
    const sorted = [...snapshots].sort((a, b) => a.timestamp - b.timestamp);

    // Group by date and calculate daily average equity
    const equityMap = new Map<string, number[]>();

    sorted.forEach((snapshot) => {
      const date = new Date(snapshot.timestamp);
      const dateStr = date.toLocaleDateString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
      });

      if (!equityMap.has(dateStr)) {
        equityMap.set(dateStr, []);
      }
      equityMap.get(dateStr)!.push(parseFloat(snapshot.total_equity));
    });

    // Calculate average for each day
    return Array.from(equityMap.entries()).map(([date, equities]) => ({
      date,
      equity: equities.reduce((sum, e) => sum + e, 0) / equities.length,
    }));
  }, [snapshots]);

  // Calculate min/max for Y axis domain
  const yDomain = useMemo(() => {
    if (chartData.length === 0) {
      return [0, 10000];
    }
    const equities = chartData.map((d) => d.equity);
    const min = Math.min(...equities);
    const max = Math.max(...equities);
    const padding = (max - min) * 0.1;
    return [Math.max(0, min - padding), max + padding];
  }, [chartData]);

  // Calculate starting equity for reference line
  const startingEquity = chartData.length > 0 ? chartData[0].equity : 0;

  if (isLoading) {
    return (
      <div className={cn('bg-white rounded-2xl shadow-sm border border-gray-100 p-6', className)}>
        <div className="h-64 bg-gray-100 rounded animate-pulse" />
      </div>
    );
  }

  if (chartData.length === 0) {
    return (
      <div className={cn('bg-white rounded-2xl shadow-sm border border-gray-100 p-6', className)}>
        <div className="h-64 flex items-center justify-center text-gray-400">
          暂无净值数据
        </div>
      </div>
    );
  }

  return (
    <div className={cn('bg-white rounded-2xl shadow-sm border border-gray-100 p-6', className)}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold tracking-tight">净值走势</h3>
        <div className="text-sm text-gray-500">
          起始净值：<span className="font-mono text-gray-900">{startingEquity.toFixed(2)}</span>
        </div>
      </div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 12, fill: '#9ca3af' }}
              axisLine={{ stroke: '#e5e7eb' }}
              tickLine={{ stroke: '#e5e7eb' }}
            />
            <YAxis
              domain={yDomain}
              tick={{ fontSize: 12, fill: '#9ca3af' }}
              axisLine={{ stroke: '#e5e7eb' }}
              tickLine={{ stroke: '#e5e7eb' }}
              tickFormatter={(value) => value.toFixed(0)}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#fff',
                border: '1px solid #e5e7eb',
                borderRadius: '8px',
                boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
              }}
              labelStyle={{ color: '#6b7280', marginBottom: '4px' }}
              formatter={(value: number) => [value.toFixed(2), '净值']}
            />
            <ReferenceLine
              y={startingEquity}
              stroke="#9ca3af"
              strokeDasharray="3 3"
            />
            <Area
              type="monotone"
              dataKey="equity"
              stroke="#3b82f6"
              strokeWidth={2}
              fill="url(#equityGradient)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
