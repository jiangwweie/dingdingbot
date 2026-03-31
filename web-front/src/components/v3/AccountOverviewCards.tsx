import { Wallet, TrendingUp, TrendingDown, Lock } from 'lucide-react';
import { cn } from '../../lib/utils';
import { DecimalDisplay } from './DecimalDisplay';

interface AccountOverviewCardsProps {
  totalEquity?: string;
  availableBalance?: string;
  unrealizedPnl?: string;
  marginUsed?: string;
  isLoading?: boolean;
}

/**
 * 账户概览卡片组件
 * 显示总权益、可用余额、未实现盈亏、保证金占用 4 张卡片
 */
export function AccountOverviewCards({
  totalEquity,
  availableBalance,
  unrealizedPnl,
  marginUsed,
  isLoading,
}: AccountOverviewCardsProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div
            key={i}
            className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100 animate-pulse"
          >
            <div className="flex items-center gap-2 text-gray-500 mb-4">
              <div className="w-4 h-4 bg-gray-200 rounded" />
              <div className="h-4 bg-gray-200 rounded w-20" />
            </div>
            <div className="h-8 bg-gray-200 rounded w-32" />
          </div>
        ))}
      </div>
    );
  }

  const cards = [
    {
      title: '总权益 (USDT)',
      value: totalEquity || '0',
      icon: Wallet,
      iconColor: 'text-gray-400',
      decimals: 2,
    },
    {
      title: '可用余额 (USDT)',
      value: availableBalance || '0',
      icon: Lock,
      iconColor: 'text-gray-400',
      decimals: 2,
    },
    {
      title: '未实现盈亏 (USDT)',
      value: unrealizedPnl || '0',
      icon: parseFloat(unrealizedPnl || '0') >= 0 ? TrendingUp : TrendingDown,
      iconColor: parseFloat(unrealizedPnl || '0') >= 0 ? 'text-apple-green' : 'text-apple-red',
      valueColor:
        parseFloat(unrealizedPnl || '0') > 0
          ? 'text-apple-green'
          : parseFloat(unrealizedPnl || '0') < 0
          ? 'text-apple-red'
          : 'text-gray-900',
      prefix: parseFloat(unrealizedPnl || '0') > 0 ? '+' : undefined,
      decimals: 2,
    },
    {
      title: '保证金占用 (USDT)',
      value: marginUsed || '0',
      icon: Lock,
      iconColor: 'text-apple-orange',
      decimals: 2,
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card, index) => {
        const Icon = card.icon;
        return (
          <div
            key={index}
            className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100 hover:shadow-md transition-shadow"
          >
            <div className="flex items-center gap-2 text-gray-500 mb-4">
              <Icon className={cn('w-4 h-4', card.iconColor)} />
              <h3 className="text-sm font-medium">{card.title}</h3>
            </div>
            <div
              className={cn(
                'text-3xl font-semibold tracking-tight font-mono',
                card.valueColor || 'text-gray-900'
              )}
            >
              <DecimalDisplay
                value={card.value}
                decimals={card.decimals}
                prefix={card.prefix}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
