export type FreshnessStatus = 'Fresh' | 'Stale' | 'Possibly Dead';

export interface RuntimeOverview {
  profile: string;
  version: string;
  hash: string;
  frozen: boolean;
  symbol: string;
  timeframe: string;
  mode: string;
  backend_summary: string;
  exchange_health: string;
  pg_health: string;
  webhook_health: string;
  breaker_count: number;
  reconciliation_summary: string;
  server_time: string;
  last_runtime_update_at: string;
  last_heartbeat_at: string;
  freshness_status: FreshnessStatus;
}

export interface Signal {
  id: string;
  symbol: string;
  timeframe: string;
  direction: 'LONG' | 'SHORT' | 'FLAT';
  strategy_name: string;
  score: number;
  status: string;
  created_at: string;
}

export interface Attempt {
  id: string;
  symbol: string;
  timeframe: string;
  direction: string;
  strategy_name: string;
  final_result: string;
  filter_results_summary: string;
  reject_reason: string;
  timestamp: string;
}

export interface ExecutionIntent {
  intent_id: string;
  signal_id: string;
  symbol: string;
  status: 'PENDING' | 'EXECUTING' | 'COMPLETED' | 'FAILED';
  created_at: string;
  updated_at: string;
}

export interface Order {
  order_id: string;
  role: 'ENTRY' | 'TP' | 'SL';
  raw_role?: string;
  symbol: string;
  type?: string;
  status: 'NEW' | 'PARTIALLY_FILLED' | 'FILLED' | 'CANCELED' | 'REJECTED';
  quantity: number;
  price: number | null;
  updated_at: string;
}

export interface RuntimeHealth {
  pg_status: 'OK' | 'DEGRADED' | 'DOWN';
  exchange_status: 'OK' | 'DEGRADED' | 'DOWN';
  notification_status: 'OK' | 'DEGRADED' | 'DOWN';
  recent_warnings: string[];
  recent_errors: string[];
  startup_markers: Record<string, 'PASSED' | 'FAILED' | 'PENDING'>;
  breaker_summary: {
    total_tripped: number;
    active_breakers: string[];
    last_trip_time: string | null;
  };
  recovery_summary: {
    pending_tasks: number;
    completed_tasks: number;
    last_recovery_time: string | null;
  };
}

export interface Candidate {
  candidate_name: string;
  generated_at: string;
  source_profile: string;
  git_commit: string;
  objective: string;
  review_status: 'PASS_STRICT' | 'PASS_STRICT_WITH_WARNINGS' | 'PASS_LOOSE' | 'REJECT' | 'PENDING';
  strict_gate_result: 'PASSED' | 'FAILED';
  warnings: string[];
}

export type ReviewStatus =
  | 'PASS_STRICT'
  | 'PASS_STRICT_WITH_WARNINGS'
  | 'PASS_LOOSE'
  | 'REJECT'
  | 'PENDING';

export type StrictGateResult = 'PASSED' | 'FAILED';

export interface CandidateMetadata {
  candidate_name: string;
  generated_at: string;
  source_profile: Record<string, unknown>;
  git: Record<string, unknown>;
  objective: string;
  status: string;
}

export interface CandidateTrialItem {
  trial_number: number;
  objective_value: number | null;
  sharpe_ratio?: number | null;
  sortino_ratio?: number | null;
  total_return?: number | null;
  max_drawdown?: number | null;
  total_trades: number;
  win_rate?: number | null;
  params?: Record<string, unknown>;
  completed_at?: string | null;
}

export interface CandidateDetail {
  candidate_name: string;
  metadata: CandidateMetadata;
  best_trial: CandidateTrialItem | null;
  top_trials: CandidateTrialItem[];
  fixed_params: Record<string, unknown>;
  runtime_overrides: Record<string, unknown>;
  constraints: Record<string, unknown>;
  resolved_request: Record<string, unknown>;
  reproduce_cmd: string;
  generated_at?: string;
  source_profile?: Record<string, unknown>;
  git?: Record<string, unknown>;
  objective?: string;
  status?: string;
}

export interface ReplayContext {
  candidate_name: string;
  reproduce_cmd: string;
  metadata: CandidateMetadata;
  resolved_request: Record<string, unknown>;
  runtime_overrides: Record<string, unknown>;
}

