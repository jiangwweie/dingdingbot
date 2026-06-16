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
  ownerAttentionLabel: "无需操作" | "系统处理" | "需处理";
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
  } | null;
  strategy_groups?: OwnerSourceReadinessStrategyGroup[];
  source_health?: Record<string, OwnerSourceHealthItem | undefined>;
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
