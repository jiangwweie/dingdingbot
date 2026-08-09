import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ownerQueryClient } from "../../app/queryClient";
import { OverviewPage } from "./OverviewPage";
import { getOverview } from "./api";

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return { ...actual, getOverview: vi.fn() };
});

const overviewFixture = {
  snapshot_id: "snapshot:overview:1",
  generated_at: "2026-08-09T02:00:00.000Z",
  source_watermark: "2026-08-09T02:00:00.000Z",
  freshness: "fresh" as const,
  data: {
    observed_at_ms: 1_807_408_800_000,
    conclusion: {
      level: "intervention" as const,
      summary: "保护事实需要 Owner 确认",
      owner_action: "检查 ticket:1 的保护订单",
      evidence: [],
    },
    account_snapshot: {
      label: "Latest Admission Snapshot" as const,
      is_realtime: false as const,
      captured_at_ms: 1_807_408_700_000,
      wallet_balance: { value: "100.00", unit: "USDT" as const },
      available_margin: { value: "70.00", unit: "USDT" as const },
    },
    ticket_capacity: 3,
    active_ticket_count: 1,
    active_ticket_ids: ["ticket:1"],
    today_net_pnl: { value: "3.5100", unit: "USDT" as const },
    today_net_r: { value: "0.4800", unit: "R" as const },
    today_signal_count: 4,
    admitted_signal_count: 1,
    rejected_signal_count: 3,
    execution_incident_count: 0,
    attention_summary: ["一笔 Ticket 等待复盘"],
    evidence: [],
  },
};

const mockedGetOverview = vi.mocked(getOverview);

function renderOverview() {
  return render(
    <QueryClientProvider client={ownerQueryClient}>
      <MemoryRouter initialEntries={["/overview"]}>
        <OverviewPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  ownerQueryClient.clear();
  mockedGetOverview.mockReset();
  mockedGetOverview.mockResolvedValue(overviewFixture);
});

afterEach(() => {
  ownerQueryClient.clear();
  vi.useRealTimers();
});

it("renders intervention first and labels account values as admission snapshot", async () => {
  renderOverview();

  expect((await screen.findAllByText("需要介入"))[0]).toBeInTheDocument();
  expect(screen.getByText("Latest Admission Snapshot")).toBeInTheDocument();
  expect(screen.queryByText("实时余额")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "刷新当前页" })).toBeInTheDocument();
});

it("updates visible data age without issuing another request", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(new Date("2026-08-09T02:00:30.000Z"));
  renderOverview();
  await screen.findAllByText("需要介入");
  expect(screen.getByText("数据 刚刚")).toBeInTheDocument();

  await act(async () => vi.advanceTimersByTimeAsync(60_000));

  expect(screen.getByText("数据 1 分钟前")).toBeInTheDocument();
  expect(mockedGetOverview).toHaveBeenCalledTimes(1);
});

it("keeps the last overview visible after a failed manual refresh", async () => {
  const user = userEvent.setup();
  mockedGetOverview
    .mockResolvedValueOnce(overviewFixture)
    .mockRejectedValueOnce(new Error("offline"));
  renderOverview();

  expect(await screen.findByText("保护事实需要 Owner 确认")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "刷新当前页" }));

  expect(await screen.findByText(/刷新失败/)).toBeInTheDocument();
  expect(screen.getByText("保护事实需要 Owner 确认")).toBeInTheDocument();
});
