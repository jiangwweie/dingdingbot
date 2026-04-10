/**
 * 高级策略表单组件
 *
 * 支持：
 * - 触发器类型选择与参数配置
 * - 过滤器链动态增删改
 * - 过滤器逻辑组合 (AND/OR)
 * - 币种和周期多选
 * - 策略启用/禁用
 */

import React, { useState, useEffect } from 'react';
import {
  Modal,
  Form,
  Input,
  Select,
  Switch,
  Button,
  Card,
  Space,
  InputNumber,
  Collapse,
  message,
} from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined } from '@ant-design/icons';
import type {
  Strategy,
  CreateStrategyRequest,
  UpdateStrategyRequest,
} from '../../api/config';

const { Panel } = Collapse;
const { Option } = Select;
const { TextArea } = Input;

// ============================================================
// Type Definitions
// ============================================================

interface TriggerConfig {
  type: 'pinbar' | 'engulfing' | 'doji' | 'hammer';
  params: {
    min_wick_ratio?: number;
    max_body_ratio?: number;
    body_position_tolerance?: number;
    min_body_ratio?: number;
    max_upper_wick_ratio?: number;
  };
}

interface FilterConfig {
  type: 'ema' | 'mtf' | 'atr' | 'volume_surge';
  enabled: boolean;
  params: Record<string, any>;
}

interface StrategyFormData {
  name: string;
  description?: string;
  is_active: boolean;
  trigger: TriggerConfig;
  filters: FilterConfig[];
  filter_logic: 'AND' | 'OR';
  symbols: string[];
  timeframes: string[];
}

