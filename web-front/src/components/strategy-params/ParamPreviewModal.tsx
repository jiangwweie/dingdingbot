import React from 'react';
import { X, AlertTriangle, CheckCircle } from 'lucide-react';
import type { StrategyParamsResponse, StrategyParamsPreviewResponse } from '../../lib/api';

interface ParamPreviewModalProps {
  previewData: StrategyParamsPreviewResponse | null;
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  isLoading?: boolean;
}

/**
 * 参数变更预览对话框
 * 显示变更前后对比和警告信息
 */
export default function ParamPreviewModal({
  previewData,
  isOpen,
  onClose,
  onConfirm,
  isLoading = false,
}: ParamPreviewModalProps) {
  if (!isOpen || !previewData) return null;

  const { old_config, new_config, changes, warnings } = previewData;

  // 渲染单个参数类别的对比
  const renderParamComparison = (
    category: string,
    oldParams: Record<string, any>,
    newParams: Record<string, any>
  ) => {
    const allKeys = new Set([...Object.keys(oldParams || {}), ...Object.keys(newParams || {})]);

    return (
      <div className="mb-4">
        <h4 className="text-sm font-medium text-gray-900 capitalize mb-2">
          {category === 'pinbar' && 'Pinbar 形态'}
          {category === 'engulfing' && '吞没形态'}
          {category === 'ema' && 'EMA 趋势'}
          {category === 'mtf' && 'MTF 多周期'}
          {category === 'atr' && 'ATR 波动率'}
          {category === 'filters' && '过滤器链'}
        </h4>
        <div className="grid grid-cols-2 gap-2">
          {Array.from(allKeys).map((key) => {
            const oldValue = oldParams?.[key];
            const newValue = newParams?.[key];
            const isChanged = oldValue !== newValue;

            return (
              <div
                key={key}
                className={`p-2 rounded text-xs ${
                  isChanged
                    ? 'bg-yellow-50 border border-yellow-200'
                    : 'bg-gray-50 border border-gray-100'
                }`}
              >
                <p className="text-gray-500 mb-1">{key}</p>
                <div className="flex gap-2">
                  <span className="text-gray-400 line-through">
                    {oldValue?.toString()}
                  </span>
                  {isChanged && (
                    <span className="font-medium text-gray-900">
                      → {newValue?.toString()}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* 背景遮罩 */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* 对话框内容 */}
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[80vh] overflow-hidden">
        {/* 头部 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-blue-500 rounded-lg flex items-center justify-center">
              <CheckCircle className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-gray-900">
                参数变更预览
              </h3>
              <p className="text-xs text-gray-500">
                请在应用前仔细检查变更内容
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-lg transition"
          >
            <X className="w-5 h-5 text-gray-400" />
          </button>
        </div>

        {/* 内容区域 */}
        <div className="px-6 py-4 overflow-y-auto max-h-[60vh]">
          {/* 变更摘要 */}
          <div className="mb-6 p-4 bg-blue-50 border border-blue-100 rounded-xl">
            <p className="text-sm font-medium text-blue-900 mb-1">
              变更摘要
            </p>
            <p className="text-xs text-blue-700">
              共 {changes.length} 项参数将发生变更
            </p>
          </div>

          {/* 警告信息 */}
          {warnings.length > 0 && (
            <div className="mb-6 space-y-2">
              {warnings.map((warning, index) => (
                <div
                  key={index}
                  className="flex items-start gap-3 p-3 bg-yellow-50 border border-yellow-200 rounded-xl"
                >
                  <AlertTriangle className="w-5 h-5 text-yellow-600 flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-yellow-800">{warning}</p>
                </div>
              ))}
            </div>
          )}

          {/* 参数对比详情 */}
          <div className="space-y-4">
            {old_config && (
              <>
                {old_config.pinbar && Object.keys(old_config.pinbar).length > 0 && (
                  renderParamComparison('pinbar', old_config.pinbar, new_config.pinbar)
                )}
                {old_config.ema && Object.keys(old_config.ema).length > 0 && (
                  renderParamComparison('ema', old_config.ema, new_config.ema)
                )}
                {old_config.mtf && Object.keys(old_config.mtf).length > 0 && (
                  renderParamComparison('mtf', old_config.mtf, new_config.mtf)
                )}
                {old_config.atr && Object.keys(old_config.atr).length > 0 && (
                  renderParamComparison('atr', old_config.atr, new_config.atr)
                )}
              </>
            )}
          </div>
        </div>

        {/* 底部操作按钮 */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-100 bg-gray-50">
          <button
            onClick={onClose}
            disabled={isLoading}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition disabled:opacity-50"
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            disabled={isLoading}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-500 rounded-lg hover:bg-blue-600 transition disabled:opacity-50 flex items-center gap-2"
          >
            {isLoading ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                应用中...
              </>
            ) : (
              '确认应用'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
