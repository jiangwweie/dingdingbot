import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { ownerQueryClient } from "../../app/queryClient";
import { ReviewPage } from "./ReviewPage";
import { getReviewCenter } from "./api";

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return { ...actual, getReviewCenter: vi.fn() };
});

const evidence = (kind: "ticket" | "event" | "review", identity: string) => ({
  kind,
  identity,
  occurred_at_ms: 1_807_408_800_000,
});

const money = (value: string | null, unit: "USDT" | "R", unavailableReason: string | null = null) => ({
  value,
  unit,
  unavailable_reason: unavailableReason,
});

const reviewEnvelope = {
  snapshot_id: "snapshot:review:1",
  generated_at: "2026-08-09T08:00:00.000Z",
  source_watermark: "2026-08-09T08:00:00.000Z",
  freshness: "fresh" as const,
  data: {
    from_ms: 1_804_816_000_000,
    to_ms: 1_807_408_800_000,
    sample_count: 1,
    next_cursor: null,
    items: [{
      ticket_id: "ticket:1",
      strategy_group_id: "SOR-LONG",
      exchange_instrument_id: "BNBUSDT",
      position_side: "long" as const,
      terminal_at_ms: 1_807_408_800_000,
      review: {
        ticket_id: "ticket:1",
        review_status: "complete" as const,
        execution_classification: "complete" as const,
        economic_summary: {
          gross_pnl: money("3.80", "USDT"),
          fees: money("-0.25", "USDT"),
          funding: money("-0.04", "USDT"),
          net_pnl: money("3.5100", "USDT"),
          net_r: money("0.4800", "R"),
        },
        exit_reason: "TP1 + Runner Exit",
        attention_items: [],
        sentences: [{
          template_id: "execution_complete" as const,
          text: "执行链完整。ENTRY 后初始保护已确认；退出由 TP1 后 Runner EXIT 触发。",
          evidence: [evidence("event", "event:entry"), evidence("review", "review:ticket:1")],
        }],
        final_conclusion: "执行链完整。",
        evidence: [evidence("ticket", "ticket:1"), evidence("review", "review:ticket:1")],
      },
    }],
    net_pnl: money("3.5100", "USDT"),
    net_r: money("0.4800", "R"),
    fees: money("-0.25", "USDT"),
    funding: money("-0.04", "USDT"),
    exit_reason_breakdown: [{ label: "TP1 + Runner Exit", ticket_count: 1, evidence: [evidence("review", "review:ticket:1")] }],
    execution_quality_breakdown: [{ label: "complete", ticket_count: 1, evidence: [evidence("review", "review:ticket:1")] }],
    complete_review_count: 1,
    incomplete_review_count: 0,
    strategy_group_samples: [{ strategy_group_id: "SOR-LONG", sample_count: 1, evidence_state: "observe_only" as const, evidence: [evidence("review", "review:ticket:1")] }],
    evidence: [evidence("review", "review:ticket:1")],
  },
};

const mockedGetReviewCenter = vi.mocked(getReviewCenter);

function renderReview() {
  return render(
    <QueryClientProvider client={ownerQueryClient}>
      <MemoryRouter initialEntries={["/review"]}><ReviewPage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  ownerQueryClient.clear();
  mockedGetReviewCenter.mockReset();
  mockedGetReviewCenter.mockResolvedValue(reviewEnvelope);
});

it("renders deterministic review sentences and evidence links", async () => {
  const user = userEvent.setup();
  renderReview();

  expect(await screen.findAllByText("+3.51 U")).not.toHaveLength(0);
  await user.click(screen.getByRole("button", { name: "展开 BNBUSDT LONG 复盘" }));

  expect(screen.getByText(/执行链完整/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "review:ticket:1" })).toBeInTheDocument();
});

it("does not render a full-width insufficient-sample warning", async () => {
  renderReview();

  expect(await screen.findByText("Observe Only")).toBeInTheDocument();
  expect(screen.queryByText("样本不足 · 当前仅支持观察性结论")).not.toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
