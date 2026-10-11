import * as AlertDialog from "@radix-ui/react-alert-dialog";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { ApiError } from "../../api/errors";
import { Button } from "../../components/ui/Button";
import { Panel } from "../../components/ui/Panel";
import { StatusTag } from "../../components/ui/StatusTag";
import { getSelectionPreview, submitSelectionIntent, type SelectionPreview } from "./api";

type Intent = { mode: "dynamic" | "static"; preview: SelectionPreview; key: string };
function utc(time: number | null | undefined) { return time == null ? "—" : new Date(time).toISOString().replace(".000Z", " UTC"); }
function age(value: number | null) { return value == null ? "—" : `${Math.floor(value / 1000)}s`; }
function staticRetry(preview: SelectionPreview) {
  return preview.control?.pending_selection_mode === "static_baseline" && !!preview.control.pending_authorization_id &&
    ["FAILED_CLOSED", "ABANDONED"].includes(preview.runtime.materialization_state ?? "");
}

export function SelectionControlPanel({ strategyGroupId }: { strategyGroupId: string }) {
  const query = useQuery({ queryKey: ["owner", "selection", strategyGroupId], queryFn: () => getSelectionPreview(strategyGroupId) });
  const [intent, setIntent] = useState<Intent | null>(null);
  const [reason, setReason] = useState("");
  const [code, setCode] = useState("");
  const [conflicted, setConflicted] = useState(false);
  const submittedReason = useRef<string | null>(null);
  const mutation = useMutation({
    mutationFn: async () => {
      if (!intent?.preview.control) throw new Error("Selection control is unavailable");
      const control = intent.preview.control;
      submittedReason.current ??= reason.trim();
      if (intent.mode === "static" && (!control.rollback_baseline_id || !control.selection_epoch_id)) throw new Error("Static baseline is unavailable");
      await submitSelectionIntent(strategyGroupId, intent.mode, {
        expected_version: control.control_version, reason: submittedReason.current, idempotency_key: intent.key, totp_code: code,
        effective_period_anchor_ms: intent.preview.next_effective_period_anchor_ms,
        ...(intent.mode === "static" ? { rollback_baseline_id: control.rollback_baseline_id!, selection_epoch_id: control.selection_epoch_id! } : {}),
      });
    },
    onSuccess: async () => { setCode(""); setIntent(null); await query.refetch(); },
    onError: async (error) => {
      setCode("");
      if (error instanceof ApiError && error.status === 409) { setConflicted(true); await query.refetch(); }
    },
  });
  const preview = query.data;
  const open = async (mode: Intent["mode"]) => {
    const fresh = await query.refetch();
    const current = fresh.data;
    if (fresh.isError || !current?.runtime.installed || !current.control) return;
    if (current.control.pending_selection_mode && !(mode === "static" && staticRetry(current))) return;
    if (mode === "dynamic" && current.control.selection_mode !== "static_baseline") return;
    if (mode === "static" && (current.control.selection_mode !== "dynamic_selection" || !current.control.rollback_baseline_id || !current.control.selection_epoch_id)) return;
    setIntent({ mode, preview: current, key: `owner-selection:${globalThis.crypto.randomUUID()}` });
    submittedReason.current = null;
    setReason(""); setCode(""); setConflicted(false); mutation.reset();
  };
  const pending = preview?.control?.pending_selection_mode;
  const dynamic = preview?.control?.selection_mode === "dynamic_selection";
  const blocked = preview?.runtime.first_blocker;
  const retryStatic = preview ? staticRetry(preview) : false;
  return <Panel title={`${strategyGroupId} Selection`}>
    {!preview ? <p role="status">Selection 状态不可用；不提交任何权限变更。</p> : <>
      <div className="control-row">
        <StatusTag tone={blocked ? "attention" : "neutral"}>{!preview.runtime.installed ? "NOT_INSTALLED" : !preview.control ? "UNKNOWN" : dynamic ? "DYNAMIC" : preview.control.selection_mode === "disabled" ? "DISABLED" : "STATIC"}</StatusTag>
        <span>{preview.runtime.installed ? `${preview.cadence_hours}h Selection · 1h 延迟` : "Dynamic 不可用：Spec 未安装或未认证"}</span>
        <Button disabled={query.isError || query.isFetching || !preview.runtime.installed || preview.control?.selection_mode !== "static_baseline" || !!pending} onClick={() => void open("dynamic")}>启用 {strategyGroupId} Dynamic</Button>
        <Button disabled={query.isError || query.isFetching || !dynamic || (!!pending && !retryStatic) || !preview.control?.rollback_baseline_id} onClick={() => void open("static")}>{retryStatic ? "重新授权" : "回退"} {strategyGroupId} Static</Button>
        <Button disabled={query.isFetching} onClick={() => void query.refetch()}>刷新 {strategyGroupId}</Button>
      </div>
      {query.isError ? <p role="alert">最新预览读取失败，旧数据显示仅供参考；权限提交已禁用。</p> : null}
      <p aria-live="polite">{blocked ? `当前阻断：${blocked}` : "未发现 Selection 阻断；仍须通过正常 Entry / 风险准入。"}</p>
      {pending ? <p>等待 {pending} · period {utc(preview.control?.pending_effective_period_anchor_ms)}</p> : null}
      <dl className="grid gap-1 text-xs">
        <div>最新成功 Snapshot 完成年龄：{age(preview.runtime.latest_successful_completion_age_ms)}</div>
        <div>最新 cutoff 年龄：{age(preview.runtime.latest_successful_cutoff_age_ms)}</div>
        <div>实际 membership 来源年龄：{age(preview.runtime.membership_source_age_ms)}</div>
        <div>实际 Authority：{preview.runtime.current_authority_outcome ?? "—"}</div>
        <div>membership stale deadline：{utc(preview.runtime.membership_valid_until_ms)} · missed periods {preview.runtime.consecutive_missed_periods ?? "—"}</div>
        <div>最新合格 / selected：{preview.runtime.latest_ready_count ?? "—"} / {preview.runtime.latest_selected_count ?? "—"}</div>
        <div>Materialization：{preview.runtime.materialization_state ?? "无待执行 Generation"} · deadline {utc(preview.runtime.materialization_deadline_ms)}</div>
        <div>Vacuum：{preview.runtime.vacuum_state ?? "无"} · fenced {utc(preview.runtime.vacuum_fenced_at_ms)}</div>
      </dl>
      {preview.runtime.valid_empty_reason ? <p>最新 Desired 为 EMPTY：{preview.runtime.valid_empty_reason === "ZERO_QUALIFIED_MEMBERS" ? "合格标的为 0" : "冻结 rank band 内无合格成员"}。实际 new Entry 权限以当前 Authority 为准；VALID_EMPTY 生效后不恢复旧标的，也不追溯撤销已有 Ticket。</p> : null}
      {strategyGroupId === "MPG-001" ? <p>MPG 使用冻结的 12–16 retention band；资格不足时不补造合格成员。</p> : null}
      <ul>{preview.runtime.members.map(member => <li key={member.facts.runtime_scope_id}>{member.facts.exchange_instrument_id} · {member.first_blocker ?? "无成员级 Selection 阻断"}</li>)}</ul>
    </>}
    <AlertDialog.Root open={intent !== null} onOpenChange={value => { if (!value && !mutation.isPending) { setIntent(null); setCode(""); } }}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="control-dialog__overlay" />
        <AlertDialog.Content className="control-dialog">
          <AlertDialog.Title>确认 {strategyGroupId} {intent?.mode === "static" ? "Static 回退" : "Dynamic 激活"}</AlertDialog.Title>
          <AlertDialog.Description>仅提交下一 period 的授权意图；实际切换由 Worker 执行，已有 Ticket 生命周期不变。</AlertDialog.Description>
          <p>Decision period：{utc(intent?.preview.next_effective_period_anchor_ms)}</p>
          <p>最早新增 Entry close：{utc(intent?.preview.next_eligibility_not_before_ms)}</p>
          <label className="control-field">操作原因<input value={reason} maxLength={512} disabled={mutation.isPending || conflicted || submittedReason.current !== null} onChange={e => setReason(e.target.value)} /></label>
          <label className="control-field">验证码<input autoComplete="one-time-code" inputMode="numeric" maxLength={8} value={code} disabled={mutation.isPending || conflicted} onChange={e => setCode(e.target.value.replace(/\D/g, ""))} /></label>
          {mutation.isError ? <p role="alert" className="control-dialog__error">{conflicted ? "状态已变化，已刷新；关闭后重新确认，不会自动重提权限。" : mutation.error instanceof ApiError && mutation.error.code === "step_up_invalid" ? "验证码无效或已使用，登录会话保持。使用同一意图重试。" : mutation.error instanceof ApiError && mutation.error.code === "forbidden_request" ? "请求来源未通过安全校验；请刷新页面并核对访问地址。" : "提交未确认；刷新核对状态后，可使用同一意图重试。"}</p> : null}
          <div className="control-dialog__actions">
            <AlertDialog.Cancel asChild><Button disabled={mutation.isPending}>取消</Button></AlertDialog.Cancel>
            <Button disabled={!reason.trim() || code.length < 6 || mutation.isPending || conflicted} onClick={() => mutation.mutate()}>确认提交</Button>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  </Panel>;
}
