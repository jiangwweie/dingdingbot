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
 */
export interface RiskConfig {
  max_loss_percent: number;
  max_leverage: number;
  default_leverage: number;
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
// API Client Configuration
// ============================================================

// ============================================================
// 注意：后端配置接口路径说明
// ============================================================
// 后端配置相关接口分布在以下路径：
// - /api/v1/config/strategies - 策略管理（CRUD + Toggle）
// - /api/v1/config/risk - 风险配置
// - /api/v1/config/system - 系统配置（GET/PUT）
// ============================================================

// Axios 实例实例 1：配置管理（使用 /api/v1/config 前缀）
const configApiClient = axios.create({
  baseURL: '/api/v1/config',
  headers: {
    'Content-Type': 'application/json',
  },
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
};

// ============================================================
// Re-export types for convenience
// ============================================================

// Note: Types are already exported via the module, no need to re-export
