import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { candleFixture, strategyFixture, strategyObservationFixture, strategyTicketFixture } from "../../api/fixtures";
import { ownerQueryClient } from "../../app/queryClient";
import { getCandles } from "../trades/api";
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

const mockedGetStrategies = vi.mocked(getStrategies);
const mockedGetStrategyObservations = vi.mocked(getStrategyObservations);
const mockedGetStrategyTickets = vi.mocked(getStrategyTickets);
const mockedGetCandles = vi.mocked(getCandles);

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
  mockedGetStrategies.mockResolvedValue(strategyFixture);
  mockedGetStrategyObservations.mockResolvedValue(strategyObservationFixture);
  mockedGetStrategyTickets.mockResolvedValue(strategyTicketFixture);
  mockedGetCandles.mockResolvedValue(candleFixture);
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
