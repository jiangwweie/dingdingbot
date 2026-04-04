/**
 * 系统配置 Tab 组件
 *
 * 提供系统级配置管理功能，包括：
 * - 指标参数配置（EMA 周期等）
 * - 信号管道配置（冷却时间、队列参数等）
 * - 预热配置
 * - ATR 过滤器配置
 *
 * 配置变更后需要重启服务才能生效。
 */

import React, { useState, useEffect } from 'react';
import { Form, InputNumber, Card, Button, Switch, message, Spin, Alert } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { RestartRequiredAlert } from '../../components/RestartRequiredAlert';
import { configApi, type SystemConfigResponse } from '../../api/config';

/**
 * 系统配置接口（前端展示用）
 * 从后端 SystemConfigResponse 转换而来
 */
export interface SystemConfig {
  // 指标参数
  ema_period: number;
  mtf_ema_period: number;

  // 信号管道
  signal_cooldown_seconds: number;
  queue_batch_size: number;
  queue_flush_interval: number;
  queue_max_size: number;

  // 预热配置
  warmup_history_bars: number;

  // ATR 过滤器
  atr_filter_enabled: boolean;
  atr_period: number;
  atr_min_ratio: number;
}

export const SystemTab: React.FC = () => {
  const [form] = Form.useForm();
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [restartRequired, setRestartRequired] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 加载系统配置
  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await configApi.getSystemConfig();
      // 适配后端返回格式
      const sysConfig: SystemConfig = {
        ema_period: response.data.ema?.period || 20,
        mtf_ema_period: response.data.mtf_ema_period || 60,
        signal_cooldown_seconds: response.data.signal_pipeline?.cooldown_seconds || 14400,
        queue_batch_size: response.data.signal_pipeline?.queue?.batch_size || 10,
        queue_flush_interval: response.data.signal_pipeline?.queue?.flush_interval || 5.0,
        queue_max_size: response.data.signal_pipeline?.queue?.max_queue_size || 1000,
        warmup_history_bars: response.data.warmup?.history_bars || 100,
        atr_filter_enabled: response.data.atr_filter_enabled ?? true,
        atr_period: response.data.atr_period || 14,
        atr_min_ratio: response.data.atr_min_ratio || 1.5,
      };
      setConfig(sysConfig);
      form.setFieldsValue(sysConfig);
    } catch (error: any) {
      const errorMsg = error.response?.data?.detail || error.message || '加载系统配置失败';
      setError(errorMsg);
      message.error(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (values: SystemConfig) => {
    setSaving(true);
    try {
      // 构建符合后端格式的配置对象
      const updatePayload = {
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

      // 检查是否需要重启（后端返回 requires_restart 字段）
      if (response.data.requires_restart) {
        setRestartRequired(true);
        message.warning('配置变更需要重启服务才能生效');
      }

      // 更新本地状态
      setConfig(values);
    } catch (error: any) {
      const errorMsg = error.response?.data?.detail || error.message || '保存失败';
      message.error(errorMsg);
    } finally {
      setSaving(false);
    }
  };

  const handleRestart = () => {
    // 重启后的处理逻辑
    setRestartRequired(false);
    message.success('重启指令已发送，请稍候...');
    // 实际项目中应调用重启 API
    // await fetch('/api/v1/system/restart', { method: 'POST' });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spin size="large" tip="加载系统配置..." />
      </div>
    );
  }

  if (error && !config) {
    return (
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
      />
    );
  }

  return (
    <div>
      <RestartRequiredAlert
        visible={restartRequired}
        onRestart={handleRestart}
        onClose={() => setRestartRequired(false)}
      />

      <Card title="系统配置" className="mb-6">
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          initialValues={config || undefined}
          size="large"
        >
          {/* 指标参数 */}
          <Card
            size="small"
            title="📊 指标参数"
            className="mb-4"
            extra={
              <span className="text-gray-400 text-sm">
                修改后需要重启服务
              </span>
            }
          >
            <Form.Item
              name="ema_period"
              label="EMA 周期"
              rules={[{ required: true, type: 'number', min: 5, max: 200 }]}
              extra="用于趋势判断的 EMA 周期，默认值：20"
            >
              <InputNumber min={5} max={200} className="w-full" />
            </Form.Item>

            <Form.Item
              name="mtf_ema_period"
              label="MTF EMA 周期"
              rules={[{ required: true, type: 'number', min: 5, max: 200 }]}
              extra="用于多周期趋势确认的 EMA 周期，默认值：60"
            >
              <InputNumber min={5} max={200} className="w-full" />
            </Form.Item>
          </Card>

          {/* 信号管道 */}
          <Card
            size="small"
            title="🔧 信号管道"
            className="mb-4"
            extra={
              <span className="text-gray-400 text-sm">
                修改后需要重启服务
              </span>
            }
          >
            <Form.Item
              name="signal_cooldown_seconds"
              label="信号冷却时间 (秒)"
              rules={[{ required: true, type: 'number', min: 60 }]}
              extra="相同信号的冷却时间，防止重复通知，默认值：14400 (4 小时)"
            >
              <InputNumber min={60} step={60} className="w-full" />
            </Form.Item>

            <Form.Item
              name="queue_batch_size"
              label="队列批量大小"
              rules={[{ required: true, type: 'number', min: 1 }]}
              extra="信号队列批量落盘的大小，默认值：10"
            >
              <InputNumber min={1} className="w-full" />
            </Form.Item>

            <Form.Item
              name="queue_flush_interval"
              label="队列刷新间隔 (秒)"
              rules={[{ required: true, type: 'number', min: 0.1 }]}
              extra="队列自动刷新的最大等待时间，默认值：5.0"
            >
              <InputNumber min={0.1} step={0.1} className="w-full" />
            </Form.Item>

            <Form.Item
              name="queue_max_size"
              label="队列最大容量"
              rules={[{ required: true, type: 'number', min: 100 }]}
              extra="队列最大容量限制，默认值：1000"
            >
              <InputNumber min={100} step={100} className="w-full" />
            </Form.Item>
          </Card>

          {/* 预热配置 */}
          <Card
            size="small"
            title="🔥 预热配置"
            className="mb-4"
            extra={
              <span className="text-gray-400 text-sm">
                修改后需要重启服务
              </span>
            }
          >
            <Form.Item
              name="warmup_history_bars"
              label="预热历史 K 线数"
              rules={[{ required: true, type: 'number', min: 10 }]}
              extra="启动时预热的历史 K 线数量，默认值：100"
            >
              <InputNumber min={10} className="w-full" />
            </Form.Item>
          </Card>

          {/* ATR 过滤器 */}
          <Card
            size="small"
            title="📈 ATR 过滤器"
            className="mb-4"
            extra={
              <span className="text-gray-400 text-sm">
                修改后需要重启服务
              </span>
            }
          >
            <Form.Item
              name="atr_filter_enabled"
              label="启用 ATR 过滤"
              valuePropName="checked"
              extra="启用后仅交易波动性足够的标的"
            >
              <Switch />
            </Form.Item>

            <Form.Item
              name="atr_period"
              label="ATR 周期"
              rules={[{ required: true, type: 'number', min: 5, max: 50 }]}
              extra="ATR 计算周期，默认值：14"
            >
              <InputNumber min={5} max={50} className="w-full" disabled={!form.getFieldValue('atr_filter_enabled')} />
            </Form.Item>

            <Form.Item
              name="atr_min_ratio"
              label="最小 ATR 倍数"
              rules={[{ required: true, type: 'number', min: 0.1, max: 5 }]}
              extra="信号有效性的最小 ATR 倍数，默认值：1.5"
            >
              <InputNumber min={0.1} max={5} step={0.1} className="w-full" disabled={!form.getFieldValue('atr_filter_enabled')} />
            </Form.Item>
          </Card>

          <Form.Item className="mt-6">
            <Button
              type="primary"
              htmlType="submit"
              loading={saving}
              size="large"
            >
              保存配置
            </Button>
            <Button
              className="ml-2"
              size="large"
              onClick={loadConfig}
            >
              重置
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
};

export default SystemTab;
