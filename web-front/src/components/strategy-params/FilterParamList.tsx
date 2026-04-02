import React, { useState } from 'react';
import { Plus, Trash2, ChevronDown, ChevronRight, GripVertical, Info } from 'lucide-react';
import type { FilterType, FilterConfig } from '../../lib/api';
import { getFilterDisplayName, getDefaultFilterParams, generateId } from '../../lib/api';

interface FilterParamListProps {
  filters: FilterConfig[];
  onChange: (filters: FilterConfig[]) => void;
  disabled?: boolean;
}

const AVAILABLE_FILTERS: { type: FilterType; description: string }[] = [
  { type: 'volume_surge', description: '检测成交量异常放大' },
  { type: 'volatility_filter', description: 'ATR 波动率过滤' },
  { type: 'time_filter', description: '交易时段过滤' },
  { type: 'atr', description: 'ATR 波动率校验' },
];

/**
 * 过滤器参数列表组件
 * 支持添加、删除、启用/禁用多个过滤器
 */
export default function FilterParamList({ filters, onChange, disabled = false }: FilterParamListProps) {
  const [expandedFilterId, setExpandedFilterId] = useState<string | null>(null);
  const [showAddMenu, setShowAddMenu] = useState(false);

  const handleAddFilter = (type: FilterType) => {
    const newFilter: FilterConfig = {
      id: generateId(),
      type,
      enabled: true,
      params: getDefaultFilterParams(type),
    };
    onChange([...filters, newFilter]);
    setShowAddMenu(false);
  };

  const handleRemoveFilter = (id: string) => {
    onChange(filters.filter((f) => f.id !== id));
    if (expandedFilterId === id) {
      setExpandedFilterId(null);
    }
  };

  const handleToggleEnabled = (id: string) => {
    onChange(
      filters.map((f) => (f.id === id ? { ...f, enabled: !f.enabled } : f))
    );
  };

  const handleParamsChange = (id: string, newParams: Record<string, any>) => {
    onChange(
      filters.map((f) => (f.id === id ? { ...f, params: newParams } : f))
    );
  };

  const handleMoveUp = (index: number) => {
    if (index === 0) return;
    const newFilters = [...filters];
    [newFilters[index - 1], newFilters[index]] = [newFilters[index], newFilters[index - 1]];
    onChange(newFilters);
  };

  const handleMoveDown = (index: number) => {
    if (index === filters.length - 1) return;
    const newFilters = [...filters];
    [newFilters[index], newFilters[index + 1]] = [newFilters[index + 1], newFilters[index]];
    onChange(newFilters);
  };

  const renderFilterParams = (filter: FilterConfig) => {
    switch (filter.type) {
      case 'volume_surge':
        return (
          <div className="space-y-3">
            <div>
              <label className="text-xs text-gray-600">成交量倍数</label>
              <input
                type="number"
                step="0.1"
                min="1"
                value={(filter.params as any).multiplier || 1.5}
                onChange={(e) =>
                  handleParamsChange(filter.id, {
                    ...filter.params,
                    multiplier: parseFloat(e.target.value),
                  })
                }
                disabled={disabled}
                className="mt-1 w-full px-2 py-1.5 text-sm border border-gray-200 rounded-md disabled:bg-gray-50"
              />
              <p className="text-xs text-gray-400 mt-1">
                成交量超过平均值多少倍时触发
              </p>
            </div>
            <div>
              <label className="text-xs text-gray-600">回看周期数</label>
              <input
                type="number"
                step="1"
                min="5"
                value={(filter.params as any).lookback_periods || 20}
                onChange={(e) =>
                  handleParamsChange(filter.id, {
                    ...filter.params,
                    lookback_periods: parseInt(e.target.value),
                  })
                }
                disabled={disabled}
                className="mt-1 w-full px-2 py-1.5 text-sm border border-gray-200 rounded-md disabled:bg-gray-50"
              />
            </div>
          </div>
        );

      case 'volatility_filter':
        return (
          <div className="space-y-3">
            <div>
              <label className="text-xs text-gray-600">最小 ATR 比率</label>
              <input
                type="number"
                step="0.1"
                min="0"
                value={(filter.params as any).min_atr_ratio || 0.5}
                onChange={(e) =>
                  handleParamsChange(filter.id, {
                    ...filter.params,
                    min_atr_ratio: parseFloat(e.target.value),
                  })
                }
                disabled={disabled}
                className="mt-1 w-full px-2 py-1.5 text-sm border border-gray-200 rounded-md disabled:bg-gray-50"
              />
            </div>
            <div>
              <label className="text-xs text-gray-600">最大 ATR 比率</label>
              <input
                type="number"
                step="0.1"
                min="0"
                value={(filter.params as any).max_atr_ratio || 3}
                onChange={(e) =>
                  handleParamsChange(filter.id, {
                    ...filter.params,
                    max_atr_ratio: parseFloat(e.target.value),
                  })
                }
                disabled={disabled}
                className="mt-1 w-full px-2 py-1.5 text-sm border border-gray-200 rounded-md disabled:bg-gray-50"
              />
            </div>
            <div>
              <label className="text-xs text-gray-600">ATR 周期</label>
              <input
                type="number"
                step="1"
                min="1"
                value={(filter.params as any).atr_period || 14}
                onChange={(e) =>
                  handleParamsChange(filter.id, {
                    ...filter.params,
                    atr_period: parseInt(e.target.value),
                  })
                }
                disabled={disabled}
                className="mt-1 w-full px-2 py-1.5 text-sm border border-gray-200 rounded-md disabled:bg-gray-50"
              />
            </div>
          </div>
        );

      case 'time_filter':
        return (
          <div className="space-y-3">
            <div>
              <label className="text-xs text-gray-600">交易时段</label>
              <select
                value={(filter.params as any).session || 'any'}
                onChange={(e) =>
                  handleParamsChange(filter.id, {
                    ...filter.params,
                    session: e.target.value,
                  })
                }
                disabled={disabled}
                className="mt-1 w-full px-2 py-1.5 text-sm border border-gray-200 rounded-md disabled:bg-gray-50"
              >
                <option value="any">任意时段</option>
                <option value="asian">亚洲时段</option>
                <option value="london">伦敦时段</option>
                <option value="new_york">纽约时段</option>
              </select>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={(filter.params as any).exclude_weekend || false}
                onChange={(e) =>
                  handleParamsChange(filter.id, {
                    ...filter.params,
                    exclude_weekend: e.target.checked,
                  })
                }
                disabled={disabled}
                className="rounded border-gray-300"
              />
              <label className="text-xs text-gray-600">排除周末</label>
            </div>
          </div>
        );

      case 'atr':
        return (
          <div className="space-y-3">
            <div>
              <label className="text-xs text-gray-600">ATR 周期</label>
              <input
                type="number"
                step="1"
                min="1"
                value={(filter.params as any).period || 14}
                onChange={(e) =>
                  handleParamsChange(filter.id, {
                    ...filter.params,
                    period: parseInt(e.target.value),
                  })
                }
                disabled={disabled}
                className="mt-1 w-full px-2 py-1.5 text-sm border border-gray-200 rounded-md disabled:bg-gray-50"
              />
            </div>
            <div>
              <label className="text-xs text-gray-600">最小 ATR 比率</label>
              <input
                type="number"
                step="0.0001"
                min="0"
                value={(filter.params as any).min_atr_ratio || 0.001}
                onChange={(e) =>
                  handleParamsChange(filter.id, {
                    ...filter.params,
                    min_atr_ratio: parseFloat(e.target.value),
                  })
                }
                disabled={disabled}
                className="mt-1 w-full px-2 py-1.5 text-sm border border-gray-200 rounded-md disabled:bg-gray-50"
              />
              <p className="text-xs text-gray-400 mt-1">
                例如 0.001 表示 0.1% 的最小波动
              </p>
            </div>
          </div>
        );

      default:
        return <p className="text-xs text-gray-400">暂无参数配置</p>;
    }
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-orange-500 rounded-full" />
          <h3 className="text-sm font-semibold text-gray-900">过滤器链</h3>
          <div className="group relative">
            <Info className="w-4 h-4 text-gray-400 hover:text-gray-600 cursor-help" />
            <div className="absolute left-0 bottom-full mb-2 hidden group-hover:block w-64 p-3 bg-gray-900 text-white text-xs rounded-lg z-10">
              <p>过滤器按顺序依次执行，所有过滤器通过后信号才会触发。</p>
            </div>
          </div>
        </div>
      </div>

      {/* 过滤器列表 */}
      <div className="space-y-2 mb-4">
        {filters.length === 0 ? (
          <div className="text-center py-8 text-sm text-gray-400">
            暂无过滤器，点击下方按钮添加
          </div>
        ) : (
          filters.map((filter, index) => (
            <div
              key={filter.id}
              className={`border rounded-lg transition-colors ${
                filter.enabled
                  ? 'border-gray-200 bg-white'
                  : 'border-gray-100 bg-gray-50'
              }`}
            >
              <div className="flex items-center gap-2 p-3">
                <button
                  onClick={() =>
                    setExpandedFilterId(expandedFilterId === filter.id ? null : filter.id)
                  }
                  className="p-1 hover:bg-gray-100 rounded"
                >
                  {expandedFilterId === filter.id ? (
                    <ChevronDown className="w-4 h-4 text-gray-500" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-gray-500" />
                  )}
                </button>
                <GripVertical className="w-4 h-4 text-gray-300" />
                <div className="flex-1">
                  <p
                    className={`text-sm font-medium ${
                      filter.enabled ? 'text-gray-900' : 'text-gray-400'
                    }`}
                  >
                    {getFilterDisplayName(filter.type)}
                  </p>
                  <p className="text-xs text-gray-400">
                    {filter.enabled ? '已启用' : '已禁用'}
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => handleMoveUp(index)}
                    disabled={index === 0 || disabled}
                    className="p-1 hover:bg-gray-100 rounded disabled:opacity-30"
                    title="上移"
                  >
                    <ChevronDown className="w-4 h-4 text-gray-400 rotate-90" />
                  </button>
                  <button
                    onClick={() => handleMoveDown(index)}
                    disabled={index === filters.length - 1 || disabled}
                    className="p-1 hover:bg-gray-100 rounded disabled:opacity-30"
                    title="下移"
                  >
                    <ChevronRight className="w-4 h-4 text-gray-400 rotate-90" />
                  </button>
                  <button
                    onClick={() => handleToggleEnabled(filter.id)}
                    disabled={disabled}
                    className={`px-2 py-1 text-xs rounded transition ${
                      filter.enabled
                        ? 'bg-green-100 text-green-700 hover:bg-green-200'
                        : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                    } disabled:opacity-50`}
                  >
                    {filter.enabled ? '启用' : '禁用'}
                  </button>
                  <button
                    onClick={() => handleRemoveFilter(filter.id)}
                    disabled={disabled}
                    className="p-1 hover:bg-red-50 rounded disabled:opacity-30"
                  >
                    <Trash2 className="w-4 h-4 text-red-400" />
                  </button>
                </div>
              </div>
              {expandedFilterId === filter.id && (
                <div className="px-3 pb-3 border-t border-gray-100 pt-3">
                  {renderFilterParams(filter)}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* 添加过滤器按钮 */}
      <div className="relative">
        <button
          onClick={() => setShowAddMenu(!showAddMenu)}
          disabled={disabled}
          className="w-full py-2 border-2 border-dashed border-gray-200 rounded-lg text-sm text-gray-500 hover:border-gray-300 hover:text-gray-600 transition flex items-center justify-center gap-2 disabled:opacity-50"
        >
          <Plus className="w-4 h-4" />
          添加过滤器
        </button>

        {showAddMenu && (
          <div className="absolute bottom-full left-0 right-0 mb-2 bg-white border border-gray-200 rounded-lg shadow-lg z-10">
            <div className="p-2">
              {AVAILABLE_FILTERS.map((item) => (
                <button
                  key={item.type}
                  onClick={() => handleAddFilter(item.type)}
                  className="w-full text-left px-3 py-2 hover:bg-gray-50 rounded transition"
                >
                  <p className="text-sm font-medium text-gray-900">
                    {getFilterDisplayName(item.type)}
                  </p>
                  <p className="text-xs text-gray-500">{item.description}</p>
                </button>
              ))}
            </div>
            <button
              onClick={() => setShowAddMenu(false)}
              className="w-full px-3 py-2 text-xs text-gray-500 hover:bg-gray-50 rounded-b-lg transition"
            >
              取消
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
