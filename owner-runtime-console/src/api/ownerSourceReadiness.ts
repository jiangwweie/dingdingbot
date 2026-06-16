import { automationStateLabels, buildMockSourceReadiness, configuredMockScenario } from "../data";
import type {
  FundPoolSummary,
  OwnerAutomationState,
  OwnerConsoleSourceReadinessData,
  OwnerConsoleSourceReadinessResponse,
  OwnerHealthState,
  OwnerMockScenario,
  OwnerProductProjection,
  OwnerProductSummary,
  OwnerSourceHealth,
  OwnerSourceHealthItem,
  OwnerSourceReadinessStrategyGroup,
  OwnerSourceStatus,
  StrategyGroupProductRow,
} from "../types";

const defaultEndpoint = "/api/trading-console/owner-console-source-readiness";

const strategyDescriptions: Record<StrategyGroupProductRow["code"], string> = {
  MPG: "动量趋势",
  TEQ: "美股永续动量",
  FBS: "资金费率 / 基差压力",
  SOR: "开盘区间结构",
  PMR: "贵金属短线",
};

const strategyCodes = ["MPG", "TEQ", "FBS", "SOR", "PMR"] as const;

function shouldUseMock() {
  if (typeof window !== "undefined" && new URLSearchParams(window.location.search).has("scenario")) {
    return true;
  }
  return import.meta.env.VITE_OWNER_USE_MOCK === "true";
}

function endpointUrl() {
  return import.meta.env.VITE_OWNER_SOURCE_READINESS_URL || defaultEndpoint;
}

function runtimeMockScenario() {
  if (typeof window !== "undefined") {
    return new URLSearchParams(window.location.search).get("scenario") ?? import.meta.env.VITE_OWNER_MOCK_SCENARIO;
  }
  return import.meta.env.VITE_OWNER_MOCK_SCENARIO;
}

function asSourceStatus(value: unknown, fallback: OwnerSourceStatus): OwnerSourceStatus {
  if (value === "ready" || value === "ready_empty" || value === "ready_nonempty" || value === "degraded" || value === "unavailable") {
    return value;
  }
  return fallback;
}

function sourceItem(value: OwnerSourceHealthItem | undefined, fallbackStatus: OwnerSourceStatus, fallbackLabel: string): OwnerSourceHealthItem {
  return {
    status: asSourceStatus(value?.status, fallbackStatus),
    label: value?.owner_label || value?.label || fallbackLabel,
    detail: value?.reason ?? value?.detail ?? null,
  };
}

function mapSourceHealth(source: OwnerConsoleSourceReadinessData): OwnerSourceHealth {
  const raw = source.source_health ?? {};
  return {
    catalog: sourceItem(raw.strategy_catalog, "ready", "策略组可见"),
    runtime: sourceItem(raw.runtime_source, "degraded", "运行状态源未连接"),
    watcher: sourceItem(raw.watcher, "degraded", "观察状态暂不可用"),
    liveFacts: sourceItem(raw.live_facts, "degraded", "事实状态暂不可用"),
    accountFunds: sourceItem(raw.funds, "unavailable", "资金状态暂不可用"),
    orders: sourceItem(raw.orders, "unavailable", "订单状态暂不可用"),
    positions: sourceItem(raw.positions, "unavailable", "持仓状态暂不可用"),
    protection: sourceItem(raw.protection, "unavailable", "保护状态暂不可用"),
    reconciliation: sourceItem(raw.reconciliation, "ready", "对账正常"),
    operationAudit: sourceItem(raw.operation_audit, "ready_empty", "暂无审计动作"),
    runtimeDryRunAudit: sourceItem(raw.runtime_dry_run_audit, "degraded", "审计演练暂不可用"),
  };
}

function stateFromOwnerLabel(label: string, status: string | null | undefined): OwnerAutomationState {
  if (label === "已暂停") return "paused";
  if (label === "处理中") return "processing";
  if (label === "运行中") return "running";
  if (label === "等待机会") return "waiting_for_opportunity";
  if (label === "未启用") return "not_enabled";
  if (label === "已完成") return "completed";
  if (status === "paused") return "paused";
  if (status === "processing") return "processing";
  if (status === "running") return "running";
  if (status === "waiting_for_opportunity") return "waiting_for_opportunity";
  if (status === "not_enabled") return "not_enabled";
  if (status === "completed") return "completed";
  return "temporarily_unavailable";
}

