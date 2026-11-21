import Decimal from 'decimal.js';
import {useEffect,useState} from 'react';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {TotpActionModal} from '../TotpActionModal';
import {ApiError} from '../../api/errors';
import {
 fetchExitConfiguration,previewExitConfiguration,activateExitConfiguration,fetchExitConfigurationReceipt,previewExitSizing, type ExitSizingView,
 type ExitConfigurationIntent,type ExitConfigurationPreview,type ExitConfigurationBody,
} from '../../api/exitConfigurationApi';

const pendingKey='brc:exit-configuration:pending';
type Pending=Omit<ExitConfigurationBody,'totp_code'>;
function readPending():Pending|null {
 try {return JSON.parse(sessionStorage.getItem(pendingKey)??'null');} catch {return null;}
}
const standaloneLong = 'event_spec:SOR-1H-LONG-001:SOR-1H-LONG:v1';
const standaloneShort = 'event_spec:SOR-1H-SHORT-001:SOR-1H-SHORT:v1';
function label(event:string){
 if (event === standaloneLong) return 'SOR-多';
 if (event === standaloneShort) return 'SOR-空';
 const parts=event.split(':');
 return `${parts[1]} · ${parts[2].endsWith('SHORT')?'SHORT':'LONG'}`;
}

export function ExitConfigurationPanel(){
 const client=useQueryClient();
 const query=useQuery({queryKey:['exit-configuration'],queryFn:fetchExitConfiguration});
 const [draft,setDraft]=useState<ExitConfigurationIntent|null>(null);
 const splitTransfer=!!draft?.events.some(e=>e.event_spec_id===standaloneLong)
  && !!query.data?.current?.intent?.events?.some(e=>e.event_spec_id.includes('SOR-1H-001'));
 const [preview,setPreview]=useState<ExitConfigurationPreview|null>(null);
 const [pending,setPending]=useState<Pending|null>(readPending);
 const [busy,setBusy]=useState(false);
 const [open,setOpen]=useState(false);
 const [sizing,setSizing]=useState<ExitSizingView|null>(null);
 const [sizingInputs,setSizingInputs]=useState({event:'',symbol:'BTCUSDT',quantity:'0.007',entry:'65000',stop:'64000'});
 const [error,setError]=useState<string|null>(null);
 useEffect(()=>{if(query.data && !pending){setDraft(query.data.intent);setPreview(null);}},[query.data,pending]);
 const update=(event:string,field:string,value:string|boolean)=>{
  setDraft(current=>current?{...current,events:current.events.map(e=>e.event_spec_id===event?{...e,[field]:value}:e)}:null);
  setPreview(null);setSizing(null);setError(null);
 };
 const refresh=async()=>{await client.invalidateQueries({queryKey:['exit-configuration']});};
 const verify=async()=>{
  if(!pending)return;
  setBusy(true);
  try{
   const receipt=await fetchExitConfigurationReceipt(pending.idempotency_key);
   if(receipt && receipt.intent.account_id===pending.intent.account_id && receipt.intent.product_id===pending.intent.product_id
      && receipt.revision===pending.expected_version+1 && receipt.preview_digest===pending.preview_digest){
    sessionStorage.removeItem(pendingKey);setPending(null);setOpen(false);setError(null);await refresh();
   }else setError('该请求尚无已提交结果；保留原请求，请继续核实。');
  }catch(e){setError(e instanceof Error?e.message:'结果核实失败');}finally{setBusy(false);}
 };
 const submit=async({totp,reason}:{totp:string;reason:string})=>{
  if(!preview || pending)return;
  const operation:Pending={intent:preview.intent,expected_version:preview.intent.expected_revision,
   preview_digest:preview.preview_digest,preview_valid_until_ms:preview.valid_until_ms,
   idempotency_key:`exit-config:${crypto.randomUUID()}`,reason};
  sessionStorage.setItem(pendingKey,JSON.stringify(operation));setPending(operation);setBusy(true);setError(null);
  try{
   const result=await activateExitConfiguration({...operation,totp_code:totp});
   if(result.revision!==operation.expected_version+1 || result.intent.account_id!==operation.intent.account_id || result.preview_digest!==operation.preview_digest)throw new Error('提交回执身份不一致，需核实');
   sessionStorage.removeItem(pendingKey);setPending(null);setOpen(false);setPreview(null);await refresh();
  }catch(e){
   if(e instanceof ApiError && e.status>=400 && e.status<500 && e.status!==408){
    sessionStorage.removeItem(pendingKey);setPending(null);setPreview(null);
   }
   setError(e instanceof Error?e.message:'提交结果未知，请核实原请求');
  }finally{setBusy(false);}
 };
 return <section className="rounded-xl border border-border bg-surface p-4 space-y-3" aria-label="TP1 与 MA50 参数">
  <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold">TP1 与 MA50 参数</h2>
   <button type="button" disabled={busy} onClick={()=>void query.refetch()} className="text-sm text-brand">刷新配置</button></div>
  <p className="text-xs text-text-secondary">按策略 Event／方向配置。退出配置仅影响新交易。SOR-多、CPM、MI 和 MPG 的 BTC MA50 可单独配置。</p>
  {query.isLoading?<p>读取配置中</p>:query.isError?<p role="alert">退出配置读取失败，当前无法编辑</p>:draft&&<>
   <p className="text-xs">{query.data?.current?`当前版本 ${query.data.current.revision}`:'尚未激活新版；首次激活采用已确认参数'}</p>
   <div className="overflow-x-auto"><table className="w-full text-xs"><thead><tr>{['策略／方向','TP1 倍数 R','目标比例','最小量提升','实际比例上限','BTC 4h > SMA50'].map(h=><th key={h} className="p-2 text-left">{h}</th>)}</tr></thead>
   <tbody>{draft.events.map(e=>{const sorLong=e.event_spec_id===standaloneLong;const sor=e.event_spec_id.includes('SOR-1H-001')||sorLong||e.event_spec_id===standaloneShort;const ma=sorLong||e.event_spec_id.includes('CPM-RO-001')||e.event_spec_id.includes('MI-001')||e.event_spec_id.includes('MPG-001');const locked=!query.data?.current||busy||!!pending||splitTransfer;
    return <tr key={e.event_spec_id}><th className="p-2 text-left">{label(e.event_spec_id)}</th>
     <td className="p-2"><input aria-label={`${label(e.event_spec_id)} TP1倍数`} type="number" min="0.1" max="5" step="0.1" value={e.reward_multiple} disabled={locked} onChange={v=>update(e.event_spec_id,'reward_multiple',v.target.value)} className="w-20 rounded border border-border bg-surface p-1"/></td>
     <td className="p-2"><input aria-label={`${label(e.event_spec_id)} 目标比例`} type="number" min="0.001" max="0.5" step="0.01" value={e.target_fraction} disabled={locked||sor} onChange={v=>update(e.event_spec_id,'target_fraction',v.target.value)} className="w-20 rounded border border-border bg-surface p-1"/></td>
     <td className="p-2"><input aria-label={`${label(e.event_spec_id)} 最小量提升`} type="checkbox" checked={e.minimum_lift} disabled={locked||sor} onChange={v=>update(e.event_spec_id,'minimum_lift',v.target.checked)}/>{sor?'原规则':''}</td>
     <td className="p-2"><input aria-label={`${label(e.event_spec_id)} 实际比例上限`} type="number" min="0.001" max="0.5" step="0.01" value={e.max_actual_fraction} disabled={locked||sor} onChange={v=>update(e.event_spec_id,'max_actual_fraction',v.target.value)} className="w-20 rounded border border-border bg-surface p-1"/></td>
     <td className="p-2">{ma?<input aria-label={`${label(e.event_spec_id)} MA50`} type="checkbox" checked={e.ma50_enabled} disabled={sorLong?(busy||!!pending):locked} onChange={v=>update(e.event_spec_id,'ma50_enabled',v.target.checked)}/>:'不适用'}</td></tr>;
   })}</tbody></table></div>
   {splitTransfer&&<p className="text-xs">首次切换继承当前退出参数，可选择是否开启 SOR-多的 MA50。</p>}
   <p className="text-xs text-text-muted">比例以小数填写，0.05 表示 5%。Runner、保本、保护与时间规则从原策略继承。预览不保证成交，策略暂停状态和全局开仓开关保持原值。</p>
   <details className="rounded border border-border p-3"><summary className="cursor-pointer text-sm">按当前已采集规则核实数量示例</summary>
    <p className="text-xs my-2">仅作预校验，原仓位不变。规则缺失或过期会明确拒绝；不保证成交。</p>
    <div className="flex flex-wrap gap-2 text-xs">
     <select aria-label="数量示例策略" value={sizingInputs.event||draft.events[0].event_spec_id} onChange={e=>{setSizingInputs(v=>({...v,event:e.target.value}));setSizing(null);}}>{draft.events.map(e=><option key={e.event_spec_id} value={e.event_spec_id}>{label(e.event_spec_id)}</option>)}</select>
     {(['symbol','quantity','entry','stop'] as const).map(field=><label key={field}>{({symbol:'标的',quantity:'入场数量',entry:'入场均价',stop:'初始止损'})[field]}<input aria-label={`数量示例${field}`} value={sizingInputs[field]} className="w-24 border border-border bg-surface p-1" onChange={e=>{setSizingInputs(v=>({...v,[field]:e.target.value}));setSizing(null);}}/></label>)}
     <button type="button" disabled={busy||!!pending} onClick={async()=>{
      const selected=draft.events.find(e=>e.event_spec_id===(sizingInputs.event||draft.events[0].event_spec_id));if(!selected)return;
      setBusy(true);setError(null);try{setSizing(await previewExitSizing({event_spec_id:selected.event_spec_id,parameters:selected,
       exchange_instrument_id:`binance-usdm:${sizingInputs.symbol.toUpperCase()}:perpetual`,quantity:sizingInputs.quantity,entry_price:sizingInputs.entry,initial_stop:sizingInputs.stop}));}catch(e){setError(e instanceof Error?e.message:'数量预览失败');}finally{setBusy(false);}
     }} className="text-brand">核实数量</button>
    </div>
    {sizing&&<p className="mt-2 text-xs" role="status">{sizing.blocker?`不可执行：${sizing.blocker}`:sizing.quantities?`TP ${sizing.quantities.tp_quantity} · 实际 ${new Decimal(sizing.quantities.actual_fraction).mul(100).toFixed(3)}% · Runner ${sizing.quantities.runner_quantity}${sizing.quantities.minimum_lifted?'（最小量提升）':''}`:'数量结果不可得'}</p>}
   </details>
   <button type="button" disabled={busy||!!pending} className="rounded bg-brand px-3 py-2 text-white text-sm" onClick={async()=>{
    setBusy(true);setError(null);try{setPreview(await previewExitConfiguration(draft));}catch(e){setError(e instanceof Error?e.message:'预览失败');}finally{setBusy(false);}
   }}>生成服务端预览</button>
   {preview&&<div className="rounded border border-border p-3 space-y-2"><p className="text-sm font-semibold">新旧配置差异 · 待确认</p>
    {preview.profiles.map(p=>{const old=query.data?.sources.find(s=>s.event_spec_id===p.event_spec_id)?.profile;return <p className="text-xs" key={p.event_spec_id}>{label(p.event_spec_id)}：TP1 {old?.tp1.reward_multiple}R → {p.profile.tp1.reward_multiple}R；目标 {old?.tp1.quantity_fraction} → {p.profile.tp1.quantity_fraction}；{p.profile.execution?.quantity_policy==='target_floor_then_minimum'?'不足时提升至最小量':'按原比例向下取整'}</p>;})}
    {preview.intent.events.map(event=>{
     const current=query.data?.current?.intent?.events.find(item=>item.event_spec_id===event.event_spec_id);
     if(current?.ma50_enabled===event.ma50_enabled||(!current&&!event.ma50_enabled))return null;
     const status=event.ma50_enabled?'开启':'关闭';
     return <p className="text-xs" key={event.event_spec_id}>{label(event.event_spec_id)} MA50：{status}</p>;
    })}
    <p className="text-xs">执行按实际完整入场均价计算 R；实际 TP 比例在每笔成交计划中显示。</p>
    <button type="button" disabled={busy||!!pending} className="text-brand text-sm" onClick={()=>setOpen(true)}>TOTP 确认激活</button></div>}
  </>}
  {error&&<p role="alert" className="text-sm text-amber-600">{error}</p>}
  {pending&&<button type="button" disabled={busy} onClick={()=>void verify()} className="text-brand text-sm">核实原激活请求</button>}
  <TotpActionModal open={open} onOpenChange={setOpen} title="激活退出配置" description="仅影响新交易；不恢复暂停策略，不恢复人工票自动管理。" confirmLabel="确认激活退出配置" expectedVersion={preview?.source_configuration_revision} isSubmitting={busy} isUnknownResult={!!pending} onConfirm={submit} onVerifyStatus={verify} errorMessage={error}/>
 </section>;
}
