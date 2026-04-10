/**
 * 系统设置页面
 *
 * 功能:
 * - Level 1 配置折叠显示 (全局系统配置)
 * - 修改系统配置提示重启
 * - 整合 Profile 管理和备份恢复入口
 *
 * @route /config/system
 *
 * 支持两种变体:
 * - variant='page' (默认): 独立页面，显示标题 + 右侧快捷入口面板
 * - variant='tab': 紧凑模式，仅显示配置表单，嵌入 Tab 容器
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Form,
  InputNumber,
  Card,
  Button,
  Switch,
  message,
  Spin,
  Alert,
  Collapse,
  Space,
  Divider,
} from 'antd';
import {
  ReloadOutlined,
  SaveOutlined,
  WarningOutlined,
  DatabaseOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import { cn } from '../../lib/utils';
import { configApi, type SystemConfigResponse, type SystemConfigUpdateRequest } from '../../api/config';

// ============================================================
// Type Definitions
// ============================================================

interface SystemConfigFormValues {
  // 队列配置
  queue_batch_size: number;
  queue_flush_interval: number;
  queue_max_size: number;

  // 数据预热
  warmup_history_bars: number;

  // 信号冷却
  signal_cooldown_seconds: number;

  // EMA 配置
  ema_period: number;
  mtf_ema_period: number;

  // ATR 过滤器
  atr_filter_enabled: boolean;
  atr_period: number;
  atr_min_ratio: number;
}

// ============================================================
// Default Values
// ============================================================

const DEFAULT_CONFIG: SystemConfigFormValues = {
  // 队列配置
  queue_batch_size: 10,
  queue_flush_interval: 5.0,
  queue_max_size: 1000,

  // 数据预热
  warmup_history_bars: 100,

  // 信号冷却
  signal_cooldown_seconds: 14400, // 4 小时

  // EMA 配置
  ema_period: 60,
  mtf_ema_period: 60,

  // ATR 过滤器
  atr_filter_enabled: true,
  atr_period: 14,
  atr_min_ratio: 0.5,
};

// ============================================================
// Props
// ============================================================

interface SystemSettingsProps {
  variant?: 'page' | 'tab';
}

// ============================================================
// Shared Form Content (renders in both page and tab modes)
// ============================================================

interface SystemConfigFormProps {
  form: any;
  saving: boolean;
  isTab: boolean;
  onSubmit: (values: SystemConfigFormValues) => void;
  onReset: () => void;
  activeKey: string[];
  onActiveKeyChange: (keys: string[]) => void;
}

/** Shared form content used by both page and tab variants */
function SystemConfigForm({
  form,
  saving,
  isTab,
  onSubmit,
  onReset,
  activeKey,
  onActiveKeyChange,
}: SystemConfigFormProps) {
  return (
    <Form
      form={form}
      layout="vertical"
      onFinish={onSubmit}
      initialValues={DEFAULT_CONFIG}
      size={isTab ? 'middle' : 'large'}
    >
      {/* 全局系统配置 (Level 1) */}
      <Card
        title={
          <div className="flex items-center gap-2">
            <WarningOutlined className="text-orange-500" />
            <span>全局系统配置</span>
            <span className="text-xs text-gray-400 font-normal ml-2">
              (修改后需重启服务)
            </span>
          </div>
        }
        className="mb-4 border-orange-200 bg-orange-50/30"
      >
        <Collapse
          bordered={false}
          activeKey={activeKey}
          onChange={(keys) => onActiveKeyChange(keys as string[])}
          expandIconPosition="right"
          className="bg-transparent"
        >
          <Collapse.Panel header="点击展开高级配置" key="advanced">
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              <Divider orientation="left" className="my-2">
                队列配置
              </Divider>

              <Form.Item
                name="queue_batch_size"
                label="队列批量大小"
                rules={[{ required: true, type: 'number', min: 1, max: 100 }]}
                tooltip="信号队列批量落盘的大小，默认值：10"
                extra="较大的批量可以提高性能，但会增加延迟"
              >
                <InputNumber min={1} max={100} className="w-full" disabled={saving} />
              </Form.Item>

              <Form.Item
                name="queue_flush_interval"
                label="队列刷新间隔 (秒)"
                rules={[{ required: true, type: 'number', min: 0.1, max: 60 }]}
                tooltip="队列自动刷新的最大等待时间，默认值：5.0"
                extra="较短的间隔可以减少延迟，但会增加 I/O 压力"
              >
                <InputNumber min={0.1} max={60} step={0.1} className="w-full" disabled={saving} />
              </Form.Item>

              <Form.Item
                name="queue_max_size"
                label="队列最大容量"
                rules={[{ required: true, type: 'number', min: 100, max: 10000 }]}
                tooltip="队列最大容量限制，默认值：1000"
                extra="队列满后将触发紧急处理机制"
              >
                <InputNumber min={100} max={10000} step={100} className="w-full" disabled={saving} />
              </Form.Item>

              <Divider orientation="left" className="my-2">
                数据预热
              </Divider>

              <Form.Item
                name="warmup_history_bars"
                label="预热历史 K 线数"
                rules={[{ required: true, type: 'number', min: 50, max: 500 }]}
                tooltip="启动时预热的历史 K 线数量，默认值：100"
                extra="更多的预热数据可以提高策略准确性，但会增加启动时间"
              >
                <InputNumber min={50} max={500} step={10} className="w-full" disabled={saving} />
              </Form.Item>

              <Divider orientation="left" className="my-2">
                信号冷却
              </Divider>

              <Form.Item
                name="signal_cooldown_seconds"
                label="信号冷却时间 (秒)"
                rules={[{ required: true, type: 'number', min: 3600, max: 86400 }]}
                tooltip="相同信号的冷却时间，防止重复通知，默认值：14400 (4 小时)"
                extra="冷却时间内的相同信号将被忽略"
              >
                <InputNumber
                  min={3600}
                  max={86400}
                  step={3600}
                  className="w-full"
                  disabled={saving}
                  formatter={(value) => `${value / 3600} 小时`}
                  parser={(value) => Number(value?.replace('小时', '')) * 3600}
                />
              </Form.Item>

              <Divider orientation="left" className="my-2">
                EMA 指标
              </Divider>

              <Form.Item
                name="ema_period"
                label="EMA 周期"
                rules={[{ required: true, type: 'number', min: 5, max: 200 }]}
                tooltip="用于趋势判断的 EMA 周期，默认值：60"
                extra="较短的周期更敏感，但可能有更多虚假信号"
              >
                <InputNumber min={5} max={200} className="w-full" disabled={saving} />
              </Form.Item>

              <Form.Item
                name="mtf_ema_period"
                label="MTF EMA 周期"
                rules={[{ required: true, type: 'number', min: 5, max: 200 }]}
                tooltip="用于多周期趋势确认的 EMA 周期，默认值：60"
              >
                <InputNumber min={5} max={200} className="w-full" disabled={saving} />
              </Form.Item>

              <Divider orientation="left" className="my-2">
                ATR 过滤器
              </Divider>

              <Form.Item
                name="atr_filter_enabled"
                label="启用 ATR 过滤"
                valuePropName="checked"
                tooltip="启用后仅交易波动性足够的标的"
              >
                <Switch checkedChildren="启用" unCheckedChildren="禁用" disabled={saving} />
              </Form.Item>

              <Form.Item
                name="atr_period"
                label="ATR 周期"
                rules={[{ required: false, type: 'number', min: 5, max: 50 }]}
                tooltip="ATR 计算周期，默认值：14"
                extra="仅当启用 ATR 过滤时生效"
              >
                <InputNumber min={5} max={50} className="w-full" disabled={saving || !form.getFieldValue('atr_filter_enabled')} />
              </Form.Item>

              <Form.Item
                name="atr_min_ratio"
                label="最小 ATR 倍数"
                rules={[{ required: false, type: 'number', min: 0.1, max: 5 }]}
                tooltip="信号有效性的最小 ATR 倍数，默认值：0.5"
                extra="仅当启用 ATR 过滤时生效"
              >
                <InputNumber min={0.1} max={5} step={0.1} className="w-full" disabled={saving || !form.getFieldValue('atr_filter_enabled')} />
              </Form.Item>
            </Space>
          </Collapse.Panel>
        </Collapse>
      </Card>

      {/* 操作按钮 */}
      <Form.Item className="mt-6">
        <Space>
          <Button
            type="primary"
            htmlType="submit"
            loading={saving}
            icon={<SaveOutlined />}
            size="large"
          >
            保存配置
          </Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={onReset}
            size="large"
          >
            重置
          </Button>
        </Space>
      </Form.Item>
    </Form>
  );
}