function healthFromSource(item: OwnerSourceHealthItem): OwnerHealthState {
  if (item.status === "ready" || item.status === "ready_empty") return "normal";
  if (item.status === "ready_nonempty") return "processing";
  if (item.status === "degraded") return "unknown";
  return "abnormal";
}

function splitCode(idOrName: string): StrategyGroupProductRow["code"] {
  const token = idOrName.split("·", 1)[0]?.split("-", 1)[0]?.trim();
  return strategyCodes.find((code) => code === token) ?? "MPG";
}

function strategyRows(source: OwnerConsoleSourceReadinessData, health: OwnerSourceHealth): StrategyGroupProductRow[] {
  const rawRows = source.strategy_groups ?? [];
  const rows: OwnerSourceReadinessStrategyGroup[] = rawRows.length > 0
    ? rawRows
    : strategyCodes.map((code) => ({
        strategy_group_id: `${code}-001`,
        name: code,
        owner_label: source.owner_state?.label ?? "暂不可用",
        reason: "策略组状态暂不可用",
        selected: code === "MPG",
      }));

  return rows.map((row, index) => {
    const id = row.strategy_group_id || `${splitCode(row.name ?? "")}-001`;
    const code = splitCode(id || row.name || "");
    const sourceState = source.owner_state?.status;
    const mappedState = stateFromOwnerLabel(row.owner_label || "", row.runtime_state || sourceState);
    const state = sourceState === "waiting_for_opportunity" && mappedState === "running"
      ? "waiting_for_opportunity"
      : mappedState;
    const reason = row.reason || source.owner_state?.reason || undefined;
    return {
      id,
      code,
      name: code,
      description: strategyDescriptions[code],
      automationState: state,
      automationLabel: automationStateLabels[state],
      ownerAttention: source.owner_state?.needs_owner_action && state === "temporarily_unavailable" ? "owner_required" : state === "temporarily_unavailable" ? "system_required" : "none",
      ownerAttentionLabel: source.owner_state?.needs_owner_action && state === "temporarily_unavailable" ? "需要介入" : state === "temporarily_unavailable" ? "系统处理" : "无需操作",
      availabilityReason: state === "temporarily_unavailable" || state === "paused" ? reason || "状态暂不可用" : undefined,
      funds: healthFromSource(health.accountFunds),
      orders: healthFromSource(health.orders),
      position: healthFromSource(health.positions),
      protection: healthFromSource(health.protection),
      reconciliation: healthFromSource(health.reconciliation),
      selected: Boolean(row.selected) || index === 0,
    } satisfies StrategyGroupProductRow;
  });
}

function countState(rows: StrategyGroupProductRow[], state: OwnerAutomationState) {
  return rows.filter((row) => row.automationState === state).length;
}

function isReadySource(item: OwnerSourceHealthItem) {
  return item.status === "ready" || item.status === "ready_empty" || item.status === "ready_nonempty";
}

function hasUsableBusinessData(source: OwnerConsoleSourceReadinessData, health: OwnerSourceHealth) {
  return source.status === "ready"
    && isReadySource(health.accountFunds)
    && isReadySource(health.orders)
    && isReadySource(health.positions)
    && isReadySource(health.protection);
}

function productSummary(source: OwnerConsoleSourceReadinessData, rows: StrategyGroupProductRow[], health: OwnerSourceHealth): OwnerProductSummary {
  const ownerAttentionCount = rows.filter((row) => row.ownerAttention === "owner_required").length;
  const unavailableCount = countState(rows, "temporarily_unavailable");
  const ready = hasUsableBusinessData(source, health);
  const ownerLabel = source.owner_state?.label || source.owner_summary?.market_opportunity || "状态暂不可用";
  return {
    overallStatus: ownerAttentionCount > 0 ? "attention" : ready ? "safe" : "degraded",
    enabledCount: rows.length,
    runningCount: countState(rows, "running"),
    waitingCount: countState(rows, "waiting_for_opportunity"),
    processingCount: countState(rows, "processing"),
    unavailableCount,
    pausedCount: countState(rows, "paused"),
    ownerAttentionCount,
    dataFreshnessLabel: ready ? "数据新鲜 < 60秒" : "数据不可用",
    systemLabel: ready ? "系统正常" : "数据状态暂不可用",
    reason: ready ? ownerLabel : source.owner_summary?.funds || "状态证据待刷新",
  };
}

