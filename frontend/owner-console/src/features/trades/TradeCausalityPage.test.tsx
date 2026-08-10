import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ownerQueryClient } from "../../app/queryClient";
import { TradeCausalityPage } from "./TradeCausalityPage";
import { getCandles, getTradeCausality } from "./api";

vi.mock("../../components/charts/CausalityChart", () => ({
  default: () => <div data-testid="causality-chart">chart</div>,
}));

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return {
    ...actual,
    getCandles: vi.fn(),
    getTradeCausality: vi.fn(),
  };
});

const evidence = (kind: "signal" | "admission" | "ticket" | "aggregate" | "event" | "command" | "incident" | "settlement" | "review" | "shadow" | "fact", identity: string, occurredAtMs = 1_807_408_800_000) => ({
  kind,
  identity,
  occurred_at_ms: occurredAtMs,
});

const metric = (value: string | null, unit: "USDT" | "R") => ({ value, unit, unavailable_reason: value === null ? "ticket_active" : null });

const trade = {
  ticket_id: "ticket:1",
  strategy_group_id: "SOR-LONG",
  event_spec_id: "event:SOR",
  exchange_instrument_id: "BNBUSDT",
  position_side: "long" as const,
  ticket_status: "POSITION_PROTECTED",
  aggregate_status: "POSITION_PROTECTED",
  lifecycle_stage: "protection" as const,
  completed_stage_count: 4,
  total_stage_count: 8 as const,
  issued_at_ms: 1_807_408_800_000,
  terminal_at_ms: null,
  exit_reason: null,
  exit_reason_unavailable_reason: "ticket_active",
  gross_pnl: metric(null, "USDT"),
  fees: metric("-0.12", "USDT"),
  funding: metric("0.01", "USDT"),
  net_pnl: metric(null, "USDT"),
  net_r: metric(null, "R"),
  economics_completeness: null,
  review_id: null,
  review_revision: null,
  attention_items: ["等待保护生命周期继续"],
  evidence: [evidence("ticket", "ticket:1")],
};

const stageKeys = ["signal", "admission", "entry", "protection", "tp_runner", "exit", "reconciliation", "review"] as const;
const stageLabels = {
  signal: "Signal",
  admission: "Admission",
  entry: "Entry",
  protection: "Protection",
  tp_runner: "TP / Runner",
  exit: "Exit",
  reconciliation: "Reconciliation / Settlement",
  review: "Review",
} as const;
const stages = stageKeys.map((key, index) => ({
  key,
  label: stageLabels[key],
  status: (index < 3 ? "complete" : index === 3 ? "current" : "pending") as "complete" | "current" | "pending",
  started_at_ms: index <= 3 ? 1_807_408_800_000 + index * 60_000 : null,
  completed_at_ms: index < 3 ? 1_807_408_830_000 + index * 60_000 : null,
  duration_ms: index < 3 ? 30_000 : null,
  summary: index === 3 ? "InitialStopConfirmed 后持仓受保护" : `${key} stage`,
  evidence: index <= 3 ? [evidence("event", `event:${key}`)] : [],
}));

const detailEnvelope = {
  snapshot_id: "snapshot:causality:1",
  generated_at: "2026-08-09T02:00:00.000Z",
  source_watermark: "2026-08-09T02:00:00.000Z",
  freshness: "fresh" as const,
  data: {
    trade,
    current_stage: "protection" as const,
    current_stage_summary: "InitialStopConfirmed 后持仓受保护",
    stages,
    annotations: [
      { kind: "signal" as const, label: "Signal", occurred_at_ms: 1_807_408_800_000, price: "61000.0", evidence: [evidence("signal", "signal:1")] },
      { kind: "entry" as const, label: "ENTRY", occurred_at_ms: 1_807_408_860_000, price: "61200.0", evidence: [evidence("command", "command:entry")] },
      { kind: "stop" as const, label: "Initial Stop", occurred_at_ms: 1_807_408_920_000, price: "60000.0", evidence: [evidence("command", "command:stop")] },
    ],
    exit_reason: null,
    raw_events: [
      { ticket_id: "ticket:1", event_id: "event:stop", sequence: 4, event_type: "InitialStopConfirmed", occurred_at_ms: 1_807_408_920_000, stage: "protection" as const, classification: "mapped" as const, payload: { stop_price: "60000.0" }, evidence: [evidence("event", "event:stop")] },
    ],
    raw_commands: [
      { ticket_id: "ticket:1", command_id: "command:entry", command_kind: "ENTRY", generation: 1, status: "accepted", request_payload: { side: "buy" }, result_payload: { order_id: "order:1" }, created_at_ms: 1_807_408_850_000, completed_at_ms: 1_807_408_870_000, evidence: [evidence("command", "command:entry")] },
    ],
    raw_incidents: [],
    signal_evidence: [evidence("signal", "signal:1")],
    order_evidence: [evidence("command", "command:entry")],
    incident_evidence: [],
    event_evidence: [evidence("event", "event:stop")],
    settlement_evidence: [],
    review_evidence: [],
    evidence: [evidence("ticket", "ticket:1"), evidence("event", "event:stop")],
  },
};

