import { useState, useCallback } from 'react';
import { Settings, Download, Upload, Clock, ChevronRight, Sliders } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useApi, exportConfig, rollbackToSnapshot, updateConfig } from '../lib/api';
import ExportButton from '../components/config/ExportButton';
import ImportDialog from '../components/config/ImportDialog';
import SnapshotList from '../components/config/SnapshotList';
import SnapshotDetailDrawer from '../components/config/SnapshotDetailDrawer';
import StrategyParamPanel from '../components/strategy-params/StrategyParamPanel';
import { cn } from '../lib/utils';
import type { ConfigSnapshotListItem, SystemConfig, ConfigResponse } from '../lib/api';

interface ConfigManagementProps {
  onConfigChange?: () => void;
}

export default function ConfigManagement({ onConfigChange }: ConfigManagementProps) {
  const [activeTab, setActiveTab] = useState<'params' | 'system'>('params');
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [selectedSnapshot, setSelectedSnapshot] = useState<ConfigSnapshotListItem | null>(null);
  const [detailDrawerOpen, setDetailDrawerOpen] = useState(false);
  const [notification, setNotification] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);

  const { data: configData, mutate: mutateConfig } = useApi<ConfigResponse>('/api/config');

  const showNotification = (type: 'success' | 'error', message: string) => {
    setNotification({ type, message });
    setTimeout(() => setNotification(null), 3000);
  };

  const handleImportSuccess = useCallback(() => {
    mutateConfig();
    showNotification('success', '配置导入成功');
    onConfigChange?.();
  }, [mutateConfig, onConfigChange]);

  const handleRollback = async (snapshotId: number) => {
    try {
      await rollbackToSnapshot(snapshotId);
      mutateConfig();
      showNotification('success', '配置回滚成功');
      onConfigChange?.();
    } catch (err: any) {
      showNotification('error', err.message || '回滚失败');
      throw err;
    }
  };

  const handleSnapshotSelect = (snapshot: ConfigSnapshotListItem) => {
    setSelectedSnapshot(snapshot);
    setDetailDrawerOpen(true);
  };

  const handleRefresh = () => {
    // Refresh can be triggered by parent or internal state
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">配置管理</h1>
          <p className="text-sm text-gray-500 mt-1">
            管理策略参数、系统配置、导入导出、版本快照
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ExportButton />
          <button
            onClick={() => setImportDialogOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-black text-white rounded-lg font-medium hover:bg-gray-800 transition-colors"
          >
            <Upload className="w-4 h-4" />
            导入配置
          </button>
        </div>
      </div>

      {/* Notification */}
      {notification && (
        <div
          className={cn(
            'p-4 rounded-xl flex items-center gap-3',
            notification.type === 'success'
              ? 'bg-green-50 text-green-700 border border-green-200'
              : 'bg-red-50 text-red-700 border border-red-200'
          )}
        >
          {notification.type === 'success' ? (
            <div className="w-2 h-2 bg-green-500 rounded-full" />
          ) : (
            <div className="w-2 h-2 bg-red-500 rounded-full" />
          )}
          {notification.message}
        </div>
      )}

      {/* Tab Navigation */}
      <div className="flex border-b border-gray-200">
        <button
          onClick={() => setActiveTab('params')}
          className={`px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === 'params'
              ? 'text-blue-600 border-b-2 border-blue-600'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          <div className="flex items-center gap-2">
            <Sliders className="w-4 h-4" />
            策略参数
          </div>
        </button>
        <button
          onClick={() => setActiveTab('system')}
          className={`px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === 'system'
              ? 'text-blue-600 border-b-2 border-blue-600'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          <div className="flex items-center gap-2">
            <Settings className="w-4 h-4" />
            系统配置
          </div>
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === 'params' ? (
        /* 策略参数配置 */
        <StrategyParamPanel onParamsChange={() => mutateConfig()} />
      ) : (
        /* 系统配置管理 */
        <>
          {/* Current config summary */}
          {configData && (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-gray-100 rounded-lg">
                    <Settings className="w-6 h-6 text-gray-600" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900">当前配置</h3>
                    <p className="text-xs text-gray-500 mt-0.5">
                      最后更新：{new Date(configData.created_at).toLocaleString('zh-CN')}
                    </p>
                  </div>
                </div>
                <Link
                  to="/dashboard"
                  className="text-sm text-apple-blue hover:underline flex items-center gap-1"
                >
                  返回仪表盘 <ChevronRight className="w-4 h-4" />
                </Link>
              </div>

              {/* Config summary cards */}
              <div className="grid grid-cols-3 gap-4 mt-4">
                <div className="p-4 bg-gray-50 rounded-xl">
                  <p className="text-xs text-gray-500 mb-1">活跃策略</p>
                  <p className="text-xl font-semibold text-gray-900">
                    {configData.config.active_strategies?.length || 0}
                  </p>
                </div>
                <div className="p-4 bg-gray-50 rounded-xl">
                  <p className="text-xs text-gray-500 mb-1">币种数量</p>
                  <p className="text-xl font-semibold text-gray-900">
                    {configData.config.user_symbols?.length || 0}
                  </p>
                </div>
                <div className="p-4 bg-gray-50 rounded-xl">
                  <p className="text-xs text-gray-500 mb-1">最大杠杆</p>
                  <p className="text-xl font-semibold text-gray-900">
                    {configData.config.risk?.max_leverage || 0}x
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Snapshots section */}
          <div>
            <div className="flex items-center gap-2 mb-4">
              <Clock className="w-5 h-5 text-gray-500" />
              <h2 className="text-lg font-semibold text-gray-900">配置快照</h2>
            </div>
            <SnapshotList
              onSnapshotSelect={handleSnapshotSelect}
              onRefresh={handleRefresh}
            />
          </div>
        </>
      )}

      {/* Import dialog */}
      <ImportDialog
        open={importDialogOpen}
        onClose={() => setImportDialogOpen(false)}
        onSuccess={handleImportSuccess}
      />

      {/* Snapshot detail drawer */}
      <SnapshotDetailDrawer
        snapshot={selectedSnapshot}
        open={detailDrawerOpen}
        onClose={() => {
          setDetailDrawerOpen(false);
          setSelectedSnapshot(null);
        }}
        onRollback={handleRollback}
      />
    </div>
  );
}
