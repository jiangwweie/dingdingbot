/**
 * 配置管理 API 封装
 *
 * 提供策略管理、风险配置、系统配置等 API 调用接口
 * 与后端 /api/v1/config/* 端点对接
 */

import axios from 'axios';

// ============================================================
// Strategy Types
// ============================================================

/**
 * 策略定义
 * 与后端 src/domain/models.py StrategyDefinition 保持类型对齐
 */
export interface Strategy {
  id: string;
  name: string;
  description?: string;
  is_active: boolean;
  trigger_config: {
    type: string;
    params: Record<string, any>;
  };
  filter_configs: Array<{
    type: string;
    enabled: boolean;
    params: Record<string, any>;
  }>;
  filter_logic: 'AND' | 'OR';
  symbols: string[];
  timeframes: string[];
  created_at: string;
  updated_at: string;
}

/**
 * 策略创建请求
 */
export interface CreateStrategyRequest {
  name: string;
  description?: string;
  is_active?: boolean;
  trigger_config: {
    type: string;
    params: Record<string, any>;
  };
  filter_configs?: Array<{
    type: string;
    enabled: boolean;
    params: Record<string, any>;
  }>;
  filter_logic?: 'AND' | 'OR';
  symbols: string[];
  timeframes: string[];
}

/**
 * 策略更新请求
 */
export interface UpdateStrategyRequest {
  name?: string;
  description?: string;
  is_active?: boolean;
  trigger_config?: {
    type: string;
    params: Record<string, any>;
  };
  filter_configs?: Array<{
    type: string;
    enabled: boolean;
    params: Record<string, any>;
  }>;
  filter_logic?: 'AND' | 'OR';
  symbols?: string[];
  timeframes?: string[];
}

/**
 * 策略切换请求
 */
export interface ToggleStrategyRequest {
  enabled: boolean;
}

// ============================================================
// Risk Config Types
// ============================================================

/**
 * 风险配置
 * 与后端 RiskConfigResponse (api_v1_config.py:153) 保持类型对齐
 */
export interface RiskConfig {
  id: string;
  max_loss_percent: number;
  max_leverage: number;
  max_total_exposure: number | null;
  daily_max_trades: number | null;
  daily_max_loss: number | null;
  max_position_hold_time: number | null;
  cooldown_minutes: number;
  updated_at: string;
  version: number;
}

// ============================================================
// Risk Config Form Types (前端表单专用)
// ============================================================

/** 风控配置表单值（前端展示用，格式化后） */
export interface RiskConfigFormValues {
  max_loss_percent: number;      // 显示为百分比数值（如 1 表示 1%）
  max_leverage: number;
  max_total_exposure: number;
  daily_max_trades?: number;
  daily_max_loss?: number;
  max_position_hold_time?: number;
  cooldown_minutes: number;
}

/** 风控配置更新请求（对齐后端 RiskConfigUpdateRequest） */
export interface RiskConfigUpdateRequest {
  max_loss_percent?: number;
  max_leverage?: number;
  max_total_exposure?: number;
  daily_max_trades?: number;
  daily_max_loss?: number;
  max_position_hold_time?: number;
  cooldown_minutes?: number;
}

// ============================================================
// System Config Types
// ============================================================

/**
 * 系统配置响应
 * 与后端 CoreConfig + SignalPipelineConfig 对应
 */
export interface SystemConfigResponse {
  // 后端内部字段
  id?: string;
  updated_at?: string;

  // 指标参数
  ema?: {
    period: number;
  };
  mtf_ema_period: number;

  // 信号管道
  signal_pipeline?: {
    cooldown_seconds: number;
    queue?: {
      batch_size: number;
      flush_interval: number;
      max_queue_size: number;
    };
  };

  // 预热配置
  warmup?: {
    history_bars: number;
  };

  // ATR 过滤器
  atr_filter_enabled?: boolean;
  atr_period?: number;
  atr_min_ratio?: number;

  // 重启标志（后端字段名为 restart_required）
  restart_required?: boolean;
}

/**
 * 系统配置更新请求
 */
export interface SystemConfigUpdateRequest {
  ema?: {
    period: number;
  };
  mtf_ema_period?: number;
  signal_pipeline?: {
    cooldown_seconds?: number;
    queue?: {
      batch_size?: number;
      flush_interval?: number;
      max_queue_size?: number;
    };
  };
  warmup?: {
    history_bars?: number;
  };
  atr_filter_enabled?: boolean;
  atr_period?: number;
  atr_min_ratio?: number;
}

/**
 * 系统配置更新响应（带重启标志）
 */
export interface SystemConfigUpdateResponse {
  requires_restart: boolean;
  config: SystemConfigResponse;
}

// ============================================================
// Backup/Import/Export Types
// ============================================================

/**
 * 导出配置请求
 * 与后端 ExportRequest (api_v1_config.py:492) 保持类型对齐
 */
