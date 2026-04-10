/**
 * 触发器参数 Schema 定义
 *
 * 集中管理所有触发器类型的参数配置元数据，用于动态生成表单字段。
 * 作为 StrategyForm 和 StrategyEditor 的 SSOT (Single Source of Truth)。
 *
 * @package components/strategy
 */

// ============================================================
// Type Definitions
// ============================================================

/** 单个触发器参数字段的元数据 */
export interface TriggerParamField {
  key: string;
  label: string;
  type: 'number' | 'slider';
  min: number;
  max: number;
  step: number;
  defaultValue: number;
  tooltip?: string;
}

/** 一个触发器类型的完整 Schema */
export interface TriggerSchema {
  label: string;
  description: string;
  params: TriggerParamField[];
}

// ============================================================
// Trigger Schemas (SSOT)
// ============================================================

export const TRIGGER_SCHEMAS: Record<string, TriggerSchema> = {
  pinbar: {
    label: 'Pinbar',
    description: 'Pinbar 形态检测 - 长影线反转信号',
    params: [
      {
        key: 'min_wick_ratio',
        label: '最小影线比例',
        type: 'slider',
        min: 0.1,
        max: 2.0,
        step: 0.05,
        defaultValue: 0.6,
        tooltip: '影线占 K 线总长度的最小比例',
      },
      {
        key: 'max_body_ratio',
        label: '最大实体比例',
        type: 'slider',
        min: 0.05,
        max: 1.0,
        step: 0.05,
        defaultValue: 0.3,
        tooltip: '实体占 K 线总长度的最大比例',
      },
      {
        key: 'body_position_tolerance',
        label: '实体位置容差',
        type: 'slider',
        min: 0,
        max: 0.5,
        step: 0.05,
        defaultValue: 0.1,
        tooltip: '实体位置的容差范围',
      },
    ],
  },
  engulfing: {
    label: '吞没形态',
    description: 'Engulfing Pattern - 看涨/看跌吞没',
    params: [
      {
        key: 'min_body_ratio',
        label: '最小实体比例',
        type: 'slider',
        min: 1.0,
        max: 5.0,
        step: 0.1,
        defaultValue: 1.5,
        tooltip: '吞没 K 线实体与被吞没 K 线实体的最小比例',
      },
      {
        key: 'min_prev_body_ratio',
        label: '最小前 K 线实体比例',
        type: 'slider',
        min: 0.1,
        max: 1.0,
        step: 0.05,
        defaultValue: 0.3,
        tooltip: '前一根 K 线实体的最小比例要求',
      },
    ],
  },
  doji: {
    label: '十字星',
    description: 'Doji - 开盘价与收盘价接近',
    params: [
      {
        key: 'max_body_ratio',
        label: '最大实体比例',
        type: 'slider',
        min: 0.01,
        max: 0.3,
        step: 0.01,
        defaultValue: 0.1,
        tooltip: '实体占 K 线总长度的最大比例，越小越接近十字星',
      },
    ],
  },
  hammer: {
    label: '锤子线',
    description: 'Hammer - 长下影线小实体',
    params: [
      {
        key: 'min_wick_ratio',
        label: '最小影线比例',
        type: 'slider',
        min: 0.1,
        max: 2.0,
        step: 0.05,
        defaultValue: 0.6,
        tooltip: '下影线占 K 线总长度的最小比例',
      },
      {
        key: 'max_body_ratio',
        label: '最大实体比例',
        type: 'slider',
        min: 0.05,
        max: 1.0,
        step: 0.05,
        defaultValue: 0.3,
        tooltip: '实体占 K 线总长度的最大比例',
      },
    ],
  },
};

// ============================================================
// Helper Functions
// ============================================================

/** 获取触发器类型的默认参数值 */
export function getTriggerDefaultParams(triggerType: string): Record<string, number> {
  const schema = TRIGGER_SCHEMAS[triggerType];
  if (!schema) return {};
  const params: Record<string, number> = {};
  for (const field of schema.params) {
    params[field.key] = field.defaultValue;
  }
  return params;
}

/** 获取指定触发器类型的 Schema，未知类型返回 undefined */
export function getTriggerSchema(triggerType: string): TriggerSchema | undefined {
  return TRIGGER_SCHEMAS[triggerType];
}
