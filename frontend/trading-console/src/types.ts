export type ThemeMode = "dark" | "light";

export type SourceClass =
  | "direct"
  | "composed"
  | "derived"
  | "artifact-backed"
  | "mock-required"
  | "ui-only";

export type SessionResponse = {
  authenticated: boolean;
  username?: string | null;
  expires_at_ms?: number | null;
  current_stage: string;
  next_recommended_step: string;
  global_planning_stage: string;
  live_ready: boolean;
};

export type TradingConsoleEnvelope<TData = Record<string, unknown>> = {
  read_model: string;
  generated_at_ms: number;
  source: string;
  freshness_status: string;
  warnings: Array<Record<string, unknown>>;
  blockers: Array<Record<string, unknown>>;
  unavailable: Array<Record<string, unknown>>;
  data: TData;
  no_action_guarantee: Record<string, boolean>;
  live_ready: boolean;
};

export type Health = "normal" | "warning" | "danger" | "muted";

export type Kpi = {
  label: string;
  value: string;
  sublabel: string;
  tone: Health;
  trend?: string;
  sparkline?: number[];
  source: SourceClass;
};

export type TopStatus = {
  system: Health;
  account: Health;
  execution: Health;
  clock: string;
  notificationCount: number;
};

export type DashboardViewModel = {
  topStatus: TopStatus;
  kpis: Kpi[];
  overview: Array<{ label: string; value: string; hint: string; tone: Health }>;
  equity: number[];
  recentActions: Array<{ time: string; symbol: string; action: string; result: string; delta: string }>;
  alerts: Array<{ level: string; text: string; time: string }>;
  markets: Array<{ symbol: string; price: string; change: string; trend: number[] }>;
  riskGauges: Array<{ label: string; value: number; hint: string; tone: Health }>;
};

export type PositionRisk = {
  symbol: string;
  direction: "多" | "空";
  exposure: string;
  leverage: string;
  concentration: string;
  tone: Health;
};

export type AccountRiskViewModel = {
  topStatus: TopStatus;
  kpis: Kpi[];
  equity: number[];
  drawdown: number[];
  positions: PositionRisk[];
  budgetRows: Array<{ label: string; value: string; hint?: string }>;
  protectionRows: Array<{ label: string; value: string; tone: Health }>;
  alerts: Array<{ level: string; text: string; time: string }>;
};

export type OrderRow = {
  id: string;
  time: string;
  symbol: string;
  side: "买入" | "卖出";
  type: string;
  price: string;
  qty: string;
  notional: string;
  status: string;
  protected: boolean;
  strategy: string;
  venue: string;
};

export type OrderLedgerViewModel = {
  topStatus: TopStatus;
  kpis: Kpi[];
  orders: OrderRow[];
  selected: OrderRow;
  timeline: Array<{ title: string; time: string; meta: string; tone: Health }>;
  executionCharts: Array<{ label: string; value: string; series: number[]; tone: Health }>;
  statusDistribution: Array<{ label: string; value: number; pct: string; tone: Health }>;
};

export type StrategyCard = {
  id: string;
  state: "运行中" | "观察中" | "暂停中";
  actionability: "可执行" | "观察" | "暂停";
  purpose: string;
  direction: "仅做多" | "双向";
  symbols: string;
  fresh: string;
  health: string;
  actionsToday: number;
  tone: Health;
};

export type StrategyGroupsViewModel = {
  topStatus: TopStatus;
  kpis: Kpi[];
  strategies: StrategyCard[];
  selected: StrategyCard;
  candidatePool: Array<{ event: string; age: string; symbol: string; strategy: string; strength: number; action: string }>;
  eventStatus: Array<{ label: string; count: number; tone: Health }>;
  recentActions: Array<{ time: string; symbol: string; direction: string; action: string; strength: string; result: string }>;
  healthDistribution: Array<{ label: string; count: number; pct: string; tone: Health }>;
};

export type ExceptionItem = {
  id: string;
  priority: "高" | "中" | "低";
  title: string;
  target: string;
  time: string;
  state: string;
  tone: Health;
};

export type ExceptionsViewModel = {
  topStatus: TopStatus;
  kpis: Kpi[];
  exceptions: ExceptionItem[];
  selected: ExceptionItem;
  steps: Array<{ label: string; state: "done" | "active" | "pending" }>;
  impact: Array<{ label: string; value: string; tone: Health }>;
  health: Array<{ label: string; value: string; tone: Health }>;
  audit: Array<{ time: string; text: string; author: string }>;
};

