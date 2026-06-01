const BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

export type ApiError = {
  status: number;
  message: string;
  payload?: unknown;
};

export type SessionResponse = {
  authenticated: boolean;
  username?: string | null;
  expires_at_ms?: number | null;
  current_stage: string;
  next_recommended_step: string;
  global_planning_stage: string;
  live_ready: false;
};

export type DashboardResponse = {
  current_stage: string;
  next_recommended_step: string;
  global_planning_stage: string;
  terminology: Record<string, string>;
  owner_questions: string[];
  live_ready: false;
};

export type RuntimeSafetyResponse = {
  runtime_bound: boolean;
  profile?: string | null;
  testnet?: boolean | null;
  gks_active?: boolean | null;
  startup_guard_armed?: boolean | null;
  flatness_known: boolean;
  current_stage: string;
  next_recommended_step: string;
  global_planning_stage: string;
  human_summary: string;
  live_ready: false;
};

export type ReadinessAction = {
  action_id: string;
  title: string;
  description: string;
  enabled: boolean;
  disabled_reason?: string | null;
  route?: string | null;
  button_label: string;
  what_happens: string;
  what_will_not_happen: string;
  account_impact: string;
  risk_level: 'read_only' | 'controlled_testnet' | 'blocked';
};

export type RiskDecision =
  | 'ALLOW_READ'
  | 'ALLOW_MONITOR'
  | 'BLOCK_TESTNET'
  | 'ATTENTION_REQUIRED'
  | 'BLOCK_ALL_STATE_CHANGE';

export type RuntimeState =
  | 'observe'
  | 'monitor'
  | 'testnet_rehearsal'
  | 'paused'
  | 'stopped'
  | 'flattening'
  | 'attention_required';

export type ActionCardType =
  | 'read_status'
  | 'enter_monitor'
  | 'testnet_rehearsal'
  | 'pause_new_entries'
  | 'emergency_stop_runtime'
  | 'emergency_flatten';

export type BrcActionCard = {
  action_card_id: string;
  title: string;
  action_type: ActionCardType;
  enabled: boolean;
  disabled_reason?: string | null;
  route?: string | null;
  button_label: string;
  authority_source: 'application_preflight';
  fact_snapshot_id: string;
  preflight_result_id: string;
  idempotency_key: string;
  expiry_time?: number | null;
  current_state: RuntimeState;
  allowed_next_states: RuntimeState[];
  blocked_next_states: string[];
  reversible: boolean;
  final_state_proof_required: boolean;
  hard_blocks: string[];
  advisory_warnings: string[];
  confirmation_phrase?: string | null;
  account_impact: string;
  what_will_change: string;
  what_will_not_change: string;
};

export type ReadinessResponse = {
  mode: 'standalone_console' | 'runtime_bound_console' | 'brc_ready' | 'testnet_ready' | 'blocked';
  current_conclusion: string;
  why: string[];
  account_impact: string;
  next_step: string;
  available_actions: ReadinessAction[];
  disabled_actions: ReadinessAction[];
  latest_campaign?: Record<string, unknown> | null;
  environment_boundary: Record<string, unknown>;
  runtime_state: RuntimeState;
  risk_decision: RiskDecision;
  risk_account_summary: Record<string, unknown>;
  strategy_playbook_summary: Record<string, unknown>;
  action_cards: BrcActionCard[];
  global_cutoff_controls: BrcActionCard[];
  latest_audit?: Record<string, unknown> | null;
  runtime_summary: Record<string, unknown>;
  review_summary: Record<string, unknown>;
  markets_summary: Record<string, unknown>;
  playbook_summary: Record<string, unknown>;
  parameter_summary: Record<string, unknown>;
  audit_summary: Record<string, unknown>;
  ai_investigator_summary: Record<string, unknown>;
  developer_details: Record<string, unknown>;
  live_ready: false;
};

