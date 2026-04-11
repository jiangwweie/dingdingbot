/**
 * 生效配置总览组件
 *
 * 只读展示当前生效的完整配置，包括：
 * - 交易所连接（API Key 脱敏）
 * - 系统设置（周期、EMA、MTF 映射等）
 * - 风控设置
 * - 通知渠道（Webhook URL 脱敏）
 * - 策略列表摘要
 * - 币种列表
 * - 资产轮询配置
 * - YAML 迁移状态指示
 *
 * 数据源: GET /api/v1/config/effective
 * 降级: API 404 时使用 mock 数据（开发阶段）
 */

import React, { useState } from 'react';
import {
  Collapse,
  Descriptions,
  Tag,
  Button,
  Alert,
  Spin,
  Space,
  Typography,
} from 'antd';
import {
  EyeInvisibleOutlined,
  EyeOutlined,
  CheckCircleOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import useSWR from 'swr';
import { configApi } from '../../api/config';
import type {
  EffectiveConfigResponse,
  ExchangeConfigMasked,
  MigrationStatus,
} from '../../api/config';

const { Title, Paragraph } = Typography;

// ============================================================
// Mock Data (开发阶段 fallback，后端 API 就绪后移除)
// ============================================================

const MOCK_EFFECTIVE_CONFIG: EffectiveConfigResponse = {
  exchange: {
    name: 'binance',
    api_key: 'sk***abc123',
    api_secret: '****',
    testnet: true,
  },
  system: {
    core_symbols: ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'BNB/USDT:USDT'],
    ema_period: 60,
    mtf_ema_period: 60,
    mtf_mapping: { '15m': '1h', '1h': '4h', '4h': '1d', '1d': '1w' },
    signal_cooldown_seconds: 14400,
    timeframes: ['15m', '1h'],
    atr_filter_enabled: true,
    atr_period: 14,
    atr_min_ratio: '0.5',
  },
  risk: {
    max_loss_percent: '0.01',
    max_leverage: 10,
    max_total_exposure: '0.8',
    cooldown_minutes: 5,
  },
  notification: {
    channels: [
      {
        id: '1',
        type: 'feishu',
        webhook_url: 'https://open.feishu.cn/****',
        is_active: true,
      },
    ],
  },
  strategies: [],
  symbols: [],
  asset_polling: { enabled: true, interval_seconds: 60 },
  migration_status: {
    yaml_fully_migrated: false,
    one_time_import_done: false,
    import_version: 'v1',
  },
  config_version: 1,
  created_at: new Date().toISOString(),
};

// ============================================================
// Helper Functions
// ============================================================

/** 将秒数格式化为人类可读字符串 */
function formatSeconds(seconds: number): string {
  if (seconds >= 3600) return `${seconds / 3600} 小时`;
  if (seconds >= 60) return `${seconds / 60} 分钟`;
  return `${seconds} 秒`;
}

/** 百分比字符串转百分比显示 */
function formatPercent(value: string): string {
  const num = parseFloat(value);
  return `${(num * 100).toFixed(1)}%`;
}

// ============================================================
// Main Component
// ============================================================

