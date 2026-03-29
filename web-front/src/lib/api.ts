import useSWR from 'swr';

// Import recursive logic tree types from types/strategy.ts
import type { LogicNode, LogicNodeChildren, LeafNode } from '../types/strategy';

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
  take_profit?: string;
  position_size: string;
  leverage: number;
  tags?: Array<{ name: string; value: string }>;  // Dynamic filter tags (e.g., [{"name": "EMA", "value": "Bullish"}])
  status: 'pending' | 'won' | 'lost';
  pnl_ratio?: string | null;
  win_rate?: number;
  strategy_name?: string | null;
  score?: number | string | null;
  kline_timestamp?: number;
  risk_reward_info?: string;
  source?: 'live' | 'backtest';  // Signal source: live trading or backtest
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
  default_leverage: number;
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

/**
 * Legacy strategy config for backward compatibility (deprecated)
 */
export interface LegacyStrategyConfig {
  pinbar_enabled: boolean;
  min_wick_ratio: number;
  max_body_ratio: number;
  body_position_tolerance: number;
  trend_filter_enabled: boolean;
  mtf_validation_enabled: boolean;
}

/**
 * Legacy system config for backward compatibility (deprecated)
 */
export interface LegacySystemConfig {
  strategy: LegacyStrategyConfig;
  risk: RiskConfig;
  user_symbols: string[];
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
 * Fetch strategy templates list for backtest sandbox
 */
export async function fetchStrategyTemplates(): Promise<{ id: number; name: string; description: string | null }[]> {
  const res = await fetch('/api/strategies/templates', {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to fetch strategy templates');
    (error as any).status = res.status;
    throw error;
  }
  const data = await res.json();
  return data.templates || [];
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
 * Run backtest with given parameters
 *
 * Backtest signals are automatically saved to database.
 */
export async function runBacktest(payload: BacktestRequest): Promise<BacktestReport> {
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
// Config Snapshot API (配置快照版本化 - S5-3)
// ============================================================================

/**
 * Config snapshot interface
 */
export interface ConfigSnapshot {
  id: number;
  version: string;
  config_json: string;
  description: string;
  created_at: string;
  created_by: string;
  is_active: boolean;
}

/**
 * Create snapshot request
 */
export interface CreateSnapshotRequest {
  version: string;
  description: string;
  config_json?: string;
}

/**
 * Fetch all config snapshots
 */
export async function fetchSnapshots(): Promise<{ total: number; data: ConfigSnapshot[] }> {
  const res = await fetch('/api/config/snapshots', {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to fetch snapshots');
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

/**
 * Create a new config snapshot
 */
export async function createSnapshot(payload: CreateSnapshotRequest): Promise<ConfigSnapshot> {
  const res = await fetch('/api/config/snapshots', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const error = new Error('Failed to create snapshot');
    (error as any).info = await res.json().catch(() => ({}));
    (error as any).status = res.status;
    throw error;
  }
  return res.json();
}

/**
 * Delete a config snapshot
 */
export async function deleteSnapshot(id: number): Promise<void> {
  const res = await fetch(`/api/config/snapshots/${id}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const error = new Error('Failed to delete snapshot');
    (error as any).status = res.status;
    throw error;
  }
}

/**
 * Activate a config snapshot (rollback)
 */
export async function applySnapshot(id: number): Promise<void> {
  const res = await fetch(`/api/config/snapshots/${id}/activate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const error = new Error('Failed to activate snapshot');
    (error as any).info = await res.json().catch(() => ({}));
    (error as any).status = res.status;
    throw error;
  }
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
  FILLED = 'filled',
  CANCELLED = 'cancelled',
  REJECTED = 'rejected',
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
