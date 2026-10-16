import * as AlertDialog from "@radix-ui/react-alert-dialog";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { AppShell } from "../../app/AppShell";
import { ownerQueryClient } from "../../app/queryClient";
import { Button } from "../../components/ui/Button";
import { DataAge } from "../../components/ui/DataAge";
import { ManualRefreshButton } from "../../components/ui/ManualRefreshButton";
import { PageHeader } from "../../components/ui/PageHeader";
import { Panel } from "../../components/ui/Panel";
import { StatusTag } from "../../components/ui/StatusTag";
import { UnavailablePanel } from "../../components/ui/UnavailablePanel";
import { formatOwnerReason, formatOwnerStatus } from "../../components/ui/presentation";
import {
  getControls,
  getFlattenPreview,
  setGlobalEntry,
  setStrategyControl,
  submitFlatten,
  type ControlWriteBody,
  type FlattenPreview,
  type OwnerControlOperation,
} from "./api";
import { controlsQueryKey } from "./api";
import { SelectionControlPanel } from "./SelectionControlPanel";
import { OrbSelectionControlPanel } from "./OrbSelectionControlPanel";

type PendingAction =
  | { kind: "global"; action: "pause" | "resume"; version: number }
  | { kind: "strategy"; action: "pause" | "resume"; strategyGroupId: string; version: number };

function requestId(prefix: string): string {
  return `${prefix}:${globalThis.crypto?.randomUUID?.() ?? Date.now().toString(36)}`;
}

function formatTime(value: number | null | undefined): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function operationName(_operation: OwnerControlOperation): string {
  return "受控平仓全部仓位";
}

function operationResult(operation: OwnerControlOperation): string {
  if (operation.state === "completed") {
    return operation.first_blocker ? "曾需关注，现已完成" : "已完成";
  }
  if (operation.state === "blocked") return "已阻断";
  return formatOwnerStatus(operation.state);
}

function operationTone(operation: OwnerControlOperation): "success" | "attention" | "danger" {
  if (operation.state === "completed" && !operation.first_blocker) return "success";
  if (operation.state === "blocked" || operation.state === "needs_intervention") return "danger";
  return "attention";
}

const SELECTION_GROUPS = ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"] as const;
type SelectionTabKey = (typeof SELECTION_GROUPS)[number] | "SOR-1H" | "all";

