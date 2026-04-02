/**
 * ParameterSpaceConfig.tsx
 *
 * 参数空间配置表单组件
 * 支持整数范围、浮点范围、离散选择三种参数类型
 */

import React, { useState, useCallback } from 'react';
import type {
  ParameterSpace,
  ParameterDefinition,
  IntParameter,
  FloatParameter,
  CategoricalParameter,
  OptimizationObjective,
} from '../../lib/api';
import { Plus, Trash2, HelpCircle } from 'lucide-react';

// ============================================================
// 预定义参数配置模板
// ============================================================

const PARAMETER_TEMPLATES: Record<string, { label: string; category: string; defaultDef: ParameterDefinition }> = {
  // Trigger 参数
  pinbar_min_wick_ratio: {
    label: 'Pinbar 最小影线占比',
    category: 'Trigger - Pinbar',
    defaultDef: { type: 'float', low: 0.5, high: 0.8, step: 0.05 },
  },
  pinbar_max_body_ratio: {
    label: 'Pinbar 最大实体占比',
    category: 'Trigger - Pinbar',
    defaultDef: { type: 'float', low: 0.2, high: 0.4, step: 0.05 },
  },
  pinbar_body_position_tolerance: {
    label: 'Pinbar 实体位置容差',
    category: 'Trigger - Pinbar',
    defaultDef: { type: 'float', low: 0.05, high: 0.15, step: 0.01 },
  },
  engulfing_min_body_ratio: {
    label: '吞没形态最小实体占比',
    category: 'Trigger - Engulfing',
    defaultDef: { type: 'float', low: 0.4, high: 0.7, step: 0.05 },
  },
  engulfing_require_full_engulf: {
    label: '吞没形态要求完全吞没',
    category: 'Trigger - Engulfing',
    defaultDef: { type: 'categorical', choices: [true, false] },
  },

  // Filter 参数
  ema_period: {
    label: 'EMA 周期',
    category: 'Filter - EMA',
    defaultDef: { type: 'int', low: 9, high: 50, step: 1 },
  },
  mtf_require_confirmation: {
    label: 'MTF 要求确认',
    category: 'Filter - MTF',
    defaultDef: { type: 'categorical', choices: [true, false] },
  },
  volume_surge_multiplier: {
    label: '成交量激增倍数',
    category: 'Filter - Volume',
    defaultDef: { type: 'float', low: 1.2, high: 3.0, step: 0.1 },
  },
  volume_surge_lookback_periods: {
    label: '成交量回看周期',
    category: 'Filter - Volume',
    defaultDef: { type: 'int', low: 10, high: 50, step: 5 },
  },
  volatility_min_atr_ratio: {
    label: '波动率最小 ATR 比率',
    category: 'Filter - Volatility',
    defaultDef: { type: 'float', low: 0.0005, high: 0.002, step: 0.0001 },
  },
  volatility_max_atr_ratio: {
    label: '波动率最大 ATR 比率',
    category: 'Filter - Volatility',
    defaultDef: { type: 'float', low: 0.002, high: 0.01, step: 0.0005 },
  },
  atr_period: {
    label: 'ATR 周期',
    category: 'Filter - ATR',
    defaultDef: { type: 'int', low: 7, high: 21, step: 1 },
  },
  atr_min_atr_ratio: {
    label: 'ATR 最小比率',
    category: 'Filter - ATR',
    defaultDef: { type: 'float', low: 0.0005, high: 0.002, step: 0.0001 },
  },

  // Risk 参数
  max_loss_percent: {
    label: '最大亏损比例',
    category: 'Risk',
    defaultDef: { type: 'float', low: 0.005, high: 0.02, step: 0.001, log: true },
  },
  default_leverage: {
    label: '默认杠杆倍数',
    category: 'Risk',
    defaultDef: { type: 'int', low: 1, high: 20, step: 1 },
  },
};

// ============================================================
// 子组件：整数范围输入
// ============================================================

interface IntRangeInputProps {
  parameterKey: string;
  value: IntParameter;
  onChange: (value: IntParameter) => void;
  onRemove: () => void;
}