export type Mi001SolReadinessResponse = {
  candidate: {
    id: string;
    candidate_id: string;
    strategy_family: string;
    variant_label: string;
    symbol: string;
    side: 'long';
    status: string;
  };
  evidence: {
    signal_count: number;
    mean_72h: string;
    positive_rate_72h: string;
    mean_7d: string;
    positive_rate_7d: string;
    limitations: string[];
  };
  risk_policy: {
    capital_source: string;
    account_equity: string;
    available_margin: string;
    max_leverage: number;
    operation_layer_notional_cap: string;
    max_notional_rule: string;
    max_total_loss_rule: string;
    prohibitions: string[];
  };
  readiness: {
    verdict: string;
    blockers: string[];
    checks: Array<{ check: string; status: string; evidence: string; blocking: boolean }>;
  };
  owner_actions: {
    allowed_actions: Array<{
      action_id: string;
      label: string;
      enabled: boolean;
      endpoint?: string | null;
      disabled_reason?: string | null;
      safety_text: string;
    }>;
    disabled_actions: Array<{
      action_id: string;
      label: string;
      enabled: boolean;
      endpoint?: string | null;
      disabled_reason?: string | null;
      safety_text: string;
    }>;
  };
  non_permissions: {
    no_execution_permission: true;
    no_order_permission: true;
    no_runtime_start: true;
    no_leverage_change: true;
    no_order_capability: true;
    no_automatic_trial_start: true;
  };
  startup_guard_action: {
    endpoint: string;
    label: string;
    enabled: boolean;
    enabled_when: string[];
    safety_text: string;
    does_not_start_trial: true;
    does_not_create_execution_intent: true;
    does_not_place_order: true;
  };
  terminal_state: string;
  source_refs: string[];
  live_ready: false;
};

export type StrategyGroupCandidateEvidence = {
  candidate_id: string;
  strategy_group_id: string;
  symbol: string;
  side: string;
  review_status: string;
  evidence_summary: string;
  metrics: Record<string, string>;
  limitations: string[];
  confidence_flags: string[];
  source_refs: string[];
};

export type StrategyGroupReviewabilityItem = {
  strategy_group_id: string;
  strategy_group_name: string;
  plain_language_summary: string;
  market_regime_it_eats: string;
  market_regime_it_hates: string;
  representative_candidates: string[];
  current_status: string;
  evidence_summary: string;
  key_risks: string[];
  confidence_flags: string[];
  owner_action_options: string[];
  next_recommended_action: string;
  not_allowed_now: string[];
  evidence_reviewability: string;
  live_readonly_observation_readiness: string;
  bounded_trial_readiness: string;
  main_blockers: string[];
  source_refs: string[];
  display_model_only: true;
  not_runtime_source_of_truth: true;
  no_execution_permission: true;
  no_order_permission: true;
  no_runtime_start: true;
  no_automatic_strategy_routing: true;
};

export type StrategyGroupReviewabilityResponse = {
  generated_from: string;
  primary_groups: StrategyGroupReviewabilityItem[];
  secondary_groups: StrategyGroupReviewabilityItem[];
  candidate_evidence: StrategyGroupCandidateEvidence[];
  observation_chain_summary: Record<string, unknown>;
  non_permissions: Record<string, boolean>;
  source_refs: string[];
  live_ready: false;
};

export type StrategyGroupObservationCandidate = {
  candidate_id: string;
  strategy_group_id: string;
  symbol: string;
  side: string;
  observation_role: string;
  evaluator_glue_status: string;
  signal_contract: string[];
  review_windows: string[];
  latest_signal_preview: Record<string, unknown>;
  evidence_payload_fields: string[];
  evidence_record_mapping: string;
  readiness_status: string;
  blockers: string[];
  not_allowed_now: string[];
  source_refs: string[];
};

export type StrategyGroupObservationRecord = {
  record_id: string;
  candidate_id: string;
  strategy_group_id: string;
  symbol: string;
  side: string;
  evaluated_at_ms: number;
  recorded_at_ms?: number | null;
  source: string;
  source_type: string;
  market_source: string;
  market_bar_timestamp_ms: number;
  market_bar_close?: string | null;
  signal_type: string;
  confidence: string;
  reason_codes: string[];
  human_summary: string;
  evidence_payload: Record<string, unknown>;
  signal_snapshot: Record<string, unknown>;
  invalidation_conditions: Array<Record<string, unknown>>;
  review_windows: string[];
  review_status_by_window: Record<string, string>;
  input_refs: Record<string, unknown>;
  sink_status: string;
  not_order: true;
  not_execution_intent: true;
  no_execution_permission: true;
  no_order_permission: true;
  no_runtime_start: true;
};

