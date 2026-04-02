/**
 * OptimizationPage.tsx
 *
 * 策略参数优化页面
 * 整合参数配置、进度监控和结果可视化
 */

import React, { useState } from 'react';
import { TrendingUp, History, Settings } from 'lucide-react';
import { OptimizationProgress } from '../components/optimizer/OptimizationProgress';
import { OptimizationResults } from '../components/optimizer/OptimizationResults';
import { fetchOptimizationResults } from '../lib/api';
import type { OptimizationResults as OptimizationResultsType } from '../lib/api';

type TabType = 'progress' | 'results' | 'history';

export const OptimizationPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>('progress');
  const [currentOptimizationId, setCurrentOptimizationId] = useState<string | null>(null);
  const [completedResults, setCompletedResults] = useState<OptimizationResultsType | null>(null);

  const handleOptimizationComplete = (optimizationId: string) => {
    setCurrentOptimizationId(optimizationId);
    setActiveTab('results');
    // 加载结果
    fetchOptimizationResults(optimizationId).then(setCompletedResults);
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* 顶部导航 */}
      <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <TrendingUp className="w-6 h-6 text-blue-600" />
              <h1 className="text-xl font-bold text-gray-900 dark:text-white">
                策略参数优化
              </h1>
            </div>

            <div className="flex gap-2">
              <TabButton
                active={activeTab === 'progress'}
                onClick={() => setActiveTab('progress')}
                icon={<Settings className="w-4 h-4" />}
                label="参数配置"
              />
              <TabButton
                active={activeTab === 'results'}
                onClick={() => setActiveTab('results')}
                icon={<TrendingUp className="w-4 h-4" />}
                label="优化结果"
                disabled={!completedResults}
              />
              <TabButton
                active={activeTab === 'history'}
                onClick={() => setActiveTab('history')}
                icon={<History className="w-4 h-4" />}
                label="历史记录"
              />
            </div>
          </div>
        </div>
      </div>

      {/* 主内容区 */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activeTab === 'progress' && (
          <OptimizationProgressWrapper onComplete={handleOptimizationComplete} />
        )}

        {activeTab === 'results' && completedResults && (
          <OptimizationResults
            results={completedResults}
            onApplyParams={(params) => {
              console.log('应用参数:', params);
              // TODO: 实现参数应用到策略
            }}
          />
        )}

        {activeTab === 'history' && <OptimizationHistory />}
      </div>
    </div>
  );
};

// ============================================================
// 子组件
// ============================================================

interface TabButtonProps {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  disabled?: boolean;
}

const TabButton: React.FC<TabButtonProps> = ({
  active,
  onClick,
  icon,
  label,
  disabled,
}) => (
  <button
    onClick={onClick}
    disabled={disabled}
    className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors flex items-center gap-2 ${
      active
        ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
        : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
    } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
  >
    {icon}
    {label}
  </button>
);

interface OptimizationProgressWrapperProps {
  onComplete: (id: string) => void;
}

const OptimizationProgressWrapper: React.FC<OptimizationProgressWrapperProps> = ({
  onComplete,
}) => {
  const [optimizationId, setOptimizationId] = useState<string | undefined>();

  // 监听优化完成
  React.useEffect(() => {
    if (!optimizationId) return;

    const checkCompletion = async () => {
      try {
        const { fetchOptimizationStatus } = await import('../lib/api');
        const status = await fetchOptimizationStatus(optimizationId);

        if (['completed', 'stopped', 'failed'].includes(status.status)) {
          onComplete(optimizationId);
        }
      } catch (err) {
        console.error('检查优化状态失败:', err);
      }
    };

    const interval = setInterval(checkCompletion, 3000);
    return () => clearInterval(interval);
  }, [optimizationId, onComplete]);

  return (
    <OptimizationProgress
      optimizationId={optimizationId}
    />
  );
};

// ============================================================
// 历史记录组件
// ============================================================

const OptimizationHistory: React.FC = () => {
  const [history, setHistory] = useState<Array<{
    optimization_id: string;
    status: string;
    created_at: string;
    objective: string;
    symbol: string;
    timeframe: string;
    best_value?: number;
  }>>([]);

  React.useEffect(() => {
    // TODO: 实现历史记录 API 调用
    // fetchOptimizations().then(setHistory);
  }, []);

  if (history.length === 0) {
    return (
      <div className="text-center py-12">
        <History className="w-12 h-12 text-gray-400 mx-auto mb-4" />
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
          暂无历史记录
        </h3>
        <p className="text-gray-500 dark:text-gray-400">
          开始第一次优化后，这里会显示历史优化记录
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
          历史优化记录
        </h3>
      </div>

      <table className="w-full">
        <thead className="bg-gray-50 dark:bg-gray-700">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
              时间
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
              交易对
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
              周期
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
              优化目标
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
              状态
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
              最佳值
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
              操作
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
          {history.map((item) => (
            <tr key={item.optimization_id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
              <td className="px-4 py-3 text-sm text-gray-900 dark:text-white">
                {new Date(item.created_at).toLocaleString('zh-CN')}
              </td>
              <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                {item.symbol}
              </td>
              <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                {item.timeframe}
              </td>
              <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                {item.objective}
              </td>
              <td className="px-4 py-3">
                <StatusBadge status={item.status} />
              </td>
              <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white">
                {item.best_value?.toFixed(4) || '-'}
              </td>
              <td className="px-4 py-3">
                <button className="text-blue-600 hover:text-blue-700 text-sm font-medium">
                  查看结果
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

interface StatusBadgeProps {
  status: string;
}

const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  const styles: Record<string, string> = {
    completed: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
    running: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
    stopped: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
    failed: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  };

  const labels: Record<string, string> = {
    completed: '已完成',
    running: '进行中',
    stopped: '已停止',
    failed: '失败',
  };

  return (
    <span
      className={`px-2.5 py-0.5 text-xs font-medium rounded-full ${
        styles[status] || 'bg-gray-100 text-gray-800'
      }`}
    >
      {labels[status] || status}
    </span>
  );
};

export default OptimizationPage;
