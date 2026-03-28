import React, { useState, useCallback } from 'react';
import { Zap, Plus, Trash2 } from 'lucide-react';
import { cn } from '../lib/utils';
import {
  StrategyDefinition,
  TriggerConfig,
  FilterConfig,
  TriggerType,
  generateId,
  getDefaultTriggerParams,
  convertStrategyToLogicNode,
  convertLogicNodeToStrategy,
} from '../lib/api';
import NodeRenderer from './NodeRenderer';

interface StrategyBuilderProps {
  strategies: StrategyDefinition[];
  onChange: (strategies: StrategyDefinition[]) => void;
  readOnly?: boolean;
}

/**
 * 策略构建器组件
 *
 * Schema 驱动的策略编辑器，支持：
 * - 多策略管理
 * - 递归逻辑树编辑（内部转换）
 * - Trigger/Filter 动态配置
 * - 与后端扁平结构兼容
 */
export default function StrategyBuilder({
  strategies,
  onChange,
  readOnly = false,
}: StrategyBuilderProps) {
  const [expandedStrategyIds, setExpandedStrategyIds] = useState<Set<string>>(new Set());

  // 切换策略展开/折叠状态
  const toggleStrategyExpanded = useCallback((strategyId: string) => {
    setExpandedStrategyIds(prev => {
      const next = new Set(prev);
      if (next.has(strategyId)) {
        next.delete(strategyId);
      } else {
        next.add(strategyId);
      }
      return next;
    });
  }, []);

  // 更新策略名称
  const handleStrategyNameChange = useCallback((index: number, newName: string) => {
    const newStrategies = [...strategies];
    if (newStrategies[index]) {
      newStrategies[index].name = newName;
      onChange(newStrategies);
    }
  }, [strategies, onChange]);

  // 更新策略作用域
  const handleApplyToChange = useCallback((index: number, newApplyTo: string[]) => {
    const newStrategies = [...strategies];
    if (newStrategies[index]) {
      newStrategies[index].apply_to = newApplyTo;
      onChange(newStrategies);
    }
  }, [strategies, onChange]);

  // 删除策略
  const handleDeleteStrategy = useCallback((index: number) => {
    const newStrategies = strategies.filter((_, i) => i !== index);
    onChange(newStrategies);
  }, [strategies, onChange]);

  // 添加新策略
  const handleAddStrategy = useCallback(() => {
    const newStrategy: StrategyDefinition = {
      id: generateId(),
      name: `新策略 ${strategies.length + 1}`,
      trigger: {
        id: generateId(),
        type: 'pinbar',
        enabled: true,
        params: getDefaultTriggerParams('pinbar'),
      },
      filters: [],
      filter_logic: 'AND' as const,
      is_global: true,
      apply_to: [],
      logic_tree: convertStrategyToLogicNode({
        id: generateId(),
        name: `新策略 ${strategies.length + 1}`,
        trigger: {
          id: generateId(),
          type: 'pinbar',
          enabled: true,
          params: getDefaultTriggerParams('pinbar'),
        },
        filters: [],
        filter_logic: 'AND' as const,
        is_global: true,
        apply_to: [],
      }),
    };
    onChange([...strategies, newStrategy]);
  }, [strategies, onChange]);

  // 添加 Trigger 到策略
  const handleAddTrigger = useCallback((strategyIndex: number, triggerType: TriggerType) => {
    const newStrategies = [...strategies];
    const strategy = newStrategies[strategyIndex];
    if (!strategy) return;

    // Replace the existing trigger (only one trigger per strategy)
    strategy.trigger = {
      id: generateId(),
      type: triggerType,
      enabled: true,
      params: getDefaultTriggerParams(triggerType),
    };

    // 重建 logic_tree
    strategy.logic_tree = convertStrategyToLogicNode(strategy);

    onChange(newStrategies);
  }, [strategies, onChange]);

  // 添加 Filter 到策略
  const handleAddFilter = useCallback((strategyIndex: number, filterType: string) => {
    const newStrategies = [...strategies];
    const strategy = newStrategies[strategyIndex];
    if (!strategy) return;

    strategy.filters.push({
      id: generateId(),
      type: filterType as any,
      enabled: true,
      params: {},
    });

    // 重建 logic_tree
    strategy.logic_tree = convertStrategyToLogicNode(strategy);

    onChange(newStrategies);
  }, [strategies, onChange]);

  // 删除 Filter
  const handleDeleteFilter = useCallback((strategyIndex: number, filterIndex: number) => {
    const newStrategies = [...strategies];
    const strategy = newStrategies[strategyIndex];
    if (!strategy) return;

    strategy.filters = strategy.filters.filter((_, i) => i !== filterIndex);

    // 重建 logic_tree
    strategy.logic_tree = convertStrategyToLogicNode(strategy);

    onChange(newStrategies);
  }, [strategies, onChange]);

  // 更新 Trigger 配置
  const handleUpdateTrigger = useCallback((strategyIndex: number, updatedTrigger: TriggerConfig) => {
    const newStrategies = [...strategies];
    const strategy = newStrategies[strategyIndex];
    if (!strategy) return;

    // 更新 trigger 字段
    strategy.trigger = updatedTrigger;

    // 重建 logic_tree
    strategy.logic_tree = convertStrategyToLogicNode(strategy);

    onChange(newStrategies);
  }, [strategies, onChange]);

  // 更新 Filter 配置
  const handleUpdateFilter = useCallback((strategyIndex: number, updatedFilter: FilterConfig) => {
    const newStrategies = [...strategies];
    const strategy = newStrategies[strategyIndex];
    if (!strategy) return;

    const filterIndex = strategy.filters.findIndex(f => f.id === updatedFilter.id);
    if (filterIndex !== -1) {
      strategy.filters[filterIndex] = updatedFilter;

      // 重建 logic_tree
      strategy.logic_tree = convertStrategyToLogicNode(strategy);

      onChange(newStrategies);
    }
  }, [strategies, onChange]);

  // 处理逻辑树变更 - 从递归树转换回扁平结构
  const handleLogicNodeChange = useCallback((strategyIndex: number, newNode: LogicNode | LeafNode) => {
    const newStrategies = [...strategies];
    const strategy = newStrategies[strategyIndex];
    if (!strategy) return;

    // 如果是 AND 根节点，提取 trigger 和 filters
    if ('gate' in newNode && newNode.gate === 'AND') {
      const triggerChildren = newNode.children.filter(
        (child): child is TriggerLeaf => isTriggerLeaf(child)
      );
      const filterChildren = newNode.children.filter(
        (child): child is FilterLeaf => isFilterLeaf(child)
      );

      if (triggerChildren.length > 0) {
        strategy.trigger = triggerChildren[0].config;
      }
      strategy.filters = filterChildren.map(f => f.config);
    }

    onChange(newStrategies);
  }, [strategies, onChange]);

  const triggerOptions: { type: TriggerType; label: string }[] = [
    { type: 'pinbar', label: 'Pinbar (针 bar)' },
    { type: 'engulfing', label: 'Engulfing (吞没)' },
    { type: 'doji', label: 'Doji (十字星)' },
    { type: 'hammer', label: 'Hammer (锤子线)' },
  ];

  const filterOptions: { type: string; label: string }[] = [
    { type: 'ema', label: 'EMA 趋势' },
    { type: 'mtf', label: 'MTF 多周期' },
    { type: 'atr', label: 'ATR 波动率' },
    { type: 'volume_surge', label: '成交量激增' },
    { type: 'volatility_filter', label: '波动率过滤' },
  ];

  if (strategies.length === 0) {
    return (
      <div className="text-center py-8">
        <Zap className="w-12 h-12 mx-auto mb-3 text-gray-300" />
        <p className="text-sm text-gray-500 mb-4">暂无策略配置</p>
        <button
          onClick={handleAddStrategy}
          disabled={readOnly}
          className="flex items-center gap-2 px-4 py-2 bg-black text-white rounded-lg hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors mx-auto"
        >
          <Plus className="w-4 h-4" />
          添加策略
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Strategy List */}
      {strategies.map((strategy, index) => {
        const isExpanded = expandedStrategyIds.has(strategy.id);
        const logicNode = convertStrategyToLogicNode(strategy);

        return (
          <div
            key={String(strategy.id)}
            className="bg-white rounded-xl border border-gray-200 overflow-hidden"
          >
            {/* Strategy Header */}
            <div className="flex items-center gap-3 p-4 border-b border-gray-100 bg-gray-50">
              <button
                onClick={() => toggleStrategyExpanded(strategy.id)}
                className="p-1 hover:bg-gray-200 rounded transition-colors"
              >
                {isExpanded ? (
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                ) : (
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                )}
              </button>

              <input
                type="text"
                value={strategy.name}
                onChange={(e) => handleStrategyNameChange(index, e.target.value)}
                disabled={readOnly}
                className="flex-1 px-2 py-1 text-sm font-medium bg-transparent border-b border-transparent hover:border-gray-300 focus:border-black outline-none transition-colors disabled:cursor-not-allowed"
              />

              <div className="flex items-center gap-2">
                {!readOnly && (
                  <>
                    {/* Add Trigger Dropdown - Replace existing trigger */}
                    <div className="relative group">
                      <button className="flex items-center gap-1 px-2 py-1 text-xs bg-purple-100 text-purple-700 rounded hover:bg-purple-200 transition-colors">
                        <Plus className="w-3 h-3" />
                        触发器
                      </button>
                      <div className="absolute right-0 top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-10 hidden group-hover:block">
                        {triggerOptions.map((option) => (
                          <button
                            key={option.type}
                            onClick={() => handleAddTrigger(index, option.type)}
                            className="block w-full text-left px-3 py-2 text-xs hover:bg-gray-50 transition-colors"
                          >
                            {option.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Add Filter Dropdown */}
                    <div className="relative group">
                      <button className="flex items-center gap-1 px-2 py-1 text-xs bg-orange-100 text-orange-700 rounded hover:bg-orange-200 transition-colors">
                        <Plus className="w-3 h-3" />
                        过滤器
                      </button>
                      <div className="absolute right-0 top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-10 hidden group-hover:block">
                        {filterOptions.map((option) => (
                          <button
                            key={option.type}
                            onClick={() => handleAddFilter(index, option.type)}
                            className="block w-full text-left px-3 py-2 text-xs hover:bg-gray-50 transition-colors"
                          >
                            {option.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    <button
                      onClick={() => handleDeleteStrategy(index)}
                      className="p-1.5 hover:bg-red-100 rounded transition-colors"
                      title="删除策略"
                    >
                      <Trash2 className="w-4 h-4 text-red-500" />
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Strategy Content */}
            {isExpanded && (
              <div className="p-4">
                {/* Apply To */}
                <div className="mb-4">
                  <label className="block text-xs font-medium text-gray-600 mb-2">
                    作用域（留空表示全局）
                  </label>
                  <input
                    type="text"
                    value={strategy.apply_to.join(', ')}
                    onChange={(e) => {
                      const values = e.target.value.split(',').map(v => v.trim()).filter(Boolean);
                      handleApplyToChange(index, values);
                    }}
                    disabled={readOnly}
                    placeholder="例如：BTC/USDT:USDT:15m, ETH/USDT:USDT:1h"
                    className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg outline-none focus:border-black transition-colors disabled:bg-gray-100"
                  />
                </div>

                {/* Logic Tree Editor */}
                <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                  <div className="flex items-center gap-2 mb-3">
                    <Zap className="w-4 h-4 text-yellow-600" />
                    <span className="text-sm font-semibold text-gray-700">逻辑树</span>
                  </div>

                  {/* Current Trigger */}
                  <div className="mb-3">
                    <span className="text-xs font-medium text-gray-600 mb-2 block">当前触发器</span>
                    <div className="bg-purple-50 border border-purple-200 rounded-lg p-3">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="px-2 py-0.5 bg-purple-100 text-purple-700 text-xs font-semibold rounded">
                          {triggerOptions.find(t => t.type === strategy.trigger.type)?.label || strategy.trigger.type}
                        </span>
                        {strategy.trigger.enabled === false && (
                          <span className="text-xs text-gray-400 italic">(已禁用)</span>
                        )}
                      </div>
                      {Object.entries(strategy.trigger.params).map(([key, value]) => (
                        <div key={key} className="flex items-center gap-2 text-xs">
                          <label className="text-gray-600 capitalize w-32">{key.replace(/_/g, ' ')}:</label>
                          <input
                            type={typeof value === 'number' ? 'number' : 'text'}
                            value={String(value)}
                            onChange={(e) => {
                              const newValue = typeof value === 'number' ? parseFloat(e.target.value) || 0 : e.target.value;
                              handleUpdateTrigger(index, {
                                ...strategy.trigger,
                                params: { ...strategy.trigger.params, [key]: newValue },
                              });
                            }}
                            disabled={readOnly}
                            className="flex-1 px-2 py-1 border border-gray-300 rounded text-sm disabled:bg-gray-100"
                          />
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Current Filters */}
                  {strategy.filters.length > 0 && (
                    <div className="mb-3">
                      <span className="text-xs font-medium text-gray-600 mb-2 block">
                        过滤器 ({strategy.filters.length})
                      </span>
                      {strategy.filters.map((filter, filterIndex) => (
                        <div
                          key={String(filter.id)}
                          className="bg-orange-50 border border-orange-200 rounded-lg p-3 mb-2"
                        >
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-2">
                              <span className="px-2 py-0.5 bg-orange-100 text-orange-700 text-xs font-semibold rounded">
                                {filterOptions.find(f => f.type === filter.type)?.label || filter.type}
                              </span>
                              {filter.enabled === false && (
                                <span className="text-xs text-gray-400 italic">(已禁用)</span>
                              )}
                            </div>
                            {!readOnly && (
                              <button
                                onClick={() => handleDeleteFilter(index, filterIndex)}
                                className="p-1 hover:bg-red-100 rounded transition-colors"
                              >
                                <Trash2 className="w-3 h-3 text-red-500" />
                              </button>
                            )}
                          </div>
                          {Object.entries(filter.params || {}).map(([key, value]) => (
                            <div key={key} className="flex items-center gap-2 text-xs">
                              <label className="text-gray-600 capitalize w-32">{key.replace(/_/g, ' ')}:</label>
                              <input
                                type={typeof value === 'number' ? 'number' : 'text'}
                                value={String(value)}
                                onChange={(e) => {
                                  const newValue = typeof value === 'number' ? parseFloat(e.target.value) || 0 : e.target.value;
                                  handleUpdateFilter(index, {
                                    ...filter,
                                    params: { ...filter.params, [key]: newValue },
                                  });
                                }}
                                disabled={readOnly}
                                className="flex-1 px-2 py-1 border border-gray-300 rounded text-sm disabled:bg-gray-100"
                              />
                            </div>
                          ))}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Visual Logic Tree using NodeRenderer */}
                  <div className="mt-4 pt-4 border-t border-gray-200">
                    <span className="text-xs font-medium text-gray-600 mb-2 block">可视化逻辑树</span>
                    <NodeRenderer
                      node={logicNode}
                      onChange={(newNode) => handleLogicNodeChange(index, newNode as LogicNode)}
                      readOnly={readOnly}
                      onUpdateTrigger={(trigger) => handleUpdateTrigger(index, trigger)}
                      onUpdateFilter={(filter) => handleUpdateFilter(index, filter)}
                    />
                  </div>
                </div>
              </div>
            )}
          </div>
        );
      })}

      {/* Add Strategy Button */}
      {!readOnly && (
        <button
          onClick={handleAddStrategy}
          className="w-full py-3 border-2 border-dashed border-gray-300 rounded-xl text-gray-500 hover:border-black hover:text-black transition-colors flex items-center justify-center gap-2"
        >
          <Plus className="w-5 h-5" />
          添加新策略
        </button>
      )}
    </div>
  );
}