const IntRangeInput: React.FC<IntRangeInputProps> = ({
  parameterKey,
  value,
  onChange,
  onRemove,
}) => {
  return (
    <div className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
      <span className="text-sm font-medium text-gray-700 dark:text-gray-300 w-32">
        {parameterKey}
      </span>

      <div className="flex items-center gap-2">
        <label className="text-xs text-gray-500">最小值:</label>
        <input
          type="number"
          value={value.low}
          onChange={(e) => onChange({ ...value, low: parseInt(e.target.value) || 0 })}
          className="w-20 px-2 py-1 text-sm border rounded dark:bg-gray-700 dark:border-gray-600"
        />
      </div>

      <div className="flex items-center gap-2">
        <label className="text-xs text-gray-500">最大值:</label>
        <input
          type="number"
          value={value.high}
          onChange={(e) => onChange({ ...value, high: parseInt(e.target.value) || 0 })}
          className="w-20 px-2 py-1 text-sm border rounded dark:bg-gray-700 dark:border-gray-600"
        />
      </div>

      <div className="flex items-center gap-2">
        <label className="text-xs text-gray-500">步长:</label>
        <input
          type="number"
          value={value.step || 1}
          onChange={(e) => onChange({ ...value, step: parseInt(e.target.value) || 1 })}
          className="w-16 px-2 py-1 text-sm border rounded dark:bg-gray-700 dark:border-gray-600"
        />
      </div>

      <button
        onClick={onRemove}
        className="ml-auto p-1.5 text-red-500 hover:bg-red-100 dark:hover:bg-red-900/30 rounded transition-colors"
        title="删除参数"
      >
        <Trash2 className="w-4 h-4" />
      </button>
    </div>
  );
};

// ============================================================
// 子组件：浮点范围输入
// ============================================================

interface FloatRangeInputProps {
  parameterKey: string;
  value: FloatParameter;
  onChange: (value: FloatParameter) => void;
  onRemove: () => void;
}

const FloatRangeInput: React.FC<FloatRangeInputProps> = ({
  parameterKey,
  value,
  onChange,
  onRemove,
}) => {
  return (
    <div className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
      <span className="text-sm font-medium text-gray-700 dark:text-gray-300 w-32">
        {parameterKey}
      </span>

      <div className="flex items-center gap-2">
        <label className="text-xs text-gray-500">最小值:</label>
        <input
          type="number"
          step="0.0001"
          value={value.low}
          onChange={(e) => onChange({ ...value, low: parseFloat(e.target.value) || 0 })}
          className="w-24 px-2 py-1 text-sm border rounded dark:bg-gray-700 dark:border-gray-600"
        />
      </div>

      <div className="flex items-center gap-2">
        <label className="text-xs text-gray-500">最大值:</label>
        <input
          type="number"
          step="0.0001"
          value={value.high}
          onChange={(e) => onChange({ ...value, high: parseFloat(e.target.value) || 0 })}
          className="w-24 px-2 py-1 text-sm border rounded dark:bg-gray-700 dark:border-gray-600"
        />
      </div>

      <div className="flex items-center gap-2">
        <label className="text-xs text-gray-500">步长:</label>
        <input
          type="number"
          step="0.0001"
          value={value.step || ''}
          onChange={(e) => onChange({ ...value, step: parseFloat(e.target.value) || undefined })}
          className="w-20 px-2 py-1 text-sm border rounded dark:bg-gray-700 dark:border-gray-600"
          placeholder="可选"
        />
      </div>

      <div className="flex items-center gap-1">
        <input
          type="checkbox"
          id={`log-${parameterKey}`}
          checked={value.log || false}
          onChange={(e) => onChange({ ...value, log: e.target.checked })}
          className="w-4 h-4"
        />
        <label htmlFor={`log-${parameterKey}`} className="text-xs text-gray-500">
          对数刻度
        </label>
      </div>

      <button
        onClick={onRemove}
        className="ml-auto p-1.5 text-red-500 hover:bg-red-100 dark:hover:bg-red-900/30 rounded transition-colors"
        title="删除参数"
      >
        <Trash2 className="w-4 h-4" />
      </button>
    </div>
  );
};

// ============================================================
// 子组件：离散选择输入
// ============================================================

interface CategoricalInputProps {
  parameterKey: string;
  value: CategoricalParameter;
  onChange: (value: CategoricalParameter) => void;
  onRemove: () => void;
}

