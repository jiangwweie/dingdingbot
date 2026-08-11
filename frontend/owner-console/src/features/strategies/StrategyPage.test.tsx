import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { strategyFixture, strategyTicketFixture } from "../../api/fixtures";
import { ownerQueryClient } from "../../app/queryClient";
import { StrategyPage } from "./StrategyPage";
import { getStrategies, getStrategyTickets } from "./api";

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return { ...actual, getStrategies: vi.fn(), getStrategyTickets: vi.fn() };
});

const mockedGetStrategies = vi.mocked(getStrategies);
const mockedGetStrategyTickets = vi.mocked(getStrategyTickets);

function renderStrategies() {
  return render(
    <QueryClientProvider client={ownerQueryClient}>
      <MemoryRouter initialEntries={["/strategies?view=current"]}><StrategyPage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  ownerQueryClient.clear();
  mockedGetStrategies.mockReset();
  mockedGetStrategyTickets.mockReset();
  mockedGetStrategies.mockResolvedValue(strategyFixture);
  mockedGetStrategyTickets.mockResolvedValue(strategyTicketFixture);
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
