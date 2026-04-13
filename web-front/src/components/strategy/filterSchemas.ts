/**
 * 过滤器参数 Schema 定义
 *
 * 集中管理所有过滤器类型的参数配置元数据，用于动态生成表单字段。
 * 作为 StrategyEditor 过滤器链配置的 SSOT (Single Source of Truth)。
 *
 * @package components/strategy
 */

// ============================================================
// Type Definitions
// ============================================================

/** 单个过滤器参数字段的元数据 */
export interface FilterParamField {
  key: string;
  label: string;
  type: 'number' | 'slider';
  min: number;
  max: number;
  step: number;
  defaultValue: number;
  tooltip?: string;
}

/** 一个过滤器类型的完整 Schema */
export interface FilterSchema {
  label: string;
  description: string;
  params: FilterParamField[];
}

// ============================================================
// Filter Schemas (SSOT)
// ============================================================

export const FILTER_SCHEMAS: Record<string, FilterSchema> = {
  ema_trend: {
    label: 'EMA 趋势',
    description: '只允许与 EMA 趋势方向相同的信号通过',
    params: [
      {
        key: 'period',
        label: 'EMA 周期',
        type: 'slider',
        min: 5,
        max: 200,
        step: 5,
        defaultValue: 60,
        tooltip: 'EMA 计算周期，越大趋势越平滑',
      },
    ],
  },
  mtf: {
    label: 'MTF 多周期',
    description: '检查高一级周期的趋势方向',
    params: [],
  },
  atr: {
    label: 'ATR 波动率',
    description: '过滤波动率过低或过高的信号',
    params: [
      {
        key: 'period',
        label: 'ATR 周期',
        type: 'slider',
        min: 5,
        max: 50,
        step: 1,
        defaultValue: 14,
        tooltip: 'ATR 计算周期',
      },
      {
        key: 'min_atr_ratio',
        label: '最小 ATR 比率',
        type: 'slider',
        min: 0.1,
        max: 3.0,
        step: 0.1,
        defaultValue: 0.5,
        tooltip: 'K 线振幅与 ATR 的最小比值',
      },
    ],
  },
  volume_surge: {
    label: '成交量激增',
    description: '只允许成交量显著高于平均的信号',
    params: [
      {
        key: 'volume_multiplier',
        label: '成交量倍数',
        type: 'slider',
        min: 1.0,
        max: 10.0,
        step: 0.1,
        defaultValue: 2.0,
        tooltip: '成交量需超过平均值的倍数',
      },
    ],
  },
};

// ============================================================
// Helper Functions
// ============================================================

/** 获取过滤器类型的默认参数值 */
export function getFilterDefaultParams(filterType: string): Record<string, any> {
  const schema = FILTER_SCHEMAS[filterType];
  if (!schema) return {};
  const params: Record<string, any> = {};
  for (const field of schema.params) {
    params[field.key] = field.defaultValue;
  }
  return params;
}

/** 获取指定过滤器类型的 Schema，未知类型返回 undefined */
export function getFilterSchema(filterType: string): FilterSchema | undefined {
  return FILTER_SCHEMAS[filterType];
}