export type StrategyGroupLiveReadOnlyObservationResponse = {
  generated_from: string;
  candidates: StrategyGroupObservationCandidate[];
  current_signals: StrategyGroupObservationRecord[];
  signal_history: StrategyGroupObservationRecord[];
  sink_summary: Record<string, unknown>;
  input_source_summary: Record<string, unknown>;
  review_hook_summary: Record<string, unknown>;
  runner_mapping: Record<string, unknown>;
  observation_chain_summary: Record<string, unknown>;
  non_permissions: Record<string, boolean>;
  live_observation_active: false;
  live_ready: false;
};

export type ObservationCaseForwardReview = {
  review_window: string;
  review_status: string;
  review_due_at_ms: number;
  forward_return_pct?: string | null;
  mfe_pct?: string | null;
  mae_pct?: string | null;
  calculated_at_ms?: number | null;
  notes?: string | null;
};

export type ObservationCaseQueueItem = {
  case_id: string;
  observation_id: string;
  strategy_group_id: string;
  candidate_id: string;
  symbol: string;
  side: string;
  signal_type: 'would_enter';
  case_status: string;
  owner_review_status: string;
  observed_at_ms: number;
  recorded_at_ms?: number | null;
  market_bar_timestamp_ms: number;
  market_bar_close?: string | null;
  source_type: string;
  market_source: string;
  review_windows: string[];
  completed_review_windows: string[];
  pending_review_windows: string[];
  forward_reviews: ObservationCaseForwardReview[];
  risk_tags: string[];
  reason_codes: string[];
  human_summary: string;
  owner_interpretation: string;
  source_refs: string[];
  not_order: true;
  not_execution_intent: true;
  no_execution_permission: true;
  no_order_permission: true;
  no_runtime_start: true;
};

export type ObservationCaseQueueResponse = {
  generated_from: string;
  queue_status: string;
  sink_source: string;
  forward_review_source: string;
  case_count: number;
  cases: ObservationCaseQueueItem[];
  excluded_signal_types: string[];
  supported_future_cases: Record<string, string>;
  non_permissions: Record<string, boolean>;
  source_refs: string[];
};

export type BnbTrialReadinessGate = {
  gate_id: string;
  gate_name: string;
  current_status: string;
  required_for_testnet_rehearsal: boolean;
  required_for_small_live_trial: boolean;
  existing_source_or_code_path: string;
  gap: string;
  recommended_action: string;
  risk_if_skipped: string;
  owner_decision_required: boolean;
};

export type BnbTrialDesignSummary = {
  design_id: string;
  status: string[];
  mode: string;
  trigger: string;
  allowed_scope: string[];
  risk_controls: string[];
  exit_controls: string[];
  recordkeeping: string[];
  blockers: string[];
  non_permissions: string[];
};

export type BnbExecutionBoundaryItem = {
  boundary: string;
  code_path: string;
  current_assessment: string;
  bnb_chain_touches_path: boolean;
  required_control: string;
};

export type BnbOwnerDecisionItem = {
  decision_id: string;
  question: string;
  options: string[];
  recommended_default: string;
  authorization_effect: string;
};

export type Mi001BnbTrialReadinessGapResponse = {
  generated_from: 'mi001_bnb_trial_readiness_gap_v1';
  candidate_id: 'MI-001-BNB-LONG';
  strategy_group_id: 'MI-001';
  symbol: 'BNB/USDT:USDT';
  side: 'long';
  current_phase: string;
  current_status: string[];
  readiness_verdict: 'not_testnet_ready_not_live_ready';
  gap_matrix: BnbTrialReadinessGate[];
  testnet_rehearsal_design: BnbTrialDesignSummary;
  small_live_trial_readiness_draft: BnbTrialDesignSummary;
  execution_boundary_audit: BnbExecutionBoundaryItem[];
  owner_decision_checklist: BnbOwnerDecisionItem[];
  api_console_impact: Record<string, string | boolean>;
  non_permissions: Record<string, boolean>;
  source_refs: string[];
  live_ready: false;
};

export type StrategyProfile = {
  strategy_group: string;
  strategy_id: string;
  candidate_id: string;
  symbol: string;
  side: string;
  execution_mode: 'observe_only' | 'owner_confirm_each_entry' | 'auto_within_budget';
  auto_within_budget: false;
  owner_confirm_each_entry: true;
  not_runtime_source_of_truth: true;
};

