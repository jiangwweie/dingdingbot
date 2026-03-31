import { TrendingUp, TrendingDown } from 'lucide-react';
import { cn } from '../../lib/utils';
import { DecimalDisplay } from './DecimalDisplay';

interface PnLStatisticsCardsProps {
  dailyPnl?: string;
  weeklyPnl?: string;
  monthlyPnl?: string;
  totalPnl?: string;
  isLoading?: boolean;
}

/**
 * 盈亏统计卡片组件
 * 显示日盈亏、周盈亏、月盈亏、总盈亏统计
 */
export function PnLStatisticsCards({
  dailyPnl,
  weeklyPnl,
  monthlyPnl,
  totalPnl,
  isLoading,
}: PnLStatisticsCardsProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div
            key={i}
            className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100 animate-pulse"
          >
            <div className="h-4 bg-gray-200 rounded w-24 mb-4" />
            <div className="h-8 bg-gray-200 rounded w-32" />
          </div>
        ))}
      </div>
    );
  }

  const cards = [
    {
      title: '日盈亏 (USDT)',
      value: dailyPnl || '0',
      period: '今日',
    },
    {
      title: '周盈亏 (USDT)',
      value: weeklyPnl || '0',
      period: '本周',
    },
    {
      title: '月盈亏 (USDT)',
      value: monthlyPnl || '0',
      period: '本月',
    },
    {
      title: '总盈亏 (USDT)',
      value: totalPnl || '0',
      period: '总计',
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card, index) => {
        const value = parseFloat(card.value);
        const isPositive = value > 0;
        const isNegative = value < 0;
        const Icon = isPositive ? TrendingUp : isNegative ? TrendingDown : TrendingUp;

        return (
          <div
            key={index}
            className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100 hover:shadow-md transition-shadow"
          >
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-gray-500">{card.title}</h3>
              <Icon
                className={cn(
                  'w-4 h-4',
                  isPositive ? 'text-apple-green' : isNegative ? 'text-apple-red' : 'text-gray-400'
                )}
              />
            </div>
            <div
              className={cn(
                'text-2xl font-semibold tracking-tight font-mono',
                isPositive ? 'text-apple-green' : isNegative ? 'text-apple-red' : 'text-gray-900'
              )}
            >
              <DecimalDisplay
                value={card.value}
                decimals={2}
                prefix={isPositive ? '+' : undefined}
              />
            </div>
            <p className="text-xs text-gray-400 mt-1">{card.period}</p>
          </div>
        );
      })}
    </div>
  );
}
