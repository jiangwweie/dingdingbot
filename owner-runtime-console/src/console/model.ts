import type { OwnerAutomationState, OwnerAttentionState, OwnerHealthState, OwnerImportantChange, OwnerProductProjection, OwnerProductSummary, OwnerSourceHealthItem, OwnerSourceStatus, StrategyGroupProductRow } from "../types";

export type ThemeMode = "dark" | "light";
export type Tone = "safe" | "waiting" | "processing" | "danger" | "paused" | "neutral";
export type BackendConnectionState =
  | "loading"
  | "connected"
  | "unavailable"
  | "unauthorized";
export type NavigationKey = "home" | "strategies" | "funds" | "orders" | "records" | "system";

export type ConsoleContext = {
  connectionState: BackendConnectionState;
  sourceLabel: string | undefined;
  refreshedAt: string | null;
};

export const navigationTitles: Record<NavigationKey, string> = {
  home: "首页",
  strategies: "策略组",
  funds: "资金",
  orders: "订单与持仓",
  records: "记录",
  system: "系统",
};

export const navigationDescriptions: Record<NavigationKey, string> = {
  home: "系统总览和重要状态",
  strategies: "策略组可用性与观察状态",
  funds: "账户资金与安全资金池",
  orders: "成交单、保护单、持仓和对账",
  records: "重要变化与复盘入口",
  system: "只读连接、数据状态和安全保证",
};

export const noActionGuaranteeLabels: Record<string, string> = {
  places_order: "不会下单",
  cancels_order: "不会撤单",
  replaces_order: "不会改单",
  flattens_position: "不会平仓",
  starts_runtime: "不会启动策略运行",
  grants_auto_execution: "不会授权自动交易",
  mutates_pg: "不会写入生产库",
  calls_operation_layer: "不会触发实盘动作",
  calls_final_gate: "不会执行安全判定",
  exchange_write_called: "不会写交易所",
};

export const stateTone: Record<OwnerAutomationState, Tone> = {
  not_enabled: "paused",
  running: "safe",
  waiting_for_opportunity: "waiting",
  processing: "processing",
  temporarily_unavailable: "danger",
  paused: "paused",
  completed: "safe",
};

export const attentionTone: Record<OwnerAttentionState, Tone> = {
  none: "neutral",
  system_required: "processing",
  owner_required: "danger",
};

export const healthTone: Record<OwnerHealthState, Tone> = {
  normal: "safe",
  processing: "processing",
  abnormal: "danger",
  unknown: "paused",
};

export const sourceStatusTone: Record<OwnerSourceStatus, Tone> = {
  ready: "safe",
  ready_empty: "safe",
  ready_nonempty: "processing",
  degraded: "processing",
  unavailable: "danger",
};

export const sourceKindLabels: Record<OwnerImportantChange["sourceKind"], string> = {
  strategy_state: "策略组",
  safety_state: "安全",
  fund_pool: "资金",
  post_action: "处理",
  system: "系统",
};

export function toneClass(tone: Tone) {
  return {
    safe: "border-[color:var(--status-safe-border)] bg-[color:var(--status-safe-bg)] text-[color:var(--status-safe)]",
    waiting: "border-[color:var(--status-waiting-border)] bg-[color:var(--status-waiting-bg)] text-[color:var(--status-waiting)]",
    processing: "border-[color:var(--status-processing-border)] bg-[color:var(--status-processing-bg)] text-[color:var(--status-processing)]",
    danger: "border-[color:var(--status-danger-border)] bg-[color:var(--status-danger-bg)] text-[color:var(--status-danger)]",
    paused: "border-[color:var(--status-paused-border)] bg-[color:var(--status-paused-bg)] text-[color:var(--status-paused)]",
    neutral: "border-border bg-muted text-muted-foreground",
  }[tone];
}

export function toneTextClass(tone: Tone) {
  return {
    safe: "text-[color:var(--status-safe)]",
    waiting: "text-[color:var(--status-waiting)]",
    processing: "text-[color:var(--status-processing)]",
    danger: "text-[color:var(--status-danger)]",
    paused: "text-[color:var(--status-paused)]",
    neutral: "",
  }[tone];
}

export function toneDotClass(tone: Tone) {
  return {
    safe: "bg-[color:var(--status-safe)]",
    waiting: "bg-[color:var(--status-waiting)]",
    processing: "bg-[color:var(--status-processing)]",
    danger: "bg-[color:var(--status-danger)]",
    paused: "bg-[color:var(--status-paused)]",
    neutral: "bg-muted-foreground",
  }[tone];
}

