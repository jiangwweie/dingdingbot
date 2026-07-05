import type {
  AccountRiskViewModel,
  DashboardViewModel,
  ExceptionsViewModel,
  OrderLedgerViewModel,
  StrategyGroupsViewModel,
  TradingConsoleEnvelope,
} from "./types";
import {
  accountRiskMock,
  dashboardMock,
  exceptionsMock,
  orderLedgerMock,
  strategyGroupsMock,
} from "./mock";

const numberFormat = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
});

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item) => item && typeof item === "object") as Record<string, unknown>[] : [];
}

function money(value: unknown, fallback: string): string {
  const n = Number(value);
  return Number.isFinite(n) ? numberFormat.format(n) : fallback;
}

export function toDashboardViewModel(envelope?: TradingConsoleEnvelope): DashboardViewModel {
  if (!envelope) return dashboardMock;
  const data = asRecord(envelope.data);
  const account = asRecord(data.account_snapshot_summary);
  const orders = asRecord(data.orders);
  const openOrders = asArray(orders.pg_open);
  return {
    ...dashboardMock,
    kpis: dashboardMock.kpis.map((kpi) => {
      if (kpi.label === "持仓订单数") return { ...kpi, value: `${openOrders.length || 38} 个`, source: "direct" };
      if (kpi.label === "持仓盈亏") return { ...kpi, value: `${money(account.unrealized_pnl, "+8,246.37")} USDT`, source: "direct" };
      return kpi;
    }),
    topStatus: {
      ...dashboardMock.topStatus,
      system: envelope.blockers.length ? "danger" : envelope.warnings.length ? "warning" : "normal",
    },
  };
}

export function toAccountRiskViewModel(envelope?: TradingConsoleEnvelope): AccountRiskViewModel {
  if (!envelope) return accountRiskMock;
  const data = asRecord(envelope.data);
  const account = asRecord(data.account);
  const margin = asRecord(data.margin_facts);
  const positions = asArray(data.positions);
  return {
    ...accountRiskMock,
    kpis: accountRiskMock.kpis.map((kpi) => {
      if (kpi.label.startsWith("账户净值")) return { ...kpi, value: money(account.total_balance ?? margin.wallet_equity, kpi.value), source: "direct" };
      if (kpi.label.startsWith("可用保证金")) return { ...kpi, value: money(margin.available_margin, kpi.value), source: "direct" };
      return kpi;
    }),
    positions: positions.length
      ? positions.slice(0, 5).map((item, index) => ({
          symbol: String(item.symbol || `SYMBOL-${index + 1}`),
          direction: String(item.direction || item.side || "LONG").toUpperCase().startsWith("SHORT") ? "空" : "多",
          exposure: money(item.exposure ?? item.notional ?? item.quantity, accountRiskMock.positions[index]?.exposure || "0"),
          leverage: `${item.leverage || accountRiskMock.positions[index]?.leverage || "1.00x"}`,
          concentration: accountRiskMock.positions[index]?.concentration || "0.0%",
          tone: accountRiskMock.positions[index]?.tone || "normal",
        }))
      : accountRiskMock.positions,
  };
}

export function toOrderLedgerViewModel(envelope?: TradingConsoleEnvelope): OrderLedgerViewModel {
  if (!envelope) return orderLedgerMock;
  const data = asRecord(envelope.data);
  const rows = asArray(data.orders);
  const orders = rows.length
    ? rows.slice(0, 8).map((item, index) => ({
        id: String(item.order_id || item.id || `ORDER-${index + 1}`),
        time: String(item.created_at || item.updated_at || orderLedgerMock.orders[index % orderLedgerMock.orders.length].time).slice(11, 19) || "00:00:00",
        symbol: String(item.symbol || "-"),
        side: String(item.side || item.direction || "").toUpperCase().startsWith("SELL") ? "卖出" as const : "买入" as const,
        type: String(item.type || item.order_type || item.order_role || "订单"),
        price: String(item.price || item.average_exec_price || "-"),
        qty: String(item.qty || item.quantity || "-"),
        notional: money(item.notional || item.value, "-"),
        status: String(item.status || "unknown"),
        protected: Boolean(item.protected || item.reduce_only || item.order_role),
        strategy: String(item.strategy_group_id || item.strategy_family_id || "runtime"),
        venue: String(item.exchange || item.venue || "PG"),
      }))
    : orderLedgerMock.orders;
  return { ...orderLedgerMock, orders, selected: orders[0] };
}

export function toStrategyGroupsViewModel(envelope?: TradingConsoleEnvelope): StrategyGroupsViewModel {
  if (!envelope) return strategyGroupsMock;
  const data = asRecord(envelope.data);
  const ownerState = asRecord(data.owner_state);
  const blockerClass = String(ownerState.blocker_class || "");
  return {
    ...strategyGroupsMock,
    topStatus: {
      ...strategyGroupsMock.topStatus,
      execution: blockerClass === "hard_safety_stop" ? "danger" : blockerClass ? "warning" : "normal",
    },
  };
}

export function toExceptionsViewModel(envelope?: TradingConsoleEnvelope): ExceptionsViewModel {
  if (!envelope) return exceptionsMock;
  const data = asRecord(envelope.data);
  const tasks = asArray(data.recovery_tasks);
  const mismatches = asArray(data.mismatches);
  const exceptions = [...tasks, ...mismatches].slice(0, 8).map((item, index) => ({
    id: String(item.id || item.task_id || item.order_id || exceptionsMock.exceptions[index % exceptionsMock.exceptions.length].id),
    priority: index < 2 ? "高" as const : index < 4 ? "中" as const : "低" as const,
    title: String(item.title || item.message || item.classification || exceptionsMock.exceptions[index % exceptionsMock.exceptions.length].title),
    target: String(item.symbol || item.target || item.exchange || "-"),
    time: String(item.created_at || item.updated_at || exceptionsMock.exceptions[index % exceptionsMock.exceptions.length].time).slice(11, 19) || "00:00:00",
    state: String(item.status || "待处理"),
    tone: index < 2 ? "danger" as const : index < 4 ? "warning" as const : "muted" as const,
  }));
  return {
    ...exceptionsMock,
    exceptions: exceptions.length ? exceptions : exceptionsMock.exceptions,
    selected: exceptions[0] || exceptionsMock.selected,
  };
}

