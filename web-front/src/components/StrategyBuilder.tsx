import { useState, useCallback, useMemo, Key } from 'react';
import {
  Plus,
  X,
  Settings,
  Trash2,
  GripVertical,
  ChevronDown,
  ChevronRight,
  AlertCircle,
  CheckCircle,
  Filter,
  Zap,
} from 'lucide-react';
import { cn } from '../lib/utils';
import {
  StrategyDefinition,
  TriggerConfig,
  FilterConfig,
  TriggerType,
  FilterType,
  generateId,
  getDefaultFilterParams,
  getDefaultTriggerParams,
  getFilterDisplayName,
  getTriggerDisplayName,
  DEFAULT_SYMBOLS,
  DEFAULT_TIMEFRAMES,
  DEFAULT_SETTLEMENTS,
  buildScopeString,
  parseScopeString,
} from '../lib/api';

// ============================================================================
// Trigger Type Options
// ============================================================================

const TRIGGER_OPTIONS: { type: TriggerType; name: string; description: string }[] = [
  { type: 'pinbar', name: 'Pinbar', description: '针 bar/锤子线形态' },
  { type: 'engulfing', name: 'Engulfing', description: '吞没形态' },
  { type: 'doji', name: 'Doji', description: '十字星' },
  { type: 'hammer', name: 'Hammer', description: '锤子线' },
];

const FILTER_OPTIONS: { type: FilterType; name: string; description: string }[] = [
  { type: 'ema', name: 'EMA 趋势', description: '均线趋势方向校验' },
  { type: 'mtf', name: 'MTF 验证', description: '多周期共振确认' },
  { type: 'volume_surge', name: '成交量激增', description: '成交量异常放大' },
  { type: 'volatility_filter', name: '波动率过滤', description: 'ATR 波动率筛选' },
  { type: 'time_filter', name: '时间窗口', description: '交易时段过滤' },
  { type: 'price_action', name: '价格行为', description: 'K 线形态过滤' },
];

// ============================================================================
// Props
// ============================================================================

interface StrategyBuilderProps {
  strategies: StrategyDefinition[];
  onChange: (strategies: StrategyDefinition[]) => void;
  readOnly?: boolean;
}

interface TriggerEditorProps {
  trigger: TriggerConfig;
  onChange: (trigger: TriggerConfig) => void;
  readOnly?: boolean;
}

interface FilterItemProps {
  filter: FilterConfig;
  onChange: (filter: FilterConfig) => void;
  onRemove: () => void;
  readOnly?: boolean;
  key?: Key;
}

interface StrategyCardProps {
  strategy: StrategyDefinition;
  onChange: (strategy: StrategyDefinition) => void;
  onRemove: () => void;
  readOnly?: boolean;
  key?: Key;
}

interface AddFilterMenuProps {
  onAdd: (type: FilterType) => void;
}

interface AddStrategyMenuProps {
  onAdd: (type: TriggerType) => void;
}

// ============================================================================
// Trigger Parameter Editors
// ============================================================================

function PinbarParamsEditor({
  params,
  onChange,
  readOnly,
}: {
  params: any;
  onChange: (params: any) => void;
  readOnly?: boolean;
}) {
  return (
    <div className="space-y-3">
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          最小影线比率
        </label>
        <input
          type="number"
          step="0.05"
          min="0.1"
          max="0.9"
          value={params.min_wick_ratio}
          onChange={(e) => onChange({ ...params, min_wick_ratio: parseFloat(e.target.value) || 0 })}
          disabled={readOnly}
          className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          最大实体比率
        </label>
        <input
          type="number"
          step="0.05"
          min="0.05"
          max="0.5"
          value={params.max_body_ratio}
          onChange={(e) => onChange({ ...params, max_body_ratio: parseFloat(e.target.value) || 0 })}
          disabled={readOnly}
          className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          实体位置容差
        </label>
        <input
          type="number"
          step="0.05"
          min="0.05"
          max="0.3"
          value={params.body_position_tolerance}
          onChange={(e) => onChange({ ...params, body_position_tolerance: parseFloat(e.target.value) || 0 })}
          disabled={readOnly}
          className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
        />
      </div>
    </div>
  );
}

