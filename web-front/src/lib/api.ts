import useSWR from 'swr';

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
  ema_trend: 'bullish' | 'bearish';
  mtf_status: 'confirmed' | 'rejected' | 'disabled' | 'unavailable';
  status: 'pending' | 'won' | 'lost';
  pnl_ratio?: string | null;
  win_rate?: number;
  strategy_name?: string | null;
  score?: number | string | null;
  kline_timestamp?: number;
  risk_reward_info?: string;
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
  | 'price_action';

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
  stage: string;
  passed: boolean;
  reason?: string;
  details?: Record<string, any>;
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
 * Run backtest with given parameters
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