export type RiskCapProfile = {
  cap_profile_id: string;
  profile_status: 'present' | 'missing';
  max_concurrent_position: number;
  max_daily_attempts: number;
  max_trial_attempts: number;
  max_notional_usdt: string;
  leverage: string;
  no_auto_reentry: boolean;
  no_averaging_down: boolean;
  no_auto_top_up: boolean;
  no_transfer: boolean;
  no_withdrawal: boolean;
  owner_confirm_each_entry: boolean;
  live_ready: false;
  testnet_rehearsal_requires_owner_authorization: boolean;
};

export type StrategyTrialReadinessResponse = {
  generated_from: 'strategy_trial_readiness_v1';
  strategy_profile: StrategyProfile;
  observation_case: Record<string, string | number | string[] | null>;
  risk_cap_profile: RiskCapProfile;
  preflight_result: {
    status: 'ready' | 'blocked' | 'unknown';
    blockers: string[];
    warnings: string[];
    evidence: Record<string, string | boolean>;
    next_owner_action: string;
    execution_intent_created: false;
    order_created: false;
    live_order_created: false;
    execution_permission_granted: false;
  };
  owner_decision_state: Record<string, string | boolean | string[]>;
  rehearsal_readiness_state: Record<string, string | boolean | string[]>;
  fact_checks: {
    generated_at_ms: number;
    candidate_id: string;
    symbol: string;
    side: string;
    facts: Array<{
      fact_id: 'active_position' | 'open_order' | 'gks' | 'startup_guard' | 'reconciliation' | 'account_facts';
      status: 'clear' | 'blocked' | 'stale' | 'unknown' | 'unavailable' | 'required_before_rehearsal' | 'not_checked';
      source: string;
      blocking: boolean;
      blocker?: string | null;
      blockers: string[];
      observed_at_ms?: number | null;
      evidence: Record<string, string | number | boolean | null>;
      notes: string[];
    }>;
    blockers: string[];
    warnings: string[];
    execution_intent_created: false;
    order_created: false;
    execution_permission_granted: false;
    live_ready: false;
  };
  readiness_verdict: 'testnet_rehearsal_ready' | 'testnet_rehearsal_blocked_with_explicit_reasons' | 'testnet_rehearsal_completed';
  blockers: string[];
  warnings: string[];
  evidence: Record<string, string | boolean | number | null>;
  market_data_architecture: Record<string, string | boolean>;
  non_permissions: Record<string, boolean>;
  reusable_for_future_profiles: true;
  live_ready: false;
  auto_execution_ready: false;
};

export type StrategyTrialArchitectureGovernanceResponse = {
  generated_from: 'strategy_trial_architecture_governance_v1';
  final_state: string;
  bnb_state: 'bnb_first_carrier_consolidated';
  owner_review_packet: {
    packet_id: string;
    carrier: {
      carrier_id: string;
      strategy_family: string;
      strategy_id: string;
      candidate_id: string;
      symbol: string;
      runtime_symbol: string;
      side: 'long' | 'short';
      execution_mode: 'owner_confirm_each_entry';
      quantity: string;
      max_notional: string;
      leverage: string;
      max_leverage_allowed: string;
      protection_plan_type: 'single_tp_plus_sl';
      strategy_family_order_authority: false;
      carrier_is_order_authority: false;
      live_ready: false;
      auto_execution_ready: false;
    };
    testnet_rehearsal_result: 'completed_with_valid_protection';
    testnet_rehearsal_evidence: Record<string, string | boolean>;
    strategy_warnings: Array<{
      warning_id: string;
      severity: 'info' | 'warning';
      owner_ack_required: boolean;
      acknowledged: boolean;
      blocks_after_ack: false;
      description: string;
    }>;
    hard_safety_blockers: Array<{
      blocker_id: string;
      active: boolean;
      blocks_after_ack: true;
      description: string;
      source: string;
    }>;
    next_owner_action: 'explicit_owner_live_authorization_required';
    live_authorization_effect: string;
    no_execution_permission: true;
    no_order_permission: true;
    no_runtime_start: true;
    live_ready: false;
  };
  authorization_draft: Record<string, string | boolean>;
  minimal_live_trial_gate: {
    can_execute_bounded_live_trial: boolean;
    final_state: string;
    hard_blockers: string[];
    acknowledgement_blockers: string[];
    warnings: string[];
    live_ready: false;
    execution_intent_created: false;
    order_created: false;
    execution_permission_granted: false;
  };
  architecture_classification: Array<Record<string, string>>;
  generic_now: string[];
  carrier_specific_by_design: string[];
  technical_debt_later: string[];
  not_live_ready_until_explicit_owner_live_authorization: true;
  not_auto_execution_ready: true;
  no_real_funds: true;
  non_permissions: Record<string, boolean>;
};

