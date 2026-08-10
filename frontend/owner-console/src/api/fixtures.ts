import type { components } from "./schema";

const generatedAt = "2026-08-09T08:00:00.000Z";
const baseTime = 1_807_408_800_000;
const evidence = (kind: components["schemas"]["EvidenceRef"]["kind"], identity: string, occurredAtMs = baseTime) => ({ kind, identity, occurred_at_ms: occurredAtMs });
const money = (value: string | null, unit: components["schemas"]["MoneyMetric"]["unit"] = "USDT", unavailableReason: string | null = null) => ({ value, unit, unavailable_reason: unavailableReason });

export const overviewFixture = {
  snapshot_id: "snapshot:overview:e2e",
  generated_at: generatedAt,
  source_watermark: generatedAt,
  freshness: "fresh",
  data: {
    observed_at_ms: baseTime,
    conclusion: { level: "no_action", summary: "系统运行正常，无需 Owner 操作", owner_action: null, evidence: [evidence("fact", "overview:fresh")] },
    account_snapshot: { label: "Latest Admission Snapshot", is_realtime: false, captured_at_ms: baseTime - 60_000, wallet_balance: money("103.5100"), available_margin: money("72.3400") },
    ticket_capacity: 3,
    active_ticket_count: 1,
    active_ticket_ids: ["ticket:active:1"],
    today_net_pnl: money("3.5100"),
    today_net_r: money("0.4800", "R"),
    today_signal_count: 4,
    admitted_signal_count: 1,
    rejected_signal_count: 3,
    execution_incident_count: 0,
    attention_summary: ["一笔活动 Ticket 已受初始保护"],
    evidence: [evidence("fact", "overview:fresh"), evidence("ticket", "ticket:active:1")],
  },
} satisfies components["schemas"]["ApiEnvelope_OwnerOverview_"];

export const rejectedSignal = {
  signal_event_id: "signal:rejected:1",
  exposure_episode_id: "episode:rejected:1",
  strategy_group_id: "SOR-LONG",
  strategy_version_id: "sor-v1",
  event_spec_id: "event:SOR",
  exchange_instrument_id: "BTCUSDT",
  position_side: "long",
  occurred_at_ms: baseTime - 3_600_000,
  expires_at_ms: baseTime,
  admission_decision_id: "decision:rejected:1",
  decision_status: "rejected",
  first_blocker: "gross_stop_risk_capacity_exhausted",
  binding_constraint: "gross_stop_risk_capacity_exhausted",
  ticket_id: null,
  shadow_summary: { shadow_outcome_id: "shadow:1", status: "completed", mfe_r: "1.25", mae_r: "-0.40", completion_reason: "horizon_complete", observed_through_ms: baseTime, completed_at_ms: baseTime, interpretation: "Observation only; this Shadow Outcome is not execution.", evidence: [evidence("shadow", "shadow:1")] },
  evidence: [evidence("signal", "signal:rejected:1"), evidence("admission", "decision:rejected:1")],
} satisfies components["schemas"]["SignalListItem"];

export const admittedSignal = {
  ...rejectedSignal,
  signal_event_id: "signal:admitted:2",
  exposure_episode_id: "episode:admitted:2",
  admission_decision_id: "decision:admitted:2",
  decision_status: "admitted",
  first_blocker: null,
  binding_constraint: null,
  ticket_id: "ticket:active:1",
  shadow_summary: null,
  evidence: [evidence("signal", "signal:admitted:2"), evidence("admission", "decision:admitted:2")],
} satisfies components["schemas"]["SignalListItem"];

export const signalListFixture = {
  snapshot_id: "snapshot:signals:e2e",
  generated_at: generatedAt,
  source_watermark: generatedAt,
  freshness: "fresh",
  data: { items: [rejectedSignal, admittedSignal], next_cursor: null },
} satisfies components["schemas"]["ApiEnvelope_SignalListPage_"];