function EngulfingParamsEditor({
  params,
  onChange,
  readOnly,
}: {
  params: any;
  onChange: (params: any) => void;
  readOnly?: boolean;
}) {
  return (
    <div className="space-y-3">
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          最小实体比率
        </label>
        <input
          type="number"
          step="0.05"
          min="0.1"
          max="0.9"
          value={params.min_body_ratio}
          onChange={(e) => onChange({ ...params, min_body_ratio: parseFloat(e.target.value) || 0 })}
          disabled={readOnly}
          className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
        />
      </div>
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={params.require_full_engulf}
          onChange={(e) => onChange({ ...params, require_full_engulf: e.target.checked })}
          disabled={readOnly}
          className="rounded border-gray-300 text-black focus:ring-black"
        />
        <label className="text-xs text-gray-600">要求完全吞没</label>
      </div>
    </div>
  );
}

function DojiParamsEditor({
  params,
  onChange,
  readOnly,
}: {
  params: any;
  onChange: (params: any) => void;
  readOnly?: boolean;
}) {
  return (
    <div className="space-y-3">
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          最大实体比率
        </label>
        <input
          type="number"
          step="0.01"
          min="0.01"
          max="0.2"
          value={params.max_body_ratio}
          onChange={(e) => onChange({ ...params, max_body_ratio: parseFloat(e.target.value) || 0 })}
          disabled={readOnly}
          className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          最小总范围
        </label>
        <input
          type="number"
          step="0.0001"
          min="0.0001"
          value={params.min_total_range}
          onChange={(e) => onChange({ ...params, min_total_range: parseFloat(e.target.value) || 0 })}
          disabled={readOnly}
          className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
        />
      </div>
    </div>
  );
}

function HammerParamsEditor({
  params,
  onChange,
  readOnly,
}: {
  params: any;
  onChange: (params: any) => void;
  readOnly?: boolean;
}) {
  return (
    <div className="space-y-3">
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          最小下影线比率
        </label>
        <input
          type="number"
          step="0.05"
          min="0.3"
          max="0.9"
          value={params.min_lower_wick_ratio}
          onChange={(e) => onChange({ ...params, min_lower_wick_ratio: parseFloat(e.target.value) || 0 })}
          disabled={readOnly}
          className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          最大上影线比率
        </label>
        <input
          type="number"
          step="0.05"
          min="0"
          max="0.5"
          value={params.max_upper_wick_ratio}
          onChange={(e) => onChange({ ...params, max_upper_wick_ratio: parseFloat(e.target.value) || 0 })}
          disabled={readOnly}
          className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          最小实体比率
        </label>
        <input
          type="number"
          step="0.05"
          min="0.05"
          max="0.3"
          value={params.min_body_ratio}
          onChange={(e) => onChange({ ...params, min_body_ratio: parseFloat(e.target.value) || 0 })}
          disabled={readOnly}
          className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
        />
      </div>
    </div>
  );
}

// ============================================================================
// Filter Parameter Editors
// ============================================================================

/**
 * Generic filter editor that dynamically renders form fields based on paramsSchema
 * Supports: number, string, boolean, enum (select)
 */
