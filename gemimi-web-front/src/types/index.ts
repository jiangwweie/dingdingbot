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
  direction: 'LONG' | 'SHORT' | 'FLAT';
  strategy_name: string;
  final_result: 'ACCEPTED' | 'REJECTED';
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
  symbol: string;
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

export interface CandidateMetadata {
  study_name?: string;
  trials?: number;
  duration_seconds?: number;
  created_by?: string;
  engine?: string;
  [key: string]: unknown;
}

export interface BestTrial {
  number: number;
  value: number;
  params?: Record<string, string | number | boolean>;
}

export interface TrialReference {
  number: number;
  value: number;
}

export interface RubricEvaluation {
  sharpe_ratio?: number;
  total_trades?: number;
  max_drawdown?: number;
  [key: string]: unknown;
}

export interface CandidateDetail {
  candidate_name: string;
  metadata: CandidateMetadata;
  best_trial: BestTrial;
  top_trials: TrialReference[];
  fixed_params: Record<string, string | number | boolean>;
  runtime_overrides: Record<string, string | number | boolean>;
  constraints: Record<string, string | number | boolean>;
  resolved_request: string;
  rubric_evaluation: RubricEvaluation;
}

export interface ReplayContext {
  candidate_name: string;
  reproduce_cmd: string;
  metadata: CandidateMetadata;
  resolved_request: Record<string, string | number | boolean>;
  runtime_overrides: Record<string, string | number | boolean>;
}
