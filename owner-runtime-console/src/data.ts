import type {
  FundPoolSummary,
  OwnerAutomationState,
  OwnerHealthState,
  OwnerImportantChange,
  OwnerMockScenario,
  OwnerConsoleSourceReadinessResponse,
  OwnerProductProjection,
  OwnerProductSummary,
  StrategyGroupProductRow,
} from "./types";

export const automationStateLabels: Record<OwnerAutomationState, string> = {
  not_enabled: "未启用",
  running: "运行中",
  waiting_for_opportunity: "等待机会",
  processing: "处理中",
  temporarily_unavailable: "暂不可用",
  paused: "已暂停",
  completed: "已完成",
};

export const healthLabels: Record<OwnerHealthState, string> = {
  normal: "正常",
  processing: "处理中",
  abnormal: "异常",
  unknown: "未知",
};

const baseFundPool: FundPoolSummary = {
  label: "安全资金池",
  code: "LIVE-SAFE-1",
  budget: "$5,000",
  reserved: "$3,160",
  available: "$1,840",
  openOrders: 1,
  activePositions: 5,
  accountLabel: "资金正常",
  ordersLabel: "有订单处理中",
  positionsLabel: "有持仓处理中",
  reconciliationLabel: "对账正常",
  protectionLabel: "正常",
  fundsLocked: true,
};

const baseSourceHealth = {
  catalog: { status: "ready", label: "策略组目录可用" },
  runtime: { status: "ready", label: "运行状态可用" },
  watcher: { status: "ready", label: "观察状态正常" },
  liveFacts: { status: "ready", label: "事实状态正常" },
  accountFunds: { status: "ready", label: "资金正常" },
  orders: { status: "ready_nonempty", label: "有订单处理中" },
  positions: { status: "ready_nonempty", label: "有持仓处理中" },
  protection: { status: "ready", label: "保护正常" },
  reconciliation: { status: "ready", label: "对账正常" },
  operationAudit: { status: "ready", label: "审计详情可用" },
} as const;

const baseStrategies: StrategyGroupProductRow[] = [
  {
    id: "MPG-001",
    code: "MPG",
    name: "MPG",
    description: "动量趋势",
    automationState: "running",
    automationLabel: "运行中",
    ownerAttention: "none",
    ownerAttentionLabel: "无需操作",
    funds: "normal",
    orders: "normal",
    position: "normal",
    protection: "normal",
    reconciliation: "normal",
    selected: true,
  },
  {
    id: "TEQ-001",
    code: "TEQ",
    name: "TEQ",
    description: "量化轮动套利",
    automationState: "waiting_for_opportunity",
    automationLabel: "等待机会",
    ownerAttention: "none",
    ownerAttentionLabel: "无需操作",
    funds: "normal",
    orders: "normal",
    position: "normal",
    protection: "normal",
    reconciliation: "normal",
  },
  {
    id: "FBS-001",
    code: "FBS",
    name: "FBS",
    description: "资金费率套利",
    automationState: "waiting_for_opportunity",
    automationLabel: "等待机会",
    ownerAttention: "none",
    ownerAttentionLabel: "无需操作",
    funds: "normal",
    orders: "normal",
    position: "normal",
    protection: "normal",
    reconciliation: "normal",
  },
  {
    id: "SOR-001",
    code: "SOR",
    name: "SOR",
    description: "开盘区间结构",
    automationState: "processing",
    automationLabel: "处理中",
    ownerAttention: "none",
    ownerAttentionLabel: "无需操作",
    availabilityReason: "有订单处理中，等待系统完成",
    funds: "normal",
    orders: "processing",
    position: "normal",
    protection: "normal",
    reconciliation: "processing",
  },
  {
    id: "PMR-001",
    code: "PMR",
    name: "PMR",
    description: "资金流监控",
    automationState: "paused",
    automationLabel: "已暂停",
    ownerAttention: "none",
    ownerAttentionLabel: "无需操作",
    funds: "normal",
    orders: "normal",
    position: "normal",
    protection: "normal",
    reconciliation: "normal",
  },
];