export type StartupGuardReadinessArmResponse = {
  action: 'startup_guard_preflight_arm';
  status: 'armed' | 'already_armed' | 'blocked';
  armed_before?: boolean | null;
  armed_after?: boolean | null;
  runtime_bound: boolean;
  runtime_control_api_enabled: boolean;
  runtime_effect: 'startup_guard_process_state_only' | 'none';
  execution_permission_granted: false;
  order_permission_granted: false;
  trial_started: false;
  strategy_runtime_started: false;
  execution_intent_created: false;
  order_created: false;
  exchange_write_methods_called: false;
  next_checklist_verdict: string;
  notes: string[];
  live_ready: false;
};

export type MarketsOrdersResponse = {
  conclusion: string;
  account_impact: string;
  source: AccountFactsSource;
  truth_level: AccountFactsTruthLevel;
  reconciliation_status: Record<string, unknown>;
  symbols: Array<Record<string, unknown>>;
  open_orders: Array<Record<string, unknown>>;
  active_positions: Array<Record<string, unknown>>;
  recent_orders: Array<Record<string, unknown>>;
  recent_fills: Array<Record<string, unknown>>;
  exposure_by_symbol: Record<string, Record<string, unknown>>;
  unknown_or_unmanaged_orders: Array<Record<string, unknown>>;
  unknown_or_unmanaged_positions: Array<Record<string, unknown>>;
  limitations: string[];
  warnings: string[];
  blockers: string[];
  developer_details: Record<string, unknown>;
  live_ready: false;
};

export type AccountFactsSource = 'local_pg' | 'exchange_testnet' | 'exchange_live' | 'mixed' | 'unavailable';
export type AccountFactsTruthLevel = 'summary' | 'exchange_read' | 'reconciled' | 'unavailable';

export type AccountFactsResponse = {
  source: AccountFactsSource;
  truth_level: AccountFactsTruthLevel;
  generated_at_ms: number;
  evidence_refs: string[];
  checked_sources: string[];
  source_snapshots: Record<string, unknown>;
  reconciliation_checked_at_ms: number;
  mismatch_count: number;
  unknown_unmanaged_counts: Record<string, number>;
  account_summary: Record<string, unknown>;
  positions: Array<Record<string, unknown>>;
  open_orders: Array<Record<string, unknown>>;
  recent_orders: Array<Record<string, unknown>>;
  recent_fills: Array<Record<string, unknown>>;
  exposure_by_symbol: Record<string, Record<string, unknown>>;
  unknown_or_unmanaged_orders: Array<Record<string, unknown>>;
  unknown_or_unmanaged_positions: Array<Record<string, unknown>>;
  connection_health: Record<string, unknown>;
  reconciliation_status: Record<string, unknown>;
  limitations: string[];
  warnings: string[];
  blockers: string[];
  live_ready: false;
};

export type StrategyFamily = {
  strategy_family_id: string;
  family_key: string;
  name: string;
  description?: string;
  status: string;
  owner?: string;
  created_at_ms?: number;
  updated_at_ms?: number;
};

export type AdmissionDecision = {
  admission_decision_id: string;
  admission_request_id: string;
  decision: string;
  trial_env: string;
  trial_stage: string;
  strategy_family_version_id: string;
  playbook_id?: string | null;
  evidence_packet_id: string;
  owner_market_regime_input_id: string;
  trial_constraint_snapshot_id: string;
  execution_mode: string;
  risk_profile?: string;
  blockers_json?: string[];
  warnings_json?: string[];
  risk_disclosure_json?: Record<string, unknown>;
  known_gaps_json?: Record<string, unknown>;
  constraints_snapshot_json?: Record<string, unknown>;
  owner_risk_acceptance_id?: string | null;
  created_at_ms?: number;
};