export function isBusinessDataUnavailable(summary: OwnerProductSummary | null) {
  if (!summary) return false;
  return !summary.dataFreshnessLabel.startsWith("数据新鲜");
}

export function strategyRiskLabel(strategy: StrategyGroupProductRow | null) {
  if (!strategy) return "未声明";
  return {
    MPG: "标准",
    TEQ: "标准",
    FBS: "保守",
    SOR: "标准",
    PMR: "观察",
  }[strategy.code] ?? "未声明";
}

export function observationModeLabel(strategy: StrategyGroupProductRow | null) {
  if (!strategy) return "未启用";
  if (strategy.automationState === "paused") return "暂停";
  if (strategy.automationState === "temporarily_unavailable") return "暂不可用";
  if (strategy.automationState === "completed") return "已完成";
  if (strategy.automationState === "not_enabled") return "未启用";
  return "边界内自动";
}

export function moneyNumber(value: string) {
  const parsed = Number(value.replace(/[$,]/g, ""));
  return Number.isFinite(parsed) ? parsed : 0;
}

export function percentOf(value: string, total: string) {
  const denominator = moneyNumber(total);
  if (denominator <= 0) return 0;
  return Math.round((moneyNumber(value) / denominator) * 1000) / 10;
}

export function selectedStrategyFor(projection: OwnerProductProjection, selectedId: string | null) {
  return projection.strategies.find((strategy) => strategy.id === selectedId)
    ?? projection.strategies.find((strategy) => strategy.selected)
    ?? projection.strategies[0]
    ?? null;
}

export function homepageOperatingState(projection: OwnerProductProjection): {
  label: string;
  detail: string;
  tone: Tone;
  ownerAction: string;
} {
  const summary = projection.productSummary;
  const readiness = projection.realOrderReadiness;
  const sourceHealth = projection.sourceHealth;

  if (summary.ownerAttentionCount > 0 || summary.overallStatus === "attention") {
    return {
      label: "需要介入",
      detail: summary.reason || "有事项需要 Owner 处理",
      tone: "danger",
      ownerAction: "查看需要介入的策略组",
    };
  }

  if (readiness.submitBlockerReview.required || _hasSafetyBlocker(projection)) {
    return {
      label: "安全边界阻断",
      detail: readiness.ownerDetail || "真实订单保持关闭，等待系统处理安全状态",
      tone: "danger",
      ownerAction: "等待系统处理或查看系统状态",
    };
  }

  if (_hasEngineeringBlocker(sourceHealth)) {
    return {
      label: "工程状态暂不可用",
      detail: _firstEngineeringDetail(sourceHealth) || "运行、观察或状态源需要刷新",
      tone: "processing",
      ownerAction: "等待自动修复或查看系统状态",
    };
  }

  if (summary.processingCount > 0) {
    return {
      label: "系统处理中",
      detail: "系统正在处理订单、保护、对账或状态刷新",
      tone: "processing",
      ownerAction: "无需操作",
    };
  }

  if (summary.waitingCount > 0 || readiness.status === "waiting_for_market") {
    return {
      label: "等待市场机会",
      detail: "自动化正常运行，当前没有可用市场机会",
      tone: "waiting",
      ownerAction: "无需操作",
    };
  }

  return {
    label: "运行中",
    detail: "自动化正常运行",
    tone: "safe",
    ownerAction: "无需操作",
  };
}

function _hasSafetyBlocker(projection: OwnerProductProjection) {
  const readiness = projection.realOrderReadiness;
  if (readiness.blockedCount <= 0) return false;
  return readiness.matrix.some((item) => {
    const blockerClass = item.blockerClass || "";
    return item.blocksRealSubmit || blockerClass.includes("safety") || blockerClass.includes("active_position");
  }) || readiness.submitBlockingKeys.length > 0;
}

function _hasEngineeringBlocker(sourceHealth: OwnerProductProjection["sourceHealth"]) {
  return [
    sourceHealth.runtime,
    sourceHealth.watcher,
    sourceHealth.liveFacts,
    sourceHealth.runtimeDryRunAudit,
    sourceHealth.deployChannel,
  ].some(_isEngineeringUnavailable);
}

function _isEngineeringUnavailable(item: OwnerSourceHealthItem) {
  return item.status === "degraded" || item.status === "unavailable";
}

function _firstEngineeringDetail(sourceHealth: OwnerProductProjection["sourceHealth"]) {
  const item = [
    sourceHealth.runtime,
    sourceHealth.watcher,
    sourceHealth.liveFacts,
    sourceHealth.runtimeDryRunAudit,
    sourceHealth.deployChannel,
  ].find(_isEngineeringUnavailable);
  return item?.detail || item?.label || null;
}