const candleEnvelope = {
  snapshot_id: "snapshot:candles:1",
  generated_at: "2026-08-09T02:00:00.000Z",
  source_watermark: "2026-08-09T02:00:00.000Z",
  freshness: "fresh" as const,
  data: {
    candles: [
      { open_time_ms: 1_807_408_000_000, close_time_ms: 1_807_408_899_999, open: "60800", high: "61300", low: "60700", close: "61200", volume: "1200" },
      { open_time_ms: 1_807_408_900_000, close_time_ms: 1_807_409_799_999, open: "61200", high: "61400", low: "60900", close: "61100", volume: "900" },
    ],
  },
};

const mockedGetTradeCausality = vi.mocked(getTradeCausality);
const mockedGetCandles = vi.mocked(getCandles);

function renderCausality(initialEntry: string) {
  return render(
    <QueryClientProvider client={ownerQueryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes><Route path="/trades/:ticketId" element={<TradeCausalityPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  ownerQueryClient.clear();
  mockedGetTradeCausality.mockReset();
  mockedGetCandles.mockReset();
  mockedGetTradeCausality.mockResolvedValue(detailEnvelope);
  mockedGetCandles.mockResolvedValue(candleEnvelope);
});

afterEach(() => ownerQueryClient.clear());

it("shows eight stages before requesting candles", async () => {
  const user = userEvent.setup();
  renderCausality("/trades/ticket%3A1");

  expect(await screen.findAllByTestId("lifecycle-stage")).toHaveLength(8);
  expect(screen.getAllByText("已完成")).toHaveLength(3);
  expect(screen.getAllByText("进行中")).toHaveLength(2);
  expect(screen.getAllByText("等待执行")).toHaveLength(4);
  expect(mockedGetCandles).not.toHaveBeenCalled();

  await user.click(screen.getByRole("button", { name: "展开 K 线" }));
  expect(await screen.findByTestId("causality-chart")).toBeInTheDocument();
  expect(mockedGetCandles).toHaveBeenCalledTimes(1);
});

it("keeps lifecycle facts visible when public candles fail", async () => {
  const user = userEvent.setup();
  mockedGetCandles.mockRejectedValue(new Error("market unavailable"));
  renderCausality("/trades/ticket%3A1");
  await user.click(await screen.findByRole("button", { name: "展开 K 线" }));

  expect(await screen.findByText("公共行情不可用")).toBeInTheDocument();
  expect(screen.getByText("InitialStopConfirmed")).toBeInTheDocument();
});

it("retries failed candles only after an explicit manual refresh", async () => {
  const user = userEvent.setup();
  mockedGetCandles
    .mockRejectedValueOnce(new Error("market unavailable"))
    .mockResolvedValueOnce(candleEnvelope);
  renderCausality("/trades/ticket%3A1");

  await user.click(await screen.findByRole("button", { name: "展开 K 线" }));
  expect(await screen.findByText("公共行情不可用")).toBeInTheDocument();
  expect(mockedGetCandles).toHaveBeenCalledTimes(1);

  await user.click(screen.getByRole("button", { name: "刷新当前页" }));
  expect(await screen.findByTestId("causality-chart")).toBeInTheDocument();
  expect(mockedGetCandles).toHaveBeenCalledTimes(2);
});

it("opens the already loaded K-line data in a full-screen review dialog without another request", async () => {
  const user = userEvent.setup();
  renderCausality("/trades/ticket%3A1");

  await user.click(await screen.findByRole("button", { name: "展开 K 线" }));
  await screen.findByTestId("causality-chart");
  expect(mockedGetCandles).toHaveBeenCalledTimes(1);

  await user.click(screen.getByRole("button", { name: "全屏复盘 K 线" }));
  expect(await screen.findByRole("dialog", { name: /BNBUSDT LONG · 15m K 线复盘/ })).toBeInTheDocument();
  expect(mockedGetCandles).toHaveBeenCalledTimes(1);
});
