import {useEffect,useState} from 'react';
import {apiClient} from '../../api/client';
import {apiErrorFromResponse} from '../../api/errors';
import {ApiError} from '../../api/errors';
import {TotpActionModal} from '../TotpActionModal';

type Preview={request_id:string;ticket_id:string;expected_review_id:string;state:string;preview_digest:string|null;
 preview?:{entry_quantity:string;exit_quantity:string;old_metrics:Record<string,unknown>;metrics:Record<string,unknown>}|null};
type Approval={request_id:string;approved_preview_digest:string;expected_version:number;reason:string;idempotency_key:string};
function metric(value:unknown){if(value==='complete')return '已完整';if(value==='external_exit_unavailable')return '退出成交明细待补齐';if(value==='funding_unavailable')return '资金费待核实';return typeof value==='string'?value:'待核实';}
export function ReviewEnrichmentPanel({ticketId,revision}:{ticketId:string;revision:number}){
 const key=`brc:review-enrichment:${ticketId}`;
 const [preview,setPreview]=useState<Preview|null>(null);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState<string|null>(null);
 const [open,setOpen]=useState(false);
 const [pending,setPending]=useState<Approval|null>(()=>{try{return JSON.parse(sessionStorage.getItem(key)??'null');}catch{return null;}});
 useEffect(()=>{setPreview(null);setError(null);setOpen(false);try{setPending(JSON.parse(sessionStorage.getItem(key)??'null'));}catch{setPending(null);}},[key]);
 const read=async(id:string)=>{
  const r=await apiClient.GET('/api/owner/v1/controls/review-enrichment/requests/{request_id}',{params:{path:{request_id:id}}});
  if(!r.response.ok||!r.data)throw apiErrorFromResponse(r.response,r.error);
  const data=r.data as unknown as Preview;
  if(data.ticket_id!==ticketId||data.request_id!==id)throw new Error('核算预览身份不一致');
  setPreview(data);return data;
 };
 const verify=async()=>{
  if(!pending)return;setBusy(true);setError(null);
  try{const data=await read(pending.request_id);
   if(data.preview_digest===pending.approved_preview_digest&&['approved','applied'].includes(data.state)){
    sessionStorage.removeItem(key);setPending(null);setOpen(false);
   }else setError('原请求尚未确认，继续保留原请求核实。');
  }catch(e){setError(e instanceof Error?e.message:'核实失败');}finally{setBusy(false);}
 };
 const prepare=async()=>{setBusy(true);setError(null);try{
  if(preview){await read(preview.request_id);return;}
  const r=await apiClient.POST('/api/owner/v1/controls/review-enrichment/{ticket_id}/request',{params:{path:{ticket_id:ticketId}}});
  if(!r.response.ok||!r.data)throw apiErrorFromResponse(r.response,r.error);
  const id=r.data.request_id;if(!id)throw new Error('预览请求回执缺失');await read(id);
 }catch(e){setError(e instanceof Error?e.message:'预览失败');}finally{setBusy(false);}};
 const approve=async({totp,reason}:{totp:string;reason:string})=>{
  if(!preview?.preview_digest||pending)return;
  const op:Approval={request_id:preview.request_id,approved_preview_digest:preview.preview_digest,
   expected_version:revision,reason,idempotency_key:`review-enrichment:${crypto.randomUUID()}`};
  sessionStorage.setItem(key,JSON.stringify(op));setPending(op);setBusy(true);setError(null);
  try{const r=await apiClient.POST('/api/owner/v1/controls/review-enrichment/apply',{body:{...op,totp_code:totp}});
   if(!r.response.ok||!r.data)throw apiErrorFromResponse(r.response,r.error);
   const data=await read(op.request_id);
   if(data.preview_digest!==op.approved_preview_digest||!['approved','applied'].includes(data.state))throw new Error('批准结果尚待核实');
   sessionStorage.removeItem(key);setPending(null);setOpen(false);
  }catch(e){if(e instanceof ApiError&&e.status>=400&&e.status<500&&e.status!==408){sessionStorage.removeItem(key);setPending(null);setPreview(null);}setError(e instanceof Error?e.message:'批准结果未知');}
  finally{setBusy(false);}
 };
 return <section className="rounded border border-border p-3 text-xs space-y-2" aria-label="核算补证据">
  <p className="font-semibold">核算补证据</p><p>仅补齐已终态交易的核算记录，保留原版本。不会操作订单或恢复自动管理。</p>
  <button disabled={busy||!!pending} onClick={()=>void prepare()} className="text-brand">{preview?'刷新核算预览':'生成核算补齐预览'}</button>
  {preview&&<><p>{({pending:'证据核验中',preview_ready:'差异已就绪，待复核',approved:'已批准，等待记账',applied:'已追加核算版本',superseded:'原记录已变更，请重新核实'} as Record<string,string>)[preview.state]??'状态待核实'}</p>
   {preview.preview&&<><p>入场总量 {preview.preview.entry_quantity} · 退出总量 {preview.preview.exit_quantity}</p>
    <table className="w-full"><thead><tr><th>核算项</th><th>原记录</th><th>补齐结果</th></tr></thead><tbody>
     {([['gross_realized_pnl_quote','交易毛盈亏'],['trading_fees_quote','手续费'],['funding_quote','资金费'],['net_pnl_quote','净盈亏'],['economics_completeness','证据完整性']] as const).map(([field,label])=><tr key={field}><th>{label}</th><td>{metric(preview.preview?.old_metrics?.[field])}</td><td>{metric(preview.preview?.metrics[field])}</td></tr>)}
    </tbody></table></>}
   {preview.state==='preview_ready'&&<button disabled={busy||!!pending} onClick={()=>setOpen(true)} className="text-brand">复核差异并通过 TOTP 批准</button>}
  </>}
  {pending&&<button disabled={busy} onClick={()=>void verify()} className="text-brand">核实原批准请求</button>}
  {error&&<p role="alert">{error}</p>}
  <TotpActionModal open={open} onOpenChange={setOpen} title="批准核算补齐" description="仅批准当前预览的经济记录修订，原记录保留。" confirmLabel="批准本次差异" expectedVersion={revision} isSubmitting={busy} isUnknownResult={!!pending} onConfirm={approve} onVerifyStatus={verify} errorMessage={error}/>
 </section>;
}
