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
  activateSorDynamicSelection,
  setGlobalEntry,
  setStrategyControl,
  submitFlatten,
  type ControlWriteBody,
  type FlattenPreview,
  type OwnerControlOperation,
} from "./api";
import { controlsQueryKey } from "./api";

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

export function ControlsPage() {
  const controls = useQuery({ queryKey: controlsQueryKey, queryFn: getControls });
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const [totpCode, setTotpCode] = useState("");
  const [flattenPreview, setFlattenPreview] = useState<FlattenPreview | null>(null);
  const [confirmationText, setConfirmationText] = useState("");
  const [dynamicActivationOpen, setDynamicActivationOpen] = useState(false);

  const refresh = async () => {
    await ownerQueryClient.invalidateQueries({ queryKey: controlsQueryKey });
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

  const dynamicActivationMutation = useMutation({
    mutationFn: async () => activateSorDynamicSelection({
      expected_version: data?.dynamic_selection.control_version ?? 0,
      effective_session_start_ms: nextUtcSessionStartMs(),
      reason: "owner_activate_sor_dynamic_selection_v0",
      idempotency_key: requestId("owner-request-sor-dynamic"),
      totp_code: totpCode,
    }),
    onSuccess: async () => {
      setDynamicActivationOpen(false);
      setTotpCode("");
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
  const dynamicPending = data.dynamic_selection.pending_selection_mode === "dynamic_selection";
  const dynamicActive = data.dynamic_selection.selection_mode === "dynamic_selection";
  const operation = data.current_operation;
  const actionNeedsTotp = pendingAction?.action === "resume";

  return (
    <AppShell
      dataTime={<DataAge generatedAt={new Date(data.generated_at_ms).toISOString()} />}
      statusLabel={globalPaused ? "ENTRY 已暂停" : "运行中"}
      statusTone={globalPaused ? "attention" : "success"}
    >
      {pageHeader}

      <section className="control-summary-strip">
        <div><span>全局 ENTRY</span><strong>{globalPaused ? "已暂停" : "运行中"}</strong></div>
        <div><span>暂停策略</span><strong className="tabular-number">{pausedCount}</strong></div>
        <div><span>活动 Ticket</span><strong className="tabular-number">{data.global_entry.active_ticket_count}</strong></div>
        <div><span>当前受控操作</span><strong>{operation ? operationResult(operation) : "无"}</strong></div>
      </section>

      <Panel title="全局 ENTRY 控制">
        <div className="control-row control-row--global">
          <div className="control-row__identity">
            <strong>全部策略新开仓</strong>
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
                <div><strong>{strategy.strategy_group_id}</strong><small title={strategy.reason}>{formatOwnerReason(strategy.reason).label}</small></div>
                <StatusTag tone={paused ? "attention" : "success"}>{paused ? "已暂停" : "已启用"}</StatusTag>
                <span>{formatOwnerStatus(strategy.effective_state)}</span>
                <span className="tabular-number">v{strategy.control_version} · {formatTime(strategy.updated_at_ms)}</span>
                <Button onClick={() => setPendingAction({ kind: "strategy", action: paused ? "resume" : "pause", strategyGroupId: strategy.strategy_group_id, version: strategy.control_version })}>
                  {paused ? "恢复" : "暂停"}
                </Button>
              </div>
            );
          })}
        </div>
      </Panel>

      <Panel title="SOR Dynamic Universe">
        <div className="control-row control-row--global">
          <div className="control-row__identity">
            <strong>首个 Dynamic Selection Session</strong>
            <span>固定 24 Candidate · 当前 Static baseline 将在下一 UTC Session 后由正式 Materialization 接管</span>
          </div>
          <StatusTag tone={dynamicActive ? "success" : "attention"}>{dynamicActive ? "已启用" : dynamicPending ? "已授权" : "待激活"}</StatusTag>
          <div className="control-row__facts"><span>下一 UTC Session</span><strong>{formatTime(nextUtcSessionStartMs())}</strong></div>
          <Button disabled={dynamicActive || dynamicPending} onClick={() => setDynamicActivationOpen(true)}>{dynamicActive ? "Dynamic 已启用" : dynamicPending ? "等待生效" : "激活 Dynamic"}</Button>
        </div>
      </Panel>

      <Panel title="当前受控操作">
        {operation ? (
          <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3">
            <StatusTag tone={operationTone(operation)}>{operationResult(operation)}</StatusTag>
            <span className="min-w-0 truncate">{operationName(operation)}</span>
            <span className="tabular-number text-[var(--color-text-secondary)]">{operation.target_ticket_ids.length} 个 Ticket</span>
          </div>
        ) : <div className="compact-empty">当前没有进行中的受控操作</div>}
      </Panel>

      <section className="danger-zone">
        <div>
          <span className="danger-zone__eyebrow">危险操作</span>
          <h2>受控平仓全部仓位</h2>
          <p>先暂停全局 ENTRY，再由 Lifecycle 请求退出服务器冻结的全部活动 Ticket。页面不能选择数量、方向或订单类型。</p>
        </div>
        <Button className="owner-button--danger" disabled={previewMutation.isPending} onClick={() => previewMutation.mutate()}>
          {previewMutation.isPending ? "读取权威事实" : "受控平仓全部仓位"}
        </Button>
      </section>

      <Panel title="控制操作历史">
        {data.recent_operations.length ? data.recent_operations.map((item) => (
          <div className="grid min-h-[52px] grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 border-t border-[var(--color-divider)] py-2 first:border-t-0" key={item.authorization_id}>
            <div className="grid min-w-0 gap-1"><strong className="truncate text-[12px]">{operationName(item)}</strong><span className="truncate text-[11px] text-[var(--color-text-secondary)]">{item.target_ticket_ids.length} 个 Ticket · {formatTime(item.updated_at_ms)}</span>{item.first_blocker ? <small className="truncate text-[10px] text-[var(--color-text-secondary)]" title={item.first_blocker}>过程关注：{formatOwnerReason(item.first_blocker).label}</small> : null}</div>
            <StatusTag tone={operationTone(item)}>{operationResult(item)}</StatusTag>
          </div>
        )) : <div className="compact-empty">暂无受控平仓操作记录</div>}
      </Panel>

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

      <AlertDialog.Root open={dynamicActivationOpen} onOpenChange={(open) => { if (!open) { setDynamicActivationOpen(false); setTotpCode(""); } }}>
        <AlertDialog.Portal>
          <AlertDialog.Overlay className="control-dialog__overlay" />
          <AlertDialog.Content className="control-dialog">
            <AlertDialog.Title>确认激活 SOR Dynamic Universe</AlertDialog.Title>
            <AlertDialog.Description>将为下一 UTC Session 写入一次性 Dynamic Selection 请求。当前 Static Universe 在正式切换前继续作为权威集合。</AlertDialog.Description>
            <div className="mt-3 grid gap-1 text-[11px] text-[var(--color-text-secondary)]"><span>下一 UTC Session</span><strong className="tabular-number text-[var(--color-text-primary)]">{formatTime(nextUtcSessionStartMs())}</strong></div>
            <label className="control-field">Google Authenticator 验证码<input autoComplete="one-time-code" inputMode="numeric" maxLength={8} value={totpCode} onChange={(event) => setTotpCode(event.target.value.replace(/\D/g, ""))} /></label>
            {dynamicActivationMutation.isError ? <p className="control-dialog__error">激活未提交；请刷新当前状态后重试。</p> : null}
            <div className="control-dialog__actions"><AlertDialog.Cancel asChild><Button>取消</Button></AlertDialog.Cancel><AlertDialog.Action asChild><Button disabled={totpCode.length < 6 || dynamicActivationMutation.isPending} onClick={(event) => { event.preventDefault(); dynamicActivationMutation.mutate(); }}>确认激活</Button></AlertDialog.Action></div>
          </AlertDialog.Content>
        </AlertDialog.Portal>
      </AlertDialog.Root>
    </AppShell>
  );
}

function nextUtcSessionStartMs(nowMs = Date.now()): number {
  const dayMs = 24 * 60 * 60 * 1000;
  return (Math.floor(nowMs / dayMs) + 1) * dayMs;
}
