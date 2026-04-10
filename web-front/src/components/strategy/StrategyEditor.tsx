/**
 * 策略编辑器抽屉组件
 *
 * 抽屉式策略编辑器，支持：
 * - 策略基本信息编辑
 * - 触发器参数配置
 * - 过滤器链配置
 * - 风控参数配置
 * - 自动保存机制（防抖 1 秒）
 *
 * @package components/strategy
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Drawer,
  Form,
  Input,
  Select,
  Switch,
  Button,
  Space,
  InputNumber,
  Collapse,
  message,
  Spin,
  Alert,
} from 'antd';
import { SaveOutlined, RotateLeftOutlined } from '@ant-design/icons';
import type { Strategy, CreateStrategyRequest, UpdateStrategyRequest } from '../../api/config';
import { getTriggerDefaultParams, getTriggerSchema } from './triggerSchemas';

// ============================================================
// Type Definitions
// ============================================================

interface TriggerConfig {
  type: 'pinbar' | 'engulfing' | 'doji' | 'hammer';
  params: Record<string, number>;
}

interface FilterConfig {
  type: 'ema' | 'mtf' | 'atr' | 'volume_surge';
  enabled: boolean;
  params: Record<string, any>;
}

interface StrategyFormValues {
  name: string;
  description?: string;
  is_active: boolean;
  trigger_type: string;
  trigger_params: Record<string, number>;
  filters: FilterConfig[];
  filter_logic: 'AND' | 'OR';
  symbols: string[];
  timeframes: string[];
  max_loss_percent: number;
  max_leverage: number;
}

// ============================================================
// Props Interface
// ============================================================

export interface StrategyEditorDrawerProps {
  visible: boolean;
  strategy: Strategy | null;
  onClose: () => void;
  onSave: (data: CreateStrategyRequest | UpdateStrategyRequest) => void;
  loading?: boolean;
}

// ============================================================
// Options Constants
// ============================================================

const TRIGGER_OPTIONS = [
  { value: 'pinbar', label: 'Pinbar (锤子线)' },
  { value: 'engulfing', label: 'Engulfing (吞没)' },
  { value: 'doji', label: 'Doji (十字星)' },
  { value: 'hammer', label: 'Hammer (倒锤子)' },
];

const FILTER_TYPE_OPTIONS = [
  { value: 'ema', label: 'EMA 趋势' },
  { value: 'mtf', label: 'MTF 多周期' },
  { value: 'atr', label: 'ATR 波动率' },
  { value: 'volume_surge', label: '成交量激增' },
];

const FILTER_LOGIC_OPTIONS = [
  { value: 'AND', label: '全部满足 (AND)' },
  { value: 'OR', label: '任一满足 (OR)' },
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
  { value: '1d', label: '日线' },
  { value: '1w', label: '周线' },
];

// ============================================================
// Default Values
// ============================================================

const DEFAULT_FILTER_PARAMS: Record<string, Record<string, any>> = {
  ema: { period: 60 },
  mtf: { mapping: '15m->1h', ema_period: 60 },
  atr: { period: 14, min_atr_ratio: 0.5 },
  volume_surge: { volume_multiplier: 2.0 },
};

// ============================================================
// StrategyEditorDrawer Component
// ============================================================

export const StrategyEditorDrawer: React.FC<StrategyEditorDrawerProps> = ({
  visible,
  strategy,
  onClose,
  onSave,
  loading = false,
}) => {
  const [form] = Form.useForm();
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [autoSaveTimer, setAutoSaveTimer] = useState<NodeJS.Timeout | null>(null);

  // 初始化表单数据
  useEffect(() => {
    if (visible) {
      if (strategy) {
        // 编辑模式：填充现有数据
        const tt = strategy.trigger_config?.type || 'pinbar';
        form.setFieldsValue({
          name: strategy.name,
          description: strategy.description,
          is_active: strategy.is_active,
          trigger_type: tt,
          trigger_params: strategy.trigger_config?.params || getTriggerDefaultParams(tt),
          filter_logic: strategy.filter_logic || 'AND',
          symbols: strategy.symbols || [],
          timeframes: strategy.timeframes || [],
        });
      } else {
        // 创建模式：使用默认值
        form.resetFields();
        form.setFieldsValue({
          name: '',
          description: '',
          is_active: true,
          trigger_type: 'pinbar',
          trigger_params: getTriggerDefaultParams('pinbar'),
          filter_logic: 'AND',
          symbols: ['BTC/USDT:USDT'],
          timeframes: ['1h'],
          max_loss_percent: 0.01,
          max_leverage: 10,
        });
      }
      setHasUnsavedChanges(false);
    }
  }, [visible, strategy, form]);

  // 监听表单变化，标记未保存状态
  const handleValuesChange = useCallback(() => {
    setHasUnsavedChanges(true);

    // 清除之前的定时器
    if (autoSaveTimer) {
      clearTimeout(autoSaveTimer);
    }

    // 设置新的自动保存定时器（1 秒防抖）
    const timer = setTimeout(() => {
      handleSubmit();
    }, 1000);

    setAutoSaveTimer(timer);
  }, [autoSaveTimer]);

  // 清理定时器
  useEffect(() => {
    return () => {
      if (autoSaveTimer) {
        clearTimeout(autoSaveTimer);
      }
    };
  }, [autoSaveTimer]);

  // 处理提交
  const handleSubmit = useCallback(async () => {
    try {
      const values = await form.validateFields();
      const payload: CreateStrategyRequest | UpdateStrategyRequest = {
        name: values.name,
        description: values.description,
        is_active: values.is_active,
        trigger_config: {
          type: values.trigger_type,
          params: values.trigger_params,
        },
        filter_configs: values.filters || [],
        filter_logic: values.filter_logic,
        symbols: values.symbols,
        timeframes: values.timeframes,
      };

      onSave(payload);
      setHasUnsavedChanges(false);

      if (!strategy) {
        message.success('策略创建成功');
      }
    } catch (error: any) {
      console.error('表单验证失败:', error);
      if (error.errorFields) {
        message.error('请完善表单信息');
      }
    }
  }, [form, onSave, strategy]);

  // 处理取消
  const handleCancel = () => {
    if (hasUnsavedChanges) {
      // 有未保存的更改，提示用户
      const confirmed = window.confirm('有未保存的更改，确定要关闭吗？');
      if (!confirmed) return;
    }
    form.resetFields();
    onClose();
  };

  // 触发器类型
  const triggerType = Form.useWatch('trigger_type', form) || 'pinbar';

  // 渲染触发器参数表单
  const renderTriggerParams = useMemo(() => {
    const schema = getTriggerSchema(triggerType);
    if (!schema) {
      return (
        <div className="text-sm text-gray-400 py-2">
          未知触发器类型: {triggerType}，暂无参数配置
        </div>
      );
    }

    return (
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        {schema.params.map((field) => (
          <Form.Item
            key={field.key}
            name={['trigger_params', field.key]}
            label={field.label}
            rules={[
              { type: 'number', min: field.min, max: field.max, message: `${field.label} 范围为 ${field.min} ~ ${field.max}` },
            ]}
            tooltip={field.tooltip}
            initialValue={field.defaultValue}
          >
            <InputNumber
              min={field.min}
              max={field.max}
              step={field.step}
              style={{ width: '100%' }}
              disabled={loading}
            />
          </Form.Item>
        ))}
      </Space>
    );
  }, [triggerType, loading]);

  return (
    <Drawer
      title={strategy ? '编辑策略' : '创建策略'}
      placement="right"
      width={720}
      open={visible}
      onClose={handleCancel}
      maskClosable={false}
      extra={
        <Space>
          <Button icon={<RotateLeftOutlined />} onClick={handleCancel} disabled={loading}>
            取消
          </Button>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            onClick={handleSubmit}
            loading={loading}
            disabled={!hasUnsavedChanges || loading}
          >
            {loading ? '保存中...' : hasUnsavedChanges ? '保存' : '已保存'}
          </Button>
        </Space>
      }
    >
      <Form
        form={form}
        layout="vertical"
        requiredMark="optional"
        onValuesChange={handleValuesChange}
        scrollToFirstError
      >
        {/* 基本信息 */}
        <Collapse
          defaultActiveKey={['basic', 'trigger', 'filters', 'risk']}
          bordered={false}
          className="mb-4"
        >
          <Collapse.Panel header="基本信息" key="basic">
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              <Form.Item
                name="name"
                label="策略名称"
                rules={[
                  { required: true, message: '请输入策略名称' },
                  { max: 50, message: '策略名称不能超过 50 个字符' },
                ]}
              >
                <Input placeholder="例如：Pinbar 15m 保守策略" disabled={loading} />
              </Form.Item>

              <Form.Item
                name="description"
                label="策略描述"
                rules={[{ max: 500, message: '描述不能超过 500 个字符' }]}
              >
                <Input.TextArea
                  rows={3}
                  placeholder="简要描述策略特点和适用场景"
                  showCount
                  disabled={loading}
                />
              </Form.Item>

              <Form.Item
                name="is_active"
                label="启用状态"
                valuePropName="checked"
                tooltip="禁用后的策略将不会产生交易信号"
              >
                <Switch checkedChildren="启用" unCheckedChildren="禁用" disabled={loading} />
              </Form.Item>
            </Space>
          </Collapse.Panel>

          <Collapse.Panel header="触发器配置" key="trigger">
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              <Form.Item
                name="trigger_type"
                label="触发器类型"
                rules={[{ required: true, message: '请选择触发器类型' }]}
              >
                <Select disabled={loading}>
                  {TRIGGER_OPTIONS.map((opt) => (
                    <Select.Option key={opt.value} value={opt.value}>
                      {opt.label}
                    </Select.Option>
                  ))}
                </Select>
              </Form.Item>

              {renderTriggerParams}
            </Space>
          </Collapse.Panel>

          <Collapse.Panel header="过滤器链" key="filters">
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              <Form.Item
                name="filter_logic"
                label="过滤器组合逻辑"
                tooltip="AND=所有过滤器必须满足，OR=任一过滤器满足即可"
              >
                <Select disabled={loading}>
                  {FILTER_LOGIC_OPTIONS.map((opt) => (
                    <Select.Option key={opt.value} value={opt.value}>
                      {opt.label}
                    </Select.Option>
                  ))}
                </Select>
              </Form.Item>

              <Alert
                type="info"
                showIcon
                message="过滤器配置暂未开放"
                description="当前支持 EMA 趋势、MTF 多周期、ATR 波动率、成交量激增等过滤器，将在后续版本开放配置。"
                className="mb-2"
              />

              <Form.Item name="filters" noStyle>
                <Input.TextArea style={{ display: 'none' }} />
              </Form.Item>
            </Space>
          </Collapse.Panel>

          <Collapse.Panel header="作用域配置" key="scope">
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
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
                  disabled={loading}
                >
                  {SYMBOL_OPTIONS.map((opt) => (
                    <Select.Option key={opt.value} value={opt.value}>
                      {opt.label}
                    </Select.Option>
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
                  disabled={loading}
                >
                  {TIMEFRAME_OPTIONS.map((opt) => (
                    <Select.Option key={opt.value} value={opt.value}>
                      {opt.label}
                    </Select.Option>
                  ))}
                </Select>
              </Form.Item>
            </Space>
          </Collapse.Panel>

          <Collapse.Panel header="风控参数" key="risk">
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              <Form.Item
                name="max_loss_percent"
                label="最大亏损比例"
                rules={[{ type: 'number', min: 0.001, max: 0.1 }]}
                tooltip="单笔交易最大允许亏损比例，默认 0.01 (1%)"
                initialValue={0.01}
              >
                <InputNumber
                  min={0.001}
                  max={0.1}
                  step={0.005}
                  style={{ width: '100%' }}
                  disabled={loading}
                  formatter={(value) => `${(Number(value) * 100).toFixed(1)}%`}
                  parser={(value) => Number(value?.replace('%', '')) / 100}
                />
              </Form.Item>

              <Form.Item
                name="max_leverage"
                label="最大杠杆倍数"
                rules={[{ type: 'number', min: 1, max: 125 }]}
                tooltip="最大允许使用的杠杆倍数"
                initialValue={10}
              >
                <InputNumber
                  min={1}
                  max={125}
                  step={1}
                  style={{ width: '100%' }}
                  disabled={loading}
                />
              </Form.Item>
            </Space>
          </Collapse.Panel>
        </Collapse>

        {/* 未保存更改提示 */}
        {hasUnsavedChanges && !loading && (
          <Alert
            type="warning"
            showIcon
            message="有未保存的更改"
            description='修改将在 1 秒后自动保存，或点击“保存”按钮立即保存'
            className="mt-4"
            action={
              <Button size="small" type="primary" onClick={handleSubmit}>
                立即保存
              </Button>
            }
          />
        )}
      </Form>
    </Drawer>
  );
};

export default StrategyEditorDrawer;
