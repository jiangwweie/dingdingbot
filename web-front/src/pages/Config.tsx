/**
 * 配置管理页面
 *
 * 提供完整的配置 CRUD 功能，包括：
 * - 系统信息（只读）
 * - 风控配置（可编辑）
 * - 系统配置（可编辑）
 * - 币池管理（可编辑）
 * - 通知配置（可编辑）
 * - 导入/导出功能
 */

import { useState, useCallback, useEffect } from 'react';
import { useSWRConfig } from 'swr';
import {
  Download,
  Upload,
  Save,
  RotateCcw,
  AlertCircle,
  CheckCircle,
  Plus,
  Trash2,
  X,
  FileText,
  Eye,
  Settings,
  Info,
} from 'lucide-react';
import { cn } from '../lib/utils';
import ConfigTooltip, { ConfigLabel } from '../components/ConfigTooltip';
import ConfigSection from '../components/ConfigSection';
import {
  fetchAllConfig,
  updateRiskConfig,
  updateSystemConfigV1,
  addSymbol,
  deleteSymbol,
  updateSymbol,
  addNotification,
  updateNotification,
  deleteNotification,
  exportConfig,
  previewConfigImport,
  confirmConfigImport,
  type AllConfigResponse,
  type RiskConfigV1,
  type SystemConfigV1,
  type SymbolConfigV1,
  type NotificationConfigV1,
  type ImportPreviewResponse,
} from '../lib/api';
import {
  RISK_CONFIG_DESCRIPTIONS,
  SYSTEM_CONFIG_DESCRIPTIONS,
  SYMBOL_CONFIG_DESCRIPTIONS,
  NOTIFICATION_CONFIG_DESCRIPTIONS,
} from '../lib/config-descriptions';