const baseImportantChanges: OwnerImportantChange[] = [
  {
    id: "change-1",
    title: "MPG 已进入运行状态",
    detail: "资金、订单、持仓与保护均正常",
    tone: "safe",
    sourceKind: "strategy_state",
  },
  {
    id: "change-2",
    title: "SOR 正在处理订单",
    detail: "系统会完成处理并回写状态",
    tone: "processing",
    sourceKind: "post_action",
  },
  {
    id: "change-3",
    title: "安全资金池正常",
    detail: "资金锁定与保护状态均正常",
    tone: "safe",
    sourceKind: "fund_pool",
  },
];

function cloneStrategies() {
  return baseStrategies.map((strategy) => ({ ...strategy }));
}

function applySelection(rows: StrategyGroupProductRow[], selectedId = "MPG-001") {
  return rows.map((strategy) => ({
    ...strategy,
    selected: strategy.id === selectedId,
  }));
}

function countState(rows: StrategyGroupProductRow[], state: OwnerAutomationState) {
  return rows.filter((strategy) => strategy.automationState === state).length;
}

function buildProjection(
  scenario: OwnerMockScenario,
  rows: StrategyGroupProductRow[],
  overrides: Partial<OwnerProductSummary> = {},
  fundPool: FundPoolSummary = baseFundPool,
  importantChanges: OwnerImportantChange[] = baseImportantChanges,
): OwnerProductProjection {
  const selected = rows.find((strategy) => strategy.selected) ?? rows[0] ?? null;
  const ownerAttentionCount = rows.filter((strategy) => strategy.ownerAttention === "owner_required").length;
  const unavailableCount = countState(rows, "temporarily_unavailable");

  return {
    asOf: "2026-06-15T19:20:00+08:00",
    source: "mock",
    scenario,
    productSummary: {
      overallStatus: ownerAttentionCount > 0 ? "attention" : unavailableCount > 0 ? "degraded" : "safe",
      enabledCount: rows.filter((strategy) => strategy.automationState !== "not_enabled").length,
      runningCount: countState(rows, "running"),
      waitingCount: countState(rows, "waiting_for_opportunity"),
      processingCount: countState(rows, "processing"),
      unavailableCount,
      pausedCount: countState(rows, "paused"),
      ownerAttentionCount,
      dataFreshnessLabel: "数据新鲜 < 60秒",
      systemLabel: ownerAttentionCount > 0 ? "需处理" : unavailableCount > 0 ? "暂不可用" : "系统正常",
      ...overrides,
    },
    strategies: rows,
    selectedStrategyId: selected?.id ?? null,
    fundPool,
    sourceHealth: baseSourceHealth,
    importantChanges,
    noActionGuarantee: {
      places_order: false,
      cancels_order: false,
      replaces_order: false,
      flattens_position: false,
      starts_runtime: false,
      grants_auto_execution: false,
      mutates_pg: false,
      calls_operation_layer: false,
      calls_final_gate: false,
      exchange_write_called: false,
    },
  };
}

