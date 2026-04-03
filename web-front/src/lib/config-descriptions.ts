/**
 * 配置描述元数据
 *
 * 为所有配置项提供标签、说明、单位、范围等元数据
 * 用于 Tooltip 组件显示配置说明
 */

export interface ConfigDescription {
  label: string;
  description: string;
  unit?: string;
  min?: number;
  max?: number;
  readonly?: boolean;
  requires_restart?: boolean;
}

// 风控配置描述
export const RISK_CONFIG_DESCRIPTIONS: Record<string, ConfigDescription> = {
  max_loss_percent: {
    label: '单笔最大损失',
    description: '每笔交易愿意承担的最大风险百分比。1% 表示如果触发止损，最多损失账户总额的 1%。建议范围：0.5%~2%',
    unit: '%',
    min: 0.1,
    max: 5.0,
    requires_restart: false,
  },
  max_total_exposure: {
    label: '最大总敞口',
    description: '所有未平仓头寸占账户总价值的最大比例。用于控制整体风险暴露。建议范围：50%~100%',
    unit: '%',
    min: 0.5,
    max: 1.0,
    requires_restart: false,
  },
  max_leverage: {
    label: '最大杠杆倍数',
    description: '系统允许使用的最大杠杆倍数。币安合约最大支持 125x，建议保守使用 5x-20x',
    unit: 'x',
    min: 1,
    max: 125,
    requires_restart: false,
  },
};

// 系统配置描述
export const SYSTEM_CONFIG_DESCRIPTIONS: Record<string, ConfigDescription> = {
  history_bars: {
    label: '历史 K 线数量',
    description: '每个币种周期订阅的历史 K 线数量，用于指标计算（如 EMA）。数量越多计算越准确，但会增加内存消耗',
    min: 50,
    max: 500,
    requires_restart: true,
  },
  queue_batch_size: {
    label: '队列批处理大小',
    description: '信号队列批处理的大小。达到此数量时批量刷新信号，减少 API 调用频率',
    min: 1,
    max: 100,
    requires_restart: true,
  },
  queue_flush_interval: {
    label: '队列刷新间隔',
    description: '信号队列的最大等待时间（秒）。即使未达到批处理大小，也会强制刷新，确保信号及时推送',
    unit: '秒',
    min: 1,
    max: 60,
    requires_restart: true,
  },
};

// 币种配置描述
export const SYMBOL_CONFIG_DESCRIPTIONS: Record<string, ConfigDescription> = {
  symbol: {
    label: '币种代码',
    description: '币种交易对格式：BTC/USDT:USDT（永续合约）或 BTC/USDT（现货）',
    readonly: true,
  },
  is_core: {
    label: '核心币种',
    description: '核心币种（BTC、ETH、SOL、BNB）为系统内置，不可删除',
    readonly: true,
  },
  is_enabled: {
    label: '启用状态',
    description: '关闭后将停止监控该币种的 K 线数据，但不删除配置',
  },
};

// 通知配置描述
export const NOTIFICATION_CONFIG_DESCRIPTIONS: Record<string, ConfigDescription> = {
  channel: {
    label: '通知渠道',
    description: '支持的的通知渠道：飞书（Feishu）、企业微信（WeCom）、Telegram',
    readonly: true,
  },
  webhook_url: {
    label: 'Webhook URL',
    description: '通知渠道的 Webhook 地址。此地址用于推送交易信号',
    readonly: false,
  },
  is_enabled: {
    label: '启用状态',
    description: '关闭后将停止通过此渠道发送通知，但保留配置',
  },
};

// 通用配置描述（按 key 索引）
export const CONFIG_DESCRIPTIONS: Record<string, ConfigDescription> = {
  ...RISK_CONFIG_DESCRIPTIONS,
  ...SYSTEM_CONFIG_DESCRIPTIONS,
  ...SYMBOL_CONFIG_DESCRIPTIONS,
  ...NOTIFICATION_CONFIG_DESCRIPTIONS,
};

/**
 * 获取配置项的描述信息
 */
export function getConfigDescription(key: string): ConfigDescription | undefined {
  return CONFIG_DESCRIPTIONS[key];
}
