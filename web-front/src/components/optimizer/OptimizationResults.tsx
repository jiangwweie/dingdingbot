/**
 * OptimizationResults.tsx
 *
 * 优化结果可视化组件
 * 展示参数重要性、优化路径、平行坐标图等
 */

import React, { useMemo } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  ScatterChart,
  Scatter,
  ZAxis,
  Legend,
} from 'recharts';
import {
  Trophy,
  TrendingUp,
  BarChart3,
  Download,
  Copy,
  CheckCircle,
} from 'lucide-react';
import type {
  OptimizationResults as OptimizationResultsType,
  OptimizationHistoryPoint,
  ParameterImportance,
  ParallelCoordinatePoint,
} from '../../lib/api';

// ============================================================
// 最佳参数卡片
// ============================================================

interface BestParamsCardProps {
  results: OptimizationResultsType;
  onApply: (params: Record<string, any>) => void;
  onCopy: () => void;
}

export const BestParamsCard: React.FC<BestParamsCardProps> = ({
  results,
  onApply,
  onCopy,
}) => {
  const { best_trial } = results;

  return (
    <div className="bg-gradient-to-br from-yellow-50 to-orange-50 dark:from-yellow-900/20 dark:to-orange-900/20 border-2 border-yellow-300 dark:border-yellow-700 rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <Trophy className="w-8 h-8 text-yellow-600 dark:text-yellow-400" />
          <div>
            <h3 className="text-lg font-bold text-yellow-800 dark:text-yellow-300">
              最佳参数
            </h3>
            <p className="text-sm text-yellow-600 dark:text-yellow-400">
              Trial #{best_trial.trial_number}
            </p>
          </div>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold text-yellow-700 dark:text-yellow-300">
            {best_trial.objective_value.toFixed(4)}
          </div>
          <div className="text-xs text-yellow-600 dark:text-yellow-400">
            目标函数值
          </div>
        </div>
      </div>

      {/* 指标网格 */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-4">
        <MetricBox
          label="总收益"
          value={`${(best_trial.metrics.total_return * 100).toFixed(2)}%`}
        />
        <MetricBox
          label="夏普比率"
          value={best_trial.metrics.sharpe_ratio.toFixed(2)}
        />
        <MetricBox
          label="索提诺比率"
          value={best_trial.metrics.sortino_ratio.toFixed(2)}
        />
        <MetricBox
          label="最大回撤"
          value={`${(best_trial.metrics.max_drawdown * 100).toFixed(2)}%`}
        />
        <MetricBox
          label="胜率"
          value={`${(best_trial.metrics.win_rate * 100).toFixed(1)}%`}
        />
        <MetricBox
          label="交易次数"
          value={best_trial.metrics.total_trades.toString()}
        />
      </div>

      {/* 参数列表 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg p-4 mb-4">
        <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
          参数详情
        </h4>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {Object.entries(best_trial.params).map(([key, value]) => (
            <div
              key={key}
              className="flex justify-between items-center py-2 px-3 bg-gray-50 dark:bg-gray-700 rounded"
            >
              <span className="text-sm text-gray-600 dark:text-gray-400">
                {key}
              </span>
              <span className="text-sm font-mono font-medium text-gray-900 dark:text-white">
                {typeof value === 'number' && value % 1 !== 0
                  ? value.toFixed(4)
                  : String(value)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* 操作按钮 */}
      <div className="flex gap-3">
        <button
          onClick={() => onApply(best_trial.params)}
          className="flex-1 px-4 py-2 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors"
        >
          应用到策略
        </button>
        <button
          onClick={onCopy}
          className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 font-medium rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors flex items-center gap-2"
        >
          <Copy className="w-4 h-4" />
          复制
        </button>
        <button
          onClick={() => {
            const data = JSON.stringify(best_trial.params, null, 2);
            const blob = new Blob([data], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `best-params-${results.optimization_id}.json`;
            a.click();
          }}
          className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 font-medium rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors flex items-center gap-2"
        >
          <Download className="w-4 h-4" />
          下载
        </button>
      </div>
    </div>
  );
};

const MetricBox: React.FC<{ label: string; value: string }> = ({
  label,
  value,
}) => (
  <div className="text-center p-2 bg-white dark:bg-gray-800 rounded-lg">
    <div className="text-xs text-gray-500 dark:text-gray-400">{label}</div>
    <div className="text-lg font-bold text-gray-900 dark:text-white">
      {value}
    </div>
  </div>
);

// ============================================================
// 优化路径图（目标函数值变化）
// ============================================================

interface OptimizationPathChartProps {
  results: OptimizationResultsType;
}

export const OptimizationPathChart: React.FC<OptimizationPathChartProps> = ({
  results,
}) => {
  const data = useMemo(() => {
    let bestSoFar = -Infinity;
    return results.trials
      .filter((t) => t.objective_value !== null)
      .map((trial) => {
        if (trial.objective_value !== null) {
          bestSoFar = Math.max(bestSoFar, trial.objective_value);
        }
        return {
          trial: trial.trial_number,
          value: trial.objective_value,
          best: bestSoFar,
        };
      });
  }, [results]);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
      <div className="flex items-center gap-2 mb-4">
        <TrendingUp className="w-5 h-5 text-blue-600" />
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
          优化路径（目标函数值变化）
        </h3>
      </div>

      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
            <XAxis
              dataKey="trial"
              label={{ value: 'Trial', position: 'insideBottom', offset: -5 }}
              stroke="#6B7280"
            />
            <YAxis stroke="#6B7280" />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1F2937',
                border: 'none',
                borderRadius: '8px',
                color: '#F9FAFB',
              }}
            />
            <Legend />
            <Line
              type="monotone"
              dataKey="value"
              stroke="#3B82F6"
              strokeWidth={2}
              dot={false}
              name="当前值"
            />
            <Line
              type="monotone"
              dataKey="best"
              stroke="#10B981"
              strokeWidth={2}
              dot={false}
              name="最优值"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

// ============================================================
// 参数重要性图
// ============================================================

interface ParameterImportanceChartProps {
  results: OptimizationResultsType;
}

export const ParameterImportanceChart: React.FC<ParameterImportanceChartProps> =
  ({ results }) => {
    const data = useMemo(() => {
      if (!results.importance) return [];

      return Object.entries(results.importance)
        .map(([param, importance]) => ({
          name: param.length > 20 ? param.slice(0, 20) + '...' : param,
          fullName: param,
          importance: Number(importance) * 100,
        }))
        .sort((a, b) => b.importance - a.importance);
    }, [results]);

    if (data.length === 0) {
      return (
        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
          <div className="text-center text-gray-500 dark:text-gray-400 py-8">
            暂无参数重要性数据
          </div>
        </div>
      );
    }

    return (
      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-2 mb-4">
          <BarChart3 className="w-5 h-5 text-purple-600" />
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            参数重要性排名
          </h3>
        </div>

        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
              <XAxis
                type="number"
                domain={[0, 100]}
                label={{ value: '重要性 (%)', position: 'insideBottom', offset: -5 }}
                stroke="#6B7280"
              />
              <YAxis
                type="category"
                dataKey="name"
                width={120}
                stroke="#6B7280"
                tick={{ fontSize: 12 }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1F2937',
                  border: 'none',
                  borderRadius: '8px',
                  color: '#F9FAFB',
                }}
                formatter={(value: number) => [`${value.toFixed(2)}%`, '重要性']}
                labelFormatter={(label) => data.find((d) => d.name === label)?.fullName || label}
              />
              <Bar dataKey="importance" fill="#8B5CF6" name="重要性" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  };

// ============================================================
// 平行坐标图（简化版 - 使用散点图矩阵替代）
// ============================================================

interface ParallelCoordinatesChartProps {
  results: OptimizationResultsType;
  selectedParams: string[];
}

export const ParallelCoordinatesChart: React.FC<ParallelCoordinatesChartProps> =
  ({ results, selectedParams }) => {
    const data = useMemo(() => {
      return results.trials
        .filter((t) => t.state === 'COMPLETE' && t.objective_value !== null)
        .map((trial) => ({
          trial: trial.trial_number,
          value: trial.objective_value as number,
          ...Object.fromEntries(
            selectedParams.map((key) => [
              key,
              trial.params[key] ?? 0,
            ])
          ),
        }));
    }, [results, selectedParams]);

    if (selectedParams.length === 0) {
      return (
        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
          <div className="text-center text-gray-500 dark:text-gray-400 py-8">
            请选择要展示的参数
          </div>
        </div>
      );
    }

    // 简化版：展示参数与目标值的关系散点图
    return (
      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp className="w-5 h-5 text-green-600" />
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            参数 - 性能关系（散点图）
          </h3>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {selectedParams.slice(0, 4).map((param) => (
            <div key={param} className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                  <XAxis
                    type="number"
                    dataKey={param}
                    name={param}
                    stroke="#6B7280"
                    tick={{ fontSize: 10 }}
                  />
                  <YAxis
                    type="number"
                    dataKey="value"
                    name="目标值"
                    stroke="#6B7280"
                  />
                  <Tooltip
                    cursor={{ strokeDasharray: '3 3' }}
                    contentStyle={{
                      backgroundColor: '#1F2937',
                      border: 'none',
                      borderRadius: '8px',
                      color: '#F9FAFB',
                    }}
                  />
                  <Scatter
                    data={data}
                    fill="#3B82F6"
                    name="试验"
                  />
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          ))}
        </div>
      </div>
    );
  };

// ============================================================
// Top N 试验表格
// ============================================================

interface TopTrialsTableProps {
  results: OptimizationResultsType;
  limit?: number;
}

export const TopTrialsTable: React.FC<TopTrialsTableProps> = ({
  results,
  limit = 10,
}) => {
  const topTrials = useMemo(() => {
    return [...results.top_trials]
      .sort((a, b) => b.objective_value - a.objective_value)
      .slice(0, limit);
  }, [results, limit]);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
          Top {limit} 试验
        </h3>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-gray-50 dark:bg-gray-700">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                排名
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                Trial #
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                目标值
              </th>
              {Object.keys(topTrials[0]?.params || {})
                .slice(0, 5)
                .map((key) => (
                  <th
                    key={key}
                    className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase"
                  >
                    {key}
                  </th>
                ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
            {topTrials.map((trial, index) => (
              <tr
                key={trial.trial_number}
                className={
                  index === 0
                    ? 'bg-yellow-50 dark:bg-yellow-900/10'
                    : 'hover:bg-gray-50 dark:hover:bg-gray-700'
                }
              >
                <td className="px-4 py-3">
                  {index === 0 ? (
                    <Trophy className="w-5 h-5 text-yellow-600" />
                  ) : (
                    <span className="text-gray-500">#{index + 1}</span>
                  )}
                </td>
                <td className="px-4 py-3 text-sm text-gray-900 dark:text-white">
                  {trial.trial_number}
                </td>
                <td className="px-4 py-3 text-sm font-medium text-blue-600 dark:text-blue-400">
                  {trial.objective_value.toFixed(4)}
                </td>
                {Object.entries(trial.params)
                  .slice(0, 5)
                  .map(([key, value]) => (
                    <td
                      key={key}
                      className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400 font-mono"
                    >
                      {typeof value === 'number' && value % 1 !== 0
                        ? value.toFixed(4)
                        : String(value)}
                    </td>
                  ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// ============================================================
// 主组件：优化结果展示
// ============================================================

interface OptimizationResultsProps {
  results: OptimizationResultsType;
  onApplyParams?: (params: Record<string, any>) => void;
}

export const OptimizationResults: React.FC<OptimizationResultsProps> = ({
  results,
  onApplyParams,
}) => {
  const [copied, setCopied] = React.useState(false);
  const [selectedParams, setSelectedParams] = React.useState<string[]>(() => {
    if (results.best_trial?.params) {
      return Object.keys(results.best_trial.params).slice(0, 3);
    }
    return [];
  });

  const handleCopy = () => {
    navigator.clipboard.writeText(JSON.stringify(results.best_trial.params, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const paramKeys = results.best_trial
    ? Object.keys(results.best_trial.params)
    : [];

  return (
    <div className="space-y-6">
      {/* 最佳参数卡片 */}
      <BestParamsCard
        results={results}
        onApply={onApplyParams || (() => {})}
        onCopy={handleCopy}
      />

      {copied && (
        <div className="fixed top-4 right-4 bg-green-600 text-white px-4 py-2 rounded-lg shadow-lg flex items-center gap-2 animate-pulse">
          <CheckCircle className="w-4 h-4" />
          已复制到剪贴板
        </div>
      )}

      {/* 优化路径图 */}
      <OptimizationPathChart results={results} />

      {/* 参数重要性图 */}
      <ParameterImportanceChart results={results} />

      {/* 平行坐标图 */}
      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            参数选择器
          </h3>
          <div className="flex gap-2 flex-wrap">
            {paramKeys.map((key) => (
              <button
                key={key}
                onClick={() =>
                  setSelectedParams((prev) =>
                    prev.includes(key)
                      ? prev.filter((p) => p !== key)
                      : [...prev, key]
                  )
                }
                className={`px-3 py-1 text-xs rounded-full transition-colors ${
                  selectedParams.includes(key)
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                }`}
              >
                {key}
              </button>
            ))}
          </div>
        </div>
        <ParallelCoordinatesChart results={results} selectedParams={selectedParams} />
      </div>

      {/* Top N 试验表格 */}
      <TopTrialsTable results={results} limit={10} />
    </div>
  );
};

export default OptimizationResults;