export const signalDetailFixture = {
  snapshot_id: "snapshot:signal-detail:e2e",
  generated_at: generatedAt,
  source_watermark: generatedAt,
  freshness: "fresh",
  data: {
    signal: rejectedSignal,
    what_happened: "The persisted AdmissionDecision rejected this Signal; no Ticket was created.",
    why_no_ticket: "gross_stop_risk_capacity_exhausted",
    fact_snapshots: [{ signal_event_id: rejectedSignal.signal_event_id, fact_definition_id: "fact:gross-stop-risk", role: "condition", value: false, satisfied: false, observed_at_ms: baseTime - 3_600_000, valid_until_ms: baseTime, projection_version: 1 }],
    shadow_summary: rejectedSignal.shadow_summary,
    evidence: rejectedSignal.evidence,
  },
} satisfies components["schemas"]["ApiEnvelope_SignalAdmissionDetail_"];

export const activeTrade = {
  ticket_id: "ticket:active:1",
  strategy_group_id: "SOR-LONG",
  event_spec_id: "event:SOR",
  exchange_instrument_id: "BNBUSDT",
  position_side: "long",
  ticket_status: "POSITION_PROTECTED",
  aggregate_status: "POSITION_PROTECTED",
  lifecycle_stage: "protection",
  completed_stage_count: 4,
  total_stage_count: 8,
  issued_at_ms: baseTime - 2_700_000,
  terminal_at_ms: null,
  exit_reason: null,
  exit_reason_unavailable_reason: "ticket_active",
  gross_pnl: money(null, "USDT", "ticket_active"),
  fees: money("-0.1200"),
  funding: money("0.0100"),
  net_pnl: money(null, "USDT", "ticket_active"),
  net_r: money(null, "R", "ticket_active"),
  economics_completeness: null,
  review_id: null,
  review_revision: null,
  attention_items: ["等待退出"],
  evidence: [evidence("ticket", "ticket:active:1")],
} satisfies components["schemas"]["TradeListItem"];

export const terminalTrade = {
  ...activeTrade,
  ticket_id: "ticket:terminal:2",
  strategy_group_id: "MPG-SHORT",
  exchange_instrument_id: "BTCUSDT",
  position_side: "short",
  ticket_status: "TERMINAL",
  aggregate_status: "TERMINAL",
  lifecycle_stage: "review",
  completed_stage_count: 8,
  terminal_at_ms: baseTime,
  exit_reason: "TP1 + Runner Exit",
  exit_reason_unavailable_reason: null,
  gross_pnl: money("3.8000"),
  fees: money("-0.2500"),
  funding: money("-0.0400"),
  net_pnl: money("3.5100"),
  net_r: money("0.4800", "R"),
  economics_completeness: "complete",
  review_id: "review:ticket:terminal:2",
  review_revision: 1,
  attention_items: [],
  evidence: [evidence("ticket", "ticket:terminal:2"), evidence("review", "review:ticket:terminal:2")],
} satisfies components["schemas"]["TradeListItem"];

export const tradeListFixture = {
  snapshot_id: "snapshot:trades:e2e",
  generated_at: generatedAt,
  source_watermark: generatedAt,
  freshness: "fresh",
  data: { items: [activeTrade, terminalTrade], next_cursor: null },
} satisfies components["schemas"]["ApiEnvelope_TradeListPage_"];

const stageKeys: components["schemas"]["LifecycleStageView"]["key"][] = ["signal", "admission", "entry", "protection", "tp_runner", "exit", "reconciliation", "review"];
const stageLabels = ["Signal", "Admission", "Entry", "Protection", "TP / Runner", "Exit", "Reconciliation / Settlement", "Review"];
const activeStages = stageKeys.map((key, index) => ({ key, label: stageLabels[index] ?? key, status: index < 3 ? "complete" as const : index === 3 ? "current" as const : "pending" as const, started_at_ms: index <= 3 ? baseTime - (4 - index) * 600_000 : null, completed_at_ms: index < 3 ? baseTime - (4 - index) * 600_000 + 300_000 : null, duration_ms: index < 3 ? 300_000 : null, summary: key === "protection" ? "InitialStopConfirmed 后持仓受保护" : `${key} stage`, evidence: index <= 3 ? [evidence("event", `event:${key}:active`)] : [] }));