export interface StrictGateCheckItem {
  gate: string;
  threshold: string;
  actual?: string | null;
  passed: boolean;
}

export interface ReviewSummary {
  candidate_name: string;
  review_status: ReviewStatus;
  strict_gate_result: StrictGateResult;
  strict_v1_checklist: StrictGateCheckItem[];
  warnings: string[];
  params_at_boundary: string[];
  summary: string;
}

export interface BacktestRecord {
  id: string;
  candidate_ref: string;
  symbol: string;
  timeframe: string;
  start_date: string;
  end_date: string;
  status: 'COMPLETED' | 'RUNNING' | 'FAILED';
  metrics: {
    total_return: number | null;
    sharpe: number | null;
    max_drawdown: number | null;
    win_rate: number | null;
    trades: number | null;
  };
}

export type ResearchJobStatus = 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELED';
export type CandidateRecordStatus = 'DRAFT' | 'REVIEWED' | 'REJECTED' | 'RECOMMENDED';

export interface ResearchEngineCostSpec {
  initial_balance: string | number;
  slippage_rate: string | number;
  tp_slippage_rate: string | number;
  fee_rate: string | number;
}

export interface ResearchSpec {
  kind?: 'backtest';
  name: string;
  profile_name?: string;
  symbol: string;
  timeframe: string;
  start_time_ms: number;
  end_time_ms: number;
  limit?: number;
  mode?: 'v3_pms';
  costs?: ResearchEngineCostSpec;
  notes?: string | null;
}

export interface ResearchJob {
  id: string;
  kind: 'backtest';
  name: string;
  spec_ref: string;
  status: ResearchJobStatus;
  run_result_id: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  requested_by: string;
  error_code: string | null;
  error_message: string | null;
  progress_pct: number | null;
  spec: ResearchSpec;
}

export interface ResearchJobListResponse {
  jobs: ResearchJob[];
  total: number;
  limit: number;
  offset: number;
}

export interface ResearchJobAccepted {
  status: 'accepted';
  job_id: string;
  job_status: ResearchJobStatus;
}

export interface ResearchRunResult {
  id: string;
  job_id: string;
  kind: 'backtest';
  spec_snapshot: Record<string, unknown>;
  summary_metrics: Record<string, unknown>;
  artifact_index: Record<string, string>;
  source_profile: string | null;
  generated_at: string;
}

export interface ResearchRunListResponse {
  runs: ResearchRunResult[];
  total: number;
  limit: number;
  offset: number;
}

export interface CandidateRecord {
  id: string;
  run_result_id: string;
  candidate_name: string;
  status: CandidateRecordStatus;
  review_notes: string;
  applicable_market: string | null;
  risks: string[];
  recommendation: string | null;
  created_at: string;
  updated_at: string;
}

export interface CompareResponse {
  baseline_label: string;
  candidate_a_label: string;
  candidate_b_label: string | null;
  rows: CompareRow[];
}

export interface CompareRow {
  metric: string;
  baseline: number | null;
  candidate_a: number | null;
  candidate_b: number | null;
  diff_a: number | null;
  diff_b: number | null;
}

export interface Position {
  symbol: string;
  direction: 'LONG' | 'SHORT';
  quantity: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  pnl_percent: number;
  leverage: number;
}

export interface PortfolioContext {
  total_equity: number;
  available_balance: number;
  unrealized_pnl: number;
  total_exposure: number;
  daily_loss_used: number;
  daily_loss_limit: number;
  max_total_exposure: number;
  leverage_usage: number;
  positions: Position[];
}

export interface AppEvent {
  id: string;
  timestamp: string;
  category: 'STARTUP' | 'RECONCILIATION' | 'BREAKER' | 'RECOVERY' | 'WARNING' | 'ERROR' | 'SIGNAL' | 'EXECUTION';
  severity: 'INFO' | 'WARN' | 'ERROR' | 'SUCCESS';
  message: string;
  related_entities?: string[];
}

export interface ConfigSnapshot {
  identity: {
    profile: string;
    version: string;
    hash: string;
  };
  market: Record<string, unknown>;
  strategy: Record<string, unknown>;
  risk: Record<string, unknown>;
  execution: Record<string, unknown>;
  backend: Record<string, unknown>;
  source_of_truth_hints: string[];
  profile?: string;
  version?: number;
  hash?: string;
  environment?: Record<string, unknown>;
}
