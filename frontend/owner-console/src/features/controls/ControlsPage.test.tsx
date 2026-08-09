import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
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
  strategies: [
    { strategy_group_id: "SOR-001", entry_state: "enabled" as const, control_version: 1, last_event_id: "event:1", reason: "seed_enabled", updated_at_ms: 1_800_000_000_000, configured_state: "enabled" as const, effective_state: "enabled" as const },
  ],
  current_operation: null,
  events: [],
};

beforeEach(() => {
  ownerQueryClient.clear();
  vi.mocked(getControls).mockResolvedValue(controlsFixture);
  vi.mocked(getFlattenPreview).mockResolvedValue({
    runtime_profile_id: "tiny-live-v1",
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
