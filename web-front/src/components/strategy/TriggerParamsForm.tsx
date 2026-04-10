/**
 * 触发器参数动态表单组件
 *
 * 根据触发器类型 (triggerType) 自动渲染对应的参数配置字段。
 * 使用 Slider + InputNumber 联动，直接集成到父级 Ant Design Form 中。
 *
 * @package components/strategy
 */

import React from 'react';
import { Form, Slider, InputNumber, FormInstance } from 'antd';
import { getTriggerSchema, getTriggerDefaultParams } from './triggerSchemas';

// ============================================================
// Props Interface
// ============================================================

export interface TriggerParamsFormProps {
  /** 触发器类型 (pinbar / engulfing / doji / hammer) */
  triggerType: string;
  /** Ant Design 表单实例，用于注册子字段 */
  form: FormInstance;
  /** 是否禁用（加载状态） */
  disabled?: boolean;
}

// ============================================================
// TriggerParamsForm Component
// ============================================================

/**
 * 动态触发器参数表单
 *
 * 根据 triggerType 从 triggerSchemas 中获取参数定义，
 * 渲染 Slider + InputNumber 联动控件，字段值直接写入父级 form。
 *
 * 使用方式：
 *   <TriggerParamsForm triggerType={watchedTriggerType} form={form} />
 *
 * 字段路径：trigger_params.{paramKey}
 */
export const TriggerParamsForm: React.FC<TriggerParamsFormProps> = ({
  triggerType,
  form,
  disabled = false,
}) => {
  const schema = getTriggerSchema(triggerType);

  // 未知触发器类型的兜底处理
  if (!schema) {
    return (
      <div className="text-sm text-gray-400 py-2">
        未知触发器类型: {triggerType}，暂无参数配置
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {schema.params.map((field) => {
        const fieldPath = ['trigger_params', field.key];

        return (
          <Form.Item
            key={field.key}
            name={fieldPath}
            label={field.label}
            tooltip={field.tooltip}
            rules={[
              {
                type: 'number',
                min: field.min,
                max: field.max,
                message: `${field.label} 范围为 ${field.min} ~ ${field.max}`,
              },
            ]}
            initialValue={field.defaultValue}
          >
            <SliderInputNumber
              min={field.min}
              max={field.max}
              step={field.step}
              disabled={disabled}
            />
          </Form.Item>
        );
      })}
    </div>
  );
};

// ============================================================
// SliderInputNumber - Slider 与 InputNumber 联动控件
// ============================================================

interface SliderInputNumberProps {
  min: number;
  max: number;
  step: number;
  disabled?: boolean;
}

/**
 * Slider 与 InputNumber 联动复合控件
 *
 * 通过 value / onChange 受控模式实现双向同步：
 * - 拖动 Slider 时 InputNumber 同步更新
 * - 修改 InputNumber 时 Slider 同步更新
 */
const SliderInputNumber: React.FC<SliderInputNumberProps> = ({
  min,
  max,
  step,
  disabled,
}) => {
  return (
    <div className="flex items-center gap-3">
      <Slider
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        className="flex-1"
      />
      <InputNumber
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        className="w-24"
        controls={false}
      />
    </div>
  );
};

export default TriggerParamsForm;
