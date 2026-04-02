import { Fragment, useState, useEffect } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { X, Clock, User, CheckCircle, FileText, Code, Eye } from 'lucide-react';
import { fetchSnapshotDetail, type ConfigSnapshotDetail, type ConfigSnapshotListItem } from '../../lib/api';
import { cn } from '../../lib/utils';
import { formatDistanceToNow } from 'date-fns';
import { zhCN } from 'date-fns/locale';

interface SnapshotDetailDrawerProps {
  snapshot: ConfigSnapshotListItem | null;
  open: boolean;
  onClose: () => void;
  onRollback: (id: number) => void;
}

export default function SnapshotDetailDrawer({
  snapshot,
  open,
  onClose,
  onRollback,
}: SnapshotDetailDrawerProps) {
  const [detail, setDetail] = useState<ConfigSnapshotDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showJson, setShowJson] = useState(false);
  const [rollingBack, setRollingBack] = useState(false);

  useEffect(() => {
    if (snapshot && open) {
      setLoading(true);
      setError(null);
      fetchSnapshotDetail(snapshot.id)
        .then((data) => setDetail(data))
        .catch((err: any) => setError(err.message || '获取快照详情失败'))
        .finally(() => setLoading(false));
    }
  }, [snapshot, open]);

  const handleRollback = async () => {
    if (!detail || !confirm(`确定要回滚到版本 ${detail.version} 吗？\n\n回滚后当前配置将被替换为此快照的配置。`)) {
      return;
    }

    setRollingBack(true);
    try {
      await onRollback(detail.id);
      onClose();
    } catch (err: any) {
      // Error is handled by parent component
    } finally {
      setRollingBack(false);
    }
  };

  const handleClose = () => {
    setDetail(null);
    setError(null);
    setShowJson(false);
    onClose();
  };

  const renderConfigPreview = () => {
    if (!detail) return null;

    if (showJson) {
      return (
        <pre className="text-xs font-mono text-gray-700 overflow-auto max-h-96 bg-gray-50 rounded-lg p-4">
          {JSON.stringify(detail.config, null, 2)}
        </pre>
      );
    }

    // 简化预览
    const config = detail.config;
    return (
      <div className="space-y-4">
        {/* 策略数量 */}
        <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
          <span className="text-sm text-gray-600">活跃策略</span>
          <span className="text-sm font-semibold text-gray-900">
            {config.active_strategies?.length || 0} 个
          </span>
        </div>

        {/* 风控配置 */}
        {config.risk && (
          <div className="p-3 bg-gray-50 rounded-lg space-y-2">
            <p className="text-sm font-medium text-gray-700">风控参数</p>
            <div className="flex justify-between text-xs text-gray-600">
              <span>最大亏损：{(config.risk.max_loss_percent * 100).toFixed(1)}%</span>
              <span>最大杠杆：{config.risk.max_leverage}x</span>
              <span>默认杠杆：{config.risk.default_leverage}x</span>
            </div>
          </div>
        )}

        {/* 币种列表 */}
        <div className="p-3 bg-gray-50 rounded-lg">
          <p className="text-sm font-medium text-gray-700 mb-2">币种列表</p>
          <div className="flex flex-wrap gap-1">
            {(config.user_symbols || []).slice(0, 10).map((symbol: string) => (
              <span
                key={symbol}
                className="px-2 py-1 bg-white border border-gray-200 rounded text-xs text-gray-700"
              >
                {symbol}
              </span>
            ))}
            {(config.user_symbols || []).length > 10 && (
              <span className="px-2 py-1 text-xs text-gray-400">
                +{config.user_symbols.length - 10} 更多
              </span>
            )}
          </div>
        </div>

        {/* 策略列表 */}
        {config.active_strategies && config.active_strategies.length > 0 && (
          <div className="p-3 bg-gray-50 rounded-lg">
            <p className="text-sm font-medium text-gray-700 mb-2">策略触发器</p>
            <div className="space-y-1">
              {config.active_strategies.map((s: any, idx: number) => (
                <div
                  key={idx}
                  className="flex items-center justify-between text-xs"
                >
                  <span className="text-gray-700">{s.name || s.trigger?.type || '未命名策略'}</span>
                  <span className="text-gray-400">
                    {s.filters?.length || 0} 个过滤器
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <Transition appear show={open} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={handleClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/25 backdrop-blur-sm" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-end">
            <Transition.Child
              as={Fragment}
              enter="transform transition ease-out duration-300"
              enterFrom="translate-x-full"
              enterTo="translate-x-0"
              leave="transform transition ease-in duration-200"
              leaveFrom="translate-x-0"
              leaveTo="translate-x-full"
            >
              <Dialog.Panel className="w-full max-w-lg bg-white shadow-2xl">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
                  <div className="flex items-center gap-3">
                    <FileText className="w-5 h-5 text-gray-500" />
                    <Dialog.Title className="text-lg font-semibold text-gray-900">
                      快照详情
                    </Dialog.Title>
                  </div>
                  <button
                    onClick={handleClose}
                    className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                  >
                    <X className="w-5 h-5 text-gray-500" />
                  </button>
                </div>

                {/* Content */}
                {loading ? (
                  <div className="p-8 text-center text-gray-400">
                    <div className="w-8 h-8 border-2 border-gray-200 border-t-black rounded-full animate-spin mx-auto mb-2" />
                    加载中...
                  </div>
                ) : error ? (
                  <div className="p-8 text-center text-red-500">{error}</div>
                ) : detail ? (
                  <div className="p-6 space-y-4 max-h-[calc(100vh-200px)] overflow-y-auto">
                    {/* Version header */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-lg font-semibold text-gray-900">
                          {detail.version}
                        </span>
                        {detail.is_active && (
                          <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-50 text-green-700 rounded text-xs font-medium">
                            <CheckCircle className="w-3 h-3" />
                            当前生效
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Description */}
                    <div className="p-3 bg-gray-50 rounded-lg">
                      <p className="text-sm text-gray-600">
                        {detail.description || '无描述'}
                      </p>
                    </div>

                    {/* Meta info */}
                    <div className="flex items-center gap-4 text-xs text-gray-400">
                      <span className="flex items-center gap-1">
                        <User className="w-3 h-3" />
                        {detail.created_by}
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {formatDistanceToNow(new Date(detail.created_at), {
                          addSuffix: true,
                          locale: zhCN,
                        })}
                      </span>
                    </div>

                    {/* Config preview toggle */}
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setShowJson(!showJson)}
                        className="inline-flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg border border-gray-200 hover:bg-gray-50 transition-colors"
                      >
                        {showJson ? <Eye className="w-4 h-4" /> : <Code className="w-4 h-4" />}
                        {showJson ? '简化视图' : 'JSON 源码'}
                      </button>
                    </div>

                    {/* Config preview */}
                    {renderConfigPreview()}
                  </div>
                ) : null}

                {/* Footer actions */}
                {detail && (
                  <div className="px-6 py-4 border-t border-gray-100 bg-gray-50 space-y-3">
                    <button
                      onClick={handleRollback}
                      disabled={detail.is_active || rollingBack}
                      className={cn(
                        'w-full py-2.5 rounded-lg font-medium transition-all',
                        detail.is_active || rollingBack
                          ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                          : 'bg-black text-white hover:bg-gray-800'
                      )}
                    >
                      {rollingBack ? '回滚中...' : detail.is_active ? '已是当前版本' : '回滚到此版本'}
                    </button>
                    <p className="text-xs text-gray-500 text-center">
                      回滚将替换当前配置，建议先导出备份
                    </p>
                  </div>
                )}
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
}