function GenericFilterEditor({
  params,
  onChange,
  readOnly,
}: {
  params: any;
  onChange: (params: any) => void;
  readOnly?: boolean;
}) {
  const renderField = (key: string, schema: any, value: any) => {
    const handleChange = (newValue: any) => {
      onChange({ ...params, [key]: newValue });
    };

    switch (schema.type) {
      case 'boolean':
        return (
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={value ?? schema.default ?? false}
              onChange={(e) => handleChange(e.target.checked)}
              disabled={readOnly}
              className="rounded border-gray-300 text-black focus:ring-black"
            />
            <label className="text-xs text-gray-600">{schema.description || key}</label>
          </div>
        );
      case 'number':
        return (
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              {schema.description || key}
            </label>
            <input
              type="number"
              step={schema.type === 'number' ? '0.1' : '1'}
              min={schema.min}
              max={schema.max}
              value={value ?? schema.default ?? ''}
              onChange={(e) => handleChange(schema.type === 'number' ? parseFloat(e.target.value) || schema.default : parseInt(e.target.value) || schema.default)}
              disabled={readOnly}
              className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
            />
          </div>
        );
      case 'string':
        if (schema.enum) {
          return (
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                {schema.description || key}
              </label>
              <select
                value={value ?? schema.default ?? ''}
                onChange={(e) => handleChange(e.target.value)}
                disabled={readOnly}
                className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
              >
                {schema.enum.map((opt: string) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            </div>
          );
        }
        return (
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              {schema.description || key}
            </label>
            <input
              type="text"
              value={value ?? schema.default ?? ''}
              onChange={(e) => handleChange(e.target.value)}
              disabled={readOnly}
              className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
            />
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="space-y-3">
      {Object.entries(params).map(([key, value]) => (
        <div key={key}>
          {renderField(key, { type: typeof value, description: key }, value)}
        </div>
      ))}
    </div>
  );
}

function EmaFilterEditor({
  params,
  onChange,
  readOnly,
}: {
  params: any;
  onChange: (params: any) => void;
  readOnly?: boolean;
}) {
  return (
    <div className="space-y-3">
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          EMA 周期
        </label>
        <input
          type="number"
          step="1"
          min="5"
          max="200"
          value={params.period}
          onChange={(e) => onChange({ ...params, period: parseInt(e.target.value) || 60 })}
          disabled={readOnly}
          className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          趋势方向
        </label>
        <select
          value={params.trend_direction || 'either'}
          onChange={(e) => onChange({ ...params, trend_direction: e.target.value })}
          disabled={readOnly}
          className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
        >
          <option value="either">任意方向</option>
          <option value="bullish">仅多头</option>
          <option value="bearish">仅空头</option>
        </select>
      </div>
    </div>
  );
}

function VolumeSurgeFilterEditor({
  params,
  onChange,
  readOnly,
}: {
  params: any;
  onChange: (params: any) => void;
  readOnly?: boolean;
}) {
  return (
    <div className="space-y-3">
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          成交量倍数
        </label>
        <input
          type="number"
          step="0.1"
          min="1"
          max="5"
          value={params.multiplier}
          onChange={(e) => onChange({ ...params, multiplier: parseFloat(e.target.value) || 1.5 })}
          disabled={readOnly}
          className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          回看周期数
        </label>
        <input
          type="number"
          step="1"
          min="5"
          max="100"
          value={params.lookback_periods}
          onChange={(e) => onChange({ ...params, lookback_periods: parseInt(e.target.value) || 20 })}
          disabled={readOnly}
          className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
        />
      </div>
    </div>
  );
}

function VolatilityFilterEditor({
  params,
  onChange,
  readOnly,
}: {
  params: any;
  onChange: (params: any) => void;
  readOnly?: boolean;
}) {
  return (
    <div className="space-y-3">
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          最小 ATR 比率
        </label>
        <input
          type="number"
          step="0.1"
          min="0.1"
          max="2"
          value={params.min_atr_ratio}
          onChange={(e) => onChange({ ...params, min_atr_ratio: parseFloat(e.target.value) || 0.5 })}
          disabled={readOnly}
          className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          最大 ATR 比率
        </label>
        <input
          type="number"
          step="0.1"
          min="1"
          max="5"
          value={params.max_atr_ratio}
          onChange={(e) => onChange({ ...params, max_atr_ratio: parseFloat(e.target.value) || 3 })}
          disabled={readOnly}
          className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          ATR 周期
        </label>
        <input
          type="number"
          step="1"
          min="7"
          max="28"
          value={params.atr_period}
          onChange={(e) => onChange({ ...params, atr_period: parseInt(e.target.value) || 14 })}
          disabled={readOnly}
          className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
        />
      </div>
    </div>
  );
}

function TimeFilterEditor({
  params,
  onChange,
  readOnly,
}: {
  params: any;
  onChange: (params: any) => void;
  readOnly?: boolean;
}) {
  return (
    <div className="space-y-3">
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          交易时段
        </label>
        <select
          value={params.session || 'any'}
          onChange={(e) => onChange({ ...params, session: e.target.value })}
          disabled={readOnly}
          className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
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
          checked={params.exclude_weekend}
          onChange={(e) => onChange({ ...params, exclude_weekend: e.target.checked })}
          disabled={readOnly}
          className="rounded border-gray-300 text-black focus:ring-black"
        />
        <label className="text-xs text-gray-600">排除周末</label>
      </div>
    </div>
  );
}

function PriceActionFilterEditor({
  params,
  onChange,
  readOnly,
}: {
  params: any;
  onChange: (params: any) => void;
  readOnly?: boolean;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={params.require_closed_candle}
          onChange={(e) => onChange({ ...params, require_closed_candle: e.target.checked })}
          disabled={readOnly}
          className="rounded border-gray-300 text-black focus:ring-black"
        />
        <label className="text-xs text-gray-600">要求 K 线闭合</label>
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          最小实体比率
        </label>
        <input
          type="number"
          step="0.05"
          min="0"
          max="0.5"
          value={params.min_body_size || 0}
          onChange={(e) => onChange({ ...params, min_body_size: parseFloat(e.target.value) || 0 })}
          disabled={readOnly}
          className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          最大实体比率
        </label>
        <input
          type="number"
          step="0.05"
          min="0.1"
          max="1"
          value={params.max_body_size || 1}
          onChange={(e) => onChange({ ...params, max_body_size: parseFloat(e.target.value) || 1 })}
          disabled={readOnly}
          className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
        />
      </div>
    </div>
  );
}

// ============================================================================
// Trigger Editor Component
// ============================================================================

function TriggerEditor({ trigger, onChange, readOnly }: TriggerEditorProps) {
  const handleParamsChange = useCallback(
    (newParams: any) => {
      onChange({ ...trigger, params: newParams });
    },
    [trigger, onChange]
  );

  const renderParamsEditor = () => {
    switch (trigger.type) {
      case 'pinbar':
        return <PinbarParamsEditor params={trigger.params} onChange={handleParamsChange} readOnly={readOnly} />;
      case 'engulfing':
        return <EngulfingParamsEditor params={trigger.params} onChange={handleParamsChange} readOnly={readOnly} />;
      case 'doji':
        return <DojiParamsEditor params={trigger.params} onChange={handleParamsChange} readOnly={readOnly} />;
      case 'hammer':
        return <HammerParamsEditor params={trigger.params} onChange={handleParamsChange} readOnly={readOnly} />;
      default:
        return <div className="text-xs text-gray-400">未知触发器类型</div>;
    }
  };

  return (
    <div className="space-y-3">
      {!readOnly && (
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">
            触发器类型
          </label>
          <select
            value={trigger.type}
            onChange={(e) => {
              const newType = e.target.value as TriggerType;
              onChange({
                ...trigger,
                type: newType,
                params: getDefaultTriggerParams(newType),
              });
            }}
            disabled={readOnly}
            className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-black transition-colors disabled:bg-gray-100"
          >
            {TRIGGER_OPTIONS.map((opt) => (
              <option key={opt.type} value={opt.type}>
                {opt.name} - {opt.description}
              </option>
            ))}
          </select>
        </div>
      )}
      {renderParamsEditor()}
    </div>
  );
}

// ============================================================================
// Filter Item Component
// ============================================================================

function FilterItem({ filter, onChange, onRemove, readOnly }: FilterItemProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  const handleParamsChange = useCallback(
    (newParams: any) => {
      onChange({ ...filter, params: newParams });
    },
    [filter, onChange]
  );

  const renderParamsEditor = () => {
    switch (filter.type) {
      case 'ema':
        return <EmaFilterEditor params={filter.params} onChange={handleParamsChange} readOnly={readOnly} />;
      case 'mtf':
        // MTF 使用通用动态渲染，底层自动推导周期，不需要 higher_timeframe 参数
        return <GenericFilterEditor params={filter.params} onChange={handleParamsChange} readOnly={readOnly} />;
      case 'volume_surge':
        return <VolumeSurgeFilterEditor params={filter.params} onChange={handleParamsChange} readOnly={readOnly} />;
      case 'volatility_filter':
        return <VolatilityFilterEditor params={filter.params} onChange={handleParamsChange} readOnly={readOnly} />;
      case 'time_filter':
        return <TimeFilterEditor params={filter.params} onChange={handleParamsChange} readOnly={readOnly} />;
      case 'price_action':
        return <PriceActionFilterEditor params={filter.params} onChange={handleParamsChange} readOnly={readOnly} />;
      default:
        return <div className="text-xs text-gray-400">未知过滤器类型</div>;
    }
  };

  return (
    <div className="border border-gray-200 rounded-lg bg-white overflow-hidden">
      {/* Filter Header */}
      <div className="flex items-center gap-2 px-3 py-2 bg-gray-50 border-b border-gray-200">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="p-1 hover:bg-gray-200 rounded transition-colors"
          disabled={readOnly}
        >
          {isExpanded ? (
            <ChevronDown className="w-4 h-4 text-gray-500" />
          ) : (
            <ChevronRight className="w-4 h-4 text-gray-500" />
          )}
        </button>
        <Filter className="w-4 h-4 text-gray-400" />
        <span className="flex-1 text-sm font-medium text-gray-700">
          {getFilterDisplayName(filter.type)}
        </span>
        <label className="flex items-center gap-1 text-xs text-gray-500">
          <input
            type="checkbox"
            checked={filter.enabled}
            onChange={(e) => onChange({ ...filter, enabled: e.target.checked })}
            disabled={readOnly}
            className="rounded border-gray-300 text-black focus:ring-black"
          />
          启用
        </label>
        {!readOnly && (
          <button
            onClick={onRemove}
            className="p-1 hover:bg-red-100 rounded transition-colors"
          >
            <X className="w-4 h-4 text-red-500" />
          </button>
        )}
      </div>

      {/* Filter Body */}
      {isExpanded && (
        <div className="p-3 space-y-3">{renderParamsEditor()}</div>
      )}
    </div>
  );
}

// ============================================================================
// Add Filter Menu Component
// ============================================================================

function AddFilterMenu({ onAdd }: AddFilterMenuProps) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full py-2 border-2 border-dashed border-gray-300 rounded-lg text-gray-500 text-sm font-medium hover:border-black hover:text-black transition-colors flex items-center justify-center gap-2"
      >
        <Plus className="w-4 h-4" />
        串联新过滤器
      </button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-50"
            onClick={() => setIsOpen(false)}
            aria-label="Close menu"
          />
          <div
            className="fixed left-1/2 -translate-x-1/2 top-[280px] w-full max-w-md bg-white rounded-lg shadow-xl border border-gray-200 z-[60] max-h-64 overflow-y-auto"
            style={{ marginLeft: 'max(-200px, calc(-50vw + 200px))' }}
          >
            <div className="p-2 border-b border-gray-100 flex items-center justify-between sticky top-0 bg-white">
              <span className="text-xs font-medium text-gray-500">选择过滤器类型</span>
              <button
                onClick={() => setIsOpen(false)}
                className="p-1 hover:bg-gray-100 rounded"
              >
                <X className="w-3 h-3 text-gray-400" />
              </button>
            </div>
            {FILTER_OPTIONS.map((opt) => (
              <button
                key={opt.type}
                onClick={() => {
                  onAdd(opt.type);
                  setIsOpen(false);
                }}
                className="w-full px-4 py-3 text-left hover:bg-gray-50 transition-colors border-b border-gray-100 last:border-b-0"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-blue-50 flex items-center justify-center flex-shrink-0">
                    <Filter className="w-4 h-4 text-blue-500" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-gray-900">
                      {opt.name}
                    </div>
                    <div className="text-xs text-gray-500 truncate">
                      {opt.description}
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ============================================================================
// Strategy Card Component
// ============================================================================

interface StrategyCardProps {
  strategy: StrategyDefinition;
  onChange: (strategy: StrategyDefinition) => void;
  onRemove: () => void;
  readOnly?: boolean;
}

function StrategyCard({
  strategy,
  onChange,
  onRemove,
  readOnly,
}: StrategyCardProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  const handleTriggerChange = useCallback(
    (newTrigger: TriggerConfig) => {
      onChange({ ...strategy, trigger: newTrigger });
    },
    [strategy, onChange]
  );

  const handleFilterChange = useCallback(
    (index: number, newFilter: FilterConfig) => {
      const newFilters = [...strategy.filters];
      newFilters[index] = newFilter;
      onChange({ ...strategy, filters: newFilters });
    },
    [strategy, onChange]
  );

  const handleFilterRemove = useCallback(
    (index: number) => {
      const newFilters = strategy.filters.filter((_, i) => i !== index);
      onChange({ ...strategy, filters: newFilters });
    },
    [strategy, onChange]
  );

  const handleAddFilter = useCallback(
    (type: FilterType) => {
      const newFilter: FilterConfig = {
        id: generateId(),
        type,
        enabled: true,
        params: getDefaultFilterParams(type),
      };
      onChange({ ...strategy, filters: [...strategy.filters, newFilter] });
    },
    [strategy, onChange]
  );

  const handleFilterLogicChange = useCallback(
    (newLogic: 'AND' | 'OR') => {
      onChange({ ...strategy, filter_logic: newLogic });
    },
    [strategy, onChange]
  );

  const handleIsGlobalChange = useCallback(
    (checked: boolean) => {
      onChange({
        ...strategy,
        is_global: checked,
        // When enabling global, clear apply_to; when disabling, initialize with empty array
        apply_to: checked ? [] : strategy.apply_to
      });
    },
    [strategy, onChange]
  );

  const handleAddScope = useCallback(
    (symbol: string, settlement: string, timeframe: string) => {
      const scopeString = buildScopeString(symbol, settlement, timeframe);
      if (!strategy.apply_to.includes(scopeString)) {
        onChange({ ...strategy, apply_to: [...strategy.apply_to, scopeString] });
      }
    },
    [strategy, onChange]
  );

  const handleRemoveScope = useCallback(
    (index: number) => {
      const newApplyTo = strategy.apply_to.filter((_, i) => i !== index);
      onChange({ ...strategy, apply_to: newApplyTo });
    },
    [strategy, onChange]
  );

  return (
    <div className="border border-gray-200 rounded-xl bg-white overflow-hidden shadow-sm">
      {/* Strategy Header */}
      <div className="flex items-center gap-3 px-4 py-3 bg-gradient-to-r from-gray-50 to-white border-b border-gray-200">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="p-1 hover:bg-gray-200 rounded transition-colors"
        >
          {isExpanded ? (
            <ChevronDown className="w-5 h-5 text-gray-500" />
          ) : (
            <ChevronRight className="w-5 h-5 text-gray-500" />
          )}
        </button>
        <Zap className="w-5 h-5 text-amber-500" />
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-gray-900">{strategy.name}</h3>
          <p className="text-xs text-gray-500">
            {getTriggerDisplayName(strategy.trigger.type)} • {strategy.filters.length} 过滤器
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1 text-xs text-gray-500">
            <input
              type="checkbox"
              checked={strategy.trigger.enabled}
              onChange={(e) =>
                onChange({ ...strategy, trigger: { ...strategy.trigger, enabled: e.target.checked } })
              }
              disabled={readOnly}
              className="rounded border-gray-300 text-black focus:ring-black"
            />
            启用策略
          </label>
          {!readOnly && (
            <button
              onClick={onRemove}
              className="p-2 hover:bg-red-100 rounded-lg transition-colors"
            >
              <Trash2 className="w-4 h-4 text-red-500" />
            </button>
          )}
        </div>
      </div>

      {/* Strategy Body */}
      {isExpanded && (
        <div className="p-4 space-y-4">
          {/* Trigger Section */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Zap className="w-4 h-4 text-amber-500" />
              <h4 className="text-sm font-medium text-gray-700">触发器配置</h4>
            </div>
            <div className="pl-6">
              <TriggerEditor
                trigger={strategy.trigger}
                onChange={handleTriggerChange}
                readOnly={readOnly}
              />
            </div>
          </div>

          {/* Filters Section */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Filter className="w-4 h-4 text-blue-500" />
                <h4 className="text-sm font-medium text-gray-700">过滤器链</h4>
              </div>
              {!readOnly && (
                <select
                  value={strategy.filter_logic}
                  onChange={(e) =>
                    handleFilterLogicChange(e.target.value as 'AND' | 'OR')
                  }
                  className="text-xs rounded-md border border-gray-300 px-2 py-1 outline-none focus:border-black"
                >
                  <option value="AND">全部满足 (AND)</option>
                  <option value="OR">任一满足 (OR)</option>
                </select>
              )}
            </div>
            <div className="pl-6 space-y-2">
              {strategy.filters.length === 0 ? (
                <div className="text-sm text-gray-400 italic py-4 text-center border border-dashed border-gray-200 rounded-lg">
                  暂无过滤器，点击下方按钮添加
                </div>
              ) : (
                strategy.filters.map((filter, index) => (
                  <FilterItem
                    key={filter.id}
                    filter={filter}
                    onChange={(f) => handleFilterChange(index, f)}
                    onRemove={() => handleFilterRemove(index)}
                    readOnly={readOnly}
                  />
                ))
              )}
              {!readOnly && (
                <AddFilterMenu onAdd={handleAddFilter} />
              )}
            </div>
          </div>

          {/* Scope Configuration Section */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded bg-purple-100 flex items-center justify-center">
                <svg className="w-3 h-3 text-purple-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <h4 className="text-sm font-medium text-gray-700">作用域配置</h4>
            </div>
            <div className="pl-6 space-y-3">
              {/* Global Switch */}
              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-200">
                <div>
                  <p className="text-sm font-medium text-gray-700">应用于全局</p>
                  <p className="text-xs text-gray-500">开启后策略将对所有币种和周期生效</p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={strategy.is_global !== false}
                    onChange={(e) => handleIsGlobalChange(e.target.checked)}
                    disabled={readOnly}
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-gray-300 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-purple-300 rounded-full peer peer-checked:bg-purple-600 peer-disabled:opacity-50 peer-disabled:cursor-not-allowed transition-colors">
                    <div className="w-4 h-4 bg-white rounded-full absolute top-1 left-1 peer-checked:left-6 transition-all" />
                  </div>
                </label>
              </div>

              {/* Apply To Selector - only shown when is_global is false */}
              {!strategy.is_global && !readOnly && (
                <div className="space-y-3">
                  <div className="p-3 bg-purple-50 rounded-lg border border-purple-200">
                    <p className="text-sm font-medium text-purple-800 mb-2">指定生效范围</p>
                    <div className="flex gap-2 flex-wrap">
                      <select
                        onChange={(e) => {
                          const symbol = e.target.value;
                          const currentSettlement = 'USDT';
                          const currentTimeframe = '15m';
                          if (symbol) handleAddScope(symbol, currentSettlement, currentTimeframe);
                          e.target.value = '';
                        }}
                        className="text-sm rounded-md border border-purple-300 px-2 py-1.5 outline-none focus:border-purple-500 bg-white"
                        defaultValue=""
                      >
                        <option value="">+ 添加币种</option>
                        {DEFAULT_SYMBOLS.map(sym => (
                          <option key={sym} value={sym}>{sym}</option>
                        ))}
                      </select>
                      <select
                        onChange={(e) => {
                          const timeframe = e.target.value;
                          if (timeframe && strategy.apply_to.length > 0) {
                            // Update all current scopes with new timeframe
                            const updated = strategy.apply_to.map(scope => {
                              const parsed = parseScopeString(scope);
                              if (parsed) {
                                return buildScopeString(parsed.symbol, parsed.settlement, timeframe);
                              }
                              return scope;
                            });
                            onChange({ ...strategy, apply_to: updated });
                          }
                          e.target.value = '';
                        }}
                        className="text-sm rounded-md border border-purple-300 px-2 py-1.5 outline-none focus:border-purple-500 bg-white"
                        defaultValue=""
                      >
                        <option value="">批量设置周期</option>
                        {DEFAULT_TIMEFRAMES.map(tf => (
                          <option key={tf} value={tf}>{tf}</option>
                        ))}
                      </select>
                    </div>
                  </div>

                  {/* Selected Scopes List */}
                  {strategy.apply_to.length > 0 ? (
                    <div className="space-y-1">
                      {strategy.apply_to.map((scope, index) => {
                        const parsed = parseScopeString(scope);
                        return (
                          <div
                            key={scope}
                            className="flex items-center justify-between p-2 bg-white border border-gray-200 rounded-md"
                          >
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-medium text-gray-700">
                                {parsed ? `${parsed.symbol} • ${parsed.timeframe}` : scope}
                              </span>
                            </div>
                            <button
                              onClick={() => handleRemoveScope(index)}
                              className="p-1 hover:bg-red-50 rounded transition-colors"
                            >
                              <X className="w-3.5 h-3.5 text-red-500" />
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="text-sm text-gray-400 italic py-3 text-center border border-dashed border-gray-200 rounded-lg">
                      点击上方"添加币种"按钮指定生效范围
                    </div>
                  )}
                </div>
              )}

              {/* Read-only display of scope */}
              {!readOnly && strategy.is_global && (
                <div className="p-3 bg-green-50 border border-green-200 rounded-lg">
                  <p className="text-xs text-green-700 flex items-center gap-1">
                    <CheckCircle className="w-3.5 h-3.5" />
                    策略将对所有币种和周期生效
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Add Strategy Menu
// ============================================================================

function AddStrategyMenu({ onAdd }: { onAdd: (type: TriggerType) => void }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full py-4 border-2 border-dashed border-gray-300 rounded-xl text-gray-500 font-medium hover:border-black hover:text-black transition-colors flex items-center justify-center gap-2"
      >
        <Plus className="w-5 h-5" />
        新增策略触发器
      </button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-50"
            onClick={() => setIsOpen(false)}
            aria-label="Close menu"
          />
          <div
            className="fixed left-1/2 -translate-x-1/2 top-[200px] w-full max-w-md bg-white rounded-xl shadow-xl border border-gray-200 z-[60] max-h-[80vh] overflow-y-auto"
          >
            <div className="p-3 border-b border-gray-100 flex items-center justify-between sticky top-0 bg-white">
              <h3 className="text-sm font-semibold text-gray-900">选择触发器类型</h3>
              <button
                onClick={() => setIsOpen(false)}
                className="p-1 hover:bg-gray-100 rounded"
              >
                <X className="w-4 h-4 text-gray-400" />
              </button>
            </div>
            {TRIGGER_OPTIONS.map((opt) => (
              <button
                key={opt.type}
                onClick={() => {
                  onAdd(opt.type);
                  setIsOpen(false);
                }}
                className="w-full px-4 py-3 text-left hover:bg-gray-50 transition-colors border-b border-gray-100 last:border-b-0"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-amber-100 flex items-center justify-center flex-shrink-0">
                    <Zap className="w-4 h-4 text-amber-600" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-gray-900">
                      {opt.name}
                    </div>
                    <div className="text-xs text-gray-500">
                      {opt.description}
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ============================================================================
// Main StrategyBuilder Component
// ============================================================================

export default function StrategyBuilder({
  strategies,
  onChange,
  readOnly = false,
}: StrategyBuilderProps) {
  const handleAddStrategy = useCallback(
    (triggerType: TriggerType) => {
      const newStrategy: StrategyDefinition = {
        id: generateId(),
        name: `新策略 ${strategies.length + 1}`,
        trigger: {
          id: generateId(),
          type: triggerType,
          enabled: true,
          params: getDefaultTriggerParams(triggerType),
        },
        filters: [],
        filter_logic: 'AND',
        is_global: true,
        apply_to: [],
      };
      onChange([...strategies, newStrategy]);
    },
    [strategies, onChange]
  );

  const handleStrategyChange = useCallback(
    (index: number, newStrategy: StrategyDefinition) => {
      const newStrategies = [...strategies];
      newStrategies[index] = newStrategy;
      onChange(newStrategies);
    },
    [strategies, onChange]
  );

  const handleStrategyRemove = useCallback(
    (index: number) => {
      const newStrategies = strategies.filter((_, i) => i !== index);
      onChange(newStrategies);
    },
    [strategies, onChange]
  );

  return (
    <div className="space-y-4">
      {strategies.length === 0 ? (
        <div className="text-center py-12 bg-gray-50 rounded-xl">
          <Zap className="w-12 h-12 text-gray-300 mx-auto mb-3" />
          <p className="text-sm text-gray-500">暂无策略配置</p>
          <p className="text-xs text-gray-400 mt-1">点击下方按钮创建第一个策略</p>
        </div>
      ) : (
        strategies.map((strategy, index) => (
          <StrategyCard
            key={strategy.id}
            strategy={strategy}
            onChange={(s) => handleStrategyChange(index, s)}
            onRemove={() => handleStrategyRemove(index)}
            readOnly={readOnly}
          />
        ))
      )}

      {!readOnly && <AddStrategyMenu onAdd={handleAddStrategy} />}

      {/* Validation Warning */}
      {!readOnly && strategies.length === 0 && (
        <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm text-amber-800 font-medium">未配置策略</p>
            <p className="text-xs text-amber-600 mt-1">
              请至少添加一个策略触发器才能执行回测或保存配置
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