const CategoricalInput: React.FC<CategoricalInputProps> = ({
  parameterKey,
  value,
  onChange,
  onRemove,
}) => {
  const [choiceInput, setChoiceInput] = useState('');

  const handleAddChoice = () => {
    if (choiceInput.trim()) {
      const parsed = JSON.parse(choiceInput);
      onChange({ ...value, choices: [...value.choices, parsed] });
      setChoiceInput('');
    }
  };

  const handleRemoveChoice = (index: number) => {
    onChange({ ...value, choices: value.choices.filter((_, i) => i !== index) });
  };

  return (
    <div className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
      <span className="text-sm font-medium text-gray-700 dark:text-gray-300 w-32">
        {parameterKey}
      </span>

      <div className="flex-1 flex items-center gap-2 flex-wrap">
        <span className="text-xs text-gray-500">可选项:</span>
        {value.choices.map((choice, index) => (
          <span
            key={index}
            className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 rounded"
          >
            {String(choice)}
            <button
              onClick={() => handleRemoveChoice(index)}
              className="hover:text-red-500"
            >
              ×
            </button>
          </span>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <input
          type="text"
          value={choiceInput}
          onChange={(e) => setChoiceInput(e.target.value)}
          placeholder="JSON 值，如：true, 10, &quot;high&quot;"
          className="w-40 px-2 py-1 text-sm border rounded dark:bg-gray-700 dark:border-gray-600"
          onKeyDown={(e) => e.key === 'Enter' && handleAddChoice()}
        />
        <button
          onClick={handleAddChoice}
          className="px-2 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          添加
        </button>
      </div>

      <button
        onClick={onRemove}
        className="ml-auto p-1.5 text-red-500 hover:bg-red-100 dark:hover:bg-red-900/30 rounded transition-colors"
        title="删除参数"
      >
        <Trash2 className="w-4 h-4" />
      </button>
    </div>
  );
};

// ============================================================
// 主组件：参数空间配置
// ============================================================

interface ParameterSpaceConfigProps {
  value: ParameterSpace;
  onChange: (value: ParameterSpace) => void;
}

export const ParameterSpaceConfig: React.FC<ParameterSpaceConfigProps> = ({
  value,
  onChange,
}) => {
  const [selectedCategory, setSelectedCategory] = useState<string>('all');

  // 获取当前已配置的参数 keys
  const configuredKeys = Object.keys(value);

  // 获取可用的参数模板（排除已配置的）
  const availableTemplates = Object.entries(PARAMETER_TEMPLATES).filter(
    ([key]) => !configuredKeys.includes(key)
  );

  // 按分类过滤
  const categories = ['all', ...new Set(Object.values(PARAMETER_TEMPLATES).map((t) => t.category))];

  const filteredTemplates = selectedCategory === 'all'
    ? availableTemplates
    : availableTemplates.filter(([, t]) => t.category === selectedCategory);

  // 添加参数
  const handleAddParameter = (key: string, defaultDef: ParameterDefinition) => {
    onChange({
      ...value,
      [key]: defaultDef,
    });
  };

  // 更新参数
  const handleUpdateParameter = (key: string, newDef: ParameterDefinition) => {
    onChange({
      ...value,
      [key]: newDef,
    });
  };

  // 删除参数
  const handleRemoveParameter = (key: string) => {
    const { [key]: _, ...rest } = value;
    onChange(rest);
  };

  return (
    <div className="space-y-6">
      {/* 已配置的参数 */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
          已配置参数 ({configuredKeys.length})
        </h3>

        {configuredKeys.length === 0 ? (
          <div className="p-6 text-center text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800 rounded-lg">
            <HelpCircle className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p>暂无参数配置，请从下方选择添加</p>
          </div>
        ) : (
          <div className="space-y-2">
            {configuredKeys.map((key) => {
              const paramDef = value[key];
              if (!paramDef) return null;

              return (
                <React.Fragment key={key}>
                  {paramDef.type === 'int' && (
                    <IntRangeInput
                      parameterKey={key}
                      value={paramDef}
                      onChange={(newDef) => handleUpdateParameter(key, newDef)}
                      onRemove={() => handleRemoveParameter(key)}
                    />
                  )}
                  {paramDef.type === 'float' && (
                    <FloatRangeInput
                      parameterKey={key}
                      value={paramDef}
                      onChange={(newDef) => handleUpdateParameter(key, newDef)}
                      onRemove={() => handleRemoveParameter(key)}
                    />
                  )}
                  {paramDef.type === 'categorical' && (
                    <CategoricalInput
                      parameterKey={key}
                      value={paramDef}
                      onChange={(newDef) => handleUpdateParameter(key, newDef)}
                      onRemove={() => handleRemoveParameter(key)}
                    />
                  )}
                </React.Fragment>
              );
            })}
          </div>
        )}
      </div>

      {/* 添加参数区域 */}
      <div className="border-t border-gray-200 dark:border-gray-700 pt-6">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            添加参数
          </h3>

          {/* 分类筛选 */}
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            className="px-3 py-1.5 text-sm border rounded dark:bg-gray-700 dark:border-gray-600"
          >
            {categories.map((cat) => (
              <option key={cat} value={cat}>
                {cat === 'all' ? '全部分类' : cat}
              </option>
            ))}
          </select>
        </div>

        {filteredTemplates.length === 0 ? (
          <div className="p-4 text-center text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800 rounded-lg">
            {selectedCategory === 'all'
              ? '所有参数已添加'
              : `「${selectedCategory}」分类下的参数已全部添加`}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {filteredTemplates.map(([key, { label, category }]) => (
              <button
                key={key}
                onClick={() => {
                  const template = PARAMETER_TEMPLATES[key];
                  handleAddParameter(key, template.defaultDef as ParameterDefinition);
                }}
                className="flex items-center gap-2 p-3 text-left bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:border-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
              >
                <Plus className="w-4 h-4 text-blue-500" />
                <div>
                  <div className="text-sm font-medium text-gray-900 dark:text-white">
                    {label}
                  </div>
                  <div className="text-xs text-gray-500">
                    {key}
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

// ============================================================
// 优化目标选择器
// ============================================================

interface ObjectiveSelectorProps {
  value: OptimizationObjective;
  onChange: (value: OptimizationObjective) => void;
}

export const ObjectiveSelector: React.FC<ObjectiveSelectorProps> = ({
  value,
  onChange,
}) => {
  const objectives: Array<{
    value: OptimizationObjective;
    label: string;
    description: string;
  }> = [
    {
      value: 'sharpe',
      label: '夏普比率',
      description: '收益风险比，越高越好',
    },
    {
      value: 'sortino',
      label: '索提诺比率',
      description: '仅考虑下行风险的收益比',
    },
    {
      value: 'pnl_maxdd',
      label: '收益回撤比',
      description: '总收益与最大回撤的比值',
    },
    {
      value: 'total_return',
      label: '总收益率',
      description: '追求最大绝对收益',
    },
    {
      value: 'win_rate',
      label: '胜率',
      description: '盈利交易占比',
    },
  ];

  return (
    <div className="space-y-2">
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
        优化目标
      </label>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {objectives.map((obj) => (
          <label
            key={obj.value}
            className={`
              relative flex flex-col p-4 border rounded-lg cursor-pointer transition-all
              ${
                value === obj.value
                  ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                  : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'
              }
            `}
          >
            <input
              type="radio"
              name="optimization_objective"
              value={obj.value}
              checked={value === obj.value}
              onChange={() => onChange(obj.value)}
              className="sr-only"
            />
            <div className="flex items-center gap-2">
              <div
                className={`
                  w-4 h-4 rounded-full border-2 flex items-center justify-center
                  ${
                    value === obj.value
                      ? 'border-blue-500 bg-blue-500'
                      : 'border-gray-400'
                  }
                `}
              >
                {value === obj.value && (
                  <div className="w-1.5 h-1.5 rounded-full bg-white" />
                )}
              </div>
              <span className="font-medium text-gray-900 dark:text-white">
                {obj.label}
              </span>
            </div>
            <span className="mt-2 text-xs text-gray-500 dark:text-gray-400 ml-6">
              {obj.description}
            </span>
          </label>
        ))}
      </div>
    </div>
  );
};

export default ParameterSpaceConfig;
