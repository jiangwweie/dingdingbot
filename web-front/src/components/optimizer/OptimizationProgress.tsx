/**
 * OptimizationProgress.tsx
 *
 * 优化进度监控页面
 * 实时显示试验进度、当前最优参数和预计剩余时间
 */

import React, { useEffect, useState } from 'react';
import { Play, Pause, StopCircle, RefreshCw, Clock, Target, TrendingUp } from 'lucide-react';
import type {
  OptimizationStatus,
  OptimizationRequest,
  ParameterSpace,
  OptimizationObjective,
} from '../../lib/api';
import {
  runOptimization,
  fetchOptimizationStatus,
  stopOptimization,
} from '../../lib/api';
import { ParameterSpaceConfig, ObjectiveSelector } from './ParameterSpaceConfig';

// ============================================================
// 配置表单组件
// ============================================================

interface OptimizationConfigFormProps {
  onSubmit: (config: OptimizationRequest) => void;
  isLoading: boolean;
}

const OptimizationConfigForm: React.FC<OptimizationConfigFormProps> = ({
  onSubmit,
  isLoading,
}) => {
  const [symbol, setSymbol] = useState('BTC/USDT:USDT');
  const [timeframe, setTimeframe] = useState('15m');
  const [startTime, setStartTime] = useState<string>('');
  const [endTime, setEndTime] = useState<string>('');
  const [objective, setObjective] = useState<OptimizationObjective>('sharpe');
  const [nTrials, setNTrials] = useState(100);
  const [timeoutSeconds, setTimeoutSeconds] = useState<number | undefined>(undefined);
  const [parameterSpace, setParameterSpace] = useState<ParameterSpace>({});

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const config: OptimizationRequest = {
      symbol,
      timeframe,
      start_time: startTime ? new Date(startTime).getTime() : Date.now() - 30 * 24 * 60 * 60 * 1000,
      end_time: endTime ? new Date(endTime).getTime() : Date.now(),
      objective,
      n_trials: nTrials,
      timeout_seconds: timeoutSeconds,
      parameter_space: parameterSpace,
    };

    onSubmit(config);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* 基础配置 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            交易对
          </label>
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
          >
            <option value="BTC/USDT:USDT">BTC/USDT:USDT</option>
            <option value="ETH/USDT:USDT">ETH/USDT:USDT</option>
            <option value="SOL/USDT:USDT">SOL/USDT:USDT</option>
            <option value="BNB/USDT:USDT">BNB/USDT:USDT</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            时间周期
          </label>
          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
          >
            <option value="5m">5 分钟</option>
            <option value="15m">15 分钟</option>
            <option value="1h">1 小时</option>
            <option value="4h">4 小时</option>
            <option value="1d">1 天</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            开始时间
          </label>
          <input
            type="datetime-local"
            value={startTime}
            onChange={(e) => setStartTime(e.target.value)}
            className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            结束时间
          </label>
          <input
            type="datetime-local"
            value={endTime}
            onChange={(e) => setEndTime(e.target.value)}
            className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
          />
        </div>
      </div>

      {/* 优化目标 */}
      <ObjectiveSelector value={objective} onChange={setObjective} />

      {/* 试验次数和超时 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            试验次数
          </label>
          <input
            type="number"
            value={nTrials}
            onChange={(e) => setNTrials(parseInt(e.target.value) || 100)}
            min="1"
            max="1000"
            className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            超时时间（秒，可选）
          </label>
          <input
            type="number"
            value={timeoutSeconds || ''}
            onChange={(e) => setTimeoutSeconds(e.target.value ? parseInt(e.target.value) : undefined)}
            placeholder="3600"
            className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600"
          />
        </div>
      </div>

      {/* 参数空间配置 */}
      <div className="border-t border-gray-200 dark:border-gray-700 pt-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          参数空间配置
        </h3>
        <ParameterSpaceConfig value={parameterSpace} onChange={setParameterSpace} />
      </div>

      {/* 提交按钮 */}
      <div className="flex justify-end pt-4">
        <button
          type="submit"
          disabled={isLoading || Object.keys(parameterSpace).length === 0}
          className="px-6 py-2.5 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
        >
          <Play className="w-4 h-4" />
          启动优化
        </button>
      </div>
    </form>
  );
};

