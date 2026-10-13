import * as AlertDialog from '@radix-ui/react-alert-dialog';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { ApiError } from '../../api/errors';
import { Button } from '../../components/ui/Button';
import { Panel } from '../../components/ui/Panel';
import { StatusTag } from '../../components/ui/StatusTag';
import { getOrbSelectionPreview, submitOrbDynamicIntent, submitOrbStaticIntent, type OrbSelectionPreview } from './api';

const label = 'SOR-1H（1h 入场 / 15m 退出）';
const status = (value: unknown) => typeof value === 'string' ? value : '—';
const utc = (value: number | null | undefined) => value == null ? '—' : new Date(value).toISOString().replace('.000Z', ' UTC');
type Intent = { mode: "dynamic" | "static"; preview: OrbSelectionPreview; key: string; reason?: string };
export function OrbSelectionControlPanel() {
  const query = useQuery({ queryKey: ['owner','selection','SOR-1H-001'], queryFn: getOrbSelectionPreview });
  const [intent,setIntent] = useState<Intent | null>(null);
  const [reason,setReason] = useState('');
  const [code,setCode] = useState('');
  const [conflict,setConflict] = useState(false);
  const mutation = useMutation({mutationFn:async()=>{
    if (!intent?.preview.control) throw new Error('SOR-1H control unavailable');
    const savedReason = intent.reason ?? reason.trim();
    setIntent({...intent,reason:savedReason});
    const body={expected_version:intent.preview.control.control_version,reason:savedReason,idempotency_key:intent.key,totp_code:code};
    if(intent.mode==='static') {
      if(!intent.preview.control.rollback_baseline_id || !intent.preview.control.selection_epoch_id)throw new Error('Frozen Static source unavailable');
      await submitOrbStaticIntent({...body,effective_period_anchor_ms:intent.preview.next_effective_period_anchor_ms,
        rollback_baseline_id:intent.preview.control.rollback_baseline_id,selection_epoch_id:intent.preview.control.selection_epoch_id});
    } else await submitOrbDynamicIntent({...body,effective_session_start_ms:intent.preview.next_effective_period_anchor_ms});
  },onSuccess:async()=>{setCode('');setIntent(null);await query.refetch();},onError:async(error)=>{
    setCode('');if(error instanceof ApiError && error.status===409){setConflict(true);await query.refetch();}
  }});
  const preview=query.data;
  const control=preview?.control;
  const runtime=preview?.runtime;
  const pending=control?.pending_selection_mode;
  const disabled=query.isError || query.isFetching || !preview?.installed || !control || control.selection_mode!=='static_baseline' || !!pending;
  async function open(mode: "dynamic" | "static" = "dynamic"){
    const fresh=await query.refetch();
    if(fresh.isError || !fresh.data?.installed || !fresh.data.control || (mode==='dynamic' ? fresh.data.control.selection_mode!=='static_baseline' : fresh.data.control.selection_mode!=='dynamic_selection' || !fresh.data.control.rollback_baseline_id || !fresh.data.control.selection_epoch_id) || fresh.data.control.pending_selection_mode)return;
    setIntent({mode,preview:fresh.data,key:`owner-orb:${globalThis.crypto.randomUUID()}`});setReason('');setCode('');setConflict(false);mutation.reset();
  }
  return <Panel title={label}>
    <div className='control-row'>
      <StatusTag tone='neutral'>{!preview?.installed ? '未安装' : control?.selection_mode==='dynamic_selection' ? 'Dynamic' : 'Static'}</StatusTag>
      <Button disabled={disabled} onClick={()=>void open()}>启用 SOR-1H Dynamic</Button>
      <Button disabled={query.isError||query.isFetching||!preview?.installed||control?.selection_mode!=="dynamic_selection"||!!pending||!control.rollback_baseline_id} onClick={()=>void open("static")}>回退 SOR-1H Static</Button>
      <Button disabled={query.isFetching} onClick={()=>void query.refetch()}>刷新 SOR-1H</Button>
    </div>
    <p>独立多空策略；旧 SOR-001 保持退役。</p>
    <p>准备时间：{utc(preview?.next_prepare_not_before_ms)}</p>
    <p>最早新增入场收盘：{utc(preview?.next_eligibility_not_before_ms)}</p>
    <p>当前 Authority：{status(runtime?.current_authority?.authority.authority_outcome)} · 首个可交易收盘：{utc(runtime?.first_eligible_close_time_ms)}</p>
    <p>当日结果：{runtime?.selection_job?.state ?? '等待'} · 选中成员：{runtime?.snapshot_disposition?.snapshot.selected_count ?? '—'}</p>
    {pending ? <p>原选币授权等待系统接管；普通失败保留授权并自动重试。</p> : null}
    {runtime?.current_authority?.authority.authority_outcome==='VALID_EMPTY' ? <p>合法空集，等待后续选币；已有 Ticket 继续原退出规则。</p> : null}
    {query.isError ? <p role='alert'>当前状态读取失败，授权提交已禁用。</p> : null}
    <AlertDialog.Root open={intent!==null} onOpenChange={value=>{if(!value&&!mutation.isPending){setIntent(null);setCode('');}}}>
      <AlertDialog.Portal><AlertDialog.Overlay className='control-dialog__overlay'/><AlertDialog.Content className='control-dialog'>
        <AlertDialog.Title>确认 SOR-1H {intent?.mode==='static' ? 'Static 回退' : 'Dynamic 激活'}</AlertDialog.Title>
        <AlertDialog.Description>提交独立多空选币意图，系统完成准备和审计后接管；已有 Ticket 保持原退出规则。</AlertDialog.Description>
        <p>准备时间：{utc(intent?.preview.next_prepare_not_before_ms)}</p><p>最早入场收盘：{utc(intent?.preview.next_eligibility_not_before_ms)}</p>
        <label className='control-field'>操作原因<input value={reason} maxLength={512} disabled={mutation.isPending||conflict||!!intent?.reason} onChange={e=>setReason(e.target.value)}/></label>
        <label className='control-field'>验证码<input autoComplete='one-time-code' inputMode='numeric' maxLength={8} value={code} disabled={mutation.isPending||conflict} onChange={e=>setCode(e.target.value.replace(/\D/g,''))}/></label>
        {mutation.isError ? <p role='alert'>{conflict ? '状态已变化，已刷新；关闭后重新确认。' : '提交未确认；可使用同一意图重试，验证码已清除。'}</p> : null}
        <div className='control-dialog__actions'><AlertDialog.Cancel asChild><Button disabled={mutation.isPending}>取消</Button></AlertDialog.Cancel>
          <Button disabled={!reason.trim()||code.length<6||mutation.isPending||conflict} onClick={()=>mutation.mutate()}>确认提交</Button></div>
      </AlertDialog.Content></AlertDialog.Portal>
    </AlertDialog.Root>
  </Panel>;
}
