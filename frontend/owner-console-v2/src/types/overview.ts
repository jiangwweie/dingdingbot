// Types for Overview Page in BRC Owner Console V2

export type SystemHealthStatus = 'healthy' | 'attention' | 'danger';

export interface SystemPulseData {
  status: SystemHealthStatus;
  status_label: string;
  summary: string;
  details: string;
  active_strategy_count: number;
  total_strategy_count: number;
  entry_status_label: string;
  incidents_count: number;
  data_freshness_seconds: number;
  ticket_capacity_used: number;
  ticket_capacity_total: number;
}

export interface TodayPerformanceMetrics {
  net_pnl_usd: number;
  net_r: number;
  completed_trades_count: number;
  win_trades_count: number;
  loss_trades_count: number;
  win_rate_percent: number;
  profit_factor: number;
}

export interface TradeEpisodeSummary {
  ticket_id: string;
  strategy_id: string;
  strategy_name_zh: string;
  symbol: string;
  side: 'long' | 'short';
  entry_price: number;
  current_price: number;
  pnl_usd: number;
  pnl_r: number;
  duration_formatted: string;
  protection_status: 'protected_initial' | 'breakeven_moved' | 'trailing' | 'exit_pending';
  protection_label: string;
  stop_price: number;
  take_profit_price?: number;
  tp1_status: 'pending' | 'completed' | 'none';
  // Detailed causality nodes for Drawer
  causality_stages?: CausalityStageNode[];
}

export interface CausalityStageNode {
  stage_number: number;
  stage_name: string;
  stage_title: string;
  timestamp_utc: string;
  status: 'passed' | 'active' | 'pending' | 'failed';
  summary_zh: string;
  evidence_json?: Record<string, any>;
}

export interface StrategyPerformanceItem {
  strategy_id: string;
  name_zh: string;
  timeframe: string;
  status: 'running' | 'waiting' | 'paused' | 'blocked';
  status_label: string;
  today_r: number;
  today_trades_count: number;
  win_count: number;
  loss_count: number;
  active_tickets_count: number;
}

export interface RecentEventNotice {
  id: string;
  timestamp_utc: string;
  type: 'info' | 'success' | 'warning' | 'alert';
  title: string;
  detail: string;
  source_worker: 'Observation' | 'Entry' | 'Lifecycle' | 'Reconciliation' | 'Selection';
}
