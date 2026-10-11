import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { ownerQueryClient } from "../../app/queryClient";
import { ApiError } from "../../api/errors";
import { SelectionControlPanel } from "./SelectionControlPanel";
import { getSelectionPreview, submitSelectionIntent } from "./api";
import { selectionFixture } from "./selectionFixtures";

vi.mock("./api", () => ({ getSelectionPreview: vi.fn(), submitSelectionIntent: vi.fn() }));
beforeEach(() => {
  ownerQueryClient.clear(); vi.clearAllMocks();
  vi.mocked(getSelectionPreview).mockResolvedValue(selectionFixture);
  vi.mocked(submitSelectionIntent).mockResolvedValue();
});
it("uses server-owned period and version, never hand-entered authority", async () => {
  const user = userEvent.setup();
  render(<QueryClientProvider client={ownerQueryClient}><SelectionControlPanel strategyGroupId="CPM-RO-001" /></QueryClientProvider>);
  await user.click(await screen.findByRole("button", { name: "启用 CPM-RO-001 Dynamic" }));
  await user.type(screen.getByLabelText("操作原因"), "live experiment");
  await user.type(screen.getByLabelText("验证码"), "123456");
  await user.click(screen.getByRole("button", { name: "确认提交" }));
  await waitFor(() => expect(submitSelectionIntent).toHaveBeenCalledOnce());
  expect(submitSelectionIntent).toHaveBeenCalledWith("CPM-RO-001", "dynamic", expect.objectContaining({
    expected_version: 7, effective_period_anchor_ms: 360000000, reason: "live experiment", totp_code: "123456",
  }));
  expect(screen.queryByLabelText(/version|idempotency|epoch/i)).not.toBeInTheDocument();
});