export type AdmissionTrialBinding = {
  binding_id: string;
  admission_decision_id: string;
  owner_risk_acceptance_id?: string | null;
  trial_constraint_snapshot_id: string;
  strategy_family_version_id: string;
  playbook_id: string;
  trial_env: string;
  trial_stage: string;
  execution_mode: string;
  binding_status: string;
  campaign_id?: string | null;
  runtime_carrier_id?: string | null;
  created_by_operation_id?: string;
  created_by_preflight_id?: string;
  created_at_ms?: number;
  updated_at_ms?: number;
};

export type AuditTrailResponse = {
  conclusion: string;
  account_impact: string;
  timeline: Array<Record<string, unknown>>;
  operation_results: Array<Record<string, unknown>>;
  operator_actions: Array<Record<string, unknown>>;
  workflow_runs: Array<Record<string, unknown>>;
  review_decisions: Array<Record<string, unknown>>;
  developer_details: Record<string, unknown>;
  live_ready: false;
};

export type InvestigatorResponse = {
  intent: string;
  conclusion: string;
  reason: string;
  account_impact: string;
  evidence_summary: string[];
  trace: Array<Record<string, unknown>>;
  next_step: string;
  developer_details: Record<string, unknown>;
  live_ready: false;
};

export type OperatorPlanResponse = {
  plan: Record<string, unknown>;
  action: Record<string, unknown>;
  live_ready: false;
  access_boundary: string;
};

export type OperatorRunResponse = {
  run: Record<string, unknown>;
  action?: Record<string, unknown> | null;
  inventory: Record<string, unknown>;
  live_ready: false;
  access_boundary: string;
};

export type WorkflowResponse = {
  workflow: Record<string, unknown>;
  intent?: Record<string, unknown> | null;
  live_ready: false;
  access_boundary: string;
};

export type ReviewDecisionResponse = {
  review_decision: Record<string, unknown>;
  live_ready: false;
  access_boundary?: string;
};

export type OperationCapabilityStatus =
  | 'enabled'
  | 'available'
  | 'operation_preflight_available'
  | 'preflight_planning_available'
  | 'preflight_dry_run_available'
  | 'legacy_dev_path'
  | 'requires_operation_layer'
  | 'design_surface_with_preflight'
  | 'design_surface'
  | 'unavailable'
  | 'forbidden'
  | 'not_implemented';

export type OperationCapability = {
  operation_type: string;
  status: OperationCapabilityStatus;
  display_name: string;
  risk_level: 'read_only' | 'low' | 'medium' | 'high' | 'forbidden';
  allowed_env: string[];
  confirmation_required: boolean;
  backend_executor?: string | null;
  current_reason: string;
  requires_operation_layer: boolean;
  executable_through_operation: boolean;
  dry_run_only?: boolean;
};

export type OperationPreflightResponse = {
  operation_id: string;
  preflight_id: string;
  operation_type: string;
  decision: 'allow' | 'warn' | 'block' | 'unavailable' | 'expired';
  summary: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  account_order_summary: Record<string, unknown>;
  runtime_summary: Record<string, unknown>;
  campaign_summary: Record<string, unknown>;
  playbook_summary: Record<string, unknown>;
  risk_summary: {
    passed?: string[];
    warnings?: string[];
    blockers?: string[];
    [key: string]: unknown;
  };
  confirmation_requirement: {
    required: boolean;
    phrase?: string | null;
    expires_at_ms: number;
    totp_freshness_required: boolean;
  };
  idempotency_key: string;
  status: 'draft' | 'awaiting_confirmation' | 'executing' | 'executed' | 'blocked' | 'failed' | 'cancelled' | 'expired' | 'noop';
};