// ============================================================
// Main Component
// ============================================================

const SystemSettingsPage: React.FC<SystemSettingsProps> = ({ variant = 'page' }) => {
  const isTab = variant === 'tab';
  const navigate = useNavigate();
  const [form] = Form.useForm();

  // 状态
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [restartRequired, setRestartRequired] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [config, setConfig] = useState<SystemConfigFormValues | null>(null);

  // 折叠面板展开状态
  const [activeKey, setActiveKey] = useState<string[]>([]);

  // 加载系统配置
  const loadConfig = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await configApi.getSystemConfig();
      const data = response.data;

      // 转换后端数据格式为前端表单格式
      const sysConfig: SystemConfigFormValues = {
        queue_batch_size: data.signal_pipeline?.queue?.batch_size || DEFAULT_CONFIG.queue_batch_size,
        queue_flush_interval: data.signal_pipeline?.queue?.flush_interval || DEFAULT_CONFIG.queue_flush_interval,
        queue_max_size: data.signal_pipeline?.queue?.max_queue_size || DEFAULT_CONFIG.queue_max_size,
        warmup_history_bars: data.warmup?.history_bars || DEFAULT_CONFIG.warmup_history_bars,
        signal_cooldown_seconds: data.signal_pipeline?.cooldown_seconds || DEFAULT_CONFIG.signal_cooldown_seconds,
        ema_period: data.ema?.period || DEFAULT_CONFIG.ema_period,
        mtf_ema_period: data.mtf_ema_period || DEFAULT_CONFIG.mtf_ema_period,
        atr_filter_enabled: data.atr_filter_enabled ?? DEFAULT_CONFIG.atr_filter_enabled,
        atr_period: data.atr_period || DEFAULT_CONFIG.atr_period,
        atr_min_ratio: data.atr_min_ratio || DEFAULT_CONFIG.atr_min_ratio,
      };

      setConfig(sysConfig);
      form.setFieldsValue(sysConfig);
    } catch (err: any) {
      console.error('加载系统配置失败:', err);
      const errorMsg = err.response?.data?.detail || err.message || '加载失败';
      setError(errorMsg);
      message.error('加载系统配置失败：' + errorMsg);
    } finally {
      setLoading(false);
    }
  }, [form]);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  // 处理表单提交
  const handleSubmit = async (values: SystemConfigFormValues) => {
    setSaving(true);
    try {
      // 构建符合后端格式的配置对象
      const updatePayload: SystemConfigUpdateRequest = {
        ema: { period: values.ema_period },
        mtf_ema_period: values.mtf_ema_period,
        signal_pipeline: {
          cooldown_seconds: values.signal_cooldown_seconds,
          queue: {
            batch_size: values.queue_batch_size,
            flush_interval: values.queue_flush_interval,
            max_queue_size: values.queue_max_size,
          },
        },
        warmup: {
          history_bars: values.warmup_history_bars,
        },
        atr_filter_enabled: values.atr_filter_enabled,
        atr_period: values.atr_period,
        atr_min_ratio: values.atr_min_ratio,
      };

      const response = await configApi.updateSystemConfig(updatePayload);
      message.success('系统配置已保存');

      // 检查是否需要重启
      if (response.data.restart_required) {
        setRestartRequired(true);
        message.warning('配置变更需要重启服务才能生效');
      }

      // 更新本地状态
      setConfig(values);
    } catch (err: any) {
      console.error('保存系统配置失败:', err);
      const errorMsg = err.response?.data?.detail || err.message || '保存失败';
      message.error('保存失败：' + errorMsg);
    } finally {
      setSaving(false);
    }
  };

  // 处理重置
  const handleReset = () => {
    form.resetFields();
    if (config) {
      form.setFieldsValue(config);
    }
  };

  // 处理重启
  const handleRestart = () => {
    setRestartRequired(false);
    message.success('重启指令已发送，服务正在重启...');
    // TODO: 实际项目中应调用重启 API
    // await fetch('/api/v1/system/restart', { method: 'POST' });
  };

  // 导航到 Profile 管理
  const goToProfiles = () => {
    navigate('/config/profiles');
  };

  // 导航到备份恢复
  const goToBackup = () => {
    navigate('/config/backup');
  };

  // 导航到配置快照
  const goToSnapshots = () => {
    navigate('/snapshots');
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Spin size="large" tip="加载系统配置..." />
      </div>
    );
  }

  return (
    <div className={cn('system-settings-page', isTab && 'system-settings-tab')}>
      {/* 页面头部 (仅 page 模式显示) */}
      {!isTab && (
        <div className="page-header mb-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">系统设置</h1>
              <p className="text-sm text-gray-500 mt-1">
                配置全局系统参数、Profile 管理和备份恢复
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 重启提示 */}
      {restartRequired && (
        <Alert
          type="warning"
          showIcon
          icon={<WarningOutlined />}
          message="配置已保存，需要重启服务才能生效"
          description="修改的系统配置将在服务重启后应用，是否立即重启？"
          action={
            <Space>
              <Button type="primary" size="small" onClick={handleRestart}>
                立即重启
              </Button>
              <Button
                size="small"
                onClick={() => setRestartRequired(false)}
              >
                稍后重启
              </Button>
            </Space>
          }
          className="mb-4"
        />
      )}

      {/* 错误提示 */}
      {error && (
        <Alert
          type="error"
          showIcon
          message="加载失败"
          description={error}
          action={
            <Button type="primary" size="small" onClick={loadConfig}>
              重新加载
            </Button>
          }
          className="mb-4"
        />
      )}

      {isTab ? (
        /* Tab 模式：仅显示表单，无右侧面板 */
        <SystemConfigForm
          form={form}
          saving={saving}
          isTab={true}
          onSubmit={handleSubmit}
          onReset={handleReset}
          activeKey={activeKey}
          onActiveKeyChange={setActiveKey}
        />
      ) : (
        /* Page 模式：左侧表单 + 右侧快捷入口 */
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* 左侧：系统配置表单 */}
          <div className="lg:col-span-2">
            <SystemConfigForm
              form={form}
              saving={saving}
              isTab={false}
              onSubmit={handleSubmit}
              onReset={handleReset}
              activeKey={activeKey}
              onActiveKeyChange={setActiveKey}
            />
          </div>

          {/* 右侧：快捷入口 */}
          <div>
            {/* Profile 管理 */}
            <Card
              title="Profile 管理"
              className="mb-4 cursor-pointer hover:shadow-lg transition-shadow"
              onClick={goToProfiles}
              extra={<DatabaseOutlined className="text-blue-500" />}
            >
              <p className="text-sm text-gray-500 mb-3">
                管理不同环境配置 Profile
              </p>
              <Button type="primary" block onClick={goToProfiles}>
                进入 Profile 管理
              </Button>
            </Card>

            {/* 备份恢复 */}
            <Card
              title="备份恢复"
              className="mb-4 cursor-pointer hover:shadow-lg transition-shadow"
              onClick={goToBackup}
              extra={<SaveOutlined className="text-green-500" />}
            >
              <p className="text-sm text-gray-500 mb-3">
                导入导出配置文件，恢复历史版本
              </p>
              <Button type="primary" block onClick={goToBackup}>
                进入备份恢复
              </Button>
            </Card>

            {/* 配置快照 */}
            <Card
              title="配置快照"
              className="cursor-pointer hover:shadow-lg transition-shadow"
              onClick={goToSnapshots}
              extra={<FileTextOutlined className="text-purple-500" />}
            >
              <p className="text-sm text-gray-500 mb-3">
                查看和管理配置快照版本
              </p>
              <Button type="primary" block onClick={goToSnapshots}>
                查看快照历史
              </Button>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
};

export default SystemSettingsPage;
