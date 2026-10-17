import Decimal from 'decimal.js';
export const MoneyDecimal = Decimal.clone({precision:80});
export function priceFacts(p: {actual_entry_price?:string|null;entry_reference_price?:string|null;active_stop_price?:string|null;initial_stop_price?:string|null}) {
  return {actual:p.actual_entry_price??'未取得',reference:p.entry_reference_price??'未取得',activeStop:p.active_stop_price??'未取得',initialStop:p.initial_stop_price??'未取得'};
}
export function protectionFact(status:string) {
  if (['position_protected','runner_protected'].includes(status)) return {kind:'confirmed',confirmed:true,label:'后端已确认保护'};
  if (status.includes('outcome_unknown')) return {kind:'unknown',confirmed:false,label:'结果未知 · 保护状态待核实'};
  if (status.includes('rejected') || status.includes('incident')) return {kind:'risk',confirmed:false,label:'存在拒绝或异常 · 需核实保护'};
  if (['protection_pending','post_fill_risk_pending','tp1_pending','runner_replacement_pending','runner_old_stop_cancel_pending'].includes(status)) return {kind:'transition',confirmed:false,label:'保护安装或切换进行中'};
  return {kind:'insufficient',confirmed:false,label:'保护证据不足 · '+status};
}
export function terminalFact(t: {ticket_status:string;net_pnl?:{value?:string|null;unavailable_reason?:string|null};net_r?:{value?:string|null;unavailable_reason?:string|null}}) {
  if (['leverage_rejected','entry_rejected','entry_reconciled_absent'].includes(t.ticket_status)) return '未成交终止';
  if (t.ticket_status !== 'terminal') return '已结束 · 终态证据不足';
  if (t.net_pnl?.value != null && t.net_r?.value != null && !t.net_pnl.unavailable_reason && !t.net_r.unavailable_reason) return '已结算';
  if (t.net_pnl?.unavailable_reason==='review_missing') return '结算或 Review 证据待完成';
  return '已结束 · 经济数据不可用';
}
export function activeCoverage(loaded:string[], overview:{active_ticket_ids:string[];active_ticket_count:number|null}|null|undefined, fresh:boolean) {
  const ids=overview?.active_ticket_ids??[];
  const missing=ids.filter(id=>!loaded.includes(id));
  const extra=loaded.filter(id=>!ids.includes(id));
  const complete=!!overview && fresh && overview.active_ticket_count===ids.length && new Set(ids).size===ids.length && missing.length===0 && extra.length===0;
  return {complete,missing,extra,count:overview?.active_ticket_count??null};
}
