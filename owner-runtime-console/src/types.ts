export type OwnerAutomationState =
  | "not_enabled"
  | "running"
  | "waiting_for_opportunity"
  | "processing"
  | "temporarily_unavailable"
  | "paused"
  | "completed";

export type OwnerAttentionState = "none" | "system_required" | "owner_required";

export type OwnerHealthState = "normal" | "processing" | "abnormal" | "unknown";
export type OwnerSourceStatus = "ready" | "ready_empty" | "ready_nonempty" | "degraded" | "unavailable";

export type OwnerMockScenario =
  | "normal"
  | "processing"
  | "paused"
  | "safety"
  | "intervention"
  | "stale"
  | "empty"
  | "error";

export type OwnerProductSummary = {
  overallStatus: "safe" | "attention" | "degraded";
  enabledCount: number;
  runningCount: number;
  waitingCount: number;
  processingCount: number;
  unavailableCount: number;
  pausedCount: number;
  ownerAttentionCount: number;
  dataFreshnessLabel: string;
  systemLabel: string;
  reason?: string;
};

export type StrategyGroupProductRow = {
  id: string;
  code: "MPG" | "TEQ" | "FBS" | "SOR" | "PMR";
  name: string;
  description: string;
  automationState: OwnerAutomationState;
  automationLabel: string;
  ownerAttention: OwnerAttentionState;
  ownerAttentionLabel: "无需操作" | "系统处理" | "需要介入";
  availabilityReason?: string;
  funds: OwnerHealthState;
  orders: OwnerHealthState;
  position: OwnerHealthState;
  protection: OwnerHealthState;
  reconciliation: OwnerHealthState;
  selected?: boolean;
};

export type FundPoolSummary = {
  label: string;
  code: string;
  budget: string;
  reserved: string;
  available: string;
  openOrders: number;
  activePositions: number;
  accountLabel: string;
  ordersLabel: string;
  positionsLabel: string;
  reconciliationLabel: string;
  protectionLabel: "正常" | "异常" | "处理中" | "未知";
  fundsLocked: boolean;
};

export type OwnerSourceHealthItem = {
  status: OwnerSourceStatus;
  label: string;
  owner_label?: string;
  detail?: string | null;
  reason?: string | null;
  summary?: Record<string, unknown>;
};

export type OwnerSourceHealth = {
  catalog: OwnerSourceHealthItem;
  runtime: OwnerSourceHealthItem;
  watcher: OwnerSourceHealthItem;
  liveFacts: OwnerSourceHealthItem;
  accountFunds: OwnerSourceHealthItem;
  orders: OwnerSourceHealthItem;
  positions: OwnerSourceHealthItem;
  protection: OwnerSourceHealthItem;
  reconciliation: OwnerSourceHealthItem;
  operationAudit: OwnerSourceHealthItem;
  runtimeDryRunAudit: OwnerSourceHealthItem;
  realOrderReadiness: OwnerSourceHealthItem;
  deployChannel: OwnerSourceHealthItem;
};

export type OwnerReadinessMatrixItem = {
  key: string;
  status: string;
  blockerClass?: string | null;
  blocksRealSubmit: boolean;
  detail?: string | null;
  evidence?: unknown;
};

export type OwnerRealOrderReadiness = {
  status: string;
  ownerLabel: string;
  ownerDetail: string;
  readyForRealOrderAction: boolean;
  passCount: number;
  waitingCount: number;
  blockedCount: number;
  submitBlockingKeys: string[];
  submitBlockerReview: {
    required: boolean;
    allowed: boolean;
    projectProgressAllowed: boolean;
    continueObservationAllowed: boolean;
    realSubmitAllowed: boolean;
    nextSafeCheckpoint: string;
    blockerKeys: string[];
  };
  nextSafeCheckpoint: string;
  matrix: OwnerReadinessMatrixItem[];
};

export type OwnerRuntimeInteraction = {
  level: string;
  ownerLabel: string;
  detail: string;
  remoteInteractionCount: number;
  mutatesRemoteFiles: boolean;
  approachesRealOrder: boolean;
  callsExchangeWrite: boolean;
  placesOrder: boolean;
};

