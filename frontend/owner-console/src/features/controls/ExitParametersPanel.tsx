import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError } from "../../api/errors";
import { Button } from "../../components/ui/Button";
import { Panel } from "../../components/ui/Panel";
import { getExitParameters, previewExitParameters, publishExitParameters, type ExitBody, type ExitCurrent, type ExitPreview } from "./exitParametersApi";

type Row = ExitCurrent["rows"][number];
type Draft = { selected: boolean; reward: string; percent: string; cap: string; raise: boolean; ma50: boolean };
type Pending = { body: ExitBody; preview: ExitPreview };
function label(event: string) { const parts = event.split(":"); return `${parts[1]} · ${parts[2]?.includes("SHORT") ? "SHORT" : "LONG"}`; }
function sourceDraft(row: Row): Draft { return {selected:false,reward:row.profile.tp1.reward_multiple,percent:String(Number(row.profile.tp1.quantity_fraction)*100),
  raise:!!row.profile.tp1.quantity_rule,cap:String(Number(row.profile.tp1.quantity_rule?.max_actual_fraction ?? "0.50")*100),ma50:row.regime?.enabled ?? false}; }
export function percentFraction(value: string): string {
  if (!/^\d{1,2}(?:\.\d{1,4})?$/.test(value)) throw new Error("比例须为0至50之间的数字");
  const [whole="",decimal=""]=value.split("."); return `0.${whole.padStart(2,"0")}${decimal}`;
}
const inputClass="w-24 rounded border border-[var(--color-divider)] bg-[var(--color-background)] px-2 py-1 text-[12px]";