export const tradeCausalityFixture = {
  snapshot_id: "snapshot:causality:e2e",
  generated_at: generatedAt,
  source_watermark: generatedAt,
  freshness: "fresh",
  data: {
    trade: activeTrade,
    current_stage: "protection",
    current_stage_summary: "InitialStopConfirmed 后持仓受保护",
    stages: activeStages,
    annotations: [{ kind: "signal", label: "Signal", occurred_at_ms: baseTime - 2_700_000, price: "610.20", evidence: [evidence("signal", "signal:admitted:2")] }, { kind: "entry", label: "ENTRY", occurred_at_ms: baseTime - 1_800_000, price: "612.80", evidence: [evidence("command", "command:entry:active")] }, { kind: "stop", label: "Initial Stop", occurred_at_ms: baseTime - 900_000, price: "598.40", evidence: [evidence("command", "command:stop:active")] }],
    exit_reason: null,
    raw_events: [{ event_id: "event:initial-stop-confirmed", ticket_id: activeTrade.ticket_id, sequence: 4, event_type: "InitialStopConfirmed", payload: { stop_price: "598.40" }, occurred_at_ms: baseTime - 900_000, stage: "protection", classification: "mapped", evidence: [evidence("event", "event:initial-stop-confirmed")] }],
    raw_commands: [{ command_id: "command:entry:active", ticket_id: activeTrade.ticket_id, command_kind: "ENTRY", generation: 1, status: "accepted", request_payload: { quantity: "0.02" }, result_payload: { order_id: "order:entry:active" }, created_at_ms: baseTime - 1_800_000, completed_at_ms: baseTime - 1_770_000, evidence: [evidence("command", "command:entry:active")] }],
    raw_incidents: [],
    signal_evidence: [evidence("signal", "signal:admitted:2")],
    order_evidence: [evidence("command", "command:entry:active")],
    incident_evidence: [],
    event_evidence: [evidence("event", "event:initial-stop-confirmed")],
    settlement_evidence: [],
    review_evidence: [],
    evidence: [evidence("ticket", activeTrade.ticket_id), evidence("event", "event:initial-stop-confirmed")],
  },
} satisfies components["schemas"]["ApiEnvelope_TradeCausalityDetail_"];

export const candleFixture = {
  snapshot_id: "snapshot:candles:e2e",
  generated_at: generatedAt,
  source_watermark: generatedAt,
  freshness: "fresh",
  data: { candles: Array.from({ length: 36 }, (_, index) => ({ open_time_ms: baseTime - 32_400_000 + index * 900_000, close_time_ms: baseTime - 31_500_001 + index * 900_000, open: `${600 + index}.00`, high: `${604 + index}.00`, low: `${598 + index}.00`, close: `${602 + index}.00`, volume: `${800 + index * 10}` })) },
} satisfies components["schemas"]["ApiEnvelope_CandleSeries_"];

const completeReviewItem = {
  ticket_id: terminalTrade.ticket_id,
  strategy_group_id: terminalTrade.strategy_group_id,
  exchange_instrument_id: terminalTrade.exchange_instrument_id,
  position_side: terminalTrade.position_side,
  terminal_at_ms: terminalTrade.terminal_at_ms!,
  review: { ticket_id: terminalTrade.ticket_id, review_status: "complete", execution_classification: "complete", economic_summary: { gross_pnl: terminalTrade.gross_pnl, fees: terminalTrade.fees, funding: terminalTrade.funding, net_pnl: terminalTrade.net_pnl, net_r: money("-1.114162711864406779661016949", "R") }, exit_reason: terminalTrade.exit_reason, attention_items: [], sentences: [{ template_id: "execution_complete", text: "执行链完整。ENTRY 后初始保护已确认；退出由 TP1 后 Runner EXIT 触发。", evidence: [evidence("event", "event:terminal:complete"), evidence("review", "review:ticket:terminal:2")] }], final_conclusion: "执行链完整。", evidence: terminalTrade.evidence },
} satisfies components["schemas"]["ReviewCenterItem"];

