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
