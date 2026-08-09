import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ownerQueryClient } from "../../app/queryClient";
import { TradeListPage } from "./TradeListPage";
import { getTrades } from "./api";

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return { ...actual, getTrades: vi.fn() };
});

const metric = (value: string | null, unit: "USDT" | "R") => ({
  value,
  unit,
  unavailable_reason: value === null ? "funding_unavailable" : null,
});

const activeTicket = {
  ticket_id: "ticket:1",
  strategy_group_id: "SOR-001",
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
  exit_reason_unavailable_reason: null,
  gross_pnl: metric(null, "USDT"),
  fees: metric("-0.12", "USDT"),
  funding: metric("0.01", "USDT"),
  net_pnl: metric(null, "USDT"),
  net_r: metric(null, "R"),
  economics_completeness: null,
  review_id: null,
  review_revision: null,
  attention_items: ["等待退出"],
  evidence: [],
};

const terminalTicket = {
  ...activeTicket,
  ticket_id: "ticket:2",
  strategy_group_id: "MPG-SHORT",
  exchange_instrument_id: "BTCUSDT",
  position_side: "short" as const,
  ticket_status: "TERMINAL",
  aggregate_status: "TERMINAL",
  lifecycle_stage: "review" as const,
  completed_stage_count: 8,
  terminal_at_ms: 1_807_495_200_000,
  exit_reason: "runner_stop",
  gross_pnl: metric("4.60", "USDT"),
  net_pnl: metric("4.35", "USDT"),
  net_r: metric("1.18", "R"),
  economics_completeness: "complete" as const,
  review_id: "review:2",
  review_revision: 1,
  attention_items: [],
};

const tradeEnvelope = {
  snapshot_id: "snapshot:trades:1",
  generated_at: "2026-08-09T02:00:00.000Z",
  source_watermark: "2026-08-09T02:00:00.000Z",
  freshness: "fresh" as const,
  data: { items: [activeTicket, terminalTicket], next_cursor: null },
};

const mockedGetTrades = vi.mocked(getTrades);

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="current location">{location.pathname}{location.search}</output>;
}

function renderTrades(initialEntry: string) {
  return render(
    <QueryClientProvider client={ownerQueryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/trades" element={<TradeListPage />} />
          <Route path="/trades/:ticketId" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  ownerQueryClient.clear();
  mockedGetTrades.mockReset();
  mockedGetTrades.mockResolvedValue(tradeEnvelope);
});

afterEach(() => {
  ownerQueryClient.clear();
});

it("renders active and terminal tickets in one table", async () => {
  renderTrades("/trades?position_side=long");

  expect(await screen.findByText("POSITION_PROTECTED")).toBeInTheDocument();
  expect(screen.getByText("TERMINAL")).toBeInTheDocument();
  expect(screen.getAllByRole("row")).toHaveLength(3);
});

it("preserves filters when navigating to exact ticket detail", async () => {
  const user = userEvent.setup();
  renderTrades("/trades?strategy_group_id=SOR-001&position_side=long");
  await user.click(await screen.findByRole("link", { name: /BNBUSDT LONG/ }));

  const location = screen.getByRole("status", { name: "current location" });
  expect(location).toHaveTextContent("/trades/ticket%3A1");
  expect(location).toHaveTextContent("return=");
});

it("opens one compact ticket summary inline", async () => {
  const user = userEvent.setup();
  renderTrades("/trades");

  await user.click(await screen.findByRole("button", { name: "展开 BNBUSDT LONG 概要" }));

  expect(screen.getByText("ticket:1")).toBeInTheDocument();
  expect(screen.getByText("4/8")).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("keeps summary totals exact from API decimal strings", async () => {
  mockedGetTrades.mockResolvedValue({
    ...tradeEnvelope,
    data: {
      ...tradeEnvelope.data,
      items: [
        { ...activeTicket, fees: metric("0.10000000000000001", "USDT") },
        { ...terminalTicket, fees: metric("0.20000000000000002", "USDT") },
      ],
    },
  });
  renderTrades("/trades");

  const summary = await screen.findByRole("region", { name: "交易摘要" });
  expect(within(summary).getByText("0.30000000000000003 USDT")).toBeInTheDocument();
});
