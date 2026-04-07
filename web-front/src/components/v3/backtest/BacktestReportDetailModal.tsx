/**
 * Backtest Report Detail Modal Component
 *
 * 回测报告详情弹窗 - 展示完整的回测报告信息（BT-2 资金费用）
 */
import { XCircle, TrendingUp, TrendingDown, DollarSign, Percent, Activity, Calendar, Layers } from 'lucide-react';
import { cn } from '../../../lib/utils';
import type { BacktestReportDetail } from '../../../types/backtest';

interface BacktestReportDetailModalProps {
  report: BacktestReportDetail | null;
  onClose: () => void;
}

export default function BacktestReportDetailModal({
  report,
  onClose,
}: BacktestReportDetailModalProps) {
  if (!report) return null;

  // Format percentage string to display value
  const formatPercent = (value: string | null | undefined) => {
    if (!value) return 'N/A';
    const num = parseFloat(value) * 100;
    return `${num >= 0 ? '+' : ''}${num.toFixed(2)}%`;
  };

  // Format PnL/Cost string to display value
  const formatCurrency = (value: string | null | undefined, showSign = false) => {
    if (!value) return 'N/A';
    const num = parseFloat(value);
    if (showSign) {
      return `${num >= 0 ? '+' : ''}$${Math.abs(num).toFixed(2)}`;
    }
    return `$${num.toFixed(2)}`;
  };

  // Get color class based on value
  const getPositiveNegativeColor = (value: string | null | undefined) => {
    if (!value) return 'text-gray-400';
    const num = parseFloat(value);
    if (num > 0) return 'text-green-600';
    if (num < 0) return 'text-red-600';
    return 'text-gray-400';
  };

  // Format timestamp to readable date
  const formatDate = (timestamp: number) => {
    return new Date(timestamp).toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-xl max-w-5xl w-full max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-gray-900">回测报告详情</h2>
            <p className="text-sm text-gray-500 mt-1">
              {report.strategy_name} v{report.strategy_version} · {report.symbol} · {report.timeframe}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <XCircle className="w-6 h-6 text-gray-400" />
          </button>
        </div>

        {/* Content - Scrollable */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Time Range Banner */}
          <div className="bg-gray-50 rounded-xl p-4 mb-6 flex items-center gap-3">
            <Calendar className="w-5 h-5 text-gray-500" />
            <div className="text-sm text-gray-600">
              <span className="font-medium">回测时间：</span>
              {formatDate(report.backtest_start)} - {formatDate(report.backtest_end)}
            </div>
          </div>

          {/* Core Metrics Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            {/* Total Return */}
            <div className="p-4 bg-gradient-to-br from-green-50 to-green-100/50 rounded-xl border border-green-200">
              <div className="flex items-center gap-2 text-green-700 mb-2">
                <TrendingUp className="w-5 h-5" />
                <span className="text-sm font-medium">总收益率</span>
              </div>
              <p className={cn('text-2xl font-bold', getPositiveNegativeColor(report.total_return))}>
                {formatPercent(report.total_return)}
              </p>
            </div>

            {/* Win Rate */}
            <div className="p-4 bg-gradient-to-br from-blue-50 to-blue-100/50 rounded-xl border border-blue-200">
              <div className="flex items-center gap-2 text-blue-700 mb-2">
                <Percent className="w-5 h-5" />
                <span className="text-sm font-medium">胜率</span>
              </div>
              <p className="text-2xl font-bold text-blue-900">
                {formatPercent(report.win_rate)}
              </p>
            </div>

            {/* Total PnL */}
            <div className="p-4 bg-gradient-to-br from-purple-50 to-purple-100/50 rounded-xl border border-purple-200">
              <div className="flex items-center gap-2 text-purple-700 mb-2">
                <DollarSign className="w-5 h-5" />
                <span className="text-sm font-medium">总盈亏</span>
              </div>
              <p className={cn('text-2xl font-bold', getPositiveNegativeColor(report.total_pnl))}>
                {formatCurrency(report.total_pnl, true)}
              </p>
            </div>

            {/* Max Drawdown */}
            <div className="p-4 bg-gradient-to-br from-red-50 to-red-100/50 rounded-xl border border-red-200">
              <div className="flex items-center gap-2 text-red-700 mb-2">
                <Activity className="w-5 h-5" />
                <span className="text-sm font-medium">最大回撤</span>
              </div>
              <p className="text-2xl font-bold text-red-900">
                {formatPercent(report.max_drawdown)}
              </p>
            </div>
          </div>

          {/* Cost Breakdown */}
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden mb-6">
            <div className="px-5 py-4 bg-gray-50 border-b border-gray-200">
              <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                <Layers className="w-4 h-4" />
                成本明细
              </h3>
            </div>
            <div className="p-5">
              <div className="grid grid-cols-3 gap-4">
                {/* Total Fees */}
                <div className="text-center p-4 bg-orange-50 rounded-lg border border-orange-100">
                  <p className="text-xs text-orange-600 font-medium mb-1">总手续费</p>
                  <p className="text-lg font-bold text-orange-900">
                    {formatCurrency(report.total_fees_paid)}
                  </p>
                </div>

                {/* Total Slippage */}
                <div className="text-center p-4 bg-yellow-50 rounded-lg border border-yellow-100">
                  <p className="text-xs text-yellow-600 font-medium mb-1">总滑点成本</p>
                  <p className="text-lg font-bold text-yellow-900">
                    {formatCurrency(report.total_slippage_cost)}
                  </p>
                </div>

                {/* Total Funding Cost (BT-2) */}
                <div className={cn(
                  'text-center p-4 rounded-lg border',
                  parseFloat(report.total_funding_cost) >= 0
                    ? 'bg-red-50 border-red-100'
                    : 'bg-green-50 border-green-100'
                )}>
                  <p className={cn(
                    'text-xs font-medium mb-1',
                    parseFloat(report.total_funding_cost) >= 0
                      ? 'text-red-600'
                      : 'text-green-600'
                  )}>
                    总资金费用
                  </p>
                  <p className={cn(
                    'text-lg font-bold',
                    parseFloat(report.total_funding_cost) >= 0
                      ? 'text-red-900'
                      : 'text-green-900'
                  )}>
                    {parseFloat(report.total_funding_cost) >= 0 ? '+' : ''}
                    {formatCurrency(report.total_funding_cost)}
                  </p>
                  <p className={cn(
                    'text-xs mt-1',
                    parseFloat(report.total_funding_cost) >= 0
                      ? 'text-red-500'
                      : 'text-green-500'
                  )}>
                    {parseFloat(report.total_funding_cost) >= 0 ? '支付' : '收取'}
                  </p>
                </div>
              </div>

              {/* Net PnL Calculation */}
              <div className="mt-4 pt-4 border-t border-gray-200">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-gray-600">净盈亏计算</span>
                  <span className="text-sm text-gray-500">
                    总盈亏 - 手续费 - 滑点 - 资金费用
                  </span>
                </div>
                <p className={cn(
                  'text-xl font-bold mt-2 text-center',
                  getPositiveNegativeColor(report.total_pnl)
                )}>
                  {formatCurrency(report.total_pnl, true)}
                </p>
              </div>
            </div>
          </div>

          {/* Balance Info */}
          <div className="grid grid-cols-2 gap-4 mb-6">
            <div className="p-4 bg-gray-50 rounded-xl border border-gray-200">
              <p className="text-sm text-gray-600 mb-1">初始资金</p>
              <p className="text-xl font-bold text-gray-900">
                {formatCurrency(report.initial_balance)}
              </p>
            </div>
            <div className="p-4 bg-gray-50 rounded-xl border border-gray-200">
              <p className="text-sm text-gray-600 mb-1">最终余额</p>
              <p className={cn(
                'text-xl font-bold',
                parseFloat(report.final_balance) >= parseFloat(report.initial_balance)
                  ? 'text-green-600'
                  : 'text-red-600'
              )}>
                {formatCurrency(report.final_balance)}
              </p>
            </div>
          </div>

          {/* Trade Statistics */}
          <div className="mb-6">
            <h3 className="text-sm font-semibold text-gray-700 mb-3">交易统计</h3>
            <div className="grid grid-cols-4 gap-3">
              <div className="text-center p-3 bg-gray-50 rounded-lg border border-gray-200">
                <p className="text-xs text-gray-500 mb-1">总交易次数</p>
                <p className="text-lg font-bold text-gray-900">{report.total_trades}</p>
              </div>
              <div className="text-center p-3 bg-green-50 rounded-lg border border-green-200">
                <p className="text-xs text-green-600 mb-1">盈利交易</p>
                <p className="text-lg font-bold text-green-900">{report.winning_trades}</p>
              </div>
              <div className="text-center p-3 bg-red-50 rounded-lg border border-red-200">
                <p className="text-xs text-red-600 mb-1">亏损交易</p>
                <p className="text-lg font-bold text-red-900">{report.losing_trades}</p>
              </div>
              <div className="text-center p-3 bg-blue-50 rounded-lg border border-blue-200">
                <p className="text-xs text-blue-600 mb-1">盈亏比</p>
                <p className="text-lg font-bold text-blue-900">
                  {report.winning_trades > 0 && report.losing_trades > 0
                    ? (report.winning_trades / report.losing_trades).toFixed(2)
                    : 'N/A'}
                </p>
              </div>
            </div>
          </div>

          {/* Positions Summary */}
          {report.positions && report.positions.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-gray-700 mb-3">仓位历史（前 10 笔）</h3>
              <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-4 py-3 text-left font-medium text-gray-600">方向</th>
                        <th className="px-4 py-3 text-left font-medium text-gray-600">开仓价</th>
                        <th className="px-4 py-3 text-left font-medium text-gray-600">平仓价</th>
                        <th className="px-4 py-3 text-left font-medium text-gray-600">开仓时间</th>
                        <th className="px-4 py-3 text-left font-medium text-gray-600">平仓原因</th>
                        <th className="px-4 py-3 text-right font-medium text-gray-600">盈亏</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {report.positions.slice(0, 10).map((position, index) => (
                        <tr key={position.position_id} className="hover:bg-gray-50">
                          <td className="px-4 py-3">
                            {position.direction === 'LONG' ? (
                              <span className="px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-700 flex items-center gap-1 w-fit">
                                <TrendingUp className="w-3 h-3" />
                                做多
                              </span>
                            ) : (
                              <span className="px-2 py-1 rounded-full text-xs font-medium bg-red-100 text-red-700 flex items-center gap-1 w-fit">
                                <TrendingDown className="w-3 h-3" />
                                做空
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-gray-600 text-xs">
                            ${parseFloat(position.entry_price).toFixed(2)}
                          </td>
                          <td className="px-4 py-3 text-gray-600 text-xs">
                            {position.exit_price ? `$${parseFloat(position.exit_price).toFixed(2)}` : '未平仓'}
                          </td>
                          <td className="px-4 py-3 text-gray-500 text-xs">
                            {formatDate(position.entry_time)}
                          </td>
                          <td className="px-4 py-3 text-gray-500 text-xs">
                            {position.exit_reason || '-'}
                          </td>
                          <td className={cn(
                            'px-4 py-3 text-right font-medium text-xs',
                            parseFloat(position.realized_pnl) >= 0 ? 'text-green-600' : 'text-red-600'
                          )}>
                            {formatCurrency(position.realized_pnl, true)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              {report.positions.length > 10 && (
                <p className="text-sm text-gray-500 mt-2 text-center">
                  共 {report.positions.length} 笔交易，仅显示前 10 笔
                </p>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-200 bg-gray-50 flex justify-end">
          <button
            onClick={onClose}
            className="px-6 py-2 bg-white border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
