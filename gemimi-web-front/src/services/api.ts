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
};