interface AdvancedStrategyFormProps {
  visible: boolean;
  initialData?: Strategy | null;
  onCancel: () => void;
  onSubmit: (values: CreateStrategyRequest | UpdateStrategyRequest) => void;
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
// Trigger Config Panel Component
// ============================================================

interface TriggerConfigPanelProps {
  value?: TriggerConfig;
  onChange?: (value: TriggerConfig) => void;
}

const TriggerConfigPanel: React.FC<TriggerConfigPanelProps> = ({
  value,
  onChange,
}) => {
  const triggerType = value?.type || 'pinbar';

  const handleTypeChange = (newType: string) => {
    onChange?.({
      type: newType as TriggerConfig['type'],
      params: {},
    });
  };

  const handleParamChange = (key: string, val: number | undefined) => {
    onChange?.({
      ...value,
      params: {
        ...value?.params,
        [key]: val,
      },
    });
  };

  const renderParams = () => {
    switch (triggerType) {
      case 'pinbar':
        return (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Form.Item
              label="最小影线比例"
              name={['trigger', 'params', 'min_wick_ratio']}
              tooltip="影线长度占 K 线总长度的最小比例，默认 0.6"
            >
              <InputNumber
                min={0}
                max={1}
                step={0.1}
                defaultValue={0.6}
                value={value?.params?.min_wick_ratio}
                onChange={(val) => handleParamChange('min_wick_ratio', val)}
                style={{ width: '100%' }}
              />
            </Form.Item>
            <Form.Item
              label="最大实体比例"
              name={['trigger', 'params', 'max_body_ratio']}
              tooltip="实体长度占 K 线总长度的最大比例，默认 0.3"
            >
              <InputNumber
                min={0}
                max={1}
                step={0.1}
                defaultValue={0.3}
                value={value?.params?.max_body_ratio}
                onChange={(val) => handleParamChange('max_body_ratio', val)}
                style={{ width: '100%' }}
              />
            </Form.Item>
            <Form.Item
              label="实体位置容差"
              name={['trigger', 'params', 'body_position_tolerance']}
              tooltip="实体位置容差范围，默认 0.3"
            >
              <InputNumber
                min={0}
                max={1}
                step={0.1}
                defaultValue={0.3}
                value={value?.params?.body_position_tolerance}
                onChange={(val) => handleParamChange('body_position_tolerance', val)}
                style={{ width: '100%' }}
              />
            </Form.Item>
          </Space>
        );
      case 'engulfing':
        return (
          <Form.Item
            label="最小实体比例"
            name={['trigger', 'params', 'min_body_ratio']}
            tooltip="吞没形态中实体部分的最小比例，默认 0.5"
          >
            <InputNumber
              min={0}
              max={1}
              step={0.1}
              defaultValue={0.5}
              value={value?.params?.min_body_ratio}
              onChange={(val) => handleParamChange('min_body_ratio', val)}
              style={{ width: '100%' }}
            />
          </Form.Item>
        );
      case 'doji':
        return (
          <Form.Item
            label="最大实体比例"
            name={['trigger', 'params', 'max_body_ratio']}
            tooltip="十字星形态中实体部分的最大比例，默认 0.1"
          >
            <InputNumber
              min={0}
              max={1}
              step={0.1}
              defaultValue={0.1}
              value={value?.params?.max_body_ratio}
              onChange={(val) => handleParamChange('max_body_ratio', val)}
              style={{ width: '100%' }}
            />
          </Form.Item>
        );
      case 'hammer':
        return (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Form.Item
              label="最小下影线比例"
              name={['trigger', 'params', 'min_wick_ratio']}
              tooltip="锤头线下影线的最小比例，默认 0.6"
            >
              <InputNumber
                min={0}
                max={1}
                step={0.1}
                defaultValue={0.6}
                value={value?.params?.min_wick_ratio}
                onChange={(val) => handleParamChange('min_wick_ratio', val)}
                style={{ width: '100%' }}
              />
            </Form.Item>
            <Form.Item
              label="最大上影线比例"
              name={['trigger', 'params', 'max_upper_wick_ratio']}
              tooltip="锤头线上影线的最大比例，默认 0.1"
            >
              <InputNumber
                min={0}
                max={1}
                step={0.1}
                defaultValue={0.1}
                value={value?.params?.max_upper_wick_ratio}
                onChange={(val) => handleParamChange('max_upper_wick_ratio', val)}
                style={{ width: '100%' }}
              />
            </Form.Item>
          </Space>
        );
      default:
        return null;
    }
  };

  return (
    <Card title="触发器配置" size="small" className="trigger-config-card">
      <Form.Item
        label="触发器类型"
        name={['trigger', 'type']}
        rules={[{ required: true, message: '请选择触发器类型' }]}
      >
        <Select
          placeholder="选择触发器类型"
          onChange={handleTypeChange}
          value={triggerType}
        >
          {TRIGGER_OPTIONS.map((opt) => (
            <Option key={opt.value} value={opt.value}>
              {opt.label}
            </Option>
          ))}
        </Select>
      </Form.Item>
      {renderParams()}
    </Card>
  );
};

// ============================================================
// Filters Config Panel Component
// ============================================================

interface FiltersConfigPanelProps {
  value?: FilterConfig[];
  onChange?: (value: FilterConfig[]) => void;
}

const FiltersConfigPanel: React.FC<FiltersConfigPanelProps> = ({
  value = [],
  onChange,
}) => {
  const [filters, setFilters] = useState<FilterConfig[]>(value);

  useEffect(() => {
    setFilters(value);
  }, [value]);

  const addFilter = () => {
    const newFilter: FilterConfig = {
      type: 'ema',
      enabled: true,
      params: { period: 60 },
    };
    const updated = [...filters, newFilter];
    setFilters(updated);
    onChange?.(updated);
  };

  const removeFilter = (index: number) => {
    const updated = filters.filter((_, i) => i !== index);
    setFilters(updated);
    onChange?.(updated);
  };

  const updateFilter = (
    index: number,
    key: keyof FilterConfig,
    val: any
  ) => {
    const updated = filters.map((f, i) =>
      i === index ? { ...f, [key]: val } : f
    );
    setFilters(updated);
    onChange?.(updated);
  };

  const updateFilterParam = (index: number, paramKey: string, val: any) => {
    const updated = filters.map((f, i) =>
      i === index
        ? { ...f, params: { ...f.params, [paramKey]: val } }
        : f
    );
    setFilters(updated);
    onChange?.(updated);
  };

  const renderFilterParams = (filter: FilterConfig, index: number) => {
    switch (filter.type) {
      case 'ema':
        return (
          <Form.Item label="EMA 周期" tooltip="EMA 均线周期数">
            <InputNumber
              value={filter.params.period || 60}
              onChange={(val) => updateFilterParam(index, 'period', val)}
              min={5}
              max={200}
              style={{ width: '100%' }}
            />
          </Form.Item>
        );
      case 'mtf':
        return (
          <div className="text-gray-400 text-sm">
            MTF 映射由系统自动处理（15m→1h, 1h→4h, 4h→1d, 1d→1w）
          </div>
        );
      case 'atr':
        return (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Form.Item label="ATR 周期" tooltip="ATR 计算周期数">
              <InputNumber
                value={filter.params.period || 14}
                onChange={(val) => updateFilterParam(index, 'period', val)}
                min={5}
                max={50}
                style={{ width: '100%' }}
              />
            </Form.Item>
            <Form.Item label="最小 ATR 倍数" tooltip="最小 ATR 比率阈值">
              <InputNumber
                value={filter.params.min_atr_ratio || 1.0}
                onChange={(val) => updateFilterParam(index, 'min_atr_ratio', val)}
                min={0.1}
                max={5}
                step={0.1}
                style={{ width: '100%' }}
              />
            </Form.Item>
          </Space>
        );
      case 'volume_surge':
        return (
          <Form.Item label="成交量倍数" tooltip="成交量激增倍数阈值">
            <InputNumber
              value={filter.params.volume_multiplier || 2.0}
              onChange={(val) => updateFilterParam(index, 'volume_multiplier', val)}
              min={1.0}
              max={10}
              step={0.5}
              style={{ width: '100%' }}
            />
          </Form.Item>
        );
      default:
        return null;
    }
  };

  return (
    <Card title="过滤器链" size="small" className="filters-config-card">
      {filters.length === 0 ? (
        <div className="empty-filters-hint">
          <p>暂无过滤器配置</p>
          <Button type="dashed" onClick={addFilter} icon={<PlusOutlined />}>
            添加第一个过滤器
          </Button>
        </div>
      ) : (
        filters.map((filter, index) => (
          <Card
            key={index}
            size="small"
            className={`filter-item ${!filter.enabled ? 'filter-disabled' : ''}`}
            style={{ marginBottom: 12 }}
            title={
              <Space>
                <span>过滤器 {index + 1}</span>
                <Select
                  value={filter.type}
                  onChange={(val) => updateFilter(index, 'type', val)}
                  style={{ width: 150 }}
                  size="small"
                >
                  {FILTER_TYPE_OPTIONS.map((opt) => (
                    <Option key={opt.value} value={opt.value}>
                      {opt.label}
                    </Option>
                  ))}
                </Select>
              </Space>
            }
            extra={
              <Space>
                <Switch
                  size="small"
                  checked={filter.enabled}
                  onChange={(val) => updateFilter(index, 'enabled', val)}
                  checkedChildren="启用"
                  unCheckedChildren="禁用"
                />
                <Button
                  danger
                  size="small"
                  icon={<DeleteOutlined />}
                  onClick={() => removeFilter(index)}
                />
              </Space>
            }
          >
            {renderFilterParams(filter, index)}
          </Card>
        ))
      )}
      {filters.length > 0 && (
        <Button
          type="dashed"
          onClick={addFilter}
          icon={<PlusOutlined />}
          style={{ width: '100%', marginTop: 8 }}
        >
          添加过滤器
        </Button>
      )}
    </Card>
  );
};

// ============================================================
// AdvancedStrategyForm Component
// ============================================================

export const AdvancedStrategyForm: React.FC<AdvancedStrategyFormProps> = ({
  visible,
  initialData,
  onCancel,
  onSubmit,
  loading = false,
}) => {
  const [form] = Form.useForm();
  const isEdit = !!initialData;

  // 内部状态：触发器和过滤器配置
  const [triggerConfig, setTriggerConfig] = useState<TriggerConfig>({
    type: 'pinbar',
    params: {},
  });
  const [filterConfigs, setFilterConfigs] = useState<FilterConfig[]>([]);
  const [filterLogic, setFilterLogic] = useState<'AND' | 'OR'>('AND');

  // 初始化表单数据
  useEffect(() => {
    if (visible) {
      if (initialData) {
        // 编辑模式：填充现有数据
        form.setFieldsValue({
          name: initialData.name,
          description: initialData.description,
          is_active: initialData.is_active,
          symbols: initialData.symbols || [],
          timeframes: initialData.timeframes || [],
          filter_logic: initialData.filter_logic || 'AND',
        });

        // 解析触发器配置
        if (initialData.trigger_config) {
          setTriggerConfig({
            type: initialData.trigger_config.type as TriggerConfig['type'],
            params: initialData.trigger_config.params || {},
          });
        }

        // 解析过滤器配置
        if (initialData.filter_configs && initialData.filter_configs.length > 0) {
          setFilterConfigs(
            initialData.filter_configs.map((f) => ({
              type: f.type as FilterConfig['type'],
              enabled: f.enabled !== false,
              params: f.params || {},
            }))
          );
        } else {
          setFilterConfigs([]);
        }

        setFilterLogic(initialData.filter_logic || 'AND');
      } else {
        // 创建模式：使用默认值
        form.resetFields();
        form.setFieldsValue({
          name: '',
          description: '',
          is_active: true,
          symbols: ['BTC/USDT:USDT'],
          timeframes: ['1h'],
          filter_logic: 'AND',
        });
        setTriggerConfig({ type: 'pinbar', params: {} });
        setFilterConfigs([]);
        setFilterLogic('AND');
      }
    }
  }, [visible, initialData, form]);

  // 处理表单提交
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();

      // 构建完整的策略请求体
      const payload: CreateStrategyRequest | UpdateStrategyRequest = {
        name: values.name,
        description: values.description,
        is_active: values.is_active,
        trigger_config: {
          type: triggerConfig.type,
          params: triggerConfig.params,
        },
        filter_configs: filterConfigs.map((f) => ({
          type: f.type,
          enabled: f.enabled,
          params: f.params,
        })),
        filter_logic: filterLogic,
        symbols: values.symbols,
        timeframes: values.timeframes,
      };

      onSubmit(payload);
    } catch (error: any) {
      console.error('表单验证失败:', error);
      if (error.errorFields) {
        message.error('请完善表单信息');
      }
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
      width={900}
      destroyOnClose
      className="advanced-strategy-form"
    >
      <Form
        form={form}
        layout="vertical"
        requiredMark="optional"
        scrollToFirstError
      >
        <Collapse
          defaultActiveKey={['basic', 'trigger', 'filters']}
          className="form-collapse"
        >
          <Panel header="基本信息" key="basic">
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              <Form.Item
                name="name"
                label="策略名称"
                rules={[
                  { required: true, message: '请输入策略名称' },
                  { max: 50, message: '策略名称不能超过 50 个字符' },
                ]}
              >
                <Input placeholder="例如：Pinbar EMA60 策略" />
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

              <Space size="large" style={{ width: '100%' }}>
                <Form.Item
                  name="symbols"
                  label="交易币种"
                  rules={[{ required: true, message: '请至少选择一个币种' }]}
                  tooltip="策略将作用于所选币种"
                  style={{ flex: 1, marginBottom: 0 }}
                >
                  <Select
                    mode="multiple"
                    placeholder="选择币种"
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
                  style={{ flex: 1, marginBottom: 0 }}
                >
                  <Select
                    mode="multiple"
                    placeholder="选择周期"
                    maxTagCount="responsive"
                  >
                    {TIMEFRAME_OPTIONS.map((opt) => (
                      <Option key={opt.value} value={opt.value}>
                        {opt.label}
                      </Option>
                    ))}
                  </Select>
                </Form.Item>
              </Space>
            </Space>
          </Panel>

          <Panel header="触发器配置" key="trigger">
            <TriggerConfigPanel
              value={triggerConfig}
              onChange={setTriggerConfig}
            />
          </Panel>

          <Panel header="过滤器链" key="filters">
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              <Form.Item
                name="filter_logic"
                label="过滤器组合逻辑"
                tooltip="AND=所有过滤器必须满足，OR=任一过滤器满足即可"
              >
                <Select
                  value={filterLogic}
                  onChange={(val) => setFilterLogic(val)}
                >
                  {FILTER_LOGIC_OPTIONS.map((opt) => (
                    <Option key={opt.value} value={opt.value}>
                      {opt.label}
                    </Option>
                  ))}
                </Select>
              </Form.Item>
              <FiltersConfigPanel
                value={filterConfigs}
                onChange={setFilterConfigs}
              />
            </Space>
          </Panel>
        </Collapse>
      </Form>
    </Modal>
  );
};

export default AdvancedStrategyForm;