function fundPool(source: OwnerConsoleSourceReadinessData, health: OwnerSourceHealth): FundPoolSummary {
  return {
    label: "安全资金池",
    code: "LIVE-SAFE-1",
    budget: health.accountFunds.status === "ready" ? "只读正常" : "未声明",
    reserved: "$0.00",
    available: health.accountFunds.status === "ready" ? "只读正常" : "未声明",
    openOrders: health.orders.status === "ready_nonempty" ? 1 : 0,
    activePositions: health.positions.status === "ready_nonempty" ? 1 : 0,
    accountLabel: source.owner_summary?.funds || health.accountFunds.label,
    ordersLabel: source.owner_summary?.orders || health.orders.label,
    positionsLabel: source.owner_summary?.positions || health.positions.label,
    reconciliationLabel: source.owner_summary?.reconciliation || health.reconciliation.label,
    protectionLabel: health.protection.status === "ready" ? "正常" : health.protection.status === "ready_nonempty" ? "处理中" : health.protection.status === "unavailable" ? "未知" : "未知",
    fundsLocked: true,
  };
}

export function sourceReadinessToProjection(response: OwnerConsoleSourceReadinessResponse, scenario?: OwnerMockScenario): OwnerProductProjection {
  const source = response.data;
  const health = mapSourceHealth(source);
  const rows = strategyRows(source, health);
  const selected = rows.find((row) => row.selected) ?? rows[0] ?? null;
  const safeOrWaiting = source.owner_state?.label || source.owner_summary?.market_opportunity || "等待机会";
  const ready = hasUsableBusinessData(source, health);
  const rowChanges = rows
    .filter((row) => row.automationState === "processing" || row.automationState === "paused" || row.automationState === "temporarily_unavailable")
    .map((row) => ({
      id: `${row.id}-state-change`,
      title: row.automationState === "processing" ? `${row.code} 正在处理订单` : row.automationState === "paused" ? `${row.code} 已暂停` : `${row.code} 暂不可用`,
      detail: row.availabilityReason || row.automationLabel,
      tone: row.automationState === "processing" ? "processing" as const : row.automationState === "paused" ? "paused" as const : "danger" as const,
      sourceKind: "strategy_state" as const,
    }));
  return {
    asOf: source.generated_at_ms ? new Date(source.generated_at_ms).toISOString() : new Date().toISOString(),
    source: response.read_model || "owner_console_source_readiness",
    scenario,
    productSummary: productSummary(source, rows, health),
    strategies: rows.map((row) => ({ ...row, selected: row.id === selected?.id })),
    selectedStrategyId: selected?.id ?? null,
    fundPool: fundPool(source, health),
    sourceHealth: health,
    importantChanges: [
      {
        id: "source-readiness-state",
        title: ready ? `系统${safeOrWaiting}` : "状态暂不可用",
        detail: ready ? `${source.owner_summary?.funds || "资金正常"}，${source.owner_summary?.orders || "暂无订单"}，${source.owner_summary?.positions || "暂无持仓"}` : source.owner_state?.reason || "等待状态恢复",
        tone: ready ? "safe" : "danger",
        sourceKind: "system",
      },
      ...rowChanges,
    ],
    noActionGuarantee: {
      places_order: Boolean(source.safety_invariants?.places_order),
      cancels_order: false,
      replaces_order: false,
      flattens_position: false,
      starts_runtime: false,
      grants_auto_execution: false,
      mutates_pg: Boolean(source.safety_invariants?.mutates_pg),
      calls_operation_layer: false,
      calls_final_gate: false,
      exchange_write_called: Boolean(source.safety_invariants?.exchange_write_called),
    },
  };
}

export async function loadOwnerSourceReadinessProjection(): Promise<OwnerProductProjection> {
  const scenario = configuredMockScenario(runtimeMockScenario());

  if (shouldUseMock()) {
    if (scenario === "error") {
      throw new Error("Owner console mock state failed");
    }
    return sourceReadinessToProjection(buildMockSourceReadiness(scenario), scenario);
  }

  const response = await fetch(endpointUrl(), {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`真实后端不可用：HTTP ${response.status}`);
  }
  return sourceReadinessToProjection((await response.json()) as OwnerConsoleSourceReadinessResponse);
}