it("retains the intent key after invalid TOTP and never logs out", async () => {
  const user = userEvent.setup(); const expired = vi.fn();
  window.addEventListener("owner-console:session-expired", expired);
  vi.mocked(submitSelectionIntent).mockRejectedValueOnce(new ApiError(403, "step_up_invalid", "invalid proof"));
  render(<QueryClientProvider client={ownerQueryClient}><SelectionControlPanel strategyGroupId="CPM-RO-001" /></QueryClientProvider>);
  await user.click(await screen.findByRole("button", { name: "启用 CPM-RO-001 Dynamic" }));
  await user.type(screen.getByLabelText("操作原因"), "test"); await user.type(screen.getByLabelText("验证码"), "123456");
  await user.click(screen.getByRole("button", { name: "确认提交" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("登录会话保持");
  expect(screen.getByLabelText("操作原因")).toBeDisabled();
  await user.type(screen.getByLabelText("验证码"), "654321"); await user.click(screen.getByRole("button", { name: "确认提交" }));
  await waitFor(() => expect(submitSelectionIntent).toHaveBeenCalledTimes(2));
  expect(vi.mocked(submitSelectionIntent).mock.calls[0]![2].idempotency_key).toBe(vi.mocked(submitSelectionIntent).mock.calls[1]![2].idempotency_key);
  expect(expired).not.toHaveBeenCalled(); window.removeEventListener("owner-console:session-expired", expired);
});

it("refreshes a 409 but never resubmits with the new version", async () => {
  const user = userEvent.setup();
  vi.mocked(submitSelectionIntent).mockRejectedValue(new ApiError(409, "control_conflict", "version changed"));
  render(<QueryClientProvider client={ownerQueryClient}><SelectionControlPanel strategyGroupId="CPM-RO-001" /></QueryClientProvider>);
  await user.click(await screen.findByRole("button", { name: "启用 CPM-RO-001 Dynamic" }));
  await user.type(screen.getByLabelText("操作原因"), "test"); await user.type(screen.getByLabelText("验证码"), "123456");
  await user.click(screen.getByRole("button", { name: "确认提交" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("不会自动重提权限");
  expect(screen.getByRole("button", { name: "确认提交" })).toBeDisabled();
  expect(getSelectionPreview).toHaveBeenCalledTimes(3); expect(submitSelectionIntent).toHaveBeenCalledOnce();
});

it("does not present an uninstalled Spec as a certified Static Selector", async () => {
  vi.mocked(getSelectionPreview).mockResolvedValue({ ...selectionFixture, control: null,
    runtime: { ...selectionFixture.runtime, installed: false, first_blocker: "SPEC_NOT_INSTALLED" } });
  render(<QueryClientProvider client={ownerQueryClient}><SelectionControlPanel strategyGroupId="CPM-RO-001" /></QueryClientProvider>);
  expect(await screen.findByText("NOT_INSTALLED")).toBeInTheDocument();
  expect(screen.queryByText("STATIC")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "启用 CPM-RO-001 Dynamic" })).toBeDisabled();
});

it("submits a frozen Static baseline and epoch without editing them", async () => {
  const user = userEvent.setup();
  vi.mocked(getSelectionPreview).mockResolvedValue({ ...selectionFixture,
    control: { ...selectionFixture.control!, selection_mode: "dynamic_selection", selection_epoch_id: "epoch:current" },
    runtime: { ...selectionFixture.runtime, selection_mode: "dynamic_selection", first_blocker: "SELECTION_STALE_PAUSED" } });
  render(<QueryClientProvider client={ownerQueryClient}><SelectionControlPanel strategyGroupId="CPM-RO-001" /></QueryClientProvider>);
  expect(await screen.findByText("DYNAMIC")).toHaveAttribute("data-tone", "attention");
  expect(screen.getByText(/当前阻断：SELECTION_STALE_PAUSED/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "回退 CPM-RO-001 Static" }));
  await user.type(screen.getByLabelText("操作原因"), "restore baseline"); await user.type(screen.getByLabelText("验证码"), "123456");
  await user.click(screen.getByRole("button", { name: "确认提交" }));
  await waitFor(() => expect(submitSelectionIntent).toHaveBeenCalledOnce());
  expect(submitSelectionIntent).toHaveBeenCalledWith("CPM-RO-001", "static", expect.objectContaining({ rollback_baseline_id: "baseline", selection_epoch_id: "epoch:current" }));
});

it("refuses cached authority after a failed fresh preview", async () => {
  const user = userEvent.setup();
  render(<QueryClientProvider client={ownerQueryClient}><SelectionControlPanel strategyGroupId="CPM-RO-001" /></QueryClientProvider>);
  const activate = await screen.findByRole("button", { name: "启用 CPM-RO-001 Dynamic" });
  vi.mocked(getSelectionPreview).mockRejectedValue(new ApiError(503, "unavailable", "preview unavailable"));
  await user.click(activate);
  expect(await screen.findByRole("alert")).toHaveTextContent("权限提交已禁用");
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(activate).toBeDisabled();
  expect(submitSelectionIntent).not.toHaveBeenCalled();
});

it("uses the freshly read server version and anchor, not the cached preview", async () => {
  const user = userEvent.setup();
  render(<QueryClientProvider client={ownerQueryClient}><SelectionControlPanel strategyGroupId="CPM-RO-001" /></QueryClientProvider>);
  const activate = await screen.findByRole("button", { name: "启用 CPM-RO-001 Dynamic" });
  vi.mocked(getSelectionPreview).mockResolvedValue({ ...selectionFixture, next_effective_period_anchor_ms: 400000000,
    control: { ...selectionFixture.control!, control_version: 9 } });
  await user.click(activate);
  await user.type(await screen.findByLabelText("操作原因"), "fresh preview");
  await user.type(screen.getByLabelText("验证码"), "123456");
  await user.click(screen.getByRole("button", { name: "确认提交" }));
  await waitFor(() => expect(submitSelectionIntent).toHaveBeenCalledOnce());
  expect(submitSelectionIntent).toHaveBeenCalledWith("CPM-RO-001", "dynamic", expect.objectContaining({
    expected_version: 9, effective_period_anchor_ms: 400000000,
  }));
});

it("keeps Desired EMPTY separate from actual authority and shows deadlines", async () => {
  vi.mocked(getSelectionPreview).mockResolvedValue({ ...selectionFixture,
    runtime: { ...selectionFixture.runtime, latest_ready_count: 0, latest_selected_count: 0, valid_empty_reason: "ZERO_QUALIFIED_MEMBERS",
      materialization_state: "DRAINING_ENTRY", materialization_deadline_ms: 378000000,
      membership_valid_until_ms: 381600000, consecutive_missed_periods: 1, current_authority_outcome: "PRE_FENCE_CONTINUITY" } });
  render(<QueryClientProvider client={ownerQueryClient}><SelectionControlPanel strategyGroupId="CPM-RO-001" /></QueryClientProvider>);
  expect(await screen.findByText(/最新 Desired 为 EMPTY/)).toHaveTextContent("实际 new Entry 权限以当前 Authority 为准");
  expect(screen.getByText(/Materialization：DRAINING_ENTRY/)).toHaveTextContent("1970-01-05T09:00:00 UTC");
  expect(screen.getByText(/membership stale deadline/)).toHaveTextContent("missed periods 1");
  expect(screen.getByText(/实际 Authority：PRE_FENCE_CONTINUITY/)).toBeInTheDocument();
});

it("allows a new Static authorization only after its pending generation has failed", async () => {
  const user = userEvent.setup();
  vi.mocked(getSelectionPreview).mockResolvedValue({ ...selectionFixture,
    control: { ...selectionFixture.control!, selection_mode: "dynamic_selection", selection_epoch_id: "epoch:current",
      pending_selection_mode: "static_baseline", pending_authorization_id: "authorization:failed", pending_effective_period_anchor_ms: 350000000 },
    runtime: { ...selectionFixture.runtime, materialization_state: "FAILED_CLOSED" } });
  render(<QueryClientProvider client={ownerQueryClient}><SelectionControlPanel strategyGroupId="CPM-RO-001" /></QueryClientProvider>);
  await user.click(await screen.findByRole("button", { name: "重新授权 CPM-RO-001 Static" }));
  await user.type(await screen.findByLabelText("操作原因"), "recover failed restoration");
  await user.type(screen.getByLabelText("验证码"), "123456");
  await user.click(screen.getByRole("button", { name: "确认提交" }));
  await waitFor(() => expect(submitSelectionIntent).toHaveBeenCalledOnce());
  expect(submitSelectionIntent).toHaveBeenCalledWith("CPM-RO-001", "static", expect.objectContaining({
    selection_epoch_id: "epoch:current", rollback_baseline_id: "baseline", effective_period_anchor_ms: 360000000,
  }));
});
