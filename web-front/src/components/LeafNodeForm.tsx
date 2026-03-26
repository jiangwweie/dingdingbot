import React from 'react';
import { LeafNode, isTriggerLeaf, isFilterLeaf } from '../types/strategy';
import { TriggerConfig, FilterConfig } from '../lib/api';
import { Zap, Filter, Settings } from 'lucide-react';
import { cn } from '../lib/utils';

interface LeafNodeFormProps {
  node: LeafNode;
  onChange?: (node: LeafNode) => void;
  readOnly?: boolean;
  onUpdateTrigger?: (config: TriggerConfig) => void;
  onUpdateFilter?: (config: FilterConfig) => void;
}

/**
 * 叶子节点表单组件
 *
 * 根据 Trigger/Filter 类型动态渲染参数输入表单
 */
export default function LeafNodeForm({
  node,
  onChange,
  readOnly = false,
  onUpdateTrigger,
  onUpdateFilter,
}: LeafNodeFormProps) {
  const isTrigger = isTriggerLeaf(node);
  const config = node.config;

  const handleParamChange = (key: string, value: any) => {
    if (!config || !onChange) return;
    const newParams = { ...config.params, [key]: value };
    const newConfig = { ...config, params: newParams };

    if (isTrigger && onUpdateTrigger) {
      onUpdateTrigger(newConfig as TriggerConfig);
    } else if (!isTrigger && onUpdateFilter) {
      onUpdateFilter(newConfig as FilterConfig);
    }
  };

  const renderParamInputs = (params: Record<string, any>) => {
    return Object.entries(params).map(([key, value]) => (
      <div key={key} className="mb-2">
        <label className="block text-xs font-medium text-gray-600 mb-1 capitalize">
          {key.replace(/_/g, ' ')}
        </label>
        {typeof value === 'boolean' ? (
          <input
            type="checkbox"
            checked={value}
            onChange={(e) => handleParamChange(key, e.target.checked)}
            disabled={readOnly}
            className="rounded border-gray-300 text-black focus:ring-black"
          />
        ) : typeof value === 'number' ? (
          <input
            type="number"
            value={value}
            onChange={(e) => handleParamChange(key, parseFloat(e.target.value) || 0)}
            disabled={readOnly}
            step="0.01"
            className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
          />
        ) : typeof value === 'string' ? (
          <input
            type="text"
            value={value}
            onChange={(e) => handleParamChange(key, e.target.value)}
            disabled={readOnly}
            className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
          />
        ) : (
          <input
            type="text"
            value={String(value)}
            onChange={(e) => handleParamChange(key, e.target.value)}
            disabled={readOnly}
            className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
          />
        )}
      </div>
    ));
  };

  // Trigger 类型显示名称
  const triggerNames: Record<string, string> = {
    pinbar: 'Pinbar (针 bar)',
    engulfing: 'Engulfing (吞没)',
    doji: 'Doji (十字星)',
    hammer: 'Hammer (锤子线)',
  };

  // Filter 类型显示名称
  const filterNames: Record<string, string> = {
    ema: 'EMA 趋势',
    ema_trend: 'EMA 趋势',
    mtf: 'MTF 多周期',
    atr: 'ATR 波动率',
    volume_surge: '成交量激增',
    volatility_filter: '波动率过滤',
    time_filter: '时间窗口',
    price_action: '价格行为',
  };

  return (
    <div
      className={cn(
        'rounded-lg border-2 p-3 mb-2 transition-all',
        isTrigger
          ? 'bg-purple-50 border-purple-200'
          : 'bg-orange-50 border-orange-200'
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        {isTrigger ? (
          <Zap className="w-4 h-4 text-purple-600" />
        ) : (
          <Filter className="w-4 h-4 text-orange-600" />
        )}

        <span
          className={cn(
            'px-2 py-1 rounded text-xs font-semibold',
            isTrigger
              ? 'bg-purple-100 text-purple-700'
              : 'bg-orange-100 text-orange-700'
          )}
        >
          {isTrigger
            ? triggerNames[config.type] || config.type
            : filterNames[config.type] || config.type}
        </span>

        <span className="text-xs text-gray-500">
          {isTrigger ? '触发器' : '过滤器'}
        </span>

        {config.enabled === false && (
          <span className="text-xs text-gray-400 italic">(已禁用)</span>
        )}
      </div>

      {/* Parameters */}
      {config.params && Object.keys(config.params).length > 0 ? (
        <div className="space-y-2">
          {renderParamInputs(config.params)}
        </div>
      ) : (
        <p className="text-xs text-gray-400 italic">无参数配置</p>
      )}
    </div>
  );
}