export function buildMockProjection(scenario: OwnerMockScenario): OwnerProductProjection {
  if (scenario === "empty") {
    return buildProjection(
      "empty",
      [],
      {
        overallStatus: "degraded",
        enabledCount: 0,
        runningCount: 0,
        waitingCount: 0,
        processingCount: 0,
        unavailableCount: 0,
        pausedCount: 0,
        ownerAttentionCount: 0,
        systemLabel: "暂无策略组",
        reason: "暂无已启用策略组",
      },
      { ...baseFundPool, reserved: "$0", available: "$5,000", openOrders: 0, activePositions: 0 },
      [],
    );
  }

  const rows = cloneStrategies();

  if (scenario === "processing") {
    rows[0].automationState = "running";
    rows[0].automationLabel = "运行中";
    rows[3].automationState = "processing";
    rows[3].automationLabel = "处理中";
    rows[3].orders = "processing";
    rows[3].reconciliation = "processing";
  }

  if (scenario === "paused") {
    rows[0].automationState = "paused";
    rows[0].automationLabel = "已暂停";
    rows[0].availabilityReason = "Owner 已暂停";
    rows[0].selected = true;
  }

  if (scenario === "intervention") {
    rows[2].automationState = "temporarily_unavailable";
    rows[2].automationLabel = "暂不可用";
    rows[2].ownerAttention = "owner_required";
    rows[2].ownerAttentionLabel = "需处理";
    rows[2].funds = "abnormal";
    rows[2].orders = "abnormal";
    rows[2].availabilityReason = "事实不可用，暂不能使用";
    rows[2].selected = true;
    rows[0].selected = false;
    return buildProjection(
      "intervention",
      applySelection(rows, "FBS-001"),
      {
        overallStatus: "attention",
        systemLabel: "需处理",
        reason: "事实不可用，暂不能使用",
      },
      { ...baseFundPool, protectionLabel: "正常" },
      [
        {
          id: "change-attention",
          title: "FBS 暂不能使用",
          detail: "事实不可用",
          tone: "danger",
          sourceKind: "strategy_state",
        },
        ...baseImportantChanges.slice(1),
      ],
    );
  }

  if (scenario === "stale") {
    rows[0].automationState = "temporarily_unavailable";
    rows[0].automationLabel = "暂不可用";
    rows[0].ownerAttention = "system_required";
    rows[0].ownerAttentionLabel = "系统处理";
    rows[0].availabilityReason = "数据不可用，暂不能使用";
    return buildProjection(
      "stale",
      applySelection(rows, "MPG-001"),
      {
        overallStatus: "degraded",
        dataFreshnessLabel: "数据不可用",
        systemLabel: "暂不可用",
        reason: "数据不可用，暂不能使用",
      },
      baseFundPool,
      [
        {
          id: "change-stale",
          title: "数据暂不可用",
          detail: "等待系统恢复",
          tone: "danger",
          sourceKind: "system",
        },
        ...baseImportantChanges.slice(1),
      ],
    );
  }

  return buildProjection(scenario, applySelection(rows));
}

export function configuredMockScenario(value: unknown): OwnerMockScenario {
  if (
    value === "normal"
    || value === "processing"
    || value === "paused"
    || value === "intervention"
    || value === "stale"
    || value === "empty"
    || value === "error"
  ) {
    return value;
  }
  return "normal";
}