export type OwnerImportantChange = {
  id: string;
  title: string;
  detail: string;
  tone: "safe" | "waiting" | "processing" | "danger" | "paused";
  sourceKind: "strategy_state" | "safety_state" | "fund_pool" | "post_action" | "system";
};

export type OwnerProductProjection = {
  asOf: string;
  source: string;
  scenario?: OwnerMockScenario;
  productSummary: OwnerProductSummary;
  strategies: StrategyGroupProductRow[];
  selectedStrategyId: string | null;
  fundPool: FundPoolSummary;
  sourceHealth: OwnerSourceHealth;
  runtimeInteraction: OwnerRuntimeInteraction;
  realOrderReadiness: OwnerRealOrderReadiness;
  importantChanges: OwnerImportantChange[];
  noActionGuarantee: Record<string, boolean>;
};

export type OwnerSourceReadinessStrategyGroup = {
  strategy_group_id: string;
  name?: string | null;
  runtime_state?: string | null;
  signal_state?: string | null;
  source_health?: OwnerSourceStatus | string | null;
  owner_label?: string | null;
  reason?: string | null;
  selected?: boolean | null;
};

export type OwnerConsoleSourceReadinessData = {
  scope: "owner_console_source_readiness" | string;
  status: "ready" | "source_unavailable" | string;
  generated_at_ms?: number | null;
  owner_state?: {
    status?: OwnerAutomationState | string | null;
    label?: string | null;
    reason?: string | null;
    next_action?: string | null;
    needs_owner_action?: boolean | null;
  } | null;
  owner_summary?: {
    strategy_groups?: string | null;
    watcher?: string | null;
    market_opportunity?: string | null;
    funds?: string | null;
    orders?: string | null;
    positions?: string | null;
    protection?: string | null;
    reconciliation?: string | null;
    operation_audit?: string | null;
    runtime_dry_run_audit?: string | null;
    real_order_readiness?: string | null;
    deploy_channel?: string | null;
  } | null;
  strategy_groups?: OwnerSourceReadinessStrategyGroup[];
  source_health?: Record<string, OwnerSourceHealthItem | undefined>;
  runtime_interaction?: {
    level?: string | null;
    owner_label?: string | null;
    detail?: string | null;
    remote_interaction_count?: number | null;
    mutates_remote_files?: boolean | null;
    approaches_real_order?: boolean | null;
    calls_exchange_write?: boolean | null;
    places_order?: boolean | null;
  } | null;
  real_order_readiness?: {
    status?: string | null;
    owner_label?: string | null;
    owner_detail?: string | null;
    ready_for_real_order_action?: boolean | null;
    pass_count?: number | null;
    waiting_count?: number | null;
    blocked_count?: number | null;
    submit_blocking_keys?: string[] | null;
    submit_blocker_review?: {
      required?: boolean | null;
      allowed?: boolean | null;
      project_progress_allowed?: boolean | null;
      continue_observation_allowed?: boolean | null;
      real_submit_allowed?: boolean | null;
      next_safe_checkpoint?: string | null;
      blocker_keys?: string[] | null;
    } | null;
    next_safe_checkpoint?: string | null;
    matrix?: Array<{
      key?: string | null;
      status?: string | null;
      blocker_class?: string | null;
      blocks_real_submit?: boolean | null;
      detail?: string | null;
      evidence?: unknown;
    }> | null;
  } | null;
  critical_unavailable_sources?: string[];
  frontend_contract?: Record<string, boolean>;
  safety_invariants?: Record<string, boolean>;
};

export type OwnerConsoleSourceReadinessResponse = {
  read_model: "owner_console_source_readiness" | string;
  generated_at_ms?: number | null;
  freshness_status?: "fresh" | "warning" | "not_live_connected" | string;
  warnings?: unknown[];
  blockers?: unknown[];
  unavailable?: unknown[];
  data: OwnerConsoleSourceReadinessData;
  live_ready?: boolean;
};