// ============================================================
// 进度显示组件
// ============================================================

interface ProgressDisplayProps {
  status: OptimizationStatus;
  onStop: () => void;
  onRefresh: () => void;
  isStopping: boolean;
}

const ProgressDisplay: React.FC<ProgressDisplayProps> = ({
  status,
  onStop,
  onRefresh,
  isStopping,
}) => {
  const { progress, current_best } = status.progress || { current_trial: 0, total_trials: 0 };
  const progressPercent = progress?.total_trials
    ? Math.round((progress.current_trial / progress.total_trials) * 100)
    : 0;

  // 格式化时间
  const formatTime = (seconds: number) => {
    if (seconds < 60) return `${Math.round(seconds)}秒`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}分${Math.round(seconds % 60)}秒`;
    return `${Math.round(seconds / 3600)}小时${Math.round((seconds % 3600) / 60)}分`;
  };

  return (
    <div className="space-y-6">
      {/* 状态栏 */}
      <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
        <div className="flex items-center gap-3">
          <div
            className={`w-3 h-3 rounded-full ${
              status.status === 'running'
                ? 'bg-green-500 animate-pulse'
                : status.status === 'completed'
                ? 'bg-blue-500'
                : status.status === 'stopped'
                ? 'bg-yellow-500'
                : 'bg-red-500'
            }`}
          />
          <span className="font-medium text-gray-900 dark:text-white">
            {status.status === 'running' && '优化进行中'}
            {status.status === 'completed' && '优化已完成'}
            {status.status === 'stopped' && '优化已停止'}
            {status.status === 'failed' && '优化失败'}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={onRefresh}
            className="p-2 text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700 rounded transition-colors"
            title="刷新状态"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          {status.status === 'running' && (
            <button
              onClick={onStop}
              disabled={isStopping}
              className="px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors flex items-center gap-2"
            >
              <StopCircle className="w-4 h-4" />
              {isStopping ? '停止中...' : '停止优化'}
            </button>
          )}
        </div>
      </div>

      {/* 进度条 */}
      {progress && (
        <div className="space-y-2">
          <div className="flex justify-between text-sm text-gray-600 dark:text-gray-400">
            <span>进度：{progress.current_trial} / {progress.total_trials}</span>
            <span>{progressPercent}%</span>
          </div>
          <div className="w-full h-3 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-600 transition-all duration-300"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          {progress.elapsed_seconds !== undefined && (
            <div className="flex justify-between text-xs text-gray-500">
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                已用：{formatTime(progress.elapsed_seconds)}
              </span>
              {progress.estimated_remaining_seconds !== undefined && (
                <span>预计剩余：{formatTime(progress.estimated_remaining_seconds)}</span>
              )}
            </div>
          )}
        </div>
      )}

      {/* 当前最优结果 */}
      {current_best && (
        <div className="p-4 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
          <div className="flex items-center gap-2 mb-3">
            <Target className="w-5 h-5 text-green-600 dark:text-green-400" />
            <span className="font-semibold text-green-800 dark:text-green-300">
              当前最优 (Trial #{current_best.trial_number})
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <div className="text-sm text-gray-600 dark:text-gray-400">目标函数值</div>
              <div className="text-2xl font-bold text-green-700 dark:text-green-300">
                {current_best.objective_value.toFixed(4)}
              </div>
            </div>

            <div>
              <div className="text-sm text-gray-600 dark:text-gray-400 mb-2">最佳参数</div>
              <div className="space-y-1">
                {Object.entries(current_best.params).slice(0, 5).map(([key, value]) => (
                  <div key={key} className="text-sm">
                    <span className="text-gray-500">{key}:</span>{' '}
                    <span className="font-mono text-gray-900 dark:text-white">
                      {typeof value === 'number' && value % 1 !== 0
                        ? value.toFixed(4)
                        : String(value)}
                    </span>
                  </div>
                ))}
                {Object.keys(current_best.params).length > 5 && (
                  <div className="text-xs text-gray-500">
                    ... 还有 {Object.keys(current_best.params).length - 5} 个参数
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 错误信息 */}
      {status.error_message && (
        <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
          <div className="flex items-start gap-3">
            <div className="text-red-600 dark:text-red-400 font-medium">错误信息</div>
            <div className="text-red-700 dark:text-red-300 text-sm">{status.error_message}</div>
          </div>
        </div>
      )}
    </div>
  );
};

// ============================================================
// 主组件
// ============================================================

interface OptimizationProgressProps {
  optimizationId?: string;
}

export const OptimizationProgress: React.FC<OptimizationProgressProps> = ({
  optimizationId: initialOptimizationId,
}) => {
  const [optimizationId, setOptimizationId] = useState<string | undefined>(
    initialOptimizationId
  );
  const [status, setStatus] = useState<OptimizationStatus | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 轮询状态
  useEffect(() => {
    if (!optimizationId) return;

    const pollStatus = async () => {
      try {
        const data = await fetchOptimizationStatus(optimizationId);
        setStatus(data);

        // 如果已完成/失败/停止，停止轮询
        if (['completed', 'failed', 'stopped'].includes(data.status)) {
          return;
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : '获取状态失败');
      }
    };

    pollStatus();
    const interval = setInterval(pollStatus, 3000); // 每 3 秒轮询一次

    return () => clearInterval(interval);
  }, [optimizationId]);

  // 启动优化
  const handleStart = async (config: OptimizationRequest) => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await runOptimization(config);
      setOptimizationId(response.optimization_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : '启动优化失败');
    } finally {
      setIsLoading(false);
    }
  };

  // 停止优化
  const handleStop = async () => {
    if (!optimizationId) return;

    setIsStopping(true);
    try {
      await stopOptimization(optimizationId);
      // 轮询会自动更新状态
    } catch (err) {
      setError(err instanceof Error ? err.message : '停止优化失败');
    } finally {
      setIsStopping(false);
    }
  };

  // 刷新状态
  const handleRefresh = async () => {
    if (!optimizationId) return;

    try {
      const data = await fetchOptimizationStatus(optimizationId);
      setStatus(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : '刷新状态失败');
    }
  };

  // 重置
  const handleReset = () => {
    setOptimizationId(undefined);
    setStatus(null);
    setError(null);
  };

  return (
    <div className="max-w-5xl mx-auto p-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-6 flex items-center gap-3">
        <TrendingUp className="w-6 h-6 text-blue-600" />
        策略参数优化
      </h1>

      {error && (
        <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
          <div className="text-red-700 dark:text-red-300">{error}</div>
        </div>
      )}

      {!optimizationId ? (
        <OptimizationConfigForm onSubmit={handleStart} isLoading={isLoading} />
      ) : status ? (
        <div className="space-y-6">
          <ProgressDisplay
            status={status}
            onStop={handleStop}
            onRefresh={handleRefresh}
            isStopping={isStopping}
          />

          {['completed', 'stopped', 'failed'].includes(status.status) && (
            <div className="flex justify-center pt-4">
              <button
                onClick={handleReset}
                className="px-6 py-2.5 bg-gray-600 text-white font-medium rounded-lg hover:bg-gray-700 transition-colors"
              >
                新建优化
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className="text-center py-12">
          <RefreshCw className="w-8 h-8 animate-spin mx-auto text-blue-600 mb-4" />
          <div className="text-gray-600 dark:text-gray-400">正在加载优化状态...</div>
        </div>
      )}
    </div>
  );
};

export default OptimizationProgress;
