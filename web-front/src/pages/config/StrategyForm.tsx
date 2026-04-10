/**
 * 策略创建/编辑表单组件
 *
 * 用于创建和编辑策略配置，支持：
 * - 触发器类型选择
 * - 过滤器配置（预留）
 * - 币种和周期选择
 * - 策略启用/禁用
 */

import React, { useEffect } from 'react';
import { Modal, Form, Input, Select, Switch, FormInstance } from 'antd';
import type {
  Strategy,
  CreateStrategyRequest,
  UpdateStrategyRequest,
} from '../../api/config';
import { TriggerParamsForm } from '../../components/strategy/TriggerParamsForm';
import { getTriggerDefaultParams } from '../../components/strategy/triggerSchemas';

const { Option } = Select;
const { TextArea } = Input;

// ============================================================
// Trigger and Filter Options
// ============================================================

const TRIGGER_OPTIONS = [
  { value: 'pinbar', label: 'Pinbar 形态' },
  { value: 'engulfing', label: '吞没形态' },
  { value: 'doji', label: '十字星' },
  { value: 'hammer', label: '锤头线' },
];

const SYMBOL_OPTIONS = [
  { value: 'BTC/USDT:USDT', label: 'BTC/USDT' },
  { value: 'ETH/USDT:USDT', label: 'ETH/USDT' },
  { value: 'SOL/USDT:USDT', label: 'SOL/USDT' },
  { value: 'BNB/USDT:USDT', label: 'BNB/USDT' },
];

const TIMEFRAME_OPTIONS = [
  { value: '15m', label: '15 分钟' },
  { value: '1h', label: '1 小时' },
  { value: '4h', label: '4 小时' },
  { value: '1d', label: '1 天' },
  { value: '1w', label: '1 周' },
];

const FILTER_LOGIC_OPTIONS = [
  { value: 'AND', label: '全部满足 (AND)' },
  { value: 'OR', label: '任一满足 (OR)' },
];

// ============================================================
// Props Interface
// ============================================================

export interface StrategyFormProps {
  visible: boolean;
  strategy?: Strategy | null;
  onCancel: () => void;
  onSubmit: (values: CreateStrategyRequest | UpdateStrategyRequest) => void;
  loading?: boolean;
}

// ============================================================
// StrategyForm Component
// ============================================================

