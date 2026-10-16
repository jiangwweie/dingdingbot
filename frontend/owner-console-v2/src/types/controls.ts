export type ConfiguredState = 'enabled' | 'paused';

export interface GlobalEntryState {
  configured_state: ConfiguredState;
  effective_state: 'enabled' | 'paused';
  policy_version: number;
  active_ticket_count: number;
  first_blocker?: string | null;
}

export type AdmissionStatus = 'cleared' | 'blocked' | 'unknown';
export type AdmissionFactSource = 'server_admission_fact' | 'client_derived' | 'unknown_fact';

export interface StrategyAdmissionHealth {
  status: AdmissionStatus;
  summary: string;
  source: AdmissionFactSource;
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
  strategy_version_id?: string | null;
  updated_at_ms: number;
  reason_label: string;
  admission_health: StrategyAdmissionHealth;
  active_tickets: ActiveTicketMini[];
  active_ticket_count?: number;
  is_retired?: boolean;
}

export interface GenericMemberFacts {
  exchange_instrument_id: string;
  runtime_scope_id: string;
  policy_enabled: boolean | null;
  scope_entry_enabled: boolean;
  entry_submit_enabled: boolean | null;
  warm_valid_until_ms: number | null;
  policy_version: number | null;
}

export interface GenericUniverseMember {
  facts: GenericMemberFacts;
  first_blocker: string | null;
}

export interface GenericSelectionDiagnostic {
  kind: 'generic';
  strategy_group_id: string;
  installed: boolean;
  cadence_hours: number;
  selection_mode: 'dynamic_selection' | 'static_baseline' | 'disabled';
  pending_selection_mode: 'dynamic_selection' | 'static_baseline' | null;
  pending_effective_period_anchor_ms: number | null;
  rollback_baseline_id: string | null;
  selection_epoch_id: string | null;
  control_version: number;
  current_authority_id: string | null;
  current_authority_outcome: string | null;
  authority_status_zh: string;
  first_blocker: string | null;
  membership_valid_until_ms: number | null;
  consecutive_missed_periods: number | null;
  latest_ready_count: number | null;
  latest_selected_count: number | null;
  materialization_generation_id: string | null;
  materialization_state: string | null;
  materialization_deadline_ms: number | null;
  vacuum_state: string | null;
  vacuum_fenced_at_ms: number | null;
  latest_successful_completion_age_ms: number | null;
  latest_successful_cutoff_age_ms: number | null;
  membership_source_age_ms: number | null;
  members: GenericUniverseMember[];
}

export interface OrbSelectionDiagnostic {
  kind: 'orb';
  strategy_group_id: string;
  installed: boolean;
  cadence_hours: 24;
  selection_mode: 'dynamic_selection' | 'static_baseline' | 'disabled';
  pending_selection_mode: 'dynamic_selection' | 'static_baseline' | null;
  pending_effective_period_anchor_ms: number | null;
  rollback_baseline_id: string | null;
  selection_epoch_id: string | null;
  control_version: number;
  authority_status_zh: string;
  authority_outcome: string | null;
  authority_id: string | null;
  authority_effective_from_ms: number | null;
  authority_expires_at_ms: number | null;
  first_eligible_close_time_ms: number | null;
  snapshot_expires_at_ms: number | null;
  snapshot_cutoff_at_ms: number | null;
  snapshot_decision_at_ms: number | null;
  snapshot_created_at_ms: number | null;
  candidate_count: number;
  ready_count: number;
  selected_count: number;
  selected_members: string[];
  materialization_state: string;
  vacuum_state: string;
  vacuum_is_blocking: boolean;
}

export type SelectionDiagnosticData = GenericSelectionDiagnostic | OrbSelectionDiagnostic;

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
