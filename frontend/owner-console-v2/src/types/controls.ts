export type ConfiguredState = 'enabled' | 'paused';

export interface GlobalEntryState {
  configured_state: ConfiguredState;
  effective_state: 'enabled' | 'paused';
  policy_version: number;
  active_ticket_count: number;
  first_blocker?: string | null;
}

export type AdmissionStatus = 'cleared' | 'blocked' | 'unknown';

export interface StrategyAdmissionHealth {
  status: AdmissionStatus;
  summary: string;
  source: 'server_admission_fact' | 'unknown_fact';
}

export interface ActiveTicketMini {
  ticket_id: string;
  symbol: string;
  side: 'long' | 'short';
  pnl_r: string;
  stage: string;
}

export interface StrategyControlItem {
  strategy_group_id: string;
  name_zh: string;
  timeframe: string;
  configured_state: ConfiguredState;
  effective_state: string;
  control_version: number;
  updated_at_ms: number;
  reason_label: string;
  admission_health: StrategyAdmissionHealth;
  active_tickets: ActiveTicketMini[];
  is_retired?: boolean;
}

export interface UniverseMemberItem {
  exchange_instrument_id: string;
  selected: boolean;
  first_blocker: string | null;
}

export interface SelectionDiagnosticData {
  strategy_group_id: string;
  installed: boolean;
  cadence_hours: number;
  selection_mode: 'dynamic_selection' | 'static_baseline' | 'disabled';
  pending_selection_mode: 'dynamic_selection' | 'static_baseline' | null;
  pending_effective_period_anchor_ms: number | null;
  rollback_baseline_id: string | null;
  selection_epoch_id: string | null;
  control_version: number;
  current_authority_outcome: string;
  authority_status_zh: string;
  membership_valid_until_ms: number;
  consecutive_missed_periods: number;
  latest_ready_count: number;
  latest_selected_count: number;
  materialization_state: string;
  materialization_deadline_ms: number | null;
  vacuum_state: string;
  vacuum_fenced_at_ms: number | null;
  latest_successful_completion_age_ms: number;
  latest_successful_cutoff_age_ms: number;
  membership_source_age_ms: number;
  members: UniverseMemberItem[];
}

export interface AccountCapacityData {
  max_concurrent_tickets: number;
  max_same_strategy_side: number;
  family_limits: {
    long_continuation: number;
    rally_failure_short: number;
    [key: string]: number;
  };
  strategy_side_active_counts: Record<string, number>;
  active_ticket_count?: number;
  remaining_ticket_slots?: number;
  gross_stop_risk?: string | null;
  gross_stop_risk_limit?: string | null;
  long_stop_risk?: string | null;
  short_stop_risk?: string | null;
  family_active_counts?: Record<string, number>;
  source?: string;
  [key: string]: any;
}

export interface FlattenPreviewTicket {
  ticket_id: string;
  strategy_group_id: string;
  instrument: string;
  side: 'long' | 'short';
  stage: string;
  unrealized_r: string;
}

export interface FlattenPreviewData {
  owner_policy_version: number;
  snapshot_digest: string;
  tickets: FlattenPreviewTicket[];
}

export interface RecentOperationItem {
  authorization_id: string;
  name: string;
  state: string;
  ticket_count: number;
  updated_at_ms: number;
  created_at_ms?: number;
  result_label?: string;
  first_blocker: string | null;
}
