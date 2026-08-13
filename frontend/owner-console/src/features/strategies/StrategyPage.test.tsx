import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { candleFixture, instrumentFixture, strategyFixture, strategyObservationFixture, strategyTicketFixture } from "../../api/fixtures";
import { ownerQueryClient } from "../../app/queryClient";
import { getCandles } from "../trades/api";
import { getControls } from "../controls/api";
import { getInstruments } from "../instruments/api";
import { StrategyPage } from "./StrategyPage";
import { getStrategies, getStrategyObservations, getStrategyTickets } from "./api";

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return { ...actual, getStrategies: vi.fn(), getStrategyObservations: vi.fn(), getStrategyTickets: vi.fn() };
});

vi.mock("../trades/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../trades/api")>();
  return { ...actual, getCandles: vi.fn() };
});

vi.mock("../controls/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../controls/api")>();
  return { ...actual, getControls: vi.fn(), setStrategyControl: vi.fn() };
});

vi.mock("../instruments/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../instruments/api")>();
  return { ...actual, getInstruments: vi.fn() };
});

vi.mock("../../components/charts/CausalityChart", () => ({
  default: () => <div data-testid="causality-chart" />,
}));

const mockedGetStrategies = vi.mocked(getStrategies);
const mockedGetStrategyObservations = vi.mocked(getStrategyObservations);
const mockedGetStrategyTickets = vi.mocked(getStrategyTickets);
const mockedGetCandles = vi.mocked(getCandles);
const mockedGetControls = vi.mocked(getControls);
const mockedGetInstruments = vi.mocked(getInstruments);

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{`${location.pathname}${location.search}`}</output>;
}

function renderStrategies() {
  return render(
    <QueryClientProvider client={ownerQueryClient}>
      <MemoryRouter initialEntries={["/strategies?view=current"]}><StrategyPage /><LocationProbe /></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  ownerQueryClient.clear();
  mockedGetStrategies.mockReset();
  mockedGetStrategyObservations.mockReset();
  mockedGetStrategyTickets.mockReset();
  mockedGetCandles.mockReset();
  mockedGetControls.mockReset();
  mockedGetInstruments.mockReset();
  mockedGetStrategies.mockResolvedValue(strategyFixture);
  mockedGetStrategyObservations.mockResolvedValue(strategyObservationFixture);
  mockedGetStrategyTickets.mockResolvedValue(strategyTicketFixture);
  mockedGetCandles.mockResolvedValue(candleFixture);
  mockedGetControls.mockResolvedValue({
    generated_at_ms: 1_800_000_000_000,
    global_entry: { configured_state: "enabled", effective_state: "enabled", policy_version: 10, active_ticket_count: 1, first_blocker: null },
    account_capacity: { max_concurrent_tickets: 3, active_ticket_count: 1, remaining_ticket_slots: 2, gross_stop_risk: "4.20", gross_stop_risk_limit: "25.80", max_gross_stop_risk_fraction: "0.06", long_stop_risk: "4.20", short_stop_risk: "0", directional_stop_risk_limit: "17.20", directional_stop_risk_limit_fraction: "0.04", reserved_margin: "21.00", gross_initial_margin_limit: "387.00", max_gross_initial_margin_utilization: "0.90", wallet_balance_basis: "430.00", margin_balance_basis: "430.00", family_active_counts: { long_continuation: 0, opening_range: 1, rally_failure_short: 0 }, family_limits: { long_continuation: 1, opening_range: 2, rally_failure_short: 1 }, source: "current_projection" },
    runtime_entry_authority: { exchange_commands_enabled: true, effective_status: "ready", runtime_profile_ids: ["tiny-live-v1", "tradfi-equity-usdm-v1"], first_blocker: null },
    strategies: [{ strategy_group_id: "SOR-US-EQ-PERP-001", entry_state: "enabled", control_version: 1, last_event_id: "event:control:1", reason: "seed_enabled", updated_at_ms: 1_800_000_000_000, configured_state: "enabled", effective_state: "enabled" }],
    current_operation: null,
    recent_operations: [],
    events: [],
  });
  mockedGetInstruments.mockResolvedValue(instrumentFixture);
});

it("shows one compact live control with shared Policy capacity and product readiness", async () => {
  renderStrategies();

  expect(await screen.findByText("SOR US Equity · Live Control")).toBeInTheDocument();
  expect(screen.getByText("LIVE ENABLED")).toBeInTheDocument();
  expect(screen.getByText("2 / 3")).toBeInTheDocument();
  expect(screen.getByText("4.20 / 25.80U")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "暂停策略" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "标的中心" })).toHaveAttribute("href", "/instruments");
});

it("opens a URL-backed TradFi Observation review with frozen price levels", async () => {
  const user = userEvent.setup();
  renderStrategies();

  expect(await screen.findByText("SOR US Equity Perpetual · v1")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "TP1 2" }));

  expect(await screen.findByRole("dialog", { name: /SOR US Equity Perpetual v1 · Observation/ })).toBeInTheDocument();
  expect(mockedGetStrategyObservations).toHaveBeenCalledWith(expect.objectContaining({
    strategy_version_id: "sgv:SOR-US-EQ-PERP-001:v1",
    first_path: "tp1_first",
  }));
  expect(mockedGetCandles).toHaveBeenCalledWith(expect.objectContaining({
    exchangeInstrumentId: "binance-usdm:AAPLUSDT:perpetual",
    timeframe: "15m",
  }));
  expect(screen.getByText("Observation only")).toBeInTheDocument();
  expect(screen.getByText("210.12", { exact: true })).toBeInTheDocument();
  expect(screen.getByText("207.84", { exact: true })).toBeInTheDocument();
  expect(screen.getByText("212.40", { exact: true })).toBeInTheDocument();
  expect(screen.getByText("209.60", { exact: true })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "全屏" })).toBeEnabled();
  expect(screen.getByTestId("location")).toHaveTextContent("observation_modal=1");
  expect(screen.getByTestId("location")).toHaveTextContent("observation_path=tp1_first");

  await user.click(screen.getByRole("button", { name: /AAPLUSDT.*LONG/ }));
  expect(screen.getByTestId("location")).toHaveTextContent("observation_id=shadow%3Astrategy%3Asor-us%3A1");
});

it("opens a URL-backed TP1 Ticket dialog and preserves strategy detail context", async () => {
  const user = userEvent.setup();
  renderStrategies();

  expect(await screen.findByText("BRF2 · v3")).toBeInTheDocument();
  expect(screen.getByText(/binance-usdm · Crypto Perp · Continuous · 1h close/)).toBeInTheDocument();
  expect(screen.getByText(/binance-usdm · Equity Perp · REGULAR \+30m–\+150m/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "TP1 1" }));

  expect(await screen.findByRole("dialog", { name: /BRF2 v3 · 已达 TP1/ })).toBeInTheDocument();
  expect(mockedGetStrategyTickets).toHaveBeenCalledWith(expect.objectContaining({
    strategy_version_id: "strategy-version:brf2:v3",
    scope: "natural",
    exit_path: "tp1_reached",
  }));
  expect(screen.getByRole("link", { name: /BTCUSDT SHORT/ })).toHaveAttribute(
    "href",
    expect.stringContaining("origin=strategy"),
  );
});
