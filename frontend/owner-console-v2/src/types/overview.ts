// Types for Overview Page in BRC Owner Console V2 (Strictly mapped to Real API)

export type SystemHealthStatus = 'healthy' | 'attention' | 'danger';

export interface SystemPulseData {
  status: SystemHealthStatus;
  status_label: string;
  summary: string;
  details: string;
  conclusion?: 'no_action' | 'attention' | 'intervention';
  freshness?: 'fresh' | 'stale' | 'unavailable' | 'contradictory';
  freshness_label?: string;
  active_strategy_count: number;
  total_strategy_count: number;
  entry_status_label: string;
  incidents_count: number;
  active_ticket_count?: number;
  ticket_capacity_used?: number;
  ticket_capacity_total?: number | null;
  data_freshness_seconds?: number;
  snapshot_id?: string;
  generated_at?: string;
}

export interface TodayPerformanceMetrics {
  income_coverage?: string;
  net_pnl_formatted?: string;
  net_pnl_usd?: number;
  net_pnl_is_positive?: boolean | null;
  net_r_formatted?: string;
  net_r?: number;
  net_r_is_positive?: boolean | null;
  completed_trades_count?: number;
  win_trades_count?: number;
  loss_trades_count?: number;
  win_rate_percent?: number;
  profit_factor?: number;
  today_signal_count?: number;
  admitted_signal_count?: number;
  rejected_signal_count?: number;
  execution_incident_count?: number;
  pnl_unavailable_reason?: string | null;
}

export interface TradeEpisodeSummary {
  ticket_id: string;
  strategy_id: string;
  strategy_name_zh: string;
  symbol: string;
  side: 'long' | 'short';
  lifecycle_stage?: string;
  lifecycle_stage_zh?: string;
  completed_stage_count?: number;
  total_stage_count?: number;
  ticket_status?: string;
  issued_at_ms?: number;
  issued_at_formatted?: string;
  attention_items?: string[];
  net_pnl_formatted?: string;
  net_r_formatted?: string;
  // Optional prototype fixture fields
  entry_price?: number;
  current_price?: number;
  pnl_usd?: number;
  pnl_r?: number;
  duration_formatted?: string;
  protection_status?: 'protected_initial' | 'breakeven_moved' | 'trailing' | 'exit_pending';
  protection_label?: string;
  stop_price?: number;
  take_profit_price?: number;
  tp1_status?: 'pending' | 'completed' | 'none';
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
  strategy_version_id?: string | null;
  name_zh: string;
  timeframe: string;
  status: 'running' | 'waiting' | 'paused' | 'blocked';
  status_label: string;
  ticket_count?: number;
  win_count: number;
  loss_count: number;
  net_pnl_formatted?: string;
  net_r_formatted?: string;
  active_tickets_count: number;
  is_metrics_available?: boolean;
  today_r?: number;
  today_trades_count?: number;
}

export interface AttentionItem {
  id: string;
  type: 'info' | 'warning' | 'alert';
  title: string;
  detail?: string;
}

export interface RecentEventNotice {
  id: string;
  timestamp_utc: string;
  type: 'info' | 'success' | 'warning' | 'alert';
  title: string;
  detail: string;
  source_worker: 'Observation' | 'Entry' | 'Lifecycle' | 'Reconciliation' | 'Selection';
}
