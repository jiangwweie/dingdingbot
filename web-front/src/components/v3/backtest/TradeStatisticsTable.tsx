import { useMemo, type ReactNode } from 'react';
import { Table, TrendingUp, TrendingDown, DollarSign, Percent, Activity, Award, ClipboardList } from 'lucide-react';
import { cn } from '../../../lib/utils';
import type { PMSBacktestReport } from '../../../lib/api';

interface TradeStatisticsTableProps {
  report: PMSBacktestReport | null;
  className?: string;
}

/**
 * 交易统计表格组件
 * 展示总交易次数、盈利次数、亏损次数、平均盈亏等统计信息
 */
export function TradeStatisticsTable({ report, className }: TradeStatisticsTableProps) {
  const stats = useMemo(() => {
    if (!report) return null;

    const initialBalance = parseFloat(report.initial_balance || '0');
    const totalPnl = parseFloat(report.total_pnl || '0');
    const totalFees = parseFloat(report.total_fees_paid || '0');
    const totalSlippage = parseFloat(report.total_slippage_cost || '0');

    // Calculate average PnL per trade
    const avgPnlPerTrade = report.total_trades > 0
      ? totalPnl / report.total_trades
      : 0;

    // Calculate average win and loss
    const positions = report.positions || [];
    const winningPositions = positions.filter(p => parseFloat(p.realized_pnl || '0') > 0);
    const losingPositions = positions.filter(p => parseFloat(p.realized_pnl || '0') <= 0);

    const totalWinPnl = winningPositions.reduce(
      (sum, p) => sum + parseFloat(p.realized_pnl || '0'),
      0
    );
    const totalLossPnl = losingPositions.reduce(
      (sum, p) => sum + parseFloat(p.realized_pnl || '0'),
      0
    );

    const avgWin = winningPositions.length > 0
      ? totalWinPnl / winningPositions.length
      : 0;
    const avgLoss = losingPositions.length > 0
      ? Math.abs(totalLossPnl) / losingPositions.length
      : 0;

    // Profit factor = Gross Win / Gross Loss
    const profitFactor = Math.abs(totalLossPnl) > 0
      ? Math.abs(totalWinPnl) / Math.abs(totalLossPnl)
      : totalWinPnl > 0 ? Infinity : 0;

    return {
      totalTrades: report.total_trades ?? 0,
      winningTrades: report.winning_trades ?? 0,
      losingTrades: report.losing_trades ?? 0,
      winRate: parseFloat(report.win_rate || '0'),
      totalPnl,
      totalFees,
      totalSlippage,
      avgPnlPerTrade,
      avgWin,
      avgLoss,
      profitFactor,
      initialBalance,
      finalBalance: parseFloat(report.final_balance || '0'),
      totalReturn: parseFloat(report.total_return || '0'),
      maxDrawdown: parseFloat(report.max_drawdown || '0'),
      sharpeRatio: report.sharpe_ratio ? parseFloat(report.sharpe_ratio) : null,
    };
  }, [report]);

  if (!report || !stats) {
    return (
      <div className={cn('bg-white rounded-xl border border-gray-200 p-6', className)}>
        <div className="flex items-center gap-2 mb-4">
          <ClipboardList className="w-5 h-5 text-gray-400" />
          <h3 className="text-sm font-semibold text-gray-700">交易统计</h3>
        </div>
        <div className="h-[200px] flex items-center justify-center text-gray-400 text-sm">
          暂无回测数据
        </div>
      </div>
    );
  }

  return (
    <div className={cn('bg-white rounded-xl border border-gray-200 p-6', className)}>
      <div className="flex items-center gap-2 mb-4">
        <ClipboardList className="w-5 h-5 text-gray-600" />
        <h3 className="text-sm font-semibold text-gray-700">交易统计</h3>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* Total Trades */}
        <StatItem
          icon={<Activity className="w-4 h-4" />}
          label="总交易次数"
          value={String(stats.totalTrades ?? 0)}
          color="blue"
        />

        {/* Winning Trades */}
        <StatItem
          icon={<TrendingUp className="w-4 h-4" />}
          label="盈利次数"
          value={String(stats.winningTrades ?? 0)}
          color="green"
        />

        {/* Losing Trades */}
        <StatItem
          icon={<TrendingDown className="w-4 h-4" />}
          label="亏损次数"
          value={String(stats.losingTrades ?? 0)}
          color="red"
        />

        {/* Win Rate */}
        <StatItem
          icon={<Percent className="w-4 h-4" />}
          label="胜率"
          value={`${((stats.winRate ?? 0) * 100).toFixed(1)}%`}
          color="purple"
        />

        {/* Profit Factor */}
        <StatItem
          icon={<Award className="w-4 h-4" />}
          label="盈利因子"
          value={
            stats.profitFactor === Infinity
              ? '∞'
              : stats.profitFactor != null ? stats.profitFactor.toFixed(2) : '0.00'
          }
          color="orange"
        />

        {/* Total PnL */}
        <StatItem
          icon={<DollarSign className="w-4 h-4" />}
          label="总盈亏"
          value={`${stats.totalPnl >= 0 ? '+' : ''}$${(stats.totalPnl ?? 0).toFixed(2)}`}
          color={stats.totalPnl != null && stats.totalPnl >= 0 ? 'green' : 'red'}
        />

        {/* Average PnL per Trade */}
        <StatItem
          icon={<DollarSign className="w-4 h-4" />}
          label="场均盈亏"
          value={`${stats.avgPnlPerTrade != null && stats.avgPnlPerTrade >= 0 ? '+' : ''}$${(stats.avgPnlPerTrade ?? 0).toFixed(2)}`}
          color={stats.avgPnlPerTrade != null && stats.avgPnlPerTrade >= 0 ? 'green' : 'red'}
        />

        {/* Average Win */}
        <StatItem
          icon={<TrendingUp className="w-4 h-4" />}
          label="平均盈利"
          value={`+$${(stats.avgWin ?? 0).toFixed(2)}`}
          color="green"
        />

        {/* Average Loss */}
        <StatItem
          icon={<TrendingDown className="w-4 h-4" />}
          label="平均亏损"
          value={`-$${(stats.avgLoss ?? 0).toFixed(2)}`}
          color="red"
        />

        {/* Total Fees */}
        <StatItem
          icon={<DollarSign className="w-4 h-4" />}
          label="总手续费"
          value={`-$${(stats.totalFees ?? 0).toFixed(2)}`}
          color="gray"
        />

        {/* Total Slippage */}
        <StatItem
          icon={<DollarSign className="w-4 h-4" />}
          label="总滑点成本"
          value={`-$${(stats.totalSlippage ?? 0).toFixed(2)}`}
          color="gray"
        />

        {/* Max Drawdown */}
        <StatItem
          icon={<Activity className="w-4 h-4" />}
          label="最大回撤"
          value={`${((stats.maxDrawdown ?? 0) * 100).toFixed(2)}%`}
          color="red"
        />
      </div>
    </div>
  );
}

interface StatItemProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  color: 'blue' | 'green' | 'red' | 'purple' | 'orange' | 'gray';
}

function StatItem({ icon, label, value, color }: StatItemProps) {
  const colorClasses = {
    blue: 'bg-blue-50 text-blue-700 border-blue-200',
    green: 'bg-green-50 text-green-700 border-green-200',
    red: 'bg-red-50 text-red-700 border-red-200',
    purple: 'bg-purple-50 text-purple-700 border-purple-200',
    orange: 'bg-orange-50 text-orange-700 border-orange-200',
    gray: 'bg-gray-50 text-gray-700 border-gray-200',
  };

  return (
    <div className={cn(
      'flex items-center gap-3 p-3 rounded-lg border',
      colorClasses[color]
    )}>
      <div className={cn(
        'w-8 h-8 rounded-full flex items-center justify-center',
        color.replace('text-', 'bg-'),
        color.replace('bg-', 'text-')
      )}>
        {icon}
      </div>
      <div>
        <p className="text-xs opacity-75">{label}</p>
        <p className="text-lg font-bold">{value}</p>
      </div>
    </div>
  );
}
