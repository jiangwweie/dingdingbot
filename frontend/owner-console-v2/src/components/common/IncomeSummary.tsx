import type { PerformanceSummary, ExitScope } from '../../api/performanceApi';
import { formatReviewMoneyMetric } from '../../mapping/reviewMapping';
import { formatShanghaiRangeDisplay } from '../../utils/timeRange';
const scopes: [ExitScope,string][]=[['all','全部实际交易'],['strategy','策略自身退出'],['owner','Owner 平仓'],['safety','安全恢复退出'],['unknown','退出原因未知']];
export function IncomeScopeBar({view='all',scope='all',onChange}:{view?:'all'|'current';scope?:ExitScope;onChange:(patch:{view?:'all'|'current';exit_scope?:ExitScope})=>void}) {
 return <div className="flex flex-wrap items-center gap-3 rounded border border-border bg-surface p-3 text-xs" data-testid="income-scope-bar">
  <label>收益范围 <select aria-label="收益范围" value={scope} onChange={e=>onChange({exit_scope:e.target.value as ExitScope})} className="ml-2 rounded border border-border bg-surface px-2 py-1">{scopes.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
  <label>版本范围 <select aria-label="版本范围" value={view} onChange={e=>onChange({view:e.target.value as 'all'|'current'})} className="ml-2 rounded border border-border bg-surface px-2 py-1"><option value="all">全部版本</option><option value="current">仅当前版本</option></select></label>
  {['strategy_group_id','strategy_version_id','exchange_instrument_id','position_side'].some(key=>new URLSearchParams(window.location.search).has(key))&&<span className="text-text-muted">对账限定：{['strategy_group_id','strategy_version_id','exchange_instrument_id','position_side'].map(key=>new URLSearchParams(window.location.search).get(key)).filter(Boolean).join(' · ')} <a className="underline" href={(()=>{const q=new URLSearchParams(window.location.search);for(const key of ['strategy_group_id','strategy_version_id','exchange_instrument_id','position_side','drawer_tab'])q.delete(key);return `?${q}`;})()}>清除对账限定</a></span>}
  <span className="text-text-muted">上海时间 · 按交易终态归属 · 不含未成交终止与未结浮盈</span>
 </div>;
}
export function IncomeSummary({summary,error,onRefresh,onSelectTicket}:{summary:PerformanceSummary|null;error?:unknown;onRefresh:()=>void;onSelectTicket?:(id:string)=>void}) {
 if(error) return <div role="alert" className="rounded border border-amber-500 p-3 text-xs">全窗口收益统计读取失败，不能以已加载明细代替总额。{error instanceof Error ? error.message : ''}<button onClick={onRefresh} className="ml-2 underline">刷新整组数据</button></div>;
 if(!summary) return <div role="status" className="p-3 text-xs">正在统计完整筛选范围...</div>;
 const labels=[['net_pnl','已核实净盈亏'],['net_r','累计单笔净 R'],['fees','手续费'],['funding','资金费']] as const;
 return <section data-testid="income-summary" className="space-y-2">
  <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
   <div className="rounded border border-border bg-surface p-3"><div className="text-xs text-text-muted">全窗口已结束交易</div><strong className="mt-2 block font-mono text-xl">{summary.sample_count}</strong><div className="text-[10px] text-text-muted">核算完整 {summary.confirmed_count} · 未核实 {summary.sample_count-summary.confirmed_count}</div></div>
   {labels.map(([key,label])=>{const metric=summary.verified_totals[key];const coverage=summary.metric_coverage[key];const money=formatReviewMoneyMetric(metric,{sign:key==='net_pnl'||key==='net_r',fractionDigits:key==='net_r'?4:2});return <div key={key} data-testid={`income-${key}`} className="rounded border border-border bg-surface p-3">
    <div className="text-xs text-text-muted">{label}</div><strong className={`mt-2 block font-mono text-lg ${money.isPositive===true?'text-emerald-600':money.isPositive===false?'text-rose-600':'text-text-secondary'}`}>{money.formatted}</strong>
    <div className="mt-1 text-[10px] text-text-muted">{coverage.available_count<coverage.total_count?'已核实部分合计':'已核实合计'} · 覆盖 {coverage.available_count}/{coverage.total_count} 笔</div>
    {coverage.missing_ticket_ids.length>0&&<details className="mt-1 text-[10px] text-amber-600"><summary>查看缺项交易</summary>{coverage.missing_ticket_ids.map(id=><button key={id} className="block break-all text-left underline" onClick={()=>onSelectTicket?.(id)}>{id}</button>)}</details>}
   </div>})}
  </div>
  <p className="text-[11px] text-text-muted" data-testid="income-scope-note">全窗口统计，与明细分页无关。{scopes.find(([key])=>key===summary.exit_scope)?.[1]} · {summary.view==='all'?'全部版本':'仅当前版本'} · {formatShanghaiRangeDisplay(summary.from_ms,summary.to_ms)}。缺失费用不按 0 计算；累计单笔净 R 不是账户收益率。</p>
  <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">{scopes.slice(1).map(([kind,label])=>{const part=summary.breakdown[kind];return <div key={kind} className="rounded border border-border bg-surface p-2 text-xs"><strong>{label}</strong><div>{part.sample_count} 笔 · 已核实净额 {formatReviewMoneyMetric(part.verified_totals.net_pnl,{sign:true}).formatted}</div><div className="text-[10px] text-text-muted">核算覆盖 {part.confirmed_count}/{part.sample_count} · 分类分项基于同一基础窗口</div></div>})}</div>
  <details className="text-[10px] text-text-muted"><summary>统计版本</summary><span className="break-all">{summary.snapshot_id}</span></details>
 </section>;
}