const EffectiveConfigView: React.FC = () => {
  const [revealedFields, setRevealedFields] = useState<Set<string>>(new Set());

  const { data, error, isLoading } = useSWR<EffectiveConfigResponse>(
    '/api/v1/config/effective',
    async () => {
      try {
        const response = await configApi.getEffectiveConfig();
        return response.data;
      } catch (err: any) {
        // 后端 API 未就绪时 (404) fallback 到 mock 数据
        if (err?.response?.status === 404) {
          console.warn('[EffectiveConfigView] API not ready, using mock data');
          return MOCK_EFFECTIVE_CONFIG;
        }
        throw err;
      }
    }
  );

  const toggleField = (key: string) => {
    setRevealedFields((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  // 加载状态
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spin size="large" tip="加载生效配置..." />
      </div>
    );
  }

  // 错误状态
  if (error) {
    return (
      <Alert
        type="error"
        showIcon
        message="加载失败"
        description={error.message || '无法获取生效配置信息'}
        action={
          <Button size="small" onClick={() => window.location.reload()}>
            重试
          </Button>
        }
      />
    );
  }

  // 防御性检查
  if (!data) {
    return <Alert type="warning" message="无数据" description="未获取到配置信息" />;
  }

  const { exchange, system, risk, notification, strategies, symbols, asset_polling, migration_status, config_version, created_at } = data;

  // 折叠面板配置
  const collapseItems = [
    // 1. 交易所连接
    {
      key: 'exchange',
      label: (
        <Space>
          交易所连接
          <Tag color={exchange.testnet ? 'blue' : 'orange'}>
            {exchange.testnet ? '测试网' : '主网'}
          </Tag>
        </Space>
      ),
      children: (
        <Descriptions column={{ xs: 1, sm: 2 }} bordered size="small">
          <Descriptions.Item label="交易所">{exchange.name}</Descriptions.Item>
          <Descriptions.Item label="网络环境">
            <Tag color={exchange.testnet ? 'blue' : 'orange'}>
              {exchange.testnet ? 'Testnet' : 'Mainnet'}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="API Key">
            <Space>
              {revealedFields.has('api_key') ? exchange.api_key : maskValue(exchange.api_key)}
              <Button
                type="link"
                size="small"
                icon={revealedFields.has('api_key') ? <EyeInvisibleOutlined /> : <EyeOutlined />}
                onClick={() => toggleField('api_key')}
              />
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="API Secret">
            <Space>
              {revealedFields.has('api_secret') ? exchange.api_secret : '****'}
              <Button
                type="link"
                size="small"
                icon={revealedFields.has('api_secret') ? <EyeInvisibleOutlined /> : <EyeOutlined />}
                onClick={() => toggleField('api_secret')}
              />
            </Space>
          </Descriptions.Item>
        </Descriptions>
      ),
    },

    // 2. 系统设置
    {
      key: 'system',
      label: '系统设置',
      children: (
        <Descriptions column={{ xs: 1, sm: 2 }} bordered size="small">
          <Descriptions.Item label="核心币种" span={2}>
            <Space wrap>
              {system.core_symbols.map((s) => (
                <Tag key={s}>{s.split(':')[0]}</Tag>
              ))}
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="监控周期" span={2}>
            <Space>
              {system.timeframes.map((tf) => (
                <Tag key={tf} color="blue">{tf}</Tag>
              ))}
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="EMA 周期">{system.ema_period}</Descriptions.Item>
          <Descriptions.Item label="MTF EMA 周期">{system.mtf_ema_period}</Descriptions.Item>
          <Descriptions.Item label="MTF 映射" span={2}>
            <Space wrap>
              {Object.entries(system.mtf_mapping).map(([k, v]) => (
                <Tag key={k}>{k} → {v}</Tag>
              ))}
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="信号冷却时间">
            {formatSeconds(system.signal_cooldown_seconds)}
          </Descriptions.Item>
          <Descriptions.Item label="ATR 过滤器">
            <Tag color={system.atr_filter_enabled ? 'green' : 'red'}>
              {system.atr_filter_enabled ? '已启用' : '已禁用'}
            </Tag>
          </Descriptions.Item>
          {system.atr_filter_enabled && (
            <>
              <Descriptions.Item label="ATR 周期">{system.atr_period}</Descriptions.Item>
              <Descriptions.Item label="最小 ATR 倍数">{system.atr_min_ratio}</Descriptions.Item>
            </>
          )}
        </Descriptions>
      ),
    },

    // 3. 风控设置
    {
      key: 'risk',
      label: '风控设置',
      children: (
        <Descriptions column={{ xs: 1, sm: 2 }} bordered size="small">
          <Descriptions.Item label="单笔最大损失">{formatPercent(risk.max_loss_percent)}</Descriptions.Item>
          <Descriptions.Item label="最大杠杆">{risk.max_leverage}x</Descriptions.Item>
          <Descriptions.Item label="最大总敞口">{formatPercent(risk.max_total_exposure)}</Descriptions.Item>
          <Descriptions.Item label="交易冷却时间">{risk.cooldown_minutes} 分钟</Descriptions.Item>
          {risk.daily_max_trades !== undefined && (
            <Descriptions.Item label="每日最大交易次数">{risk.daily_max_trades}</Descriptions.Item>
          )}
          {risk.daily_max_loss !== undefined && (
            <Descriptions.Item label="每日最大损失">{formatPercent(risk.daily_max_loss)}</Descriptions.Item>
          )}
        </Descriptions>
      ),
    },

    // 4. 通知设置
    {
      key: 'notification',
      label: '通知设置',
      children: notification.channels.length === 0 ? (
        <Paragraph type="secondary">未配置通知渠道</Paragraph>
      ) : (
        <Descriptions column={1} bordered size="small">
          {notification.channels.map((ch) => (
            <Descriptions.Item key={ch.id} label={`${ch.type === 'feishu' ? '飞书' : ch.type === 'wecom' ? '企业微信' : ch.type}`}>
              <Space>
                <Tag color={ch.is_active ? 'green' : 'red'}>
                  {ch.is_active ? '活跃' : '停用'}
                </Tag>
                <span>{ch.webhook_url}</span>
              </Space>
            </Descriptions.Item>
          ))}
        </Descriptions>
      ),
    },

    // 5. 策略列表
    {
      key: 'strategies',
      label: (
        <Space>
          策略列表
          {strategies.length > 0 && <Tag color="blue">{strategies.length}</Tag>}
        </Space>
      ),
      children: strategies.length === 0 ? (
        <Paragraph type="secondary">暂无策略</Paragraph>
      ) : (
        <Descriptions column={1} bordered size="small">
          {strategies.map((s) => (
            <Descriptions.Item key={s.id} label={s.name}>
              <Space wrap>
                <Tag color={s.is_active ? 'green' : 'red'}>
                  {s.is_active ? '已启用' : '已禁用'}
                </Tag>
                <Tag>{s.trigger_type}</Tag>
                <Tag>{s.filter_count} 个过滤器</Tag>
                {s.symbols.map((sym) => <Tag key={sym}>{sym.split(':')[0]}</Tag>)}
                {s.timeframes.map((tf) => <Tag key={tf} color="blue">{tf}</Tag>)}
              </Space>
            </Descriptions.Item>
          ))}
        </Descriptions>
      ),
    },

    // 6. 币种列表
    {
      key: 'symbols',
      label: (
        <Space>
          币种列表
          {symbols.length > 0 && <Tag color="blue">{symbols.length}</Tag>}
        </Space>
      ),
      children: symbols.length === 0 ? (
        <Paragraph type="secondary">暂无币种（使用系统默认核心币种）</Paragraph>
      ) : (
        <Space wrap>
          {symbols.map((s) => (
            <Tag key={s.symbol} color={s.is_core ? 'blue' : 'default'}>
              {s.symbol.split(':')[0]}
              {s.is_core && ' (核心)'}
            </Tag>
          ))}
        </Space>
      ),
    },

    // 7. 资产轮询
    {
      key: 'asset_polling',
      label: '资产轮询',
      children: (
        <Descriptions column={{ xs: 1, sm: 2 }} bordered size="small">
          <Descriptions.Item label="轮询开关">
            <Tag color={asset_polling.enabled ? 'green' : 'red'}>
              {asset_polling.enabled ? '已启用' : '已禁用'}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="轮询间隔">
            {asset_polling.interval_seconds} 秒
          </Descriptions.Item>
        </Descriptions>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      {/* 迁移状态指示器 */}
      {migration_status.yaml_fully_migrated ? (
        <Alert
          message="YAML 迁移完成"
          description="所有配置已从数据库读取，YAML 文件仅用于备份恢复"
          type="success"
          showIcon
          icon={<CheckCircleOutlined />}
        />
      ) : (
        <Alert
          message="YAML 迁移未完成"
          description={`首次启动后将自动从 YAML 导入配置（当前版本: ${migration_status.import_version}）`}
          type="warning"
          showIcon
          icon={<WarningOutlined />}
        />
      )}

      {/* 配置版本信息 */}
      <div className="text-xs text-gray-400">
        配置版本: v{config_version} | 创建时间: {new Date(created_at).toLocaleString('zh-CN')}
      </div>

      {/* 分组折叠面板 */}
      <Collapse accordion items={collapseItems} defaultActiveKey={['exchange', 'system', 'risk']} />
    </div>
  );
};

/**
 * 脱敏显示：保留前 4 后 4 字符，中间用 *** 替代
 */
function maskValue(value: string): string {
  if (!value || value.length <= 8) return '****';
  return `${value.slice(0, 4)}***${value.slice(-4)}`;
}

export default EffectiveConfigView;
