import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ownerQueryClient } from "../../app/queryClient";
import { SignalPage } from "./SignalPage";
import { getSignalDetail, getSignals } from "./api";

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return { ...actual, getSignalDetail: vi.fn(), getSignals: vi.fn() };
});

const rejectedSignal = {
  signal_event_id: "signal:SOR-LONG:1",
  exposure_episode_id: "episode:1",
  strategy_group_id: "SOR-LONG",
  strategy_version_id: "sor-v1",
  event_spec_id: "event:SOR",
  exchange_instrument_id: "BINANCE:BTCUSDT",
  position_side: "long" as const,
  occurred_at_ms: 1_807_408_800_000,
  expires_at_ms: 1_807_412_400_000,
  admission_decision_id: "decision:1",
  decision_status: "rejected" as const,
  first_blocker: "gross_stop_risk_capacity_exhausted",
  binding_constraint: "gross_stop_risk_capacity_exhausted",
  ticket_id: null,
  shadow_summary: {
    shadow_outcome_id: "shadow:1",
    source_kind: "portfolio_rejection" as const,
    evaluation_kind: "fixed_horizon_excursion_v1" as const,
    status: "completed" as const,
    mfe_r: "1.25",
    mae_r: "-0.40",
    first_path: null,
    first_path_at_ms: null,
    observed_bar_count: null,
    spread_bps: null,
    mark_index_deviation_bps: null,
    completion_reason: "horizon_complete",
    observed_through_ms: 1_807_495_200_000,
    completed_at_ms: 1_807_495_200_000,
    interpretation: "Observation only; this Shadow Outcome is not execution." as const,
    evidence: [],
  },
  evidence: [],
};

const admittedSignal = {
  ...rejectedSignal,
  signal_event_id: "signal:admitted:1",
  admission_decision_id: "decision:2",
  decision_status: "admitted" as const,
  first_blocker: null,
  binding_constraint: null,
  ticket_id: "ticket:1",
  shadow_summary: null,
};

const signalEnvelope = {
  snapshot_id: "snapshot:signals:1",
  generated_at: "2026-08-09T02:00:00.000Z",
  source_watermark: "2026-08-09T02:00:00.000Z",
  freshness: "fresh" as const,
  data: { items: [rejectedSignal, admittedSignal], next_cursor: null },
};

const detailEnvelope = {
  snapshot_id: "snapshot:signal:1",
  generated_at: "2026-08-09T02:00:00.000Z",
  source_watermark: "2026-08-09T02:00:00.000Z",
  freshness: "fresh" as const,
  data: {
    signal: rejectedSignal,
    what_happened: "The persisted AdmissionDecision rejected this Signal; no Ticket was created.",
    why_no_ticket: "gross_stop_risk_capacity_exhausted",
    fact_snapshots: [],
    shadow_summary: rejectedSignal.shadow_summary,
    evidence: [],
  },
};

const mockedGetSignals = vi.mocked(getSignals);
const mockedGetSignalDetail = vi.mocked(getSignalDetail);

function renderSignals(initialEntry: string) {
  return render(
    <QueryClientProvider client={ownerQueryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <SignalPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  ownerQueryClient.clear();
  mockedGetSignals.mockReset();
  mockedGetSignalDetail.mockReset();
  mockedGetSignals.mockImplementation(async (filters) => ({
    ...signalEnvelope,
    data: {
      ...signalEnvelope.data,
      items: filters.decision_status === "rejected" ? [rejectedSignal] : signalEnvelope.data.items,
    },
  }));
  mockedGetSignalDetail.mockResolvedValue(detailEnvelope);
});

afterEach(() => {
  ownerQueryClient.clear();
});

it("opens rejected signal detail inline and does not render a right drawer", async () => {
  const user = userEvent.setup();
  renderSignals("/signals?decision_status=rejected");
  await user.click(await screen.findByRole("button", { name: /展开 SOR-LONG/ }));

  expect(await screen.findByText("gross_stop_risk_capacity_exhausted")).toBeInTheDocument();
  expect(screen.getByText("Shadow Outcome")).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(mockedGetSignals).toHaveBeenLastCalledWith({ decision_status: "rejected" });
});

it("links admitted signal to its exact ticket", async () => {
  renderSignals("/signals");
  const link = await screen.findByRole("link", { name: "查看交易" });
  expect(link).toHaveAttribute("href", "/trades/ticket%3A1");
});

it("uses cached rejected detail when the inline row is reopened", async () => {
  const user = userEvent.setup();
  renderSignals("/signals?decision_status=rejected");
  const toggle = await screen.findByRole("button", { name: /展开 SOR-LONG/ });

  await user.click(toggle);
  await screen.findByText("Shadow Outcome");
  await user.click(screen.getByRole("button", { name: /收起 SOR-LONG/ }));
  await user.click(screen.getByRole("button", { name: /展开 SOR-LONG/ }));

  await screen.findByText("Shadow Outcome");
  expect(mockedGetSignalDetail).toHaveBeenCalledTimes(1);
});