export default function Config() {
  const { mutate } = useSWRConfig();

  // Loading and error states
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState('');

  // Config state
  const [riskConfig, setRiskConfig] = useState<RiskConfigV1>({
    max_loss_percent: 0.01,
    max_total_exposure: 0.8,
    max_leverage: 10,
  });
  const [systemConfig, setSystemConfig] = useState<SystemConfigV1>({
    history_bars: 100,
    queue_batch_size: 10,
    queue_flush_interval: 5,
  });
  const [symbols, setSymbols] = useState<SymbolConfigV1[]>([]);
  const [notifications, setNotifications] = useState<NotificationConfigV1[]>([]);

  // Form states
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});

  // Symbol form
  const [newSymbol, setNewSymbol] = useState('');

  // Notification form
  const [newNotification, setNewNotification] = useState<{
    channel: 'feishu' | 'wecom' | 'telegram';
    webhook_url: string;
  }>({ channel: 'feishu', webhook_url: '' });

  // Import/Export states
  const [isExporting, setIsExporting] = useState(false);
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [importYaml, setImportYaml] = useState('');
  const [importPreview, setImportPreview] = useState<ImportPreviewResponse | null>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isImporting, setIsImporting] = useState(false);

  // Fetch all config on mount
  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    setIsLoading(true);
    setErrorMessage('');
    try {
      const config = await fetchAllConfig();
      setRiskConfig(config.risk);
      setSystemConfig(config.system);
      setSymbols(config.symbols);
      setNotifications(config.notifications);
    } catch (err: any) {
      setErrorMessage(err.info?.detail || '加载配置失败，请重试');
    } finally {
      setIsLoading(false);
    }
  };

  // Handle risk config change
  const handleRiskChange = useCallback(async () => {
    setIsSaving(true);
    setValidationErrors({});
    try {
      const result = await updateRiskConfig(riskConfig);
      if (!result.requires_restart) {
        setSaveSuccess(true);
        setTimeout(() => setSaveSuccess(false), 3000);
      }
    } catch (err: any) {
      setValidationErrors({ risk: err.info?.detail || '保存失败，请重试' });
    } finally {
      setIsSaving(false);
    }
  }, [riskConfig]);

  // Handle system config change
  const handleSystemChange = useCallback(async () => {
    setIsSaving(true);
    setValidationErrors({});
    try {
      const result = await updateSystemConfigV1(systemConfig);
      if (result.requires_restart) {
        setSaveSuccess(true);
        setTimeout(() => setSaveSuccess(false), 3000);
      }
    } catch (err: any) {
      setValidationErrors({ system: err.info?.detail || '保存失败，请重试' });
    } finally {
      setIsSaving(false);
    }
  }, [systemConfig]);

  // Handle add symbol
  const handleAddSymbol = useCallback(async () => {
    if (!newSymbol.trim()) return;
    try {
      const added = await addSymbol({ symbol: newSymbol.trim().toUpperCase() });
      setSymbols((prev) => [...prev, added]);
      setNewSymbol('');
    } catch (err: any) {
      alert(err.info?.detail || '添加失败，请重试');
    }
  }, [newSymbol]);

  // Handle delete symbol
  const handleDeleteSymbol = useCallback(async (id: number, symbol: string) => {
    if (!confirm(`确定要删除币种 ${symbol} 吗？`)) return;
    try {
      await deleteSymbol(id);
      setSymbols((prev) => prev.filter((s) => s.id !== id));
    } catch (err: any) {
      alert(err.info?.detail || '删除失败，请重试');
    }
  }, []);

  // Handle toggle symbol
  const handleToggleSymbol = useCallback(async (id: number, current: boolean) => {
    try {
      const updated = await updateSymbol(id, !current);
      setSymbols((prev) => prev.map((s) => (s.id === id ? updated : s)));
    } catch (err: any) {
      alert(err.info?.detail || '更新失败，请重试');
    }
  }, []);

  // Handle add notification
  const handleAddNotification = useCallback(async () => {
    if (!newNotification.webhook_url.trim()) {
      alert('请输入 Webhook URL');
      return;
    }
    try {
      const added = await addNotification(newNotification);
      setNotifications((prev) => [...prev, added]);
      setNewNotification({ channel: 'feishu', webhook_url: '' });
    } catch (err: any) {
      alert(err.info?.detail || '添加失败，请重试');
    }
  }, [newNotification]);

  // Handle update notification
  const handleUpdateNotification = useCallback(
    async (id: number, payload: { webhook_url?: string; is_enabled?: boolean }) => {
      try {
        const updated = await updateNotification(id, payload);
        setNotifications((prev) => prev.map((n) => (n.id === id ? updated : n)));
      } catch (err: any) {
        alert(err.info?.detail || '更新失败，请重试');
      }
    },
    []
  );

  // Handle delete notification
  const handleDeleteNotification = useCallback(async (id: number) => {
    if (!confirm('确定要删除此通知渠道吗？')) return;
    try {
      await deleteNotification(id);
      setNotifications((prev) => prev.filter((n) => n.id !== id));
    } catch (err: any) {
      alert(err.info?.detail || '删除失败，请重试');
    }
  }, []);

  // Handle export
  const handleExport = useCallback(async () => {
    setIsExporting(true);
    try {
      const result = await exportConfig();
      // Create download
      const blob = new Blob([result.yaml_content], { type: 'text/yaml' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `dingpangou-config-${new Date().toISOString().split('T')[0]}.yaml`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err: any) {
      alert(err.info?.detail || '导出失败，请重试');
    } finally {
      setIsExporting(false);
    }
  }, []);

  // Handle import preview
  const handlePreviewImport = useCallback(async () => {
    setIsPreviewing(true);
    try {
      const preview = await previewConfigImport(importYaml);
      setImportPreview(preview);
    } catch (err: any) {
      alert(err.info?.detail || '预览失败，请重试');
    } finally {
      setIsPreviewing(false);
    }
  }, [importYaml]);

  // Handle confirm import
  const handleConfirmImport = useCallback(async () => {
    if (!importPreview?.valid) return;
    setIsImporting(true);
    try {
      const result = await confirmConfigImport(importYaml);
      if (result.success) {
        alert(result.message);
        await loadConfig();
        setIsImportModalOpen(false);
        setImportYaml('');
        setImportPreview(null);
      }
    } catch (err: any) {
      alert(err.info?.detail || '导入失败，请重试');
    } finally {
      setIsImporting(false);
    }
  }, [importYaml, importPreview]);

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-12 bg-white rounded-2xl shadow-sm border border-gray-100" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-48 bg-white rounded-2xl shadow-sm border border-gray-100" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">配置管理中心</h1>
          <p className="text-sm text-gray-500 mt-1">管理风控、系统、币池和通知配置</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setIsImportModalOpen(true)}
            className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <Upload className="w-4 h-4" />
            导入配置
          </button>
          <button
            onClick={handleExport}
            disabled={isExporting}
            className="flex items-center gap-2 px-4 py-2 bg-black text-white rounded-lg hover:bg-gray-800 disabled:opacity-50 transition-colors"
          >
            <Download className="w-4 h-4" />
            {isExporting ? '导出中...' : '导出配置'}
          </button>
        </div>
      </div>

      {/* Error Banner */}
      {errorMessage && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 flex items-center gap-2">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          {errorMessage}
        </div>
      )}

      {/* Success Toast */}
      {saveSuccess && (
        <div className="fixed top-4 right-4 z-50 p-4 bg-green-50 border border-green-200 rounded-xl text-green-700 shadow-lg flex items-center gap-2 animate-in fade-in slide-in-from-top-2">
          <CheckCircle className="w-5 h-5" />
          配置已保存
        </div>
      )}

      {/* System Info Section (Read-only) */}
      <ConfigSection
        title="系统信息"
        description="当前运行的系统版本和环境信息（只读）"
        fields={[
          { key: 'version', label: '系统版本', tooltip: '当前系统版本号', type: 'readonly' },
          { key: 'env', label: '运行环境', tooltip: '生产环境/测试环境', type: 'readonly' },
        ]}
        values={{ version: 'v2.0.0', env: 'production' }}
        onChange={() => {}}
      />

      {/* Risk Config Section */}
      <ConfigSection
        title="风控配置"
        description="配置交易风险参数，控制单笔损失和总敞口"
        fields={[
          {
            key: 'max_loss_percent',
            label: RISK_CONFIG_DESCRIPTIONS.max_loss_percent.label,
            tooltip: RISK_CONFIG_DESCRIPTIONS.max_loss_percent.description,
            type: 'number',
            unit: '%',
            min: 0.1,
            max: 5.0,
            step: 0.1,
          },
          {
            key: 'max_total_exposure',
            label: RISK_CONFIG_DESCRIPTIONS.max_total_exposure.label,
            tooltip: RISK_CONFIG_DESCRIPTIONS.max_total_exposure.description,
            type: 'number',
            unit: '%',
            min: 0.5,
            max: 1.0,
            step: 0.05,
          },
          {
            key: 'max_leverage',
            label: RISK_CONFIG_DESCRIPTIONS.max_leverage.label,
            tooltip: RISK_CONFIG_DESCRIPTIONS.max_leverage.description,
            type: 'number',
            unit: 'x',
            min: 1,
            max: 125,
            step: 1,
          },
        ]}
        values={{
          max_loss_percent: (riskConfig.max_loss_percent * 100).toFixed(1),
          max_total_exposure: (riskConfig.max_total_exposure || 0.8) * 100,
          max_leverage: riskConfig.max_leverage,
        }}
        onChange={(key, value) => {
          const numValue = parseFloat(value);
          if (isNaN(numValue)) return;
          setRiskConfig((prev) => ({
            ...prev,
            [key]: key === 'max_loss_percent' || key === 'max_total_exposure'
              ? numValue / 100
              : numValue,
          }));
        }}
        errors={validationErrors}
      />
      <div className="flex justify-end">
        <button
          onClick={handleRiskChange}
          disabled={isSaving}
          className="flex items-center gap-2 px-4 py-2 bg-black text-white rounded-lg hover:bg-gray-800 disabled:opacity-50 transition-colors"
        >
          <Save className="w-4 h-4" />
          {isSaving ? '保存中...' : '保存风控配置'}
        </button>
      </div>

      {/* System Config Section */}
      <ConfigSection
        title="系统配置"
        description="配置系统运行参数，修改后需要重启系统"
        fields={[
          {
            key: 'history_bars',
            label: SYSTEM_CONFIG_DESCRIPTIONS.history_bars.label,
            tooltip: SYSTEM_CONFIG_DESCRIPTIONS.history_bars.description,
            type: 'number',
            min: 50,
            max: 500,
            step: 10,
            requires_restart: true,
          },
          {
            key: 'queue_batch_size',
            label: SYSTEM_CONFIG_DESCRIPTIONS.queue_batch_size.label,
            tooltip: SYSTEM_CONFIG_DESCRIPTIONS.queue_batch_size.description,
            type: 'number',
            min: 1,
            max: 100,
            step: 1,
            requires_restart: true,
          },
          {
            key: 'queue_flush_interval',
            label: SYSTEM_CONFIG_DESCRIPTIONS.queue_flush_interval.label,
            tooltip: SYSTEM_CONFIG_DESCRIPTIONS.queue_flush_interval.description,
            type: 'number',
            unit: '秒',
            min: 1,
            max: 60,
            step: 1,
            requires_restart: true,
          },
        ]}
        values={systemConfig}
        onChange={(key, value) => {
          setSystemConfig((prev) => ({ ...prev, [key]: parseInt(value) || 0 }));
        }}
        errors={validationErrors}
      />
      <div className="flex justify-end">
        <button
          onClick={handleSystemChange}
          disabled={isSaving}
          className="flex items-center gap-2 px-4 py-2 bg-black text-white rounded-lg hover:bg-gray-800 disabled:opacity-50 transition-colors"
        >
          <Save className="w-4 h-4" />
          {isSaving ? '保存中...' : '保存系统配置'}
        </button>
      </div>

      {/* Symbol Management Section */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
        <div className="mb-5 pb-4 border-b border-gray-100">
          <h3 className="text-base font-semibold text-gray-900">币池管理</h3>
          <p className="text-sm text-gray-500 mt-1">管理监控的币种列表，核心币种不可删除</p>
        </div>

        {/* Add Symbol Form */}
        <div className="flex gap-2 mb-4">
          <input
            type="text"
            value={newSymbol}
            onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === 'Enter' && handleAddSymbol()}
            placeholder="BTC/USDT:USDT"
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-black transition-colors"
          />
          <button
            onClick={handleAddSymbol}
            className="flex items-center gap-2 px-4 py-2 bg-black text-white rounded-lg hover:bg-gray-800 transition-colors"
          >
            <Plus className="w-4 h-4" />
            添加币种
          </button>
        </div>

        {/* Symbol List */}
        <div className="space-y-2">
          {symbols.map((symbol) => (
            <div
              key={symbol.id}
              className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
            >
              <div className="flex items-center gap-3">
                <span className="font-mono text-sm font-medium">{symbol.symbol}</span>
                {symbol.is_core && (
                  <span className="px-2 py-0.5 bg-apple-blue/10 text-apple-blue text-xs rounded-full">
                    核心
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={symbol.is_enabled}
                    onChange={() => handleToggleSymbol(symbol.id, symbol.is_enabled)}
                    className="w-4 h-4 rounded border-gray-300 text-black focus:ring-black"
                  />
                  启用
                </label>
                {!symbol.is_core && (
                  <button
                    onClick={() => handleDeleteSymbol(symbol.id, symbol.symbol)}
                    className="p-1.5 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Notification Management Section */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
        <div className="mb-5 pb-4 border-b border-gray-100">
          <h3 className="text-base font-semibold text-gray-900">通知渠道</h3>
          <p className="text-sm text-gray-500 mt-1">配置交易信号通知推送渠道</p>
        </div>

        {/* Add Notification Form */}
        <div className="flex gap-2 mb-4">
          <select
            value={newNotification.channel}
            onChange={(e) =>
              setNewNotification((prev) => ({ ...prev, channel: e.target.value as any }))
            }
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-black transition-colors"
          >
            <option value="feishu">飞书</option>
            <option value="wecom">企业微信</option>
            <option value="telegram">Telegram</option>
          </select>
          <input
            type="text"
            value={newNotification.webhook_url}
            onChange={(e) =>
              setNewNotification((prev) => ({ ...prev, webhook_url: e.target.value }))
            }
            placeholder="https://webhook URL"
            onKeyDown={(e) => e.key === 'Enter' && handleAddNotification()}
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-black transition-colors"
          />
          <button
            onClick={handleAddNotification}
            className="flex items-center gap-2 px-4 py-2 bg-black text-white rounded-lg hover:bg-gray-800 transition-colors"
          >
            <Plus className="w-4 h-4" />
            添加渠道
          </button>
        </div>

        {/* Notification List */}
        <div className="space-y-3">
          {notifications.map((notification) => (
            <div
              key={notification.id}
              className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
            >
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium">
                  {notification.channel === 'feishu'
                    ? '飞书'
                    : notification.channel === 'wecom'
                    ? '企业微信'
                    : 'Telegram'}
                </span>
                <span className="font-mono text-xs text-gray-500 max-w-xs truncate">
                  {notification.webhook_url.replace(/^(https?:\/\/[^/]{4}).*/, '$1...')}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() =>
                    handleUpdateNotification(notification.id, {
                      is_enabled: !notification.is_enabled,
                    })
                  }
                  className={cn(
                    'px-3 py-1 text-xs rounded-full transition-colors',
                    notification.is_enabled
                      ? 'bg-apple-green/10 text-apple-green'
                      : 'bg-gray-200 text-gray-500'
                  )}
                >
                  {notification.is_enabled ? '已启用' : '已停用'}
                </button>
                <button
                  onClick={() => handleDeleteNotification(notification.id)}
                  className="p-1.5 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Import Modal */}
      {isImportModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => {
              setIsImportModalOpen(false);
              setImportYaml('');
              setImportPreview(null);
            }}
          />
          <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-2xl p-6 m-4 max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-semibold">导入配置</h2>
              <button
                onClick={() => {
                  setIsImportModalOpen(false);
                  setImportYaml('');
                  setImportPreview(null);
                }}
                className="p-1 hover:bg-gray-100 rounded-lg"
              >
                <X className="w-5 h-5 text-gray-500" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  YAML 配置内容
                </label>
                <textarea
                  value={importYaml}
                  onChange={(e) => setImportYaml(e.target.value)}
                  placeholder="粘贴 YAML 格式的配置内容..."
                  rows={12}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 font-mono text-sm outline-none focus:border-black transition-colors"
                />
              </div>

              {importPreview && (
                <div className="p-4 bg-gray-50 rounded-lg">
                  <h4 className="text-sm font-semibold text-gray-700 mb-2">预览结果</h4>
                  {importPreview.valid ? (
                    <div className="text-sm text-green-700 flex items-center gap-2">
                      <CheckCircle className="w-4 h-4" />
                      配置格式有效，将应用 {importPreview.changes.length} 项变更
                    </div>
                  ) : (
                    <div className="text-sm text-red-700 flex items-center gap-2">
                      <AlertCircle className="w-4 h-4" />
                      配置验证失败
                    </div>
                  )}
                  {importPreview.errors.length > 0 && (
                    <div className="mt-2 space-y-1">
                      {importPreview.errors.map((err, i) => (
                        <p key={i} className="text-xs text-red-600">
                          {err.field}: {err.message}
                        </p>
                      ))}
                    </div>
                  )}
                  {importPreview.changes.length > 0 && (
                    <div className="mt-2">
                      <p className="text-xs font-medium text-gray-600 mb-1">变更详情:</p>
                      <ul className="text-xs text-gray-600 space-y-0.5 max-h-32 overflow-y-auto">
                        {importPreview.changes.map((change, i) => (
                          <li key={i}>
                            • {change.category}.{change.field}: {change.action}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => {
                  setIsImportModalOpen(false);
                  setImportYaml('');
                  setImportPreview(null);
                }}
                className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
              >
                取消
              </button>
              <button
                onClick={handlePreviewImport}
                disabled={isPreviewing || !importYaml.trim()}
                className="flex items-center gap-2 px-4 py-2 bg-gray-200 text-gray-800 rounded-lg hover:bg-gray-300 disabled:opacity-50 transition-colors"
              >
                <Eye className="w-4 h-4" />
                {isPreviewing ? '预览中...' : '预览'}
              </button>
              <button
                onClick={handleConfirmImport}
                disabled={!importPreview?.valid || isImporting}
                className="flex items-center gap-2 px-4 py-2 bg-black text-white rounded-lg hover:bg-gray-800 disabled:opacity-50 transition-colors"
              >
                <Download className="w-4 h-4" />
                {isImporting ? '导入中...' : '确认导入'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
