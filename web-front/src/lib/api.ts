import useSWR from 'swr';

// Import recursive logic tree types from types/strategy.ts
import type { LogicNode, LogicNodeChildren, LeafNode } from '../types/strategy';

// Import v3 order/position/account types
import type {
  OrderRequest,
  OrderResponse,
  OrderCancelResponse,
  OrderStatus,
  OrderRole,
  OrderType,
  PositionInfo,
  PositionResponse,
  PositionsResponse,
  AccountBalance,
  AccountResponse,
  AccountSnapshot,
  ClosePositionRequest,
  OrderCheckRequest,
  CapitalProtectionCheckResult,
  OrdersResponse,
  OrderTreeResponse,
  OrderBatchDeleteRequest,
  OrderBatchDeleteResponse,
} from '../types/order';

export const fetcher = async (url: string) => {
  const res = await fetch(url);
  if (!res.ok) {
    const error = new Error('An error occurred while fetching the data.');
    // Attach extra info to the error object.
    (error as any).info = await res.json().catch(() => ({}));
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
};

export function useApi<T>(endpoint: string | null, refreshInterval = 30000) {
  return useSWR<T>(endpoint, fetcher, {
    refreshInterval,
    revalidateOnFocus: true,
  });
}

/**
 * Complete Signal mapping interface for Type Safety
 */
export interface Signal {
  id: string;
  created_at: string;
  symbol: string;
  timeframe: string;
  direction: 'long' | 'short';
  entry_price: string;
  stop_loss: string;
  take_profit?: string;  // 遗留字段（兼容旧数据）
  take_profit_levels?: Array<{  // S6-3: 多级别止盈
    id: string;              // TP1, TP2, ...
    position_ratio: string;  // 仓位比例
    risk_reward: string;     // 盈亏比
    price: string;           // 止盈价格
    status?: string;         // PENDING/WON/CANCELLED
  }>;
  position_size: string;
  leverage: number;
  tags?: Array<{ name: string; value: string }>;  // Dynamic filter tags (e.g., [{"name": "EMA", "value": "Bullish"}])
  status: SignalStatus;
  pnl_ratio?: string | null;
  win_rate?: number;
  strategy_name?: string | null;
  score?: number | string | null;
  kline_timestamp?: number;
  risk_reward_info?: string;
  source?: 'live' | 'backtest';  // Signal source: live trading or backtest
  // Signal coverage fields (S6-2)
  superseded_by?: string | null;  // ID of the signal that superseded this one
  opposing_signal_id?: string | null;  // ID of opposing direction signal
  opposing_signal_score?: number | string | null;  // Score of opposing signal
  // Legacy fields (deprecated, kept for backward compatibility with old signals)
  ema_trend?: 'bullish' | 'bearish';
  mtf_status?: 'confirmed' | 'rejected' | 'disabled' | 'unavailable';
}

/**
 * SignalAttempt interface for diagnostic logs
 */
export interface SignalAttempt {
  id: string;
  created_at: string;
  symbol: string;
  timeframe: string;
  strategy_name: string;
  pattern_score?: number | null;
  final_result: 'SIGNAL_FIRED' | 'NO_PATTERN' | 'FILTERED';
  filter_stage?: 'ema_trend' | 'mtf' | null;
  filter_reason?: string | null;
  details?: Record<string, any>;
  evaluation_summary?: string;
  trace_tree?: TraceNode;
}

/**
 * Fetch signal context data for detailed view
 * Returns the signal details with surrounding K-line data (10 before + signal + 10 after)
 */
export async function fetchSignalContext(signalId: string): Promise<{
  signal: Signal;
  klines: number[][]; // [timestamp_ms, open, high, low, close, volume]
}> {
  return fetcher(`/api/signals/${signalId}/context`);
}

/**
 * Delete signals by IDs or all matching filters
 */
export async function deleteSignals(payload: {
  ids?: string[];
  delete_all?: boolean;
  symbol?: string;
  direction?: string;
  strategy_name?: string;
  status?: string;
  start_time?: string;
  end_time?: string;
  source?: string;  // 'live' or 'backtest'
}): Promise<{ message: string; deleted_count: number }> {
  const res = await fetch('/api/signals', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const error = new Error('Failed to delete signals');
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

/**
 * Delete attempts by IDs or all matching filters
 */
export async function deleteAttempts(payload: {
  ids?: string[];
  delete_all?: boolean;
  symbol?: string;
  timeframe?: string;
  strategy_name?: string;
  final_result?: string;
  filter_stage?: string;
  start_time?: string;
  end_time?: string;
}): Promise<{ message: string; deleted_count: number }> {
  const res = await fetch('/api/attempts', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const error = new Error('Failed to delete attempts');
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

// ============================================================================
// Dynamic Strategy System Types (Trigger-Filter Matrix)
// ============================================================================

/**
 * Strategy trigger types - the main pattern detector
 */
export type TriggerType = 'pinbar' | 'engulfing' | 'doji' | 'hammer';

/**
 * Filter types - conditions that must pass for a signal to fire
 * Using backend short format for consistency
 */
export type FilterType =
  | 'ema'
  | 'mtf'
  | 'volume_surge'
  | 'volatility_filter'
  | 'time_filter'
  | 'price_action'
  | 'atr';

/**
 * EMA Filter parameters
 */
export interface EmaFilterParams {
  period: number;
  trend_direction?: 'bullish' | 'bearish' | 'either';
}

/**
 * MTF (Multi-Timeframe) Filter parameters
 * Note: higher_timeframe is auto-derived by backend (15m→1h→4h→1d→1w), not configurable
 */
export interface MtfFilterParams {
  require_confirmation: boolean;
}

/**
 * Volume Surge Filter parameters
 */
export interface VolumeSurgeFilterParams {
  multiplier: number;
  lookback_periods: number;
}

/**
 * Volatility Filter parameters
 */
export interface VolatilityFilterParams {
  min_atr_ratio: number;
  max_atr_ratio: number;
  atr_period?: number;
}

/**
 * Time Filter parameters
 */
export interface TimeFilterParams {
  session?: 'asian' | 'london' | 'new_york' | 'any';
  exclude_weekend?: boolean;
  hours_start?: number;
  hours_end?: number;
}

/**
 * Price Action Filter parameters
 */
export interface PriceActionFilterParams {
  min_body_size?: number;
  max_body_size?: number;
  require_closed_candle: boolean;
}

/**
 * ATR (Average True Range) Filter parameters
 * Uses ATR to filter out low-volatility noise
 */
export interface AtrFilterParams {
  period?: number;           // ATR 计算周期，默认 14
  min_atr_ratio?: number;    // 最小 ATR 比率，默认 0.001 (0.1%)
  enabled?: boolean;         // 是否启用
}

/**
 * Union type for all filter configurations
 * Each filter has a type discriminator and corresponding params
 */
export interface FilterConfig {
  id: string; // Unique ID for React keys
  type: FilterType;
  enabled: boolean;
  params:
    | EmaFilterParams
    | MtfFilterParams
    | VolumeSurgeFilterParams
    | VolatilityFilterParams
    | TimeFilterParams
    | PriceActionFilterParams
    | Record<string, any>;
}

/**
 * Pinbar trigger parameters
 */
export interface PinbarParams {
  min_wick_ratio: number;
  max_body_ratio: number;
  body_position_tolerance: number;
}

/**
 * Engulfing trigger parameters
 */
export interface EngulfingParams {
  min_body_ratio: number;
  require_full_engulf: boolean;
}

/**
 * Doji trigger parameters
 */
export interface DojiParams {
  max_body_ratio: number;
  min_total_range: number;
}

/**
 * Hammer trigger parameters
 */
export interface HammerParams {
  min_lower_wick_ratio: number;
  max_upper_wick_ratio: number;
  min_body_ratio: number;
}

/**
 * Union type for trigger configurations
 */
export interface TriggerConfig {
  id: string; // Unique ID for React keys
  type: TriggerType;
  enabled: boolean;
  params:
    | PinbarParams
    | EngulfingParams
    | DojiParams
    | HammerParams
    | Record<string, any>;
}

/**
 * Strategy definition - a trigger with its filter chain
 */
export interface StrategyDefinition {
  id: string; // Unique ID for this strategy
  name: string; // User-friendly name
  trigger: TriggerConfig;
  filters: FilterConfig[];
  filter_logic: 'AND' | 'OR'; // How to combine filter results
  is_global: boolean; // Applies to all symbols and timeframes (default: true)
  apply_to: string[]; // Specific scope entries e.g., 'BTC/USDT:USDT:15m' (default: [])
  logic_tree?: LogicNode | LeafNode; // Optional recursive logic tree (new format)
}

// ============================================================================
// Risk Configuration (unchanged structure)
// ============================================================================

/**
 * Risk management configuration interface
 */
export interface RiskConfig {
  max_loss_percent: number;
  max_leverage: number;
}

// ============================================================================
// System Configuration (refactored for dynamic strategies)
// ============================================================================

/**
 * System configuration interface with dynamic strategies array
 */
export interface SystemConfig {
  active_strategies: StrategyDefinition[];
  risk: RiskConfig;
  user_symbols: string[];
}

// ============================================================================
// Config Snapshot Types (版本化快照方案 B)
// ============================================================================

/**
 * 配置快照列表项
 */
export interface ConfigSnapshotListItem {
  id: number;
  version: string;
  description: string;
  created_at: string;
  created_by: string;
  is_active: boolean;
}

/**
 * 配置快照详情
 */
export interface ConfigSnapshotDetail {
  id: number;
  version: string;
  config: Record<string, any>;
  description: string;
  created_at: string;
  created_by: string;
  is_active: boolean;
}

/**
 * 配置快照列表响应
 */
export interface SnapshotListResponse {
  total: number;
  limit: number;
  offset: number;
  data: ConfigSnapshotListItem[];
}

/**
 * 配置快照创建请求
 */
export interface CreateSnapshotRequest {
  version: string;
  description?: string;
}

/**
 * 配置快照创建响应
 */
export interface CreateSnapshotResponse {
  id: number;
  version: string;
  description: string;
  created_at: string;
  created_by: string;
  is_active: boolean;
}

/**
 * 配置快照查询参数
 */
export interface SnapshotQueryParams {
  limit?: number;
  offset?: number;
  created_by?: string;
  is_active?: boolean;
}

/**
 * 配置响应
 */
export interface ConfigResponse {
  status: 'success';
  config: Record<string, any>;
  created_at: string;
}

/**
 * 删除响应
 */
export interface DeleteResponse {
  status: 'success';
  message: string;
}

// ============================================================================
// Backtest Types & API (for Backtester Sandbox)
// ============================================================================

/**
 * Backtest request parameters with dynamic strategies
 */
export interface BacktestRequest {
  symbol: string;
  timeframe: string;
  start_time: number; // UNIX timestamp in milliseconds
  end_time: number; // UNIX timestamp in milliseconds
  strategies?: StrategyDefinition[]; // Dynamic strategies for testing
  risk_overrides?: Partial<RiskConfig>; // Override risk params for testing
}

/**
 * PMS Backtest request parameters (v3_pms mode)
 */
export interface PMSBacktestRequest extends BacktestRequest {
  initial_balance?: number; // Initial balance for PMS backtest
}

/**
 * Backtest report response interface
 */
export interface BacktestReport {
  // Summary metrics
  total_signals: number;
  total_filtered: number;
  filtered_by_filters: Record<string, number>; // Filter type -> count mapping

  // Performance metrics (future expansion)
  win_count?: number;
  loss_count?: number;
  win_rate?: number;
  total_pnl?: number;

  // Detailed logs
  signal_logs: BacktestSignalLog[];

  // Execution metadata
  execution_time_ms: number;
  klines_analyzed: number;

  // Legacy field aliases for backward compatibility
  signal_stats?: {
    signals_fired?: number;
    filtered_by_filters?: Record<string, number>;
  };
  candles_analyzed?: number;
  attempts?: BacktestSignalLog[];
}

// ============================================================================
// PMS Backtest Types (v3.0 PMS 模式回测)
// ============================================================================

/**
 * Position summary for PMS backtest report
 */
export interface PositionSummary {
  /** 仓位 ID */
  position_id: string;
  /** 信号 ID */
  signal_id: string;
  /** 交易对 */
  symbol: string;
  /** 方向 */
  direction: 'LONG' | 'SHORT';
  /** 开仓价 (Decimal string) */
  entry_price: string;
  /** 平仓价 (Decimal string, 仅当仓位关闭时) */
  exit_price: string | null;
  /** 开仓时间戳 (ms) */
  entry_time: number;
  /** 平仓时间戳 (ms, 仅当仓位关闭时) */
  exit_time: number | null;
  /** 已实现盈亏 (Decimal string) */
  realized_pnl: string;
  /** 平仓原因 (TP1/SL/TRAILING 等) */
  exit_reason: string | null;
}

/**
 * PMS Backtest report response interface
 */
export interface PMSBacktestReport {
  /** 策略 ID */
  strategy_id: string;
  /** 策略名称 */
  strategy_name: string;
  /** 回测开始时间戳 (ms) */
  backtest_start: number;
  /** 回测结束时间戳 (ms) */
  backtest_end: number;
  /** 初始资金 (Decimal string) */
  initial_balance: string;
  /** 最终余额 (Decimal string) */
  final_balance: string;
  /** 总收益率 (%) (Decimal string) */
  total_return: string;
  /** 总交易次数 */
  total_trades: number;
  /** 盈利交易次数 */
  winning_trades: number;
  /** 亏损交易次数 */
  losing_trades: number;
  /** 胜率 (%) (Decimal string) */
  win_rate: string;
  /** 总盈亏 (USDT) (Decimal string) */
  total_pnl: string;
  /** 总手续费 (Decimal string) */
  total_fees_paid: string;
  /** 总滑点成本 (Decimal string) */
  total_slippage_cost: string;
  /** 最大回撤 (%) (Decimal string) */
  max_drawdown: string;
  /** 夏普比率 (Decimal string, 可选) */
  sharpe_ratio: string | null;
  /** 仓位历史摘要列表 */
  positions: PositionSummary[];
}

/**
 * Trace event for diagnostic tracking
 */
export interface TraceEvent {
  node_name: string;
  passed: boolean;
  reason?: string;
  metadata?: Record<string, any>;
}

/**
 * Individual signal log entry in backtest report
 */
export interface BacktestSignalLog {
  timestamp: number;
  symbol: string;
  timeframe: string;
  strategy_name?: string;
  trigger_type?: TriggerType;
  trigger_passed: boolean;
  filters_passed: TraceEvent[]; // Array of filter evaluation results
  signal_fired: boolean;
  direction?: 'long' | 'short';
  entry_price?: number;
  stop_loss?: number;
  filter_stage?: string; // Name of the filter that blocked (if any)
  filter_reason?: string; // Human-readable reason
}

/**
 * Fetch current system configuration
 */
export async function fetchSystemConfig(): Promise<SystemConfig> {
  const res = await fetch('/api/config', {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to fetch system configuration');
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

/**
 * Update system configuration (partial update supported)
 */
export async function updateSystemConfig(
  config: Partial<SystemConfig>
): Promise<SystemConfig> {
  const res = await fetch('/api/config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!res.ok) {
    const error = new Error('Failed to update system configuration');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

/**
 * Run signal-level backtest (v2_classic mode)
 *
 * 信号回测 - 仅统计信号触发和过滤器拦截情况，不涉及订单执行模拟。
 * Backtest signals are automatically saved to database.
 */
export async function runSignalBacktest(payload: BacktestRequest): Promise<BacktestReport> {
  const res = await fetch('/api/backtest/signals', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...payload,
      mode: 'v2_classic',
    }),
  });
  if (!res.ok) {
    const error = new Error('Failed to run signal backtest');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  const data = await res.json();
  return data.report || data;
}

/**
 * Run position-level PMS backtest (v3_pms mode)
 *
 * PMS 订单回测 - 包含订单执行、滑点、手续费、止盈止损等完整交易流程模拟。
 * Positions and orders are automatically saved to database.
 */
export async function runPMSBacktest(payload: PMSBacktestRequest): Promise<PMSBacktestReport> {
  const res = await fetch('/api/backtest/orders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...payload,
      mode: 'v3_pms',
    }),
  });
  if (!res.ok) {
    const error = new Error('Failed to run PMS backtest');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  const data = await res.json();
  return data.report || data;
}

/**
 * [DEPRECATED] Run backtest with given parameters
 *
 * @deprecated Use runSignalBacktest() or runPMSBacktest() instead
 * This endpoint will be removed in a future version.
 */
export async function runBacktest(payload: BacktestRequest): Promise<BacktestReport | PMSBacktestReport> {
  console.warn('runBacktest() is deprecated. Use runSignalBacktest() or runPMSBacktest() instead.');
  const res = await fetch('/api/backtest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const error = new Error('Failed to run backtest');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  const data = await res.json();
  return data.report || data;
}

/**
 * Save backtest signals to database
 */
export async function saveBacktestSignals(payload: {
  symbol: string;
  timeframe: string;
  signals: Array<{
    direction: 'long' | 'short';
    entry_price: string;
    stop_loss: string;
    position_size: string;
    leverage: number;
    tags: Array<{ name: string; value: string }>;
    risk_reward_info: string;
    strategy_name: string;
    score: number;
    kline_timestamp: number;
  }>;
}): Promise<{ message: string; saved_count: number }> {
  const res = await fetch('/api/backtest/save-signals', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const error = new Error('Failed to save backtest signals');
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

/**
 * Fetch backtest signals from database
 */
export async function fetchBacktestSignals(params?: {
  symbol?: string;
  timeframe?: string;
  strategy_name?: string;
  limit?: number;
  offset?: number;
}): Promise<{ signals: Signal[]; total: number }> {
  const queryParams = new URLSearchParams();
  if (params?.symbol) queryParams.append('symbol', params.symbol);
  if (params?.timeframe) queryParams.append('timeframe', params.timeframe);
  if (params?.strategy_name) queryParams.append('strategy_name', params.strategy_name);
  if (params?.limit) queryParams.append('limit', String(params.limit));
  if (params?.offset) queryParams.append('offset', String(params.offset));

  const res = await fetch(`/api/backtest/signals?${queryParams}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to fetch backtest signals');
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

/**
 * Fetch backtest report by ID (if backend supports persisted reports)
 */
export async function fetchBacktestReport(reportId: string): Promise<BacktestReport> {
  const res = await fetch(`/api/backtest/${reportId}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to fetch backtest report');
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

// ============================================================================
// V3 Backtest Reports API (T7 - 回测记录列表页面)
// ============================================================================

import type {
  BacktestReportSummary,
  ListBacktestReportsRequest,
  ListBacktestReportsResponse,
  BacktestReportDetail,
} from '../types/backtest';

/**
 * Fetch backtest reports list with filters, sorting, and pagination
 */
export async function fetchBacktestReports(params?: ListBacktestReportsRequest): Promise<ListBacktestReportsResponse> {
  const queryParams = new URLSearchParams();
  if (params?.strategyId) queryParams.append('strategy_id', params.strategyId);
  if (params?.symbol) queryParams.append('symbol', params.symbol);
  if (params?.startDate) queryParams.append('start_date', String(params.startDate));
  if (params?.endDate) queryParams.append('end_date', String(params.endDate));
  if (params?.page) queryParams.append('page', String(params.page));
  if (params?.pageSize) queryParams.append('page_size', String(params.pageSize));
  if (params?.sortBy) queryParams.append('sort_by', params.sortBy);
  if (params?.sortOrder) queryParams.append('sort_order', params.sortOrder);

  const res = await fetch(`/api/v3/backtest/reports?${queryParams}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to fetch backtest reports');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

/**
 * Fetch backtest report details by ID
 */
export async function fetchBacktestReportDetail(reportId: string): Promise<BacktestReportDetail> {
  const res = await fetch(`/api/v3/backtest/reports/${reportId}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to fetch backtest report details');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  const data = await res.json();
  return data.report;
}

/**
 * Delete backtest report by ID
 */
export async function deleteBacktestReport(reportId: string): Promise<{ status: string; message: string }> {
  const res = await fetch(`/api/v3/backtest/reports/${reportId}`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to delete backtest report');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

// ============================================================================
// Filter Utility Functions
// ============================================================================

/**
 * Get default params for a filter type
 */
export function getDefaultFilterParams(type: FilterType): Record<string, any> {
  switch (type) {
    case 'ema':
      return { period: 60, trend_direction: 'either' as const };
    case 'mtf':
      return { require_confirmation: true };
    case 'volume_surge':
      return { multiplier: 1.5, lookback_periods: 20 };
    case 'volatility_filter':
      return { min_atr_ratio: 0.5, max_atr_ratio: 3.0, atr_period: 14 };
    case 'time_filter':
      return { session: 'any' as const, exclude_weekend: true };
    case 'price_action':
      return { require_closed_candle: true };
    case 'atr':
      return { period: 14, min_atr_ratio: 0.001, enabled: true };
    default:
      return {};
  }
}

/**
 * Get default params for a trigger type
 */
export function getDefaultTriggerParams(type: TriggerType): Record<string, any> {
  switch (type) {
    case 'pinbar':
      return { min_wick_ratio: 0.6, max_body_ratio: 0.3, body_position_tolerance: 0.1 };
    case 'engulfing':
      return { min_body_ratio: 0.5, require_full_engulf: true };
    case 'doji':
      return { max_body_ratio: 0.1, min_total_range: 0.001 };
    case 'hammer':
      return { min_lower_wick_ratio: 0.6, max_upper_wick_ratio: 0.2, min_body_ratio: 0.1 };
    default:
      return {};
  }
}

/**
 * Generate a unique ID
 */
export function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Get display name for filter type
 */
export function getFilterDisplayName(type: FilterType): string {
  const names: Record<FilterType, string> = {
    ema: 'EMA 趋势校验',
    mtf: 'MTF 多周期验证',
    volume_surge: '成交量激增',
    volatility_filter: '波动率过滤',
    time_filter: '时间窗口过滤',
    price_action: '价格行为过滤',
    atr: 'ATR 波动率过滤',
  };
  return names[type] || type;
}

/**
 * Get display name for trigger type
 */
export function getTriggerDisplayName(type: TriggerType): string {
  const names: Record<TriggerType, string> = {
    pinbar: 'Pinbar (针 bar)',
    engulfing: 'Engulfing (吞没)',
    doji: 'Doji (十字星)',
    hammer: 'Hammer (锤子线)',
  };
  return names[type] || type;
}

/**
 * Parse a scope string into its components
 * Format: "SYMBOL/QUOTE:SETTLEMENT:TIMEFRAME" e.g., "BTC/USDT:USDT:15m"
 */
export function parseScopeString(scope: string): { symbol: string; settlement: string; timeframe: string } | null {
  const match = scope.match(/^([^:]+):([^:]+):([^:]+)$/);
  if (!match) return null;
  return {
    symbol: match[1],
    settlement: match[2],
    timeframe: match[3],
  };
}

/**
 * Build a scope string from components
 */
export function buildScopeString(symbol: string, settlement: string, timeframe: string): string {
  return `${symbol}:${settlement}:${timeframe}`;
}

/**
 * Default symbols and timeframes available for scope selection
 */
export const DEFAULT_SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT'];
export const DEFAULT_TIMEFRAMES = ['5m', '15m', '1h', '4h', '1d'];
export const DEFAULT_SETTLEMENTS = ['USDT', 'USD', 'BTC'];

// ============================================================================
// Strategy Metadata API (for dynamic form generation)
// ============================================================================

/**
 * Parameter schema definition for dynamic form generation
 */
export interface ParamSchema {
  type: 'string' | 'number' | 'boolean';
  min?: number;
  max?: number;
  default?: any;
  enum?: string[];
  description?: string;
}

/**
 * Trigger type metadata from backend
 */
export interface TriggerTypeMeta {
  type: TriggerType;
  displayName: string;
  paramsSchema: Record<string, ParamSchema>;
}

/**
 * Filter type metadata from backend
 */
export interface FilterTypeMeta {
  type: FilterType;
  displayName: string;
  paramsSchema: Record<string, ParamSchema>;
}

/**
 * Strategy metadata response from GET /api/strategies/meta
 */
export interface StrategyMetadata {
  triggers: TriggerTypeMeta[];
  filters: FilterTypeMeta[];
}

/**
 * Fetch strategy metadata for dynamic form generation
 */
export async function fetchStrategyMetadata(): Promise<StrategyMetadata> {
  const res = await fetch('/api/strategies/meta', {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to fetch strategy metadata');
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

// ============================================================================
// Strategy Preview API (热预览接口)
// ============================================================================

/**
 * Trace node in preview response
 */
export interface TraceNode {
  node_id: string;
  node_type: 'gate' | 'trigger' | 'filter';
  gate_type?: 'AND' | 'OR' | 'NOT';
  trigger_type?: TriggerType;
  filter_type?: FilterType;
  passed: boolean;
  reason?: string;
  metadata?: Record<string, any>;
  children?: TraceNode[];
}

/**
 * Preview request parameters
 */
export interface PreviewRequest {
  logic_tree: LogicNode | LogicNodeChildren;
  symbol: string;
  timeframe: string;
}

/**
 * Preview response
 */
export interface PreviewResponse {
  signal_fired: boolean;
  trace_tree: TraceNode;
  evaluation_summary?: string;
  details?: Record<string, any>;
}

/**
 * Preview a strategy configuration against recent kline data
 */
export async function previewStrategy(payload: PreviewRequest): Promise<PreviewResponse> {
  const res = await fetch('/api/strategies/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const error = new Error('Failed to preview strategy');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

/**
 * Apply a strategy template to live trading engine
 * @param id - Strategy template ID to apply
 */
export async function applyStrategy(id: string): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`/api/strategies/${id}/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to apply strategy');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

// ============================================================================
// Strategy Format Conversion Utilities (Legacy -> LogicNode)
// ============================================================================

/**
 * Convert legacy StrategyDefinition (flat trigger+filters) to LogicNode (recursive tree)
 *
 * Legacy format:
 * { trigger: TriggerConfig, filters: FilterConfig[], filter_logic: 'AND'|'OR' }
 *
 * New format (LogicNode):
 * { gate: 'AND'|'OR'|'NOT', children: (LogicNode | LeafNode)[] }
 */
export function convertStrategyToLogicNode(strategy: StrategyDefinition): import('../types/strategy').LogicNode {
  // Import types dynamically to avoid circular dependency
  const children: Array<import('../types/strategy').LogicNode | import('../types/strategy').LeafNode> = [];

  // Add trigger as first child
  children.push({
    type: 'trigger',
    id: strategy.trigger.id,
    config: strategy.trigger,
  });

  // Add filters as children
  for (const filter of strategy.filters) {
    children.push({
      type: 'filter',
      id: filter.id,
      config: filter,
    });
  }

  // Create root AND node (all conditions must pass)
  return {
    gate: 'AND',
    children,
  };
}

/**
 * Convert LogicNode back to legacy StrategyDefinition format
 */
export function convertLogicNodeToStrategy(
  node: import('../types/strategy').LogicNode,
  strategyName: string
): StrategyDefinition {
  const triggerChildren = node.children.filter(
    (child): child is import('../types/strategy').TriggerLeaf => 'type' in child && child.type === 'trigger'
  );
  const filterChildren = node.children.filter(
    (child): child is import('../types/strategy').FilterLeaf => 'type' in child && child.type === 'filter'
  );

  return {
    id: generateId(),
    name: strategyName,
    trigger: triggerChildren[0]?.config || { id: generateId(), type: 'pinbar', enabled: true, params: {} },
    filters: filterChildren.map((f) => f.config),
    filter_logic: 'AND',
    is_global: true,
    apply_to: [],
  };
}

// ============================================================================
// Signal Status Tracking API (S5-2 - 信号状态跟踪)
// ============================================================================

/**
 * Signal status enumeration
 */
export enum SignalStatus {
  GENERATED = 'generated',
  PENDING = 'pending',
  ACTIVE = 'active',
  SUPERSEDED = 'superseded',
  FILLED = 'filled',
  CANCELLED = 'cancelled',
  REJECTED = 'rejected',
  WON = 'won',
  LOST = 'lost',
}

/**
 * Signal track interface for status tracking
 */
export interface SignalTrack {
  signal_id: string;
  original_signal: Signal;
  status: SignalStatus;
  created_at: number;
  updated_at: number;
  filled_price?: string;
  filled_at?: number;
  reject_reason?: string;
  cancel_reason?: string;
}

/**
 * Fetch signal status by ID
 */
export async function getSignalStatus(signalId: string): Promise<SignalTrack> {
  const res = await fetch(`/api/signals/${signalId}/status`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to fetch signal status');
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

/**
 * List all signal statuses with optional filtering
 */
export async function listSignalStatuses(
  status?: SignalStatus,
  limit = 50
): Promise<SignalTrack[]> {
  const params = new URLSearchParams();
  if (status) params.append('status', status);
  params.append('limit', limit.toString());

  const res = await fetch(`/api/signals/status?${params}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to fetch signal statuses');
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

// ============================================================================
// V3 Positions & Orders API (Phase 6 - P6-002/P6-003)
// ============================================================================

// ============================================================================
// V3 Orders, Positions & Account API (Phase 6 - P6-002)
// ============================================================================

/**
 * Fetch positions list
 */
export async function fetchPositions(params?: {
  symbol?: string;
  is_closed?: boolean;
  limit?: number;
  offset?: number;
}): Promise<PositionsResponse> {
  const queryParams = new URLSearchParams();
  if (params?.symbol) queryParams.append('symbol', params.symbol);
  if (params?.is_closed !== undefined) queryParams.append('is_closed', String(params.is_closed));
  if (params?.limit) queryParams.append('limit', String(params.limit));
  if (params?.offset) queryParams.append('offset', String(params.offset));

  const res = await fetch(`/api/v3/positions?${queryParams}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to fetch positions');
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

/**
 * Fetch position details by ID
 */
export async function fetchPosition(positionId: string): Promise<PositionInfo> {
  const res = await fetch(`/api/v3/positions/${positionId}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to fetch position details');
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

/**
 * Close a position
 */
export async function closePosition(
  positionId: string,
  payload: ClosePositionRequest
): Promise<OrderResponse> {
  const res = await fetch(`/api/v3/positions/${positionId}/close`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const error = new Error('Failed to close position');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

/**
 * Fetch orders list
 */
export async function fetchOrders(params?: {
  symbol?: string;
  status?: OrderStatus;
  order_role?: OrderRole;
  strategy_name?: string;
  limit?: number;
  offset?: number;
}): Promise<OrdersResponse> {
  const queryParams = new URLSearchParams();
  if (params?.symbol) queryParams.append('symbol', params.symbol);
  if (params?.status) queryParams.append('status', params.status);
  if (params?.order_role) queryParams.append('order_role', params.order_role);
  if (params?.strategy_name) queryParams.append('strategy_name', params.strategy_name);
  if (params?.limit) queryParams.append('limit', String(params.limit));
  if (params?.offset) queryParams.append('offset', String(params.offset));

  const res = await fetch(`/api/v3/orders?${queryParams}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to fetch orders');
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

/**
 * Fetch order details by ID
 */
export async function fetchOrder(orderId: string): Promise<OrderResponse> {
  const res = await fetch(`/api/v3/orders/${orderId}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to fetch order details');
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

/**
 * Cancel an order
 */
export async function cancelOrder(
  orderId: string,
  symbol: string
): Promise<OrderCancelResponse> {
  const res = await fetch(`/api/v3/orders/${orderId}?symbol=${encodeURIComponent(symbol)}`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to cancel order');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

/**
 * Check order before submission (capital protection check)
 */
export async function checkOrderCapital(request: OrderCheckRequest): Promise<CapitalProtectionCheckResult> {
  const res = await fetch('/api/v3/orders/check', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const error = new Error('Order check failed');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

/**
 * Fetch account balance
 */
export async function fetchAccountBalance(): Promise<AccountBalance> {
  const res = await fetch('/api/v3/account/balance', {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to fetch account balance');
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

/**
 * Create a new order
 */
export async function createOrder(request: OrderRequest): Promise<OrderResponse> {
  const res = await fetch('/api/v3/orders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const error = new Error('Failed to create order');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

/**
 * Fetch account snapshot
 */
export async function fetchAccountSnapshot(): Promise<AccountSnapshot> {
  const res = await fetch('/api/v3/account/snapshot', {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to fetch account snapshot');
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

/**
 * Fetch account historical snapshots for equity curve
 */
export async function fetchAccountHistoricalSnapshots(days: number = 7): Promise<{ snapshots: Array<{ timestamp: number; total_equity: string }>; days: number }> {
  const res = await fetch(`/api/v3/account/snapshots/historical?days=${days}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to fetch account historical snapshots');
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

// ============================================================================
// Strategy Parameters Management API (Phase K - 策略参数配置)
// ============================================================================

/**
 * Strategy parameters response interface
 */
export interface StrategyParamsResponse {
  pinbar: Record<string, any>;
  engulfing: Record<string, any>;
  ema: Record<string, any>;
  mtf: Record<string, any>;
  atr: Record<string, any>;
  filters: Array<Record<string, any>>;
}

/**
 * Strategy parameters update request interface
 */
export interface StrategyParamsUpdateRequest {
  pinbar?: Record<string, any>;
  engulfing?: Record<string, any>;
  ema?: Record<string, any>;
  mtf?: Record<string, any>;
  atr?: Record<string, any>;
  filters?: Array<Record<string, any>>;
}

/**
 * Strategy parameters preview response interface
 */
export interface StrategyParamsPreviewResponse {
  old_config: StrategyParamsResponse;
  new_config: StrategyParamsResponse;
  changes: string[];
  warnings: string[];
}

/**
 * Get current strategy parameters
 */
export async function getStrategyParams(): Promise<StrategyParamsResponse> {
  const res = await fetch('/api/strategy/params', {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to fetch strategy parameters');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

/**
 * Update strategy parameters with hot-reload
 */
export async function updateStrategyParams(params: StrategyParamsUpdateRequest): Promise<StrategyParamsResponse> {
  const res = await fetch('/api/strategy/params', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const error = new Error('Failed to update strategy parameters');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

/**
 * Preview strategy parameter changes before applying
 */
export async function previewStrategyParams(newConfig: StrategyParamsUpdateRequest): Promise<StrategyParamsPreviewResponse> {
  const res = await fetch('/api/strategy/params/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_config: newConfig }),
  });
  if (!res.ok) {
    const error = new Error('Failed to preview strategy parameters');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

/**
 * Export strategy parameters to YAML file
 */
export async function exportStrategyParams(): Promise<Blob> {
  const res = await fetch('/api/strategy/params/export');
  if (!res.ok) {
    const error = new Error('Failed to export strategy parameters');
    (error as any).status = res.status;
    throw error;
  }
  return res.blob();
}

/**
 * Import strategy parameters from YAML file
 */
export async function importStrategyParams(file: File, description?: string): Promise<StrategyParamsResponse> {
  const formData = new FormData();
  formData.append('file', file);
  if (description) formData.append('description', description);

  const res = await fetch('/api/strategy/params/import', {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const error = new Error('Failed to import strategy parameters');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

/**
 * Fetch order kline context for charting
 * Returns order details plus K-lines surrounding the order timestamp
 *
 * @param orderId - Order ID
 * @param symbol - Symbol (e.g., "BTC/USDT:USDT")
 * @param includeChain - Whether to include order chain (TP/SL child orders)
 */
export async function fetchOrderKlineContext(orderId: string, symbol: string, includeChain: boolean = true): Promise<{
  order: OrderResponse;
  timeframe: string;
  klines: number[][]; // [timestamp_ms, open, high, low, close, volume]
  order_chain?: Array<{
    order_id: string;
    order_role: 'ENTRY' | 'TP1' | 'TP2' | 'TP3' | 'TP4' | 'TP5' | 'SL';
    direction: 'LONG' | 'SHORT';
    price: string | null;
    average_exec_price: string | null;
    filled_qty: string;
    status: 'PENDING' | 'OPEN' | 'FILLED' | 'CANCELED' | 'REJECTED' | 'EXPIRED' | 'PARTIALLY_FILLED';
    filled_at: number | null;
    created_at: number;
    exit_reason?: string | null;
  }>;
}> {
  const res = await fetch(
    `/api/v3/orders/${orderId}/klines?symbol=${encodeURIComponent(symbol)}&include_chain=${includeChain}`,
    {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    },
  );
  if (!res.ok) {
    const error = new Error('Failed to fetch order kline context');
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

// ============================================================================
// Config Snapshot Management API (版本化快照方案 B)
// ============================================================================

/**
 * 导出配置为 YAML 文件
 */
export async function exportConfig(): Promise<Blob> {
  const res = await fetch('/api/config/export');
  if (!res.ok) {
    const error = new Error('Failed to export configuration');
    (error as any).status = res.status;
    throw error;
  }
  return res.blob();
}

/**
 * 导入 YAML 配置
 * @param file YAML 配置文件
 * @param description 快照描述
 */
export async function importConfig(
  file: File,
  description?: string
): Promise<ConfigResponse> {
  const formData = new FormData();
  formData.append('file', file);
  if (description) formData.append('description', description);

  const res = await fetch('/api/config/import', {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const error = new Error('Failed to import configuration');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

/**
 * 获取快照列表（分页）
 */
export async function fetchSnapshots(
  params: SnapshotQueryParams = {}
): Promise<SnapshotListResponse> {
  const qs = new URLSearchParams();
  if (params.limit !== undefined) qs.append('limit', String(params.limit));
  if (params.offset !== undefined) qs.append('offset', String(params.offset));
  if (params.created_by !== undefined) qs.append('created_by', params.created_by);
  if (params.is_active !== undefined) qs.append('is_active', String(params.is_active));

  const res = await fetch(`/api/config/snapshots?${qs}`);
  if (!res.ok) {
    const error = new Error('Failed to fetch snapshots');
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

/**
 * 创建手动快照
 */
export async function createSnapshot(
  version: string,
  description: string
): Promise<CreateSnapshotResponse> {
  const res = await fetch('/api/config/snapshots', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ version, description }),
  });
  if (!res.ok) {
    const error = new Error('Failed to create snapshot');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

/**
 * 获取快照详情
 */
export async function fetchSnapshotDetail(id: number): Promise<ConfigSnapshotDetail> {
  const res = await fetch(`/api/config/snapshots/${id}`);
  if (!res.ok) {
    const error = new Error('Failed to fetch snapshot detail');
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

/**
 * 回滚到指定快照
 */
export async function rollbackToSnapshot(id: number): Promise<ConfigResponse> {
  const res = await fetch(`/api/config/snapshots/${id}/rollback`, {
    method: 'POST',
  });
  if (!res.ok) {
    const error = new Error('Failed to rollback to snapshot');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

/**
 * 删除快照
 */
export async function deleteSnapshot(id: number): Promise<DeleteResponse> {
  const res = await fetch(`/api/config/snapshots/${id}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const error = new Error('Failed to delete snapshot');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

// ============================================================================
// Phase 8: 策略优化器 (Optuna) API
// ============================================================================

/**
 * 参数类型定义
 */
export type ParameterType = 'int' | 'float' | 'categorical';

/**
 * 整数参数范围定义
 */
export interface IntParameter {
  type: 'int';
  low: number;
  high: number;
  step?: number;
}

/**
 * 浮点参数范围定义
 */
export interface FloatParameter {
  type: 'float';
  low: number;
  high: number;
  step?: number;
  log?: boolean;
}

/**
 * 离散选择参数定义
 */
export interface CategoricalParameter {
  type: 'categorical';
  choices: any[];
}

/**
 * 参数定义联合类型
 */
export type ParameterDefinition = IntParameter | FloatParameter | CategoricalParameter;

/**
 * 参数空间定义
 */
export interface ParameterSpace {
  // Trigger 参数
  pinbar_min_wick_ratio?: FloatParameter;
  pinbar_max_body_ratio?: FloatParameter;
  pinbar_body_position_tolerance?: FloatParameter;

  engulfing_min_body_ratio?: FloatParameter;
  engulfing_require_full_engulf?: CategoricalParameter;

  // Filter 参数
  ema_period?: IntParameter;
  mtf_require_confirmation?: CategoricalParameter;
  volume_surge_multiplier?: FloatParameter;
  volume_surge_lookback_periods?: IntParameter;
  volatility_min_atr_ratio?: FloatParameter;
  volatility_max_atr_ratio?: FloatParameter;
  atr_period?: IntParameter;
  atr_min_atr_ratio?: FloatParameter;

  // Risk 参数
  max_loss_percent?: FloatParameter;

  // 自定义参数
  [key: string]: ParameterDefinition | undefined;
}

/**
 * 优化目标类型
 */
export type OptimizationObjective =
  | 'sharpe'         // 夏普比率最大化
  | 'sortino'        // 索提诺比率最大化
  | 'pnl_maxdd'      // 收益回撤比最大化
  | 'total_return'   // 总收益最大化
  | 'win_rate';      // 胜率最大化

/**
 * 优化请求参数
 */
export interface OptimizationRequest {
  symbol: string;
  timeframe: string;
  start_time: number;
  end_time: number;
  objective: OptimizationObjective;
  parameter_space: ParameterSpace;
  n_trials: number;
  timeout_seconds?: number;
  seed?: number;
}

/**
 * 优化启动响应
 */
export interface OptimizationStartResponse {
  optimization_id: string;
  status: 'running';
  created_at: string;
  estimated_duration_seconds?: number;
}

/**
 * 优化进度状态
 */
export interface OptimizationStatus {
  optimization_id: string;
  status: 'running' | 'completed' | 'failed' | 'stopped';
  progress: {
    current_trial: number;
    total_trials: number;
    elapsed_seconds: number;
    estimated_remaining_seconds?: number;
  };
  current_best: {
    trial_number: number;
    objective_value: number;
    params: Record<string, any>;
  } | null;
  error_message?: string;
}

/**
 * 优化停止响应
 */
export interface OptimizationStopResponse {
  optimization_id: string;
  status: 'stopped';
  stopped_at: string;
  final_trial_count: number;
}

/**
 * 最佳试验结果
 */
export interface BestTrial {
  trial_number: number;
  objective_value: number;
  params: Record<string, any>;
  metrics: {
    total_return: number;
    sharpe_ratio: number;
    sortino_ratio: number;
    max_drawdown: number;
    win_rate: number;
    total_trades: number;
  };
}

/**
 * 试验历史记录
 */
export interface TrialHistory {
  trial_number: number;
  objective_value: number | null;
  params: Record<string, any>;
  datetime_start: string;
  datetime_complete: string | null;
  state: 'COMPLETE' | 'FAIL' | 'RUNNING' | 'PRUNED';
}

/**
 * 优化结果响应
 */
export interface OptimizationResults {
  optimization_id: string;
  status: 'completed' | 'stopped' | 'failed';
  study_name: string;
  total_trials: number;
  best_trial: BestTrial;
  top_trials: Array<{
    trial_number: number;
    objective_value: number;
    params: Record<string, any>;
  }>;
  trials: TrialHistory[];
  importance?: Record<string, number>;
  optimization_history?: Array<{
    trial_number: number;
    objective_value: number | null;
  }>;
}

/**
 * 参数重要性数据
 */
export interface ParameterImportance {
  param_name: string;
  importance: number;
}

/**
 * 优化历史点数据
 */
export interface OptimizationHistoryPoint {
  trial_number: number;
  objective_value: number | null;
  best_so_far: number | null;
}

/**
 * 平行坐标图数据点
 */
export interface ParallelCoordinatePoint {
  trial_number: number;
  objective_value: number;
  params: Record<string, number | string>;
}

// ============================================================================
// Phase 8 API 函数
// ============================================================================

/**
 * 启动参数优化任务
 */
export async function runOptimization(payload: OptimizationRequest): Promise<OptimizationStartResponse> {
  const res = await fetch('/api/optimization/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const error = new Error('Failed to start optimization');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

/**
 * 获取优化任务状态
 */
export async function fetchOptimizationStatus(id: string): Promise<OptimizationStatus> {
  const res = await fetch(`/api/optimization/${id}/status`);
  if (!res.ok) {
    const error = new Error('Failed to fetch optimization status');
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

/**
 * 获取优化结果
 */
export async function fetchOptimizationResults(id: string): Promise<OptimizationResults> {
  const res = await fetch(`/api/optimization/${id}/results`);
  if (!res.ok) {
    const error = new Error('Failed to fetch optimization results');
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

/**
 * 停止优化任务
 */
export async function stopOptimization(id: string): Promise<OptimizationStopResponse> {
  const res = await fetch(`/api/optimization/${id}/stop`, {
    method: 'POST',
  });
  if (!res.ok) {
    const error = new Error('Failed to stop optimization');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

/**
 * 获取优化列表
 */
export async function fetchOptimizations(params?: {
  limit?: number;
  offset?: number;
  status?: string;
}): Promise<{ optimizations: Array<{
  optimization_id: string;
  status: string;
  created_at: string;
  objective: string;
  symbol: string;
  timeframe: string;
  total_trials: number;
}>; total: number }> {
  const queryParams = new URLSearchParams();
  if (params?.limit) queryParams.append('limit', String(params.limit));
  if (params?.offset) queryParams.append('offset', String(params.offset));
  if (params?.status) queryParams.append('status', params.status);

  const res = await fetch(`/api/optimization?${queryParams}`);
  if (!res.ok) {
    const error = new Error('Failed to fetch optimizations');
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

// ============================================================================
// Order Tree API (F2 - Orders 页面树形表格集成)
// ============================================================================

/**
 * Fetch order tree data
 */
export async function fetchOrderTree(params?: {
  symbol?: string;
  timeframe?: string;
  start_date?: string;
  end_date?: string;
  days?: number;
  page?: number;
  page_size?: number;
}): Promise<OrderTreeResponse> {
  const queryParams = new URLSearchParams();
  if (params?.symbol) queryParams.append('symbol', params.symbol);
  if (params?.timeframe) queryParams.append('timeframe', params.timeframe);
  if (params?.start_date) queryParams.append('start_date', params.start_date);
  if (params?.end_date) queryParams.append('end_date', params.end_date);
  if (params?.days) queryParams.append('days', String(params.days));
  if (params?.page) queryParams.append('page', String(params.page));
  if (params?.page_size) queryParams.append('page_size', String(params.page_size));

  const res = await fetch(`/api/v3/orders/tree?${queryParams}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to fetch order tree');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

/**
 * Delete order chain batch
 */
export async function deleteOrderChain(
  request: OrderBatchDeleteRequest
): Promise<OrderBatchDeleteResponse> {
  const res = await fetch('/api/v3/orders/batch', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const error = new Error('Failed to delete order chain');
    (error as any).status = res.status;
    (error as any).info = await res.json().catch(() => ({}));
    throw error;
  }
  return res.json();
}