export const reviewFixture = {
  snapshot_id: "snapshot:review:e2e",
  generated_at: generatedAt,
  source_watermark: generatedAt,
  freshness: "fresh",
  data: { from_ms: baseTime - 30 * 86_400_000, to_ms: baseTime, sample_count: 1, next_cursor: null, items: [completeReviewItem], net_pnl: terminalTrade.net_pnl, net_r: money("-1.114162711864406779661016949", "R"), fees: terminalTrade.fees, funding: terminalTrade.funding, exit_reason_breakdown: [{ label: "deployment_drain:deploy-20260804-8627ae9c:8627ae9ca5430fd9f8b9a76935f685cd36960ccc", ticket_count: 1, evidence: terminalTrade.evidence }], execution_quality_breakdown: [{ label: "complete", ticket_count: 1, evidence: terminalTrade.evidence }], complete_review_count: 1, incomplete_review_count: 0, strategy_group_samples: [{ strategy_group_id: terminalTrade.strategy_group_id, sample_count: 1, evidence_state: "observe_only", evidence: terminalTrade.evidence }], evidence: terminalTrade.evidence },
} satisfies components["schemas"]["ApiEnvelope_ReviewCenterSummary_"];

const strategyVersionFixture = {
  strategy_group_id: "BRF2-001",
  strategy_group_display_name: "BRF2",
  strategy_version_id: "strategy-version:brf2:v3",
  version: 3,
  strategy_version_status: "active",
  is_current: true,
  ticket_count: 4,
  natural_terminal_count: 3,
  confirmed_natural_review_count: 2,
  pending_natural_review_count: 1,
  controlled_exit_count: 1,
  tp1_reached_count: 1,
  tp1_not_reached_count: 2,
  win_count: 1,
  loss_count: 1,
  net_pnl: money("8.12"),
  net_r: money("0.81", "R"),
  evidence: [evidence("fact", "strategy-version:brf2:v3")],
} satisfies components["schemas"]["StrategyVersionSummary"];

const strategyTicketRowFixture = {
  ticket_id: "ticket:strategy:brf2:tp1",
  strategy_group_id: "BRF2-001",
  event_spec_id: "event:brf2:v3",
  exchange_instrument_id: "BTCUSDT",
  position_side: "short",
  ticket_status: "terminal",
  aggregate_status: "terminal",
  lifecycle_stage: "review",
  issued_at_ms: baseTime - 4_800_000,
  terminal_at_ms: baseTime - 3_600_000,
  review_id: "review:strategy:brf2:tp1",
  review_revision: 1,
  economics_completeness: "complete",
  completed_stage_count: 8,
  total_stage_count: 8,
  exit_reason: "runner_exit",
  exit_reason_unavailable_reason: null,
  gross_pnl: money("9.36"),
  fees: money("0.82"),
  funding: money("-0.42"),
  net_pnl: money("8.12"),
  net_r: money("0.81", "R"),
  attention_items: [],
  evaluation_path: "tp1_reached",
  evidence: [evidence("ticket", "ticket:strategy:brf2:tp1"), evidence("review", "review:strategy:brf2:tp1")],
} satisfies components["schemas"]["StrategyTicketListItem"];

export const strategyFixture = {
  snapshot_id: "snapshot:strategies:e2e",
  generated_at: generatedAt,
  source_watermark: generatedAt,
  freshness: "fresh",
  data: {
    from_ms: baseTime - 30 * 86_400_000,
    to_ms: baseTime,
    view: "current",
    items: [strategyVersionFixture],
    evidence: strategyVersionFixture.evidence,
  },
} satisfies components["schemas"]["ApiEnvelope_StrategySummaryPage_"];

export const strategyTicketFixture = {
  snapshot_id: "snapshot:strategy-tickets:e2e",
  generated_at: generatedAt,
  source_watermark: generatedAt,
  freshness: "fresh",
  data: { items: [strategyTicketRowFixture], next_cursor: null },
} satisfies components["schemas"]["ApiEnvelope_StrategyTicketListPage_"];

export const ownerApiFixtures = { overviewFixture, signalListFixture, signalDetailFixture, tradeListFixture, tradeCausalityFixture, candleFixture, reviewFixture, strategyFixture, strategyTicketFixture } as const;