export const StrategyForm: React.FC<StrategyFormProps> = ({
  visible,
  strategy,
  onCancel,
  onSubmit,
  loading = false,
}) => {
  const [form] = Form.useForm();
  const isEdit = !!strategy;

  // 监听触发器类型变化，切换时重置参数为默认值
  const triggerType = Form.useWatch('trigger_type', form) || 'pinbar';

  // 重置表单数据当模态框打开时
  useEffect(() => {
    if (visible) {
      if (strategy) {
        // 编辑模式：填充现有数据
        const triggerType = strategy.trigger_config?.type || 'pinbar';
        form.setFieldsValue({
          name: strategy.name,
          description: strategy.description,
          is_active: strategy.is_active,
          trigger_type: triggerType,
          filter_logic: strategy.filter_logic || 'AND',
          symbols: strategy.symbols || [],
          timeframes: strategy.timeframes || [],
          trigger_params:
            strategy.trigger_config?.params ||
            getTriggerDefaultParams(triggerType),
        });
      } else {
        // 创建模式：使用默认值
        form.resetFields();
        form.setFieldsValue({
          is_active: true,
          trigger_type: 'pinbar',
          filter_logic: 'AND',
          symbols: ['BTC/USDT:USDT'],
          timeframes: ['1h'],
          trigger_params: getTriggerDefaultParams('pinbar'),
        });
      }
    }
  }, [visible, strategy, form]);

  // 处理表单提交
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();

      const payload: CreateStrategyRequest | UpdateStrategyRequest = {
        name: values.name,
        description: values.description,
        is_active: values.is_active,
        trigger_config: {
          type: values.trigger_type,
          params: values.trigger_params || {},
        },
        filter_configs: [], // TODO: 添加过滤器配置表单
        filter_logic: values.filter_logic,
        symbols: values.symbols,
        timeframes: values.timeframes,
      };

      onSubmit(payload);
    } catch (error) {
      console.error('表单验证失败:', error);
    }
  };

  // 处理取消
  const handleCancel = () => {
    form.resetFields();
    onCancel();
  };

  return (
    <Modal
      title={isEdit ? '编辑策略' : '创建策略'}
      open={visible}
      onOk={handleSubmit}
      onCancel={handleCancel}
      confirmLoading={loading}
      width={700}
      destroyOnClose
    >
      <Form
        form={form}
        layout="vertical"
        requiredMark="optional"
        scrollToFirstError
      >
        {/* 基本信息 */}
        <Form.Item
          name="name"
          label="策略名称"
          rules={[
            { required: true, message: '请输入策略名称' },
            { max: 50, message: '策略名称不能超过 50 个字符' },
          ]}
        >
          <Input placeholder="例如：Pinbar 15m 保守策略" />
        </Form.Item>

        <Form.Item
          name="description"
          label="策略描述"
          rules={[
            { max: 200, message: '描述不能超过 200 个字符' },
          ]}
        >
          <TextArea
            rows={2}
            placeholder="简要描述策略特点和适用场景"
            showCount
          />
        </Form.Item>

        <Form.Item
          name="is_active"
          label="启用状态"
          valuePropName="checked"
          tooltip="禁用后的策略将不会产生交易信号"
        >
          <Switch checkedChildren="启用" unCheckedChildren="禁用" />
        </Form.Item>

        {/* 触发器配置 */}
        <Form.Item
          name="trigger_type"
          label="触发器类型"
          rules={[{ required: true, message: '请选择触发器类型' }]}
          tooltip="K 线形态识别触发器"
        >
          <Select placeholder="选择触发器类型">
            {TRIGGER_OPTIONS.map((opt) => (
              <Option key={opt.value} value={opt.value}>
                {opt.label}
              </Option>
            ))}
          </Select>
        </Form.Item>

        {/* 触发器参数配置 */}
        <TriggerParamsForm triggerType={triggerType} form={form} disabled={loading} />

        {/* 过滤器配置 */}
        <Form.Item
          name="filter_logic"
          label="过滤器组合逻辑"
          tooltip="AND=所有过滤器必须满足，OR=任一过滤器满足即可"
        >
          <Select placeholder="选择过滤器组合逻辑">
            {FILTER_LOGIC_OPTIONS.map((opt) => (
              <Option key={opt.value} value={opt.value}>
                {opt.label}
              </Option>
            ))}
          </Select>
        </Form.Item>

        <Form.Item
          label="过滤器列表"
          tooltip="过滤器用于过滤掉低质量的交易信号"
        >
          <div className="filter-config-hint">
            <p className="hint-text">
              当前暂未开放过滤器配置，支持以下过滤器类型：
            </p>
            <ul className="hint-list">
              <li>EMA 趋势过滤 - 确保交易方向与大趋势一致</li>
              <li>多周期共振 (MTF) - 大周期确认信号</li>
              <li>成交量突增 - 检测异常成交量</li>
              <li>ATR 波动率 - 过滤低波动率时期</li>
              <li>时间过滤 - 限定交易时段</li>
            </ul>
          </div>
        </Form.Item>

        {/* 作用域配置 */}
        <Form.Item
          name="symbols"
          label="交易币种"
          rules={[{ required: true, message: '请至少选择一个币种' }]}
          tooltip="策略将作用于所选币种"
        >
          <Select
            mode="multiple"
            placeholder="选择交易币种"
            maxTagCount="responsive"
            showSearch
          >
            {SYMBOL_OPTIONS.map((opt) => (
              <Option key={opt.value} value={opt.value}>
                {opt.label}
              </Option>
            ))}
          </Select>
        </Form.Item>

        <Form.Item
          name="timeframes"
          label="时间周期"
          rules={[{ required: true, message: '请至少选择一个周期' }]}
          tooltip="策略将作用于所选时间周期"
        >
          <Select
            mode="multiple"
            placeholder="选择交易周期"
            maxTagCount="responsive"
          >
            {TIMEFRAME_OPTIONS.map((opt) => (
              <Option key={opt.value} value={opt.value}>
                {opt.label}
              </Option>
            ))}
          </Select>
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default StrategyForm;
