import {useQuery} from '@tanstack/react-query';
import Decimal from 'decimal.js';
import {manualProtectionLabel} from '../../mapping/tradeTruth';
import {apiClient} from '../../api/client';
import {apiErrorFromResponse} from '../../api/errors';
function percent(value:string){return new Decimal(value).mul(100).toFixed(3).replace(/\.?0+$/,'')+'%';}
export function TicketExitPlan({ticketId}:{ticketId:string}){
 const query=useQuery({queryKey:['ticket-exit-plan',ticketId],queryFn:async()=>{
  const r=await apiClient.GET('/api/owner/v1/tickets/{ticket_id}/exit-plan',{params:{path:{ticket_id:ticketId}}});
  if(!r.response.ok||!r.data)throw apiErrorFromResponse(r.response,r.error);
  return r.data;
 },enabled:!!ticketId});
 const data=query.data;const plan=data?.plan;
 if(query.isError)return <p className="text-xs text-amber-600">退出计划读取失败</p>;
 if(!data)return <p className="text-xs text-text-muted">退出计划读取中</p>;
 if(!plan)return <p className="text-xs text-text-muted">实际成交退出计划不可得，保留原票据记录</p>;
 return <div className="rounded border border-border p-3 text-xs space-y-1" aria-label="实际 TP1 计划">
  <p className="font-semibold">实际 TP1 计划 · {data.management_mode}</p>
  <p>目标 {percent(plan.target_fraction)} · 实际 {percent(plan.quantities.actual_fraction)}{plan.quantities.minimum_lifted?'（最小可执行量提升）':''}</p>
  <p>TP1 {data.tp1_filled_quantity} / {data.tp1_target_quantity} · 当前余仓 {data.current_quantity}</p>
  <p>实际入场 {plan.entry_price} · 初始止损 {plan.initial_stop} · TP {plan.tp_price} · 实际 {new Decimal(plan.actual_multiple).toFixed(3)}R</p>
  <p>{data.management_mode==='MANUAL'?manualProtectionLabel(data.protection_reason,data.stop_present,data.protection_status):`保护确认量 ${data.protected_quantity} · 止损 ${data.active_stop_price??'待核实'}`}</p>
  <p>{data.management_mode==='MANUAL'?'自动计划已停止执行，原计划仅供审计':data.management_mode==='REVIEW_REQUIRED'?'订单归属待核实，自动处置暂停':data.aggregate_status==='runner_protected'?'Runner 保护已确认':new Decimal(data.tp1_filled_quantity).lt(data.tp1_target_quantity)?'TP1 尚未完整成交，未启动保本':'TP1 已完整成交，后续保护状态按确认结果显示'}</p>
 </div>;
}