export function buildMockSourceReadiness(scenario: OwnerMockScenario): OwnerConsoleSourceReadinessResponse {
  const ready = scenario !== "stale" && scenario !== "intervention" && scenario !== "empty";
  const ownerLabel = scenario === "processing" ? "处理中" : scenario === "intervention" ? "需处理" : ready ? "等待机会" : "暂不可用";
  const sourceStatus = ready ? "ready" : "source_unavailable";
  const baseHealth = {
    strategy_catalog: { status: "ready", label: "策略组可见", detail: "mock_strategy_catalog" },
    runtime_source: { status: ready ? "ready" : "degraded", label: ready ? "运行状态正常" : "运行状态源未连接", detail: "mock_runtime_source" },
    watcher: { status: ready ? "ready" : "degraded", label: ready ? "运行中" : "观察状态暂不可用", detail: "mock_watcher" },
    live_facts: { status: ready ? "ready" : "degraded", label: ready ? "事实正常" : "事实状态暂不可用", detail: "mock_live_facts" },
    funds: { status: ready ? "ready" : "unavailable", label: ready ? "资金正常" : "资金状态暂不可用", detail: "mock_funds" },
    orders: { status: ready ? "ready_empty" : "unavailable", label: ready ? "暂无订单" : "订单状态暂不可用", detail: "mock_orders" },
    positions: { status: ready ? "ready_empty" : "unavailable", label: ready ? "暂无持仓" : "持仓状态暂不可用", detail: "mock_positions" },
    protection: { status: ready ? "ready" : "unavailable", label: ready ? "保护正常" : "保护状态暂不可用", detail: "mock_protection" },
    reconciliation: { status: ready ? "ready" : "degraded", label: ready ? "对账正常" : "对账详情暂不可用", detail: "mock_reconciliation" },
    operation_audit: { status: ready ? "ready_empty" : "degraded", label: ready ? "暂无审计动作" : "审计详情暂不可用", detail: "mock_operation_audit" },
  } as const;

  return {
    read_model: "owner_console_source_readiness",
    generated_at_ms: Date.now(),
    freshness_status: ready ? "fresh" : "warning",
    warnings: ready ? [] : [{ code: "mock_source_readiness_degraded" }],
    blockers: [],
    unavailable: [],
    live_ready: false,
    data: {
      scope: "owner_console_source_readiness",
      status: sourceStatus,
      generated_at_ms: Date.now(),
      owner_state: {
        status: scenario === "processing" ? "processing" : scenario === "intervention" ? "needs_intervention" : ready ? "waiting_for_opportunity" : "temporarily_unavailable",
        label: ownerLabel,
        reason: scenario === "intervention" ? "事实不可用，暂不能使用" : ready ? "no_fresh_strategy_signal" : "数据不可用，暂不能使用",
        next_action: "continue_watcher_observation",
        needs_owner_action: scenario === "intervention",
      },
      owner_summary: {
        strategy_groups: "可见",
        watcher: ready ? "运行中" : "观察状态暂不可用",
        market_opportunity: ownerLabel,
        funds: ready ? "资金正常" : "资金状态暂不可用",
        orders: ready ? "暂无订单" : "订单状态暂不可用",
        positions: ready ? "暂无持仓" : "持仓状态暂不可用",
        protection: ready ? "保护正常" : "保护状态暂不可用",
        reconciliation: ready ? "对账正常" : "对账详情暂不可用",
        operation_audit: ready ? "暂无审计动作" : "审计详情暂不可用",
      },
      strategy_groups: ["MPG", "TEQ", "FBS", "SOR", "PMR"].map((code, index) => {
        const isProcessing = scenario === "processing" && code === "SOR";
        const isPaused = scenario === "paused" && code === "MPG";
        const isIntervention = scenario === "intervention" && code === "FBS";
        const selected = isProcessing || isPaused || isIntervention || (scenario !== "processing" && scenario !== "paused" && scenario !== "intervention" && index === 0);
        return {
          strategy_group_id: `${code}-001`,
          name: code,
          runtime_state: isProcessing ? "processing" : isPaused ? "paused" : ready ? "observing" : "temporarily_unavailable",
          signal_state: ready ? "no_signal" : "unknown",
          source_health: ready ? "ready" : "degraded",
          owner_label: isProcessing ? "处理中" : isPaused ? "已暂停" : isIntervention || !ready ? "暂不可用" : "等待机会",
          reason: isProcessing ? "SOR 正在处理订单" : isPaused ? "Owner 已暂停" : isIntervention ? "事实不可用，暂不能使用" : ready ? "no_fresh_strategy_signal" : "数据不可用，暂不能使用",
          selected,
        };
      }),
      source_health: baseHealth,
      critical_unavailable_sources: ready ? [] : ["runtime_source"],
      frontend_contract: {
        single_api_source: true,
        hide_strategy_groups_when_runtime_degraded: false,
        ready_empty_is_not_unavailable: true,
        owner_homepage_internal_gate_terms_allowed: false,
      },
      safety_invariants: {
        read_model_only: true,
        places_order: false,
        calls_order_lifecycle: false,
        exchange_write_called: false,
        runtime_budget_mutated: false,
        creates_candidate: false,
        creates_authorization: false,
        withdrawal_or_transfer_created: false,
        mutates_pg: false,
        secrets_printed: false,
      },
    },
  };
}
