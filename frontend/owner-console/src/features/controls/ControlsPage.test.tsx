import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { ownerQueryClient } from "../../app/queryClient";
import { ControlsPage } from "./ControlsPage";
import { getControls, getFlattenPreview } from "./api";

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return {
    ...actual,
    getControls: vi.fn(),
    getFlattenPreview: vi.fn(),
    setGlobalEntry: vi.fn(),
    setStrategyControl: vi.fn(),
    submitFlatten: vi.fn(),
  };
});

const controlsFixture = {
  generated_at_ms: 1_800_000_000_000,
  global_entry: { configured_state: "enabled" as const, effective_state: "enabled" as const, policy_version: 5, active_ticket_count: 2, first_blocker: null },
  account_capacity: { max_concurrent_tickets: 3, active_ticket_count: 2, remaining_ticket_slots: 1, gross_stop_risk: "8.40", gross_stop_risk_limit: "25.80", max_gross_stop_risk_fraction: "0.06", long_stop_risk: "3.20", short_stop_risk: "5.20", directional_stop_risk_limit: "17.20", directional_stop_risk_limit_fraction: "0.04", reserved_margin: "42.00", gross_initial_margin_limit: "387.00", max_gross_initial_margin_utilization: "0.90", wallet_balance_basis: "430.00", margin_balance_basis: "430.00", family_active_counts: { long_continuation: 0, opening_range: 2, rally_failure_short: 0 }, family_limits: { long_continuation: 1, opening_range: 2, rally_failure_short: 1 }, source: "current_projection" as const },
  runtime_entry_authority: { exchange_commands_enabled: true, effective_status: "ready" as const, runtime_profile_ids: ["tiny-live-v1", "tradfi-equity-usdm-v1"], first_blocker: null },
  strategies: [
    { strategy_group_id: "SOR-001", entry_state: "enabled" as const, control_version: 1, last_event_id: "event:1", reason: "seed_enabled", updated_at_ms: 1_800_000_000_000, configured_state: "enabled" as const, effective_state: "enabled" as const },
  ],
  current_operation: null,
  recent_operations: [],
  events: [],
};

beforeEach(() => {
  ownerQueryClient.clear();
  vi.mocked(getControls).mockResolvedValue(controlsFixture);
  vi.mocked(getFlattenPreview).mockResolvedValue({
    runtime_profile_id: "account-wide",
    venue_id: "binance-usdm",
    account_id: "owner-account",
    owner_policy_version: 5,
    global_entry_enabled: true,
    ticket_ids: ["ticket:ada-short", "ticket:btc-long"],
    ticket_states: { "ticket:ada-short": "eligible", "ticket:btc-long": "eligible" },
    snapshot_digest: `sha256:${"a".repeat(64)}`,
    first_blocker: null,
  });
});

it("shows compact controls and keeps flatten scope server-owned", async () => {
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={ownerQueryClient}>
      <MemoryRouter initialEntries={["/controls"]}>
        <ControlsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByText("SOR-001")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "暂停新开仓" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "受控平仓全部仓位" }));

  expect(await screen.findByText(/ticket:ada-short/)).toBeInTheDocument();
  expect(screen.getByText(/ticket:btc-long/)).toBeInTheDocument();
  expect(screen.queryByLabelText(/数量|价格|订单类型/)).not.toBeInTheDocument();
  expect(vi.mocked(getFlattenPreview)).toHaveBeenCalledTimes(1);
});

it("shows one readable control operation instead of individual state-machine events", async () => {
  vi.mocked(getControls).mockResolvedValue({
    ...controlsFixture,
    recent_operations: [{
      authorization_id: "owner-authorization:technical-id",
      operation_kind: "flatten_all" as const,
      state: "completed",
      version: 7,
      runtime_profile_id: "account-wide",
      venue_id: "binance-usdm",
      account_id: "owner-account",
      target_ticket_ids: ["ticket:1"],
      snapshot_digest: `sha256:${"a".repeat(64)}`,
      first_blocker: "ticket_incident:cancel_order_outcome_unknown",
      claimed_by: null,
      lease_until_ms: null,
      created_at_ms: 1_800_000_000_000,
      updated_at_ms: 1_800_000_060_000,
    }],
  });
  render(<QueryClientProvider client={ownerQueryClient}><MemoryRouter initialEntries={["/controls"]}><ControlsPage /></MemoryRouter></QueryClientProvider>);

  const history = (await screen.findByText("控制操作历史")).closest("section");
  expect(history).not.toBeNull();
  expect(within(history!).getByText("受控平仓全部仓位")).toBeInTheDocument();
  expect(within(history!).getByText("曾需关注，现已完成")).toBeInTheDocument();
  expect(within(history!).getByText(/1 个 Ticket/)).toBeInTheDocument();
  expect(screen.queryByText("owner-authorization:technical-id")).not.toBeInTheDocument();
});
