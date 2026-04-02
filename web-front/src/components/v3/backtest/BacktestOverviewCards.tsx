import { useMemo } from 'react';
import { TrendingUp, TrendingDown, DollarSign, Percent, Activity, Award } from 'lucide-react';
import { cn } from '../../../lib/utils';
import type { PMSBacktestReport } from '../../../lib/api';

interface BacktestOverviewCardsProps {
  report: PMSBacktestReport | null;
  className?: string;
}

/**
 * 回测概览卡片组件
 * 显示 4 张关键指标卡片：总收益率、最大回撤、夏普比率、胜率
 */
export function BacktestOverviewCards({ report, className }: BacktestOverviewCardsProps) {
  // Parse decimal strings to numbers for display
  const metrics = useMemo(() => {
    if (!report) return null;

    return {
      totalReturn: parseFloat(report.total_return || '0'),
      maxDrawdown: parseFloat(report.max_drawdown || '0'),
      sharpeRatio: report.sharpe_ratio ? parseFloat(report.sharpe_ratio) : null,
      winRate: parseFloat(report.win_rate || '0'),
      totalTrades: report.total_trades,
      winningTrades: report.winning_trades,
      losingTrades: report.losing_trades,
      totalPnl: parseFloat(report.total_pnl || '0'),
      initialBalance: parseFloat(report.initial_balance || '0'),
      finalBalance: parseFloat(report.final_balance || '0'),
    };
  }, [report]);

  if (!report || !metrics) {
    return null;
  }

  return (
    <div className={cn('grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4', className)}>
      {/* Total Return Card */}
      <div className="bg-gradient-to-br from-green-50 to-green-100/50 rounded-xl border border-green-200 p-5">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 text-green-700">
            <TrendingUp className="w-5 h-5" />
            <span className="text-sm font-medium">总收益率</span>
          </div>
          {metrics.totalReturn >= 0 ? (
            <div className="w-8 h-8 bg-green-200 rounded-full flex items-center justify-center">
              <TrendingUp className="w-4 h-4 text-green-700" />
            </div>
          ) : (
            <div className="w-8 h-8 bg-red-200 rounded-full flex items-center justify-center">
              <TrendingDown className="w-4 h-4 text-red-700" />
            </div>
          )}
        </div>
        <div className="space-y-1">
          <p className={cn(
            'text-3xl font-bold',
            metrics.totalReturn >= 0 ? 'text-green-900' : 'text-red-900'
          )}>
            {metrics.totalReturn >= 0 ? '+' : ''}{(metrics.totalReturn * 100).toFixed(2)}%
          </p>
          <p className="text-xs text-green-600">
            {metrics.totalPnl >= 0 ? '盈利' : '亏损'} ${Math.abs(metrics.totalPnl).toFixed(2)}
          </p>
        </div>
      </div>

      {/* Max Drawdown Card */}
      <div className="bg-gradient-to-br from-red-50 to-red-100/50 rounded-xl border border-red-200 p-5">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 text-red-700">
            <Activity className="w-5 h-5" />
            <span className="text-sm font-medium">最大回撤</span>
          </div>
          <div className="w-8 h-8 bg-red-200 rounded-full flex items-center justify-center">
            <TrendingDown className="w-4 h-4 text-red-700" />
          </div>
        </div>
        <div className="space-y-1">
          <p className="text-3xl font-bold text-red-900">
            {(metrics.maxDrawdown * 100).toFixed(2)}%
          </p>
          <p className="text-xs text-red-600">
            历史最大账户跌幅
          </p>
        </div>
      </div>

      {/* Sharpe Ratio Card */}
      <div className="bg-gradient-to-br from-blue-50 to-blue-100/50 rounded-xl border border-blue-200 p-5">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 text-blue-700">
            <Award className="w-5 h-5" />
            <span className="text-sm font-medium">夏普比率</span>
          </div>
          <div className="w-8 h-8 bg-blue-200 rounded-full flex items-center justify-center">
            <Percent className="w-4 h-4 text-blue-700" />
          </div>
        </div>
        <div className="space-y-1">
          <p className={cn(
            'text-3xl font-bold',
            (metrics.sharpeRatio || 0) >= 1 ? 'text-blue-900' : 'text-blue-600'
          )}>
            {metrics.sharpeRatio !== null ? metrics.sharpeRatio.toFixed(2) : 'N/A'}
          </p>
          <p className="text-xs text-blue-600">
            {getSharpeRating(metrics.sharpeRatio)}
          </p>
        </div>
      </div>

      {/* Win Rate Card */}
      <div className="bg-gradient-to-br from-purple-50 to-purple-100/50 rounded-xl border border-purple-200 p-5">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 text-purple-700">
            <DollarSign className="w-5 h-5" />
            <span className="text-sm font-medium">胜率</span>
          </div>
          <div className="w-8 h-8 bg-purple-200 rounded-full flex items-center justify-center">
            <Activity className="w-4 h-4 text-purple-700" />
          </div>
        </div>
        <div className="space-y-1">
          <p className={cn(
            'text-3xl font-bold',
            (metrics.winRate * 100) >= 50 ? 'text-purple-900' : 'text-purple-600'
          )}>
            {(metrics.winRate * 100).toFixed(1)}%
          </p>
          <p className="text-xs text-purple-600">
            {metrics.winningTrades} 胜 / {metrics.losingTrades} 败 / 共 {metrics.totalTrades} 场
          </p>
        </div>
      </div>
    </div>
  );
}

/**
 * Get Sharpe ratio rating text
 */
function getSharpeRating(sharpeRatio: number | null): string {
  if (sharpeRatio === null) return '数据不足';
  if (sharpeRatio >= 2) return '优秀 (>2)';
  if (sharpeRatio >= 1) return '良好 (>1)';
  if (sharpeRatio >= 0.5) return '一般 (>0.5)';
  return '需改善 (<0.5)';
}
