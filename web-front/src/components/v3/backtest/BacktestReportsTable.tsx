/**
 * Backtest Reports Table Component
 *
 * 回测报告列表表格组件
 */
import { useMemo } from 'react';
import { TrendingUp, TrendingDown, ExternalLink, Trash2 } from 'lucide-react';
import { cn } from '../../../lib/utils';
import type { BacktestReportSummary } from '../../../types/backtest';

interface BacktestReportsTableProps {
  reports: BacktestReportSummary[];
  onViewDetails: (reportId: string) => void;
  onDelete: (reportId: string) => void;
  isLoading?: boolean;
  className?: string;
}

/**
 * 回测报告表格组件
 */
export function BacktestReportsTable({
  reports,
  onViewDetails,
  onDelete,
  isLoading,
  className,
}: BacktestReportsTableProps) {
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

  // Format percentage string to display value
  const formatPercent = (value: string) => {
    const num = parseFloat(value) * 100;
    return `${num >= 0 ? '+' : ''}${num.toFixed(2)}%`;
  };

  // Format PnL string to display value
  const formatPnL = (value: string) => {
    const num = parseFloat(value);
    return `${num >= 0 ? '+' : ''}$${num.toFixed(2)}`;
  };

  // Get color class based on value
  const getReturnColor = (value: string) => {
    const num = parseFloat(value);
    if (num > 0) return 'text-green-600 bg-green-50';
    if (num < 0) return 'text-red-600 bg-red-50';
    return 'text-gray-600 bg-gray-50';
  };

  const getWinRateColor = (value: string) => {
    const num = parseFloat(value) * 100;
    if (num >= 60) return 'text-green-600 bg-green-50';
    if (num >= 40) return 'text-yellow-600 bg-yellow-50';
    return 'text-red-600 bg-red-50';
  };

  if (isLoading) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
        <div className="w-6 h-6 border-2 border-gray-300 border-t-black rounded-full animate-spin mx-auto" />
        <p className="mt-3 text-sm text-gray-500">加载中...</p>
      </div>
    );
  }

  if (reports.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
        <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-3">
          <TrendingUp className="w-6 h-6 text-gray-400" />
        </div>
        <h3 className="text-sm font-medium text-gray-900">暂无回测报告</h3>
        <p className="mt-1 text-sm text-gray-500">
          配置策略并执行回测后，回测报告将显示在此处
        </p>
      </div>
    );
  }

  return (
    <div className={cn('bg-white rounded-xl border border-gray-200 overflow-hidden', className)}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="px-4 py-3 text-left font-medium text-gray-600">策略名称</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600">交易对</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600">周期</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600">回测时间</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600">收益率</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600">胜率</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600">总盈亏</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600">最大回撤</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600">交易次数</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {reports.map((report) => (
              <tr
                key={report.id}
                className="hover:bg-gray-50 transition-colors"
              >
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-gray-900">{report.strategy_name}</span>
                    <span className="text-xs text-gray-400">v{report.strategy_version}</span>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <span className="text-xs text-gray-700 font-mono">{report.symbol}</span>
                </td>
                <td className="px-4 py-3">
                  <span className="px-2 py-1 rounded-md bg-gray-100 text-gray-600 text-xs font-medium">
                    {report.timeframe}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-600 text-xs">
                  {formatDate(report.backtest_start)}
                </td>
                <td className="px-4 py-3">
                  <span className={cn(
                    'px-2 py-1 rounded-md text-xs font-medium',
                    getReturnColor(report.total_return)
                  )}>
                    {formatPercent(report.total_return)}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className={cn(
                    'px-2 py-1 rounded-md text-xs font-medium',
                    getWinRateColor(report.win_rate)
                  )}>
                    {formatPercent(report.win_rate)}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className={cn(
                    'text-xs font-medium',
                    parseFloat(report.total_pnl) >= 0 ? 'text-green-600' : 'text-red-600'
                  )}>
                    {formatPnL(report.total_pnl)}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-600 text-xs">
                  {formatPercent(report.max_drawdown)}
                </td>
                <td className="px-4 py-3 text-gray-600 text-xs">
                  {report.total_trades}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-2">
                    <button
                      onClick={() => onViewDetails(report.id)}
                      className="p-1.5 text-blue-600 hover:bg-blue-50 rounded transition-colors"
                      title="查看详情"
                    >
                      <ExternalLink className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => onDelete(report.id)}
                      className="p-1.5 text-red-600 hover:bg-red-50 rounded transition-colors"
                      title="删除报告"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