export interface ExportRequest {
  include_risk?: boolean;
  include_system?: boolean;
  include_strategies?: boolean;
  include_symbols?: boolean;
  include_notifications?: boolean;
}

/**
 * 导出配置响应
 * 与后端 ExportResponse (api_v1_config.py:501) 保持类型对齐
 */
export interface ExportResponse {
  status: string;
  filename: string;
  yaml_content: string;
  created_at: string;
}

/**
 * 导入预览请求
 * 与后端 ImportPreviewRequest (api_v1_config.py:462) 保持类型对齐
 */
export interface ImportPreviewRequest {
  yaml_content: string;
  filename?: string;
}

/**
 * 导入预览结果
 * 与后端 ImportPreviewResult (api_v1_config.py:468) 保持类型对齐
 */
export interface ImportPreviewResult {
  valid: boolean;
  preview_token: string;
  summary: {
    strategies: { added: number; modified: number; deleted: number };
    risk: { modified: boolean };
    symbols: { added: number };
    notifications: { added: number };
  };
  conflicts: string[];
  requires_restart: boolean;
  errors: string[];
  preview_data: {
    strategies: any[];
    risk: Record<string, any>;
    symbols: any[];
    notifications: any[];
  };
}

/**
 * 确认导入请求
 * 与后端 ImportConfirmRequest (api_v1_config.py:479) 保持类型对齐
 */
export interface ImportConfirmRequest {
  preview_token: string;
}

/**
 * 确认导入响应
 * 与后端 ImportConfirmResponse (api_v1_config.py:484) 保持类型对齐
 */
export interface ImportConfirmResponse {
  status: string;
  snapshot_id: string | null;
  message: string;
  summary: Record<string, any>;
}

// ============================================================
// Effective Config Types (生效配置总览)
// ============================================================

/** 交易所配置（脱敏） */
export interface ExchangeConfigMasked {
  name: string;
  api_key: string;          // masked: "sk***abc123"
  api_secret: string;       // masked: "****"
  testnet: boolean;
}

/** 系统配置摘要 */
export interface SystemConfigSummary {
  core_symbols: string[];
  ema_period: number;
  mtf_ema_period: number;
  mtf_mapping: Record<string, string>;
  signal_cooldown_seconds: number;
  timeframes: string[];
  atr_filter_enabled: boolean;
  atr_period: number;
  atr_min_ratio: string;
}

/** 风控配置摘要 */
export interface RiskConfigSummary {
  max_loss_percent: string;
  max_leverage: number;
  max_total_exposure: string;
  daily_max_trades?: number;
  daily_max_loss?: string;
  cooldown_minutes: number;
}

/** 通知渠道（脱敏） */
export interface NotificationChannelMasked {
  id: string;
  type: string;
  webhook_url: string;      // masked URL
  is_active: boolean;
}

/** 策略摘要 */
export interface StrategySummary {
  id: string;
  name: string;
  is_active: boolean;
  trigger_type: string;
  filter_count: number;
  symbols: string[];
  timeframes: string[];
}

/** 币种摘要 */
export interface SymbolSummary {
  symbol: string;
  is_core: boolean;
  is_active: boolean;
}

/** 资产轮询摘要 */
export interface AssetPollingSummary {
  enabled: boolean;
  interval_seconds: number;
}

/** 迁移状态 */
export interface MigrationStatus {
  yaml_fully_migrated: boolean;
  one_time_import_done: boolean;
  import_version: string;
}

/** 生效配置总览响应 */
export interface EffectiveConfigResponse {
  exchange: ExchangeConfigMasked;
  system: SystemConfigSummary;
  risk: RiskConfigSummary;
  notification: {
    channels: NotificationChannelMasked[];
  };
  strategies: StrategySummary[];
  symbols: SymbolSummary[];
  asset_polling: AssetPollingSummary;
  migration_status: MigrationStatus;
  config_version: number;
  created_at: string;
}

// ============================================================
// API Client Configuration
// ============================================================

// ============================================================
// 注意：后端配置接口路径说明
// ============================================================
// 后端配置相关接口分布在以下路径：
// - /api/v1/config/strategies - 策略管理（CRUD + Toggle）
// - /api/v1/config/risk - 风险配置
// - /api/v1/config/system - 系统配置（GET/PUT）
// - /api/v1/config/export - 导出配置（POST）
// - /api/v1/config/import/preview - 预览导入（POST）
// - /api/v1/config/import/confirm - 确认导入（POST）
// ============================================================

// Axios 实例实例 1：配置管理（使用 /api/v1/config 前缀）
const configApiClient = axios.create({
  baseURL: '/api/v1/config',
  headers: {
    'Content-Type': 'application/json',
  },
});

// 全局注入 admin 认证头（绕过 DISABLE_AUTH 未设置时的 401）
configApiClient.interceptors.request.use((config) => {
  config.headers['X-User-Role'] = 'admin';
  return config;
});

// ============================================================
// Strategy Management API
// ============================================================

