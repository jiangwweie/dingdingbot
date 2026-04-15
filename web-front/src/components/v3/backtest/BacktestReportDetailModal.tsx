/**
 * Backtest Report Detail Modal Component
 *
 * 回测报告详情弹窗 - 展示完整的回测报告信息（BT-2 资金费用）
 */
import { useState } from 'react';
import { XCircle, TrendingUp, TrendingDown, DollarSign, Percent, Activity, Calendar, Layers, BarChart3, ChevronDown, ChevronRight, CheckCircle, XCircle as XIcon, Info } from 'lucide-react';
import { cn } from '../../../lib/utils';
import type { BacktestReportDetail, SignalAttribution, AttributionComponent } from '../../../types/backtest';

/**
 * Signal Attribution Card - 单信号归因卡片
 */
function SignalAttributionCard({
  attribution,
  index,
  isExpanded,
  onToggle,
  getComponentDisplayName,
  getComponentBarColor,
  getStatusBadge,
}: {
  attribution: SignalAttribution;
  index: number;
  isExpanded: boolean;
  onToggle: () => void;
  getComponentDisplayName: (name: string) => string;
  getComponentBarColor: (name: string) => string;
  getStatusBadge: (status: string) => React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      {/* Header - always visible */}
      <button
        onClick={onToggle}
        className="w-full px-5 py-4 flex items-center gap-3 hover:bg-gray-50 transition-colors text-left"
      >
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 text-gray-400 flex-shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 text-gray-400 flex-shrink-0" />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-gray-500">信号 #{index + 1}</span>
            <span className="text-xs text-gray-400">·</span>
            <span className="text-xs font-medium text-indigo-600">
              最终得分: {attribution.final_score.toFixed(3)}
            </span>
          </div>
          {/* Explanation text */}
          {attribution.explanation && (
            <p className="text-sm text-gray-700 mt-1 truncate">
              {attribution.explanation}
            </p>
          )}
        </div>
        {/* Percentage summary bar */}
        <div className="hidden md:flex items-center gap-1 flex-shrink-0">
          {attribution.components.slice(0, 4).map((comp, ci) => (
            <div
              key={ci}
              className={cn('h-2 rounded-full', getComponentBarColor(comp.name))}
              style={{ width: `${Math.max(comp.percentage * 0.8, 4)}px` }}
              title={`${getComponentDisplayName(comp.name)}: ${comp.percentage.toFixed(1)}%`}
            />
          ))}
        </div>
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <div className="px-5 pb-5 border-t border-gray-100">
          {/* Component detail table */}
          <div className="mt-4">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100">
                    <th className="py-2 text-left text-xs font-medium text-gray-500">组件</th>
                    <th className="py-2 text-center text-xs font-medium text-gray-500">评分</th>
                    <th className="py-2 text-center text-xs font-medium text-gray-500">权重</th>
                    <th className="py-2 text-center text-xs font-medium text-gray-500">贡献</th>
                    <th className="py-2 text-center text-xs font-medium text-gray-500">占比</th>
                    <th className="py-2 text-center text-xs font-medium text-gray-500">状态</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {attribution.components.map((comp, ci) => (
                    <tr
                      key={ci}
                      className={cn(
                        'transition-colors',
                        comp.status === 'rejected' ? 'bg-red-50/50' : ''
                      )}
                    >
                      <td className="py-3">
                        <div className="flex items-center gap-2">
                          <div
                            className={cn('w-2 h-2 rounded-full', getComponentBarColor(comp.name))}
                          />
                          <span className="font-medium text-gray-900">
                            {getComponentDisplayName(comp.name)}
                          </span>
                        </div>
                        {/* Confidence basis */}
                        {comp.confidence_basis && (
                          <p className="text-xs text-gray-500 mt-1 ml-4">
                            {comp.confidence_basis}
                          </p>
                        )}
                      </td>
                      <td className="py-3 text-center text-gray-700">
                        {comp.score.toFixed(3)}
                      </td>
                      <td className="py-3 text-center text-gray-700">
                        {(comp.weight * 100).toFixed(0)}%
                      </td>
                      <td className="py-3 text-center font-medium text-gray-900">
                        {comp.contribution.toFixed(3)}
                      </td>
                      <td className="py-3 text-center">
                        <div className="flex items-center gap-2 justify-center">
                          <div className="w-16 bg-gray-100 rounded-full h-1.5">
                            <div
                              className={cn(
                                'h-1.5 rounded-full transition-all',
                                comp.status === 'rejected'
                                  ? 'bg-red-300'
                                  : getComponentBarColor(comp.name)
                              )}
                              style={{ width: `${Math.min(comp.percentage, 100)}%` }}
                            />
                          </div>
                          <span className="text-xs text-gray-600 w-10 text-right">
                            {comp.percentage.toFixed(1)}%
                          </span>
                        </div>
                      </td>
                      <td className="py-3 text-center">
                        {getStatusBadge(comp.status)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Stacked percentage bar visualization */}
          <div className="mt-4 pt-4 border-t border-gray-100">
            <p className="text-xs text-gray-500 mb-2">贡献分布</p>
            <div className="flex rounded-full overflow-hidden h-3 bg-gray-100">
              {attribution.components
                .filter(c => c.status === 'passed')
                .map((comp, ci) => (
                  <div
                    key={ci}
                    className={cn('transition-all', getComponentBarColor(comp.name))}
                    style={{ width: `${comp.percentage}%` }}
                    title={`${getComponentDisplayName(comp.name)}: ${comp.percentage.toFixed(1)}%`}
                  />
                ))}
            </div>
            {/* Legend */}
            <div className="flex flex-wrap gap-3 mt-2">
              {attribution.components
                .filter(c => c.status === 'passed')
                .map((comp, ci) => (
                  <div key={ci} className="flex items-center gap-1.5">
                    <div
                      className={cn('w-2.5 h-2.5 rounded-full', getComponentBarColor(comp.name))}
                    />
                    <span className="text-xs text-gray-600">
                      {getComponentDisplayName(comp.name)} ({comp.percentage.toFixed(1)}%)
                    </span>
                  </div>
                ))}
              {attribution.components.some(c => c.status === 'rejected') && (
                <div className="flex items-center gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-red-300" />
                  <span className="text-xs text-gray-600">
                    已拒绝 ({attribution.components.filter(c => c.status === 'rejected').length})
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

interface BacktestReportDetailModalProps {
  report: BacktestReportDetail | null;
  onClose: () => void;
}

export default function BacktestReportDetailModal({
  report,
  onClose,
}: BacktestReportDetailModalProps) {
  const [expandedSignals, setExpandedSignals] = useState<Set<number>>(new Set());

  if (!report) return null;

  const toggleSignalExpand = (index: number) => {
    setExpandedSignals(prev => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  // Get display name for attribution component
  const getComponentDisplayName = (name: string): string => {
    const nameMap: Record<string, string> = {
      pattern: '形态',
      ema_trend: 'EMA 趋势',
      mtf: '多周期对齐',
      atr: 'ATR 波动',
      volume_surge: '成交量异动',
      volatility_filter: '波动率过滤',
    };
    return nameMap[name] || name;
  };

  // Get color for component status
  const getStatusBadge = (status: string) => {
    if (status === 'passed') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
          <CheckCircle className="w-3 h-3" />
          通过
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">
        <XIcon className="w-3 h-3" />
        拒绝
      </span>
    );
  };

  // Get progress bar color by component name
  const getComponentBarColor = (name: string): string => {
    const colorMap: Record<string, string> = {
      pattern: 'bg-indigo-500',
      ema_trend: 'bg-blue-500',
      mtf: 'bg-cyan-500',
      atr: 'bg-amber-500',
      volume_surge: 'bg-orange-500',
      volatility_filter: 'bg-pink-500',
    };
    return colorMap[name] || 'bg-gray-500';
  };

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
                  <span className="text-sm font-medium text-gray-600">净盈亏</span>
                  <span className="text-sm text-gray-500">
                    = 最终余额 - 初始资金（已含所有费用）
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

          {/* Aggregate Attribution */}
          {report.aggregate_attribution && (
            <div className="mb-6">
              <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-indigo-500" />
                归因分析摘要
              </h3>
              <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                {/* Top section: Pattern + Filter contributions */}
                <div className="p-5 border-b border-gray-100">
                  <div className="grid grid-cols-2 gap-6">
                    {/* Average Pattern Contribution */}
                    <div>
                      <p className="text-xs text-gray-500 mb-1">平均形态贡献</p>
                      <p className="text-xl font-bold text-indigo-600">
                        {report.aggregate_attribution.avg_pattern_contribution.toFixed(1)}%
                      </p>
                    </div>
                    {/* Average Filter Contributions */}
                    <div>
                      <p className="text-xs text-gray-500 mb-2">平均过滤器贡献</p>
                      <div className="space-y-2">
                        {Object.entries(report.aggregate_attribution.avg_filter_contributions).map(([key, value]) => (
                          <div key={key} className="flex items-center gap-2">
                            <span className="text-xs text-gray-600 w-24 truncate">
                              {getComponentDisplayName(key)}
                            </span>
                            <div className="flex-1 bg-gray-100 rounded-full h-2">
                              <div
                                className={cn('h-2 rounded-full transition-all', getComponentBarColor(key))}
                                style={{ width: `${Math.min(value, 100)}%` }}
                              />
                            </div>
                            <span className="text-xs font-medium text-gray-700 w-12 text-right">
                              {value.toFixed(1)}%
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Bottom section: Top/Bottom filters */}
                <div className="grid grid-cols-2 divide-x divide-gray-100">
                  {/* Top Performing */}
                  <div className="p-4">
                    <p className="text-xs font-medium text-green-600 mb-2 flex items-center gap-1">
                      <TrendingUp className="w-3 h-3" />
                      表现最佳
                    </p>
                    <div className="space-y-1">
                      {report.aggregate_attribution.top_performing_filters.length > 0 ? (
                        report.aggregate_attribution.top_performing_filters.map((filter, idx) => (
                          <span
                            key={idx}
                            className="inline-block px-2 py-0.5 mr-1 mb-1 text-xs rounded-full bg-green-50 text-green-700 border border-green-200"
                          >
                            {getComponentDisplayName(filter)}
                          </span>
                        ))
                      ) : (
                        <p className="text-xs text-gray-400">暂无数据</p>
                      )}
                    </div>
                  </div>

                  {/* Worst Performing */}
                  <div className="p-4">
                    <p className="text-xs font-medium text-red-600 mb-2 flex items-center gap-1">
                      <TrendingDown className="w-3 h-3" />
                      表现最差
                    </p>
                    <div className="space-y-1">
                      {report.aggregate_attribution.worst_performing_filters.length > 0 ? (
                        report.aggregate_attribution.worst_performing_filters.map((filter, idx) => (
                          <span
                            key={idx}
                            className="inline-block px-2 py-0.5 mr-1 mb-1 text-xs rounded-full bg-red-50 text-red-700 border border-red-200"
                          >
                            {getComponentDisplayName(filter)}
                          </span>
                        ))
                      ) : (
                        <p className="text-xs text-gray-400">暂无数据</p>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Signal Attributions */}
          {report.signal_attributions && report.signal_attributions.length > 0 && (
            <div className="mb-6">
              <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                <Info className="w-4 h-4 text-indigo-500" />
                信号归因详情
                <span className="text-xs text-gray-400 font-normal">
                  ({report.signal_attributions.length} 个信号)
                </span>
              </h3>
              <div className="space-y-3">
                {report.signal_attributions.map((attribution, index) => (
                  <SignalAttributionCard
                    key={index}
                    attribution={attribution}
                    index={index}
                    isExpanded={expandedSignals.has(index)}
                    onToggle={() => toggleSignalExpand(index)}
                    getComponentDisplayName={getComponentDisplayName}
                    getComponentBarColor={getComponentBarColor}
                    getStatusBadge={getStatusBadge}
                  />
                ))}
              </div>
            </div>
          )}

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