export function ControlsPage() {
  const controls = useQuery({ queryKey: controlsQueryKey, queryFn: getControls });
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const [totpCode, setTotpCode] = useState("");
  const [flattenPreview, setFlattenPreview] = useState<FlattenPreview | null>(null);
  const [confirmationText, setConfirmationText] = useState("");
  const [selectionTab, setSelectionTab] = useState<SelectionTabKey>("CPM-RO-001");

  const refresh = async () => {
    await Promise.all([
      ownerQueryClient.invalidateQueries({ queryKey: controlsQueryKey }),
      ownerQueryClient.invalidateQueries({ queryKey: ["owner", "selection"] }),
    ]);
  };

  const controlMutation = useMutation({
    mutationFn: async (action: PendingAction) => {
      const body: ControlWriteBody = {
        expected_version: action.version,
        reason: "owner_manual_control",
        idempotency_key: requestId("owner-request"),
        totp_code: action.action === "resume" ? totpCode : null,
      };
      if (action.kind === "global") {
        await setGlobalEntry(action.action, body);
      } else {
        await setStrategyControl(action.strategyGroupId, action.action, body);
      }
    },
    onSuccess: async () => {
      setPendingAction(null);
      setTotpCode("");
      await refresh();
    },
  });

  const previewMutation = useMutation({
    mutationFn: getFlattenPreview,
    onSuccess: setFlattenPreview,
  });

  const flattenMutation = useMutation({
    mutationFn: async (preview: FlattenPreview) => submitFlatten({
      expected_version: preview.owner_policy_version,
      reason: "owner_flatten_all",
      idempotency_key: requestId("owner-request-flatten"),
      totp_code: totpCode,
      snapshot_digest: preview.snapshot_digest,
      confirmation_text: "确认平仓全部持仓",
    }),
    onSuccess: async () => {
      setFlattenPreview(null);
      setTotpCode("");
      setConfirmationText("");
      await refresh();
    },
  });

  const data = controls.data;
  const pausedCount = useMemo(
    () => data?.strategies.filter((item) => item.configured_state === "paused").length ?? 0,
    [data],
  );

  const pageHeader = (
    <PageHeader
      title="控制"
      description="暂停新准入、恢复权限与受控退出全部当前 Ticket"
      actions={<ManualRefreshButton isRefreshing={controls.isFetching} onRefresh={() => void controls.refetch()} />}
    />
  );

  if (!data) {
    return (
      <AppShell dataTime={<DataAge generatedAt={null} />} statusLabel={controls.isError ? "不可用" : "加载中"} statusTone="neutral">
        {pageHeader}
        <UnavailablePanel title="控制状态不可用" detail="不会把不可用解释为运行中，也不会发起任何控制操作。" />
      </AppShell>
    );
  }

  const globalPaused = data.global_entry.configured_state === "paused";
  const operation = data.current_operation;
  const actionNeedsTotp = pendingAction?.action === "resume";

  return (
    <AppShell
      dataTime={<DataAge generatedAt={new Date(data.generated_at_ms).toISOString()} />}
      statusLabel={globalPaused ? "ENTRY 已暂停" : "运行中"}
      statusTone={globalPaused ? "attention" : "success"}
    >
      {pageHeader}

      <section className="control-summary-strip mb-3">
        <div><span>全局 ENTRY</span><strong>{globalPaused ? "已暂停" : "运行中"}</strong></div>
        <div><span>暂停策略</span><strong className="tabular-number">{pausedCount}</strong></div>
        <div><span>活动 Ticket</span><strong className="tabular-number">{data.global_entry.active_ticket_count}</strong></div>
        <div><span>当前受控操作</span><strong>{operation ? operationResult(operation) : "无"}</strong></div>
      </section>

      <section className="danger-zone mb-3.5">
        <div>
          <span className="danger-zone__eyebrow">危险操作 · 紧急熔断</span>
          <h2>受控平仓全部仓位</h2>
          <p>先暂停全局 ENTRY，再由 Lifecycle 请求退出服务器冻结的全部活动 Ticket。页面不能选择数量、方向或订单类型。</p>
        </div>
        <Button className="owner-button--danger flex-none" disabled={previewMutation.isPending} onClick={() => previewMutation.mutate()}>
          {previewMutation.isPending ? "读取权威事实" : "受控平仓全部仓位"}
        </Button>
      </section>

      <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-12">
        <div className="space-y-3.5 lg:col-span-8">
          <Panel title="全局 ENTRY 控制">
            <div className="control-row control-row--global">
              <div className="control-row__identity">
                <strong className="text-[14px] font-bold text-[var(--color-text-primary)]">全部策略新开仓</strong>
                <span>Policy v{data.global_entry.policy_version} · 已有 Ticket 生命周期不受影响</span>
              </div>
              <StatusTag tone={globalPaused ? "attention" : "success"}>{globalPaused ? "已暂停" : "运行中"}</StatusTag>
              <div className="control-row__facts">
                <span>当前状态</span><strong>{formatOwnerStatus(data.global_entry.effective_state)}</strong>
              </div>
              <Button onClick={() => setPendingAction({ kind: "global", action: globalPaused ? "resume" : "pause", version: data.global_entry.policy_version })}>
                {globalPaused ? "恢复新开仓" : "暂停新开仓"}
              </Button>
            </div>
          </Panel>

          <Panel title="StrategyGroup 控制">
            <div className="strategy-control-table" role="table">
              <div className="strategy-control-table__head" role="row">
                <span>StrategyGroup</span><span>配置状态</span><span>有效状态</span><span>最近变更</span><span>操作</span>
              </div>
              {data.strategies.map((strategy) => {
                const paused = strategy.configured_state === "paused";
                return (
                  <div className="strategy-control-table__row" role="row" key={strategy.strategy_group_id}>
                    <div>
                      <strong className="font-semibold text-[var(--color-text-primary)]">{strategy.strategy_group_id}</strong>
                      <small title={strategy.reason}>{formatOwnerReason(strategy.reason).label}</small>
                    </div>
                    <StatusTag tone={strategy.strategy_group_id === "SOR-001" ? "neutral" : paused ? "attention" : "success"}>
                      {strategy.strategy_group_id === "SOR-001" ? "已退役" : paused ? "已暂停" : "已启用"}
                    </StatusTag>
                    <span className="text-[12px] font-medium">{formatOwnerStatus(strategy.effective_state)}</span>
                    <span className="tabular-number text-[11px] text-[var(--color-text-secondary)]">
                      v{strategy.control_version} · {formatTime(strategy.updated_at_ms)}
                    </span>
                    <Button
                      disabled={strategy.strategy_group_id === "SOR-001"}
                      onClick={() =>
                        setPendingAction({
                          kind: "strategy",
                          action: paused ? "resume" : "pause",
                          strategyGroupId: strategy.strategy_group_id,
                          version: strategy.control_version,
                        })
                      }
                    >
                      {paused ? "恢复" : "暂停"}
                    </Button>
                  </div>
                );
              })}
            </div>
          </Panel>

          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-divider)] pb-2.5">
              <div>
                <h3 className="m-0 text-[13px] font-bold text-[var(--color-text-primary)]">动态选币与轮动管理</h3>
                <p className="m-0 mt-0.5 text-[11px] text-[var(--color-text-secondary)]">各策略组独立的 Dynamic 准入授权与 Static 回退</p>
              </div>
              <div className="flex flex-wrap items-center gap-1 rounded bg-[var(--color-surface-secondary)] p-1 border border-[var(--color-divider)]">
                {SELECTION_GROUPS.map((group) => (
                  <button
                    key={group}
                    type="button"
                    className={`rounded px-2.5 py-1 text-[11px] font-medium transition-colors ${
                      selectionTab === group
                        ? "bg-[var(--color-emphasis)] text-[#181a20] font-bold shadow-sm"
                        : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
                    }`}
                    onClick={() => setSelectionTab(group)}
                  >
                    {group}
                  </button>
                ))}
                <button
                  type="button"
                  className={`rounded px-2.5 py-1 text-[11px] font-medium transition-colors ${
                    selectionTab === "SOR-1H"
                      ? "bg-[var(--color-emphasis)] text-[#181a20] font-bold shadow-sm"
                      : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
                  }`}
                  onClick={() => setSelectionTab("SOR-1H")}
                >
                  SOR-1H
                </button>
                <button
                  type="button"
                  className={`rounded px-2.5 py-1 text-[11px] font-medium transition-colors ${
                    selectionTab === "all"
                      ? "bg-[var(--color-emphasis)] text-[#181a20] font-bold shadow-sm"
                      : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
                  }`}
                  onClick={() => setSelectionTab("all")}
                >
                  全部平铺
                </button>
              </div>
            </div>

            <div className="space-y-3">
              {selectionTab === "all" ? (
                <>
                  {SELECTION_GROUPS.map((group) => (
                    <SelectionControlPanel key={group} strategyGroupId={group} />
                  ))}
                  <OrbSelectionControlPanel />
                </>
              ) : selectionTab === "SOR-1H" ? (
                <OrbSelectionControlPanel />
              ) : (
                <SelectionControlPanel key={selectionTab} strategyGroupId={selectionTab} />
              )}
            </div>
          </div>
        </div>

        <div className="space-y-3.5 lg:col-span-4">
          <Panel title="组合容量（只读）">
            <dl className="grid grid-cols-2 gap-2 text-xs">
              <div className="rounded border border-[var(--color-divider)] bg-[var(--color-surface-secondary)] p-2.5">
                <dt className="text-[11px] font-medium text-[var(--color-text-secondary)]">同策略同方向上限</dt>
                <dd className="m-0 mt-1 text-[15px] font-bold text-[var(--color-text-primary)]">
                  {data.account_capacity.max_same_strategy_side ?? "无额外上限（旧 Policy）"}
                </dd>
              </div>
              <div className="rounded border border-[var(--color-divider)] bg-[var(--color-surface-secondary)] p-2.5">
                <dt className="text-[11px] font-medium text-[var(--color-text-secondary)]">全局 Ticket 上限</dt>
                <dd className="m-0 mt-1 text-[15px] font-bold text-[var(--color-text-primary)]">
                  {data.account_capacity.max_concurrent_tickets}
                </dd>
              </div>
              <div className="rounded border border-[var(--color-divider)] bg-[var(--color-surface-secondary)] p-2.5">
                <dt className="text-[11px] font-medium text-[var(--color-text-secondary)]">long_continuation 上限</dt>
                <dd className="m-0 mt-1 text-[15px] font-bold text-[var(--color-text-primary)]">
                  {data.account_capacity.family_limits.long_continuation}
                </dd>
              </div>
              <div className="rounded border border-[var(--color-divider)] bg-[var(--color-surface-secondary)] p-2.5">
                <dt className="text-[11px] font-medium text-[var(--color-text-secondary)]">rally_failure_short 上限</dt>
                <dd className="m-0 mt-1 text-[15px] font-bold text-[var(--color-text-primary)]">
                  {data.account_capacity.family_limits.rally_failure_short}
                </dd>
              </div>
            </dl>
            <p className="mt-2.5 text-[11px] leading-relaxed text-[var(--color-text-secondary)]">
              Policy v{data.global_entry.policy_version} · 严格 Family、方向风险与 Netting Domain 约束仍生效；容量不授予策略 ENTRY 权限。
            </p>
            <div className="mt-2.5 flex flex-wrap gap-1.5 border-t border-[var(--color-divider)] pt-2.5">
              {Object.entries(data.account_capacity.strategy_side_active_counts ?? {}).map(([scope, count]) => (
                <span className="rounded border border-[var(--color-divider)] bg-[var(--color-surface-secondary)] px-2 py-0.5 text-[11px] text-[var(--color-text-secondary)]" key={scope}>
                  {scope}：<strong className="text-[var(--color-text-primary)]">{count}</strong> 个占用
                </span>
              ))}
            </div>
          </Panel>

          <Panel title="旧 SOR-001 已退役">
            <div className="flex items-center gap-2">
              <StatusTag tone="neutral">RETIRED</StatusTag>
              <p className="m-0 text-[12px] text-[var(--color-text-secondary)]">仅保留历史记录，不再提供恢复入场或 Dynamic 激活。</p>
            </div>
          </Panel>

          <Panel title="当前受控操作">
            {operation ? (
              <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3">
                <StatusTag tone={operationTone(operation)}>{operationResult(operation)}</StatusTag>
                <span className="min-w-0 truncate font-semibold text-[var(--color-text-primary)]">{operationName(operation)}</span>
                <span className="tabular-number text-[var(--color-text-secondary)]">{operation.target_ticket_ids.length} 个 Ticket</span>
              </div>
            ) : (
              <div className="compact-empty">当前没有进行中的受控操作</div>
            )}
          </Panel>

          <Panel title="控制操作历史">
            {data.recent_operations.length ? (
              <div className="space-y-1">
                {data.recent_operations.map((item) => (
                  <div className="grid min-h-[52px] grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 border-t border-[var(--color-divider)] py-2.5 first:border-t-0" key={item.authorization_id}>
                    <div className="grid min-w-0 gap-1">
                      <strong className="truncate text-[12px] font-semibold text-[var(--color-text-primary)]">{operationName(item)}</strong>
                      <span className="truncate text-[11px] text-[var(--color-text-secondary)]">
                        {item.target_ticket_ids.length} 个 Ticket · {formatTime(item.updated_at_ms)}
                      </span>
                      {item.first_blocker ? (
                        <small className="truncate text-[10px] text-[var(--color-text-secondary)]" title={item.first_blocker}>
                          过程关注：{formatOwnerReason(item.first_blocker).label}
                        </small>
                      ) : null}
                    </div>
                    <StatusTag tone={operationTone(item)}>{operationResult(item)}</StatusTag>
                  </div>
                ))}
              </div>
            ) : (
              <div className="compact-empty">暂无受控平仓操作记录</div>
            )}
          </Panel>
        </div>
      </div>

      <AlertDialog.Root open={pendingAction !== null} onOpenChange={(open) => { if (!open) { setPendingAction(null); setTotpCode(""); } }}>
        <AlertDialog.Portal>
          <AlertDialog.Overlay className="control-dialog__overlay" />
          <AlertDialog.Content className="control-dialog">
            <AlertDialog.Title>{pendingAction?.action === "pause" ? "确认暂停" : "确认恢复"}</AlertDialog.Title>
            <AlertDialog.Description>
              {pendingAction?.action === "pause" ? "暂停只阻断新的 ENTRY，Observation 和已有 Ticket 不受影响。" : "恢复后新的有效信号可重新创建 Ticket 和 ENTRY。"}
            </AlertDialog.Description>
            {actionNeedsTotp ? <label className="control-field">Google Authenticator 验证码<input inputMode="numeric" value={totpCode} onChange={(event) => setTotpCode(event.target.value)} /></label> : null}
            {controlMutation.isError ? <p className="control-dialog__error">操作失败，当前状态未作成功假设。</p> : null}
            <div className="control-dialog__actions"><AlertDialog.Cancel asChild><Button>取消</Button></AlertDialog.Cancel><AlertDialog.Action asChild><Button disabled={!pendingAction || (actionNeedsTotp && totpCode.length < 6) || controlMutation.isPending} onClick={(event) => { event.preventDefault(); if (pendingAction) controlMutation.mutate(pendingAction); }}>确认</Button></AlertDialog.Action></div>
          </AlertDialog.Content>
        </AlertDialog.Portal>
      </AlertDialog.Root>

      <AlertDialog.Root open={flattenPreview !== null} onOpenChange={(open) => { if (!open) { setFlattenPreview(null); setConfirmationText(""); setTotpCode(""); } }}>
        <AlertDialog.Portal>
          <AlertDialog.Overlay className="control-dialog__overlay" />
          <AlertDialog.Content className="control-dialog control-dialog--danger">
            <AlertDialog.Title>确认受控平仓全部仓位</AlertDialog.Title>
            <AlertDialog.Description>服务器已冻结当前范围；提交后全局 ENTRY 将保持暂停。</AlertDialog.Description>
            <div className="flatten-ticket-list">{flattenPreview?.ticket_ids.length ? flattenPreview.ticket_ids.map((ticketId) => <span className="tabular-number" key={ticketId}>{ticketId} · {flattenPreview.ticket_states[ticketId]}</span>) : <span>当前已经全平，将执行空仓幂等确认。</span>}</div>
            <label className="control-field">Google Authenticator 验证码<input inputMode="numeric" value={totpCode} onChange={(event) => setTotpCode(event.target.value)} /></label>
            <label className="control-field">输入“确认平仓全部持仓”<input value={confirmationText} onChange={(event) => setConfirmationText(event.target.value)} /></label>
            {flattenMutation.isError ? <p className="control-dialog__error">平仓请求未成功提交；全局 ENTRY 可能已被安全暂停，请手动刷新确认。</p> : null}
            <div className="control-dialog__actions"><AlertDialog.Cancel asChild><Button>取消</Button></AlertDialog.Cancel><AlertDialog.Action asChild><Button className="owner-button--danger" disabled={!flattenPreview || totpCode.length < 6 || confirmationText !== "确认平仓全部持仓" || flattenMutation.isPending} onClick={(event) => { event.preventDefault(); if (flattenPreview) flattenMutation.mutate(flattenPreview); }}>确认平仓全部持仓</Button></AlertDialog.Action></div>
          </AlertDialog.Content>
        </AlertDialog.Portal>
      </AlertDialog.Root>

    </AppShell>
  );
}
