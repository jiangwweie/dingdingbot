import React, { useState, useCallback, useEffect } from 'react';
import { Save, RotateCcw, Download, Upload, Eye, CheckCircle, AlertCircle } from 'lucide-react';
import PinbarParamForm from './PinbarParamForm';
import EmaParamForm from './EmaParamForm';
import FilterParamList from './FilterParamList';
import TemplateManager from './TemplateManager';
import ParamPreviewModal from './ParamPreviewModal';
import {
  getStrategyParams,
  updateStrategyParams,
  previewStrategyParams,
  exportStrategyParams,
  importStrategyParams,
  fetchStrategyParamTemplates,
  saveStrategyParamTemplate,
  loadStrategyParamTemplate,
  deleteStrategyParamTemplate,
  type StrategyParamsResponse,
  type StrategyParamsUpdateRequest,
  type FilterConfig,
  type StrategyParamTemplate,
} from '../../lib/api';

interface StrategyParamPanelProps {
  onParamsChange?: () => void;
}

/**
 * 策略参数配置主面板
 * 集成所有参数表单组件，提供保存/重置/导入导出操作
 */
export default function StrategyParamPanel({ onParamsChange }: StrategyParamPanelProps) {
  // 当前参数状态
  const [params, setParams] = useState<StrategyParamsResponse>({
    pinbar: { min_wick_ratio: 0.6, max_body_ratio: 0.3, body_position_tolerance: 0.1 },
    engulfing: {},
    ema: { period: 60 },
    mtf: {},
    atr: {},
    filters: [],
  });

  // UI 状态
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [notification, setNotification] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  // 预览对话框状态
  const [showPreview, setShowPreview] = useState(false);
  const [previewData, setPreviewData] = useState<any>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);

  // 模板列表
  const [templates, setTemplates] = useState<StrategyParamTemplate[]>([]);
  const [isTemplateLoading, setIsTemplateLoading] = useState(false);

  // 加载参数
  const loadParams = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await getStrategyParams();
      setParams(data);
      setHasUnsavedChanges(false);
    } catch (error: any) {
      showNotification('error', error.message || '加载参数失败');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // 加载模板列表
  const loadTemplates = useCallback(async () => {
    try {
      const data = await fetchStrategyParamTemplates();
      setTemplates(data);
    } catch (error) {
      console.error('Failed to load templates:', error);
    }
  }, []);

  useEffect(() => {
    loadParams();
    loadTemplates();
  }, [loadParams, loadTemplates]);

  // 显示通知
  const showNotification = (type: 'success' | 'error', message: string) => {
    setNotification({ type, message });
    setTimeout(() => setNotification(null), 3000);
  };

  // 参数变更处理
  const handlePinbarChange = useCallback((newParams: Record<string, any>) => {
    setParams((prev) => ({ ...prev, pinbar: newParams }));
    setHasUnsavedChanges(true);
  }, []);

  const handleEmaChange = useCallback((update: { ema?: Record<string, any>; mtf?: Record<string, any> }) => {
    setParams((prev) => ({
      ...prev,
      ema: update.ema ? { ...prev.ema, ...update.ema } : prev.ema,
      mtf: update.mtf ? { ...prev.mtf, ...update.mtf } : prev.mtf,
    }));
    setHasUnsavedChanges(true);
  }, []);

  const handleFiltersChange = useCallback((newFilters: FilterConfig[]) => {
    setParams((prev) => ({ ...prev, filters: newFilters }));
    setHasUnsavedChanges(true);
  }, []);

  // 保存参数
  const handleSave = async () => {
    setIsPreviewLoading(true);
    setShowPreview(true);

    try {
      // 构建更新请求（只包含已修改的字段）
      const updateRequest: StrategyParamsUpdateRequest = {};

      if (params.pinbar && Object.keys(params.pinbar).length > 0) {
        updateRequest.pinbar = params.pinbar;
      }
      if (params.ema && Object.keys(params.ema).length > 0) {
        updateRequest.ema = params.ema;
      }
      if (params.mtf && Object.keys(params.mtf).length > 0) {
        updateRequest.mtf = params.mtf;
      }
      if (params.atr && Object.keys(params.atr).length > 0) {
        updateRequest.atr = params.atr;
      }
      if (params.filters !== undefined) {
        updateRequest.filters = params.filters;
      }

      // 获取预览数据
      const preview = await previewStrategyParams(updateRequest);
      setPreviewData(preview);
    } catch (error: any) {
      showNotification('error', error.message || '获取预览失败');
      setShowPreview(false);
    } finally {
      setIsPreviewLoading(false);
    }
  };

  // 确认应用参数
  const handlePreviewConfirm = async () => {
    setIsSaving(true);
    try {
      const updateRequest: StrategyParamsUpdateRequest = {};

      if (params.pinbar && Object.keys(params.pinbar).length > 0) {
        updateRequest.pinbar = params.pinbar;
      }
      if (params.ema && Object.keys(params.ema).length > 0) {
        updateRequest.ema = params.ema;
      }
      if (params.mtf && Object.keys(params.mtf).length > 0) {
        updateRequest.mtf = params.mtf;
      }
      if (params.atr && Object.keys(params.atr).length > 0) {
        updateRequest.atr = params.atr;
      }
      if (params.filters !== undefined) {
        updateRequest.filters = params.filters;
      }

      await updateStrategyParams(updateRequest);
      setHasUnsavedChanges(false);
      showNotification('success', '参数保存成功');
      setShowPreview(false);
      onParamsChange?.();
    } catch (error: any) {
      showNotification('error', error.message || '保存失败');
    } finally {
      setIsSaving(false);
    }
  };

  // 重置参数
  const handleReset = () => {
    if (window.confirm('确定要重置为当前保存的参数吗？未保存的更改将丢失。')) {
      loadParams();
    }
  };

  // 导出参数
  const handleExport = async () => {
    try {
      const blob = await exportStrategyParams();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `strategy-params-${new Date().toISOString().split('T')[0]}.yaml`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      showNotification('success', '参数导出成功');
    } catch (error: any) {
      showNotification('error', error.message || '导出失败');
    }
  };

  // 导入参数
  const handleImport = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      const result = await importStrategyParams(file, '手动导入');
      setParams(result);
      setHasUnsavedChanges(true);
      showNotification('success', '参数导入成功');
    } catch (error: any) {
      showNotification('error', error.message || '导入失败');
    }

    // 重置 input 以允许重复导入同一文件
    event.target.value = '';
  };

  // 保存为模板
  const handleSaveTemplate = async (name: string, description?: string) => {
    setIsTemplateLoading(true);
    try {
      await saveStrategyParamTemplate(name, description);
      await loadTemplates();
      showNotification('success', '模板保存成功');
    } catch (error: any) {
      showNotification('error', error.message || '保存模板失败');
    } finally {
      setIsTemplateLoading(false);
    }
  };

  // 加载模板
  const handleLoadTemplate = async (templateId: number) => {
    setIsTemplateLoading(true);
    try {
      const result = await loadStrategyParamTemplate(templateId);
      setParams(result);
      setHasUnsavedChanges(true);
      showNotification('success', '模板加载成功');
    } catch (error: any) {
      showNotification('error', error.message || '加载模板失败');
    } finally {
      setIsTemplateLoading(false);
    }
  };

  // 删除模板
  const handleDeleteTemplate = async (templateId: number) => {
    try {
      await deleteStrategyParamTemplate(templateId);
      await loadTemplates();
      showNotification('success', '模板删除成功');
    } catch (error: any) {
      showNotification('error', error.message || '删除模板失败');
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-12">
        <div className="w-8 h-8 border-4 border-gray-200 border-t-gray-500 rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 通知提示 */}
      {notification && (
        <div
          className={`p-4 rounded-xl flex items-center gap-3 ${
            notification.type === 'success'
              ? 'bg-green-50 text-green-700 border border-green-200'
              : 'bg-red-50 text-red-700 border border-red-200'
          }`}
        >
          {notification.type === 'success' ? (
            <CheckCircle className="w-5 h-5" />
          ) : (
            <AlertCircle className="w-5 h-5" />
          )}
          {notification.message}
        </div>
      )}

      {/* 操作按钮栏 */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">策略参数配置</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            配置 Pinbar 形态、EMA 趋势、MTF 验证等参数
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="inline-flex items-center gap-2 px-3 py-2 text-sm text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition cursor-pointer">
            <Upload className="w-4 h-4" />
            导入
            <input
              type="file"
              accept=".yaml,.yml"
              onChange={handleImport}
              className="hidden"
            />
          </label>
          <button
            onClick={handleExport}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition"
          >
            <Download className="w-4 h-4" />
            导出
          </button>
          <button
            onClick={handleReset}
            disabled={!hasUnsavedChanges}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition disabled:opacity-50"
          >
            <RotateCcw className="w-4 h-4" />
            重置
          </button>
          <button
            onClick={handleSave}
            disabled={!hasUnsavedChanges || isSaving}
            className={`inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white rounded-lg transition ${
              hasUnsavedChanges && !isSaving
                ? 'bg-blue-500 hover:bg-blue-600'
                : 'bg-gray-300 cursor-not-allowed'
            }`}
          >
            <Save className="w-4 h-4" />
            {isSaving ? '保存中...' : '保存'}
          </button>
        </div>
      </div>

      {/* 未保存更改提示 */}
      {hasUnsavedChanges && (
        <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-xl flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-yellow-600" />
          <p className="text-sm text-yellow-700">
            当前参数有未保存的更改，请点击"保存"按钮应用更改
          </p>
        </div>
      )}

      {/* 参数表单区域 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 左侧：Pinbar 参数 */}
        <PinbarParamForm
          params={params.pinbar as any}
          onChange={handlePinbarChange}
          disabled={isSaving}
        />

        {/* 左侧：EMA 参数 */}
        <EmaParamForm
          emaParams={params.ema as any}
          mtfParams={params.mtf as any}
          onChange={handleEmaChange}
          disabled={isSaving}
        />
      </div>

      {/* 过滤器链 */}
      <FilterParamList
        filters={params.filters as FilterConfig[]}
        onChange={handleFiltersChange}
        disabled={isSaving}
      />

      {/* 模板管理 */}
      <TemplateManager
        templates={templates}
        onLoadTemplate={handleLoadTemplate}
        onSaveTemplate={handleSaveTemplate}
        onDeleteTemplate={handleDeleteTemplate}
        isLoading={isTemplateLoading}
      />

      {/* 预览对话框 */}
      <ParamPreviewModal
        previewData={previewData}
        isOpen={showPreview}
        onClose={() => setShowPreview(false)}
        onConfirm={handlePreviewConfirm}
        isLoading={isSaving}
      />
    </div>
  );
}