export function ExitParametersPanel() {
  const query=useQuery({queryKey:["owner","exit-parameters"],queryFn:getExitParameters});
  const [drafts,setDrafts]=useState<Record<string,Draft>>({});
  const [pending,setPending]=useState<Pending | null>(null);
  const [code,setCode]=useState("");
  const [message,setMessage]=useState("");
  const [sample,setSample]=useState({event:"",symbol:"BTCUSDT",quantity:"",entry:"",stop:""});
  function change(row: Row, fields: Partial<Draft>) {setDrafts(d=>({...d,[row.event_spec_id]:{...(d[row.event_spec_id]??sourceDraft(row)),...fields}}));setPending(null);setCode("");setMessage("");}
  const selected=(query.data?.rows??[]).filter(r=>(drafts[r.event_spec_id]??sourceDraft(r)).selected);
  const preview=useMutation({mutationFn:async()=>{
    const changes=selected.map(row=>{const d=drafts[row.event_spec_id]??sourceDraft(row);return {event_spec_id:row.event_spec_id,expected_version:row.binding.projection_version,
      expected_binding_id:row.binding.exit_binding_id,reward_multiple:d.reward,quantity_fraction:percentFraction(d.percent),
      max_actual_fraction:d.raise?percentFraction(d.cap):null,ma50_enabled:row.regime?d.ma50:null,expected_regime_revision:row.regime?.revision??null};});
    const body: ExitBody={expected_version:1,reason:"owner_exit_parameter_change",idempotency_key:`exit-parameters:${crypto.randomUUID()}`,changes,quantity_samples:[]};
    if(sample.quantity||sample.entry||sample.stop){
      const event=sample.event||selected[0]?.event_spec_id;
      if(!event||!selected.some(r=>r.event_spec_id===event)||!sample.quantity||!sample.entry||!sample.stop)throw new Error("数量示例需选中策略并完整填写数量、入场价和止损价");
      body.quantity_samples=[{event_spec_id:event,exchange_instrument_id:`binance-usdm:${sample.symbol.trim().toUpperCase()}:perpetual`,quantity:sample.quantity,entry_price:sample.entry,stop_price:sample.stop}];
    }
    return {body,preview:await previewExitParameters(body)};
  },onSuccess:result=>{setPending(result);setCode("");setMessage("");},onError:error=>{setPending(null);setMessage(error instanceof Error?error.message:"预览失败");}});
  const publish=useMutation({mutationFn:async()=>{if(!pending)throw new Error("请先预览");return publishExitParameters({...pending.body,totp_code:code});},
    onSuccess:async()=>{setPending(null);setDrafts({});setCode("");setMessage("新版本已发布，仅用于新交易；策略启停状态未改变。");await query.refetch();},
    onError:async(error)=>{setCode("");if(error instanceof ApiError&&error.status===409){setPending(null);setMessage("配置版本已变化或仍有入场发送处理中，请刷新后重新预览。");await query.refetch();}
      else setMessage("发布结果需核实；保留同一请求，输入验证码后可重试。"+ (error instanceof Error?` ${error.message}`:""));}});
  const busy=preview.isPending||publish.isPending;
  const sampleChange=(fields: Partial<typeof sample>)=>{setSample(s=>({...s,...fields}));setPending(null);setCode("");};
  return <Panel title="策略退出参数">
    <p className="mb-3 text-[12px] text-[var(--color-text-secondary)]">按策略和方向独立设置。TP1完整成交确认后才进入费用保本与原Runner；已有持仓使用其冻结版本。</p>
    {query.data?.btc_ma50?<p className="mb-3 text-[12px]">BTC 4h闭合收盘 {query.data.btc_ma50.close_price??"—"} ／ SMA50 {query.data.btc_ma50.sma50??"—"}；{query.data.btc_ma50.status==="allowed"?"收盘条件通过":query.data.btc_ma50.status==="btc4h_not_above_ma50"?"收盘条件未通过":"等待最新闭合数据"}。仅约束已启用该过滤的三策略新多单。{query.data.btc_ma50.latest_close_ms?` 闭合截至 ${new Date(query.data.btc_ma50.latest_close_ms).toISOString()}`:""}</p>:null}
    <div className="mb-3 flex gap-2">
      <Button disabled={busy||query.isFetching} onClick={()=>{setPending(null);setDrafts({});setCode("");void query.refetch();}}>刷新退出配置</Button>
      <Button disabled={busy||!query.data?.rows.length} onClick={()=>{setDrafts(Object.fromEntries((query.data?.rows??[]).map(row=>[row.event_spec_id,{...sourceDraft(row),selected:true,
        reward:row.event_spec_id.includes("SOR-1H-001")?"1.2":"1.0",percent:row.event_spec_id.includes("SOR-1H-001")?sourceDraft(row).percent:"5",
        raise:!row.event_spec_id.includes("SOR-1H-001"),cap:"50",ma50:!!row.regime}])));setPending(null);setCode("");}}>填入本次实验方案</Button>
    </div>
    {query.isError?<p role="alert">退出配置读取失败，提交已禁用。</p>:null}
    {query.isPending?<p>正在读取退出配置…</p>:null}
    {query.data&&!query.data.rows.length?<p>暂无可用的策略退出配置。</p>:null}
    {!!query.data?.rows.length?<div className="overflow-x-auto"><table className="w-full text-left text-[12px]"><thead><tr><th>选择／策略方向</th><th>当前版本</th><th>TP1倍数</th><th>目标比例%</th><th>最小量提升／上限%</th><th>BTC 4h MA50</th></tr></thead>
      <tbody>{query.data.rows.map(row=>{const d=drafts[row.event_spec_id]??sourceDraft(row),name=label(row.event_spec_id);return <tr key={row.event_spec_id} className="border-t border-[var(--color-divider)]">
        <td className="py-2"><label><input type="checkbox" disabled={busy} checked={d.selected} onChange={e=>change(row,{selected:e.target.checked})}/>{name}</label></td>
        <td>v{row.profile.exit_profile_version}<small className="block text-[10px]">{row.profile.tp1.price_basis === "actual_fill" ? "实际成交价" : "入场参考价"}</small></td>
        <td><input aria-label={`${name} TP1倍数`} className={inputClass} disabled={busy} type="number" min="0.1" max="5" step="0.1" value={d.reward} onChange={e=>change(row,{reward:e.target.value,selected:true})}/></td>
        <td><input aria-label={`${name} 目标比例`} className={inputClass} disabled={busy} type="number" min="0.01" max="50" step="0.1" value={d.percent} onChange={e=>change(row,{percent:e.target.value,selected:true})}/></td>
        <td><label><input type="checkbox" disabled={busy} checked={d.raise} onChange={e=>change(row,{raise:e.target.checked,selected:true})}/>允许提升</label><input aria-label={`${name} 实际比例上限`} className={inputClass} disabled={busy||!d.raise} type="number" max="50" min="0.01" value={d.cap} onChange={e=>change(row,{cap:e.target.value,selected:true})}/></td>
        <td>{row.regime?<label><input type="checkbox" disabled={busy} checked={d.ma50} onChange={e=>change(row,{ma50:e.target.checked,selected:true})}/>仅收盘价高于MA50准入</label>:"不适用"}</td>
      </tr>;})}</tbody></table></div>:null}
    <details className="my-3 text-[12px]"><summary>可选：验算具体仓位的真实TP1数量</summary><div className="mt-2 flex flex-wrap gap-2">
      <select aria-label="数量验算策略" value={sample.event} onChange={e=>sampleChange({event:e.target.value})}><option value="">第一个选中策略</option>{selected.map(r=><option key={r.event_spec_id} value={r.event_spec_id}>{label(r.event_spec_id)}</option>)}</select>
      {([ ["symbol","合约"],["quantity","整仓数量"],["entry","实际入场价"],["stop","初始止损价"] ] as const).map(([key,title])=><label key={key}>{title}<input className={inputClass} aria-label={title} value={sample[key]} disabled={busy} onChange={e=>sampleChange({[key]:e.target.value})}/></label>)}
    </div><p>按服务器持有的规则验算；规则陈旧会明确拒绝。展示真实比例，不增加入场仓位。</p></details>
    <Button disabled={busy||query.isError||query.isFetching||!selected.length} onClick={()=>void preview.mutateAsync().catch(()=>{})}>预览所选策略</Button>
    {pending?<div className="mt-3 rounded border border-[var(--color-divider)] p-3 text-[12px]">
      <strong>预览通过：{pending.body.changes.length}个策略事件将一起发布新版本。</strong>
      <ul>{pending.preview.profiles.map((profile,i)=>{const change=pending.body.changes[i]!,source=pending.preview.source_profiles[i];return <li key={profile.exit_profile_id}>{label(change.event_spec_id)}：{source?`原${source.tp1.reward_multiple}R／${Number(source.tp1.quantity_fraction)*100}% → `:""}实际成交价{profile.tp1.reward_multiple}R，目标{Number(profile.tp1.quantity_fraction)*100}%，{profile.tp1.quantity_rule?`最小数量提升上限${Number(profile.tp1.quantity_rule.max_actual_fraction)*100}%`:"严格向下取整"}；MA50{change.ma50_enabled==null?"不调整":change.ma50_enabled?"开启":"关闭"}</li>;})}</ul>
      {pending.preview.quantity_previews.map((q,i)=><p key={i}>{q.sample.exchange_instrument_id}：{q.plan?`TP1数量${q.plan.tp1_quantity}，实际${(Number(q.plan.actual_fraction)*100).toFixed(3)}%，剩余${q.plan.runner_quantity}`:`无法执行：${q.status}`}</p>)}
      <p>仅新交易生效，不会移动已有持仓止损，也不会恢复暂停策略。</p>
      <label>退出参数验证码<input aria-label="退出参数验证码" className={inputClass} autoComplete="one-time-code" value={code} maxLength={6} disabled={publish.isPending} onChange={e=>setCode(e.target.value.replace(/\D/g,""))}/></label>
      <Button disabled={publish.isPending||code.length!==6} onClick={()=>void publish.mutateAsync().catch(()=>{})}>确认发布新版本</Button>
    </div>:null}
    {message?<p role="status" className="mt-2 text-[12px]">{message}</p>:null}
    {query.data?.active_tickets.length?<details className="mt-3 text-[12px]"><summary>当前持仓冻结版本（{query.data.active_tickets.length}）</summary><ul>{query.data.active_tickets.map(t=><li key={t.ticket_id}>{label(t.event_spec_id)}：{t.exit_profile_id}；实际TP1比例{t.actual_tp1_fraction==null?"待成交计划确认":`${(Number(t.actual_tp1_fraction)*100).toFixed(3)}%`}</li>)}</ul></details>:null}
  </Panel>;
}
