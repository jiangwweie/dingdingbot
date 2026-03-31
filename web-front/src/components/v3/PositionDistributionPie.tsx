import { useMemo } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';
import { cn } from '../../lib/utils';

interface PositionData {
  symbol: string;
  quantity: string;
  entry_price: string;
  direction: 'LONG' | 'SHORT';
}

interface PositionDistributionPieProps {
  positions?: PositionData[];
  isLoading?: boolean;
  className?: string;
}

// Apple-inspired color palette for pie chart
const COLORS = [
  '#3b82f6', // blue
  '#8b5cf6', // violet
  '#06b6d4', // cyan
  '#84cc1e', // lime
  '#f59e0b', // amber
  '#ec4899', // pink
  '#ef4444', // red
  '#10b981', // emerald
];

/**
 * 仓位分布饼图组件
 * 显示各币种仓位占比
 */
export function PositionDistributionPie({
  positions,
  isLoading,
  className,
}: PositionDistributionPieProps) {
  // Calculate position value distribution
  const chartData = useMemo(() => {
    if (!positions || positions.length === 0) {
      return [];
    }

    // Calculate value for each position
    const positionValues = positions.map((pos) => {
      const quantity = parseFloat(pos.quantity);
      const entryPrice = parseFloat(pos.entry_price);
      return {
        symbol: pos.symbol.replace(':USDT', ''),
        value: quantity * entryPrice,
        direction: pos.direction,
      };
    });

    // Calculate total value
    const totalValue = positionValues.reduce((sum, p) => sum + p.value, 0);

    // Calculate percentage for each position
    return positionValues.map((p, index) => ({
      ...p,
      percentage: totalValue > 0 ? (p.value / totalValue) * 100 : 0,
      color: COLORS[index % COLORS.length],
    }));
  }, [positions]);

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
          暂无持仓数据
        </div>
      </div>
    );
  }

  return (
    <div className={cn('bg-white rounded-2xl shadow-sm border border-gray-100 p-6', className)}>
      <h3 className="text-lg font-semibold tracking-tight mb-4">仓位分布</h3>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              innerRadius={60}
              outerRadius={80}
              paddingAngle={2}
              dataKey="value"
              nameKey="symbol"
            >
              {chartData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                backgroundColor: '#fff',
                border: '1px solid #e5e7eb',
                borderRadius: '8px',
                boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
              }}
              formatter={(value: number, name: string, props: any) => {
                const data = chartData[props.index];
                return [
                  `${data.value.toFixed(2)} USDT (${data.percentage.toFixed(1)}%)`,
                  `${name} (${data.direction})`,
                ];
              }}
            />
            <Legend
              verticalAlign="bottom"
              height={36}
              formatter={(value, entry) => {
                const data = chartData[entry.index];
                return (
                  <span className="text-sm text-gray-600">
                    {value} ({data?.percentage.toFixed(1)}%)
                  </span>
                );
              }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