export type OperationConfirmResponse = {
  operation_id: string;
  preflight_id: string;
  status: 'executed' | 'blocked' | 'failed' | 'cancelled' | 'expired' | 'noop';
  rechecked: boolean;
  result_summary: Record<string, unknown>;
  audit_refs: Array<Record<string, unknown>>;
  campaign_refs: Array<Record<string, unknown>>;
  review_refs: Array<Record<string, unknown>>;
  next_state: Record<string, unknown>;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...(init?.headers || {}),
    },
  });

  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json') ? await response.json() : await response.text();
  if (!response.ok) {
    const detailValue = typeof payload === 'object' && payload && 'detail' in payload
      ? (payload as { detail?: unknown }).detail
      : undefined;
    const detail = typeof payload === 'object' && payload && 'message' in payload
      ? String((payload as { message?: unknown }).message)
      : typeof detailValue === 'object' && detailValue && 'message' in detailValue
        ? String((detailValue as { message?: unknown }).message)
        : typeof detailValue === 'string'
          ? detailValue
          : `API request failed: ${response.status}`;
    throw { status: response.status, message: detail, payload } satisfies ApiError;
  }
  return payload as T;
}

export const brcApi = {
  login(username: string, password: string, totpCode: string) {
    return request<SessionResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password, totp_code: totpCode }),
    });
  },
  logout() {
    return request<SessionResponse>('/api/auth/logout', { method: 'POST' });
  },
  session() {
    return request<SessionResponse>('/api/auth/session');
  },
  dashboard() {
    return request<DashboardResponse>('/api/brc/dashboard');
  },
  readiness() {
    return request<ReadinessResponse>('/api/brc/readiness');
  },
  mi001SolReadiness() {
    return request<Mi001SolReadinessResponse>('/api/brc/readiness/mi001-sol');
  },
  strategyGroupReviewability() {
    return request<StrategyGroupReviewabilityResponse>('/api/brc/strategy-groups/reviewability');
  },
  strategyGroupLiveObservationV1() {
    return request<StrategyGroupLiveReadOnlyObservationResponse>('/api/brc/strategy-groups/live-readonly-observation/v1');
  },
  strategyGroupObservationCasesV1() {
    return request<ObservationCaseQueueResponse>('/api/brc/strategy-groups/observation-cases/v1');
  },
  mi001BnbTrialReadinessGap() {
    return request<Mi001BnbTrialReadinessGapResponse>('/api/brc/readiness/mi001-bnb/trial-gap');
  },
  strategyTrialReadinessV1() {
    return request<StrategyTrialReadinessResponse>('/api/brc/strategy-trial-readiness/v1');
  },
  strategyTrialArchitectureGovernance() {
    return request<StrategyTrialArchitectureGovernanceResponse>('/api/brc/strategy-trial-architecture/bnb-first-carrier');
  },
  runStrategyGroupLiveObservationV1Once() {
    return request<StrategyGroupLiveReadOnlyObservationResponse>('/api/brc/strategy-groups/live-readonly-observation/v1/run-once', {
      method: 'POST',
    });
  },
  armStartupGuardPreflight(reason = 'MI-001 SOL Owner Console readiness preflight') {
    return request<StartupGuardReadinessArmResponse>('/api/brc/readiness/startup-guard/preflight-arm', {
      method: 'POST',
      body: JSON.stringify({ reason, updated_by: 'owner_console' }),
    });
  },
  runtimeSafety() {
    return request<RuntimeSafetyResponse>('/api/runtime/safety');
  },
  marketsOrders() {
    return request<MarketsOrdersResponse>('/api/brc/markets-orders');
  },
  accountFacts() {
    return request<AccountFactsResponse>('/api/brc/account/facts');
  },
  auditTrail(limit = 50) {
    return request<AuditTrailResponse>(`/api/brc/audit-trail?limit=${limit}`);
  },
  askInvestigator(question: string, context?: { context_type?: string; context_id?: string }) {
    return request<InvestigatorResponse>('/api/brc/investigator/ask', {
      method: 'POST',
      body: JSON.stringify({ question, ...context }),
    });
  },
  reviewPacket() {
    return request<Record<string, unknown>>('/api/brc/review-packet');
  },
  nextEligibility() {
    return request<Record<string, unknown>>('/api/brc/next-eligibility');
  },
  evidence() {
    return request<Record<string, unknown>>('/api/brc/evidence');
  },
  planOperator(text: string) {
    return request<OperatorPlanResponse>('/api/brc/operator/plan', {
      method: 'POST',
      body: JSON.stringify({ text }),
    });
  },
  runOperatorAction(actionId: string, confirmationPhrase: string) {
    return request<OperatorRunResponse>(`/api/brc/operator/actions/${encodeURIComponent(actionId)}/run`, {
      method: 'POST',
      body: JSON.stringify({ confirmation_phrase: confirmationPhrase, confirmed_by: 'owner' }),
    });
  },
  listActions(limit = 20) {
    return request<{ actions: Array<Record<string, unknown>>; live_ready: false }>(`/api/brc/operator/actions?limit=${limit}`);
  },
  createWorkflow(text: string) {
    return request<WorkflowResponse>('/api/brc/llm/workflows', {
      method: 'POST',
      body: JSON.stringify({ text }),
    });
  },
  confirmWorkflow(workflowRunId: string, confirmationPhrase: string) {
    return request<WorkflowResponse>(`/api/brc/llm/workflows/${encodeURIComponent(workflowRunId)}/confirm`, {
      method: 'POST',
      body: JSON.stringify({ confirmation_phrase: confirmationPhrase, confirmed_by: 'owner' }),
    });
  },
  listWorkflows(limit = 20) {
    return request<{ workflows: Array<Record<string, unknown>>; live_ready: false }>(`/api/brc/llm/workflows?limit=${limit}`);
  },
  listReviewDecisions(limit = 20) {
    return request<{ review_decisions: Array<Record<string, unknown>>; live_ready: false }>(`/api/brc/review-decisions?limit=${limit}`);
  },
  listStrategyFamilies(limit = 100) {
    return request<StrategyFamily[]>(`/api/brc/strategy-families?limit=${limit}`);
  },
  listAdmissionDecisions(limit = 100) {
    return request<AdmissionDecision[]>(`/api/brc/admissions/decisions?limit=${limit}`);
  },
  getAdmissionDecision(admissionDecisionId: string) {
    return request<AdmissionDecision>(`/api/brc/admissions/decisions/${encodeURIComponent(admissionDecisionId)}`);
  },
  listTrialBindings(limit = 100) {
    return request<AdmissionTrialBinding[]>(`/api/brc/admissions/trial-bindings?limit=${limit}`);
  },
  getTrialBinding(bindingId: string) {
    return request<AdmissionTrialBinding>(`/api/brc/admissions/trial-bindings/${encodeURIComponent(bindingId)}`);
  },
  currentCampaign() {
    return request<{ campaign: Record<string, unknown>; live_ready?: false }>('/api/brc/campaigns/current');
  },
  createReviewDecision(input: {
    campaign_id: string;
    source_action_id?: string;
    decision: string;
    reason_text: string;
    next_recommended_task: string;
  }) {
    return request<ReviewDecisionResponse>('/api/brc/review-decisions', {
      method: 'POST',
      body: JSON.stringify({ ...input, created_by: 'owner', metadata: { source: 'brc_operator_console' } }),
    });
  },
  operationCapabilities() {
    return request<{ capabilities: OperationCapability[]; live_ready: false }>('/api/brc/operations/capabilities');
  },
  preflightOperation(input: {
    operation_type: string;
    input_params: Record<string, unknown>;
    requested_by?: string;
    source?: Record<string, unknown>;
  }) {
    return request<OperationPreflightResponse>('/api/brc/operations/preflight', {
      method: 'POST',
      body: JSON.stringify({
        requested_by: 'owner',
        source: { kind: 'ui' },
        ...input,
      }),
    });
  },
  confirmOperation(operationId: string, input: {
    preflight_id: string;
    confirmation_phrase: string;
    idempotency_key: string;
    confirmed_by?: string;
  }) {
    return request<OperationConfirmResponse>(`/api/brc/operations/${encodeURIComponent(operationId)}/confirm`, {
      method: 'POST',
      body: JSON.stringify({ confirmed_by: 'owner', ...input }),
    });
  },
  cancelOperation(operationId: string) {
    return request<OperationConfirmResponse>(`/api/brc/operations/${encodeURIComponent(operationId)}/cancel`, {
      method: 'POST',
      body: JSON.stringify({ requested_by: 'owner' }),
    });
  },
  listOperations(limit = 20) {
    return request<{ operations: Array<Record<string, unknown>>; live_ready: false }>(`/api/brc/operations?limit=${limit}`);
  },
  operationDetail(operationId: string) {
    return request<OperationConfirmResponse | Record<string, unknown>>(`/api/brc/operations/${encodeURIComponent(operationId)}`);
  },
};