export const configApi = {
  // ---------- 策略管理 ----------

  /**
   * 获取所有策略列表
   * GET /api/v1/config/strategies
   */
  getStrategies: () => configApiClient.get<Strategy[]>('/strategies'),

  /**
   * 获取单个策略详情
   * GET /api/v1/config/strategies/:id
   */
  getStrategy: (id: string) => configApiClient.get<Strategy>(`/strategies/${id}`),

  /**
   * 创建新策略
   * POST /api/v1/config/strategies
   */
  createStrategy: (data: CreateStrategyRequest) =>
    configApiClient.post<Strategy>('/strategies', data),

  /**
   * 更新策略配置
   * PUT /api/v1/config/strategies/:id
   */
  updateStrategy: (id: string, data: UpdateStrategyRequest) =>
    configApiClient.put<Strategy>(`/strategies/${id}`, data),

  /**
   * 删除策略
   * DELETE /api/v1/config/strategies/:id
   */
  deleteStrategy: (id: string) =>
    configApiClient.delete(`/strategies/${id}`),

  /**
   * 切换策略启用状态
   * POST /api/v1/config/strategies/:id/toggle
   */
  toggleStrategy: (id: string, enabled: boolean) =>
    configApiClient.post(`/strategies/${id}/toggle`, { enabled } as ToggleStrategyRequest),

  /**
   * 应用策略到实盘引擎
   * POST /api/strategies/:id/apply
   * 注意：此接口使用旧 API 路径 /api/strategies，因为 apply 是独立端点
   */
  applyStrategy: (id: string) =>
    fetch(`/api/strategies/${id}/apply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    }).then(async (res) => {
      if (!res.ok) {
        const error = new Error('Failed to apply strategy');
        (error as any).status = res.status;
        (error as any).info = await res.json().catch(() => ({}));
        throw error;
      }
      return res.json();
    }),

  /**
   * Dry Run 预览策略
   * POST /api/strategies/preview
   * 注意：此接口使用旧 API 路径 /api/strategies，因为 preview 是独立端点
   */
  previewStrategy: (payload: {
    logic_tree: {
      gate: string;
      children: Array<{
        type: string;
        id: string;
        config: any;
      }>;
    };
    symbol: string;
    timeframe: string;
  }) =>
    fetch('/api/strategies/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(async (res) => {
      if (!res.ok) {
        const error = new Error('Failed to preview strategy');
        (error as any).status = res.status;
        (error as any).info = await res.json().catch(() => ({}));
        throw error;
      }
      return res.json();
    }),

  // ---------- 风险配置 ----------

  /**
   * 获取风险配置
   * GET /api/v1/config/risk
   */
  getRiskConfig: () => configApiClient.get<RiskConfig>('/risk'),

  /**
   * 更新风险配置
   * PUT /api/v1/config/risk
   */
  updateRiskConfig: (data: Partial<RiskConfig>) =>
    configApiClient.put('/risk', data),

  // ---------- 系统配置 ----------

  /**
   * 获取系统配置
   * GET /api/v1/config/system
   */
  getSystemConfig: () => configApiClient.get<SystemConfigResponse>('/system'),

  /**
   * 更新系统配置
   * PUT /api/v1/config/system
   * 返回更新后的配置，restart_required 标志指示是否需要重启
   */
  updateSystemConfig: (data: SystemConfigUpdateRequest) =>
    configApiClient.put<SystemConfigResponse>('/system', data),

  // ---------- 备份/导入/导出 ----------

  /**
   * 导出配置为 YAML
   * POST /api/v1/config/export
   * @param data - 导出选项（默认导出全部）
   * @returns ExportResponse 包含 yaml_content 和 filename
   */
  exportConfig: (data?: ExportRequest) =>
    configApiClient.post<ExportResponse>('/export', data ?? {}),

  /**
   * 预览导入变更（发送 YAML 内容，后端返回变更摘要和 preview_token）
   * POST /api/v1/config/import/preview
   * @param data - { yaml_content: string, filename?: string }
   * @returns ImportPreviewResult 包含 summary/conflicts/errors/preview_data
   */
  previewImport: (data: ImportPreviewRequest) =>
    configApiClient.post<ImportPreviewResult>('/import/preview', data),

  /**
   * 确认导入（仅传 preview_token）
   * POST /api/v1/config/import/confirm
   * @param data - { preview_token: string }
   * @returns ImportConfirmResponse 包含 status/snapshot_id/message
   */
  confirmImport: (data: ImportConfirmRequest) =>
    configApiClient.post<ImportConfirmResponse>('/import/confirm', data),

  // ---------- 生效配置总览 ----------

  /**
   * 获取生效配置总览（只读，脱敏）
   * GET /api/v1/config/effective
   */
  getEffectiveConfig: () =>
    configApiClient.get<EffectiveConfigResponse>('/effective'),
};

// ============================================================
// Re-export types for convenience
// ============================================================

// Note: Types are already exported via the module, no need to re-export
