import {useRef,useState} from 'react';
import Decimal from 'decimal.js';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {fetchRiskBudget,previewRiskBudget,changeRiskBudget,fetchRiskBudgetReceipt} from '../../api/riskBudgetApi';
import type {RiskBudgetBody,RiskBudgetView} from '../../api/riskBudgetApi';
import {TotpActionModal} from '../TotpActionModal';
import {ApiError} from '../../api/errors';
const pct=(v:string)=>new Decimal(v).mul(100).toString()+'%';
const storageKey='brc-risk-budget-request';
type Frozen=Omit<RiskBudgetBody,'totp_code'>&{scopeKey:string};
function restore():Frozen|null{try{const v=JSON.parse(sessionStorage.getItem(storageKey)||'null');return v&&typeof v.scopeKey==='string'&&typeof v.baseline==='string'&&typeof v.idempotency_key==='string'&&typeof v.reason==='string'&&Number.isInteger(v.expected_version)&&Number.isInteger(v.expected_directional_version)?v:null;}catch{return null;}}
const errorText=(error:unknown)=>{
 if(error instanceof ApiError){
  if(error.status===409)return '配置版本已变化或已有变更正在处理，请刷新后重新预览。';
  if(error.status===401)return '登录已过期，请重新登录后核验原请求。';
  if(error.status===403)return '身份验证未通过，请核对验证码和当前登录状态。';
  if(error.status===422)return '参数不合法，请使用 2.0%～3.0%，步长 0.1 个百分点。';
  return '服务暂不可用，请核验原请求结果后再操作。';
 }
 return error instanceof Error?error.message:'请求结果尚未确认';
};
export function RiskBudgetCard(){
 const client=useQueryClient();
 const query=useQuery({queryKey:['owner','risk-budget'],queryFn:fetchRiskBudget,refetchInterval:5000});
 const [input,setInput]=useState('');const [preview,setPreview]=useState<RiskBudgetView|null>(null);
 const [frozen,setFrozen]=useState<Frozen|null>(restore);const [busy,setBusy]=useState(false);const lock=useRef(false);
 const [error,setError]=useState<string|null>(null);const [message,setMessage]=useState<string|null>(null);
 const state=query.data;const pending=Boolean(state?.pending_baseline||state?.pending_directional_view);
 const refresh=async()=>{await query.refetch();await client.invalidateQueries({queryKey:['owner','directional-risk']});};
 const prepare=async()=>{if(lock.current||!state||pending||frozen)return;lock.current=true;setBusy(true);setError(null);try{const value=new Decimal(input||new Decimal(state.baseline).mul(100)).div(100);if(!value.gte('.02')||!value.lte('.03')||!value.mod('.001').isZero())throw new Error('请输入 2.0% 至 3.0%，步长 0.1 个百分点。');setPreview(await previewRiskBudget(value.toFixed(3)));}catch(e){setError(errorText(e));}finally{lock.current=false;setBusy(false);}};
 const verify=async()=>{if(!frozen||lock.current)return;lock.current=true;setBusy(true);try{const current=await fetchRiskBudget();if(`${current.venue_id}:${current.account_id}`!==frozen.scopeKey)throw new Error('当前账户与原请求不同。');const receipt=await fetchRiskBudgetReceipt(frozen.idempotency_key);if(receipt||current.policy_version>frozen.expected_version||current.directional_version>frozen.expected_directional_version){sessionStorage.removeItem(storageKey);setFrozen(null);setPreview(null);setError(null);setMessage(receipt?.status==='pending'?'请求已保存，等待生效。':receipt?'原请求结果已确认。':'原请求未记录，配置版本已变化，需重新预览。');await refresh();}else setError('尚未查到回执，保留同一请求身份后重试。');}catch(e){setError(errorText(e));}finally{lock.current=false;setBusy(false);}};
 const submit=async({totp,reason}:{totp:string;reason:string})=>{if(lock.current||!state||query.isError||(!frozen&&!preview))return;const scopeKey=`${state.venue_id}:${state.account_id}`;if(frozen&&frozen.scopeKey!==scopeKey){setError('当前账户与原请求不同。');return;}const operation=frozen??{scopeKey,baseline:preview!.baseline,expected_version:preview!.policy_version,expected_directional_version:preview!.directional_version,reason,idempotency_key:crypto.randomUUID()};lock.current=true;setBusy(true);setFrozen(operation);try{sessionStorage.setItem(storageKey,JSON.stringify(operation));const {scopeKey:_scope,...body}=operation;const result=await changeRiskBudget({...body,totp_code:totp});setMessage(result.status==='pending'?'请求已保存，等待生效。':result.status==='unchanged'?'配置未变化。':'风险预算已生效。');sessionStorage.removeItem(storageKey);setFrozen(null);setPreview(null);setInput('');setError(null);await refresh();}catch(e){setError(errorText(e));if(e instanceof ApiError&&e.status<500&&!frozen){sessionStorage.removeItem(storageKey);setFrozen(null);if(e.status===409){setPreview(null);await refresh();}}}finally{lock.current=false;setBusy(false);}};
 return <section aria-label="风险预算" className="rounded-xl border border-border bg-surface p-4 space-y-3"><h2 className="text-sm font-semibold text-text-primary">风险预算</h2>
 {query.isError?<p role="alert">无法读取风险预算，暂不能修改。</p>:!state?<p>正在读取风险预算…</p>:<>
 <p role="status">当前单笔上限：{pct(state.baseline)}{state.pending_baseline?` · ${pct(state.pending_baseline)} 等待生效`:state.pending_directional_view?' · 方向切换中':''}</p>
 <dl className="grid grid-cols-2 gap-3 text-sm"><div><dt>总风险上限</dt><dd>{pct(state.gross_limit)}</dd></div><div><dt>最低单笔风险量</dt><dd>{pct(state.minimum_risk)}（目标的 50%）</dd></div><div><dt>多头上限</dt><dd>{pct(state.long_limit)}</dd></div><div><dt>空头上限</dt><dd>{pct(state.short_limit)}</dd></div></dl>
 <label className="block text-sm">单笔风险上限（%）<input type="number" min="2" max="3" step="0.1" value={input||new Decimal(state.baseline).mul(100).toString()} onChange={e=>setInput(e.target.value)} disabled={pending||busy||Boolean(frozen)} className="ml-3 w-24 rounded border border-border bg-surface px-2 py-1"/></label>
 <button type="button" disabled={pending||busy||Boolean(frozen)} onClick={()=>void prepare()} className="rounded bg-brand px-4 py-2 text-sm text-white disabled:opacity-40">预览修改</button>
 <p className="text-xs text-text-muted">作用于本账户已授权策略的共享风险预算；不是持仓市值比例。总风险和方向额度自动联动。最多三笔，保证金限制和杠杆保持不变。上调可能因最低实现门槛过滤更多窄止损交易。</p>
 <p className="text-xs text-text-muted">已有持仓继续保护，不自动加仓或平仓。{state.entry_enabled?'修改不会额外授予交易权限。':'全局 ENTRY 已暂停，修改后仍保持暂停。'}</p>
 {state.wallet_balance_at_last_admission&&state.balance_captured_at_ms&&<p className="text-xs text-text-muted">最近准入余额 {state.wallet_balance_at_last_admission} USDT（{new Date(state.balance_captured_at_ms).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})}），非实时余额；实际额度在开仓前核验。{new Decimal(state.long_risk_at_stop).gt(new Decimal(state.wallet_balance_at_last_admission).mul(state.long_limit))||new Decimal(state.short_risk_at_stop).gt(new Decimal(state.wallet_balance_at_last_admission).mul(state.short_limit))?'按此快照，存量超过方向上限；存量继续保护，新增受限。':''}</p>}
 </>}
 {message&&<p role="status">{message}</p>}{error&&!preview&&!frozen&&<p role="alert">{error}</p>}
 <TotpActionModal open={Boolean(preview||frozen)} onOpenChange={open=>{if(!open&&!frozen&&!lock.current)setPreview(null);}} title="确认风险预算" description={preview?`单笔 ${pct(state?.baseline||preview.baseline)} → ${pct(preview.baseline)}；总计 ${pct(preview.gross_limit)}；多头 ${pct(preview.long_limit)}、空头 ${pct(preview.short_limit)}；最低单笔 ${pct(preview.minimum_risk)}。存量继续管理，生效可能等待已授权入场完成。`:'核验原请求，不能把未确认的请求当作失败重新提交。'} confirmLabel={frozen?'核验并重试原请求':'确认修改'} expectedVersion={frozen?.expected_version??preview?.policy_version??null} requireTotp defaultReason={frozen?.reason??'Owner 调整风险预算'} isReasonFrozen={Boolean(frozen)} isSubmitting={busy} errorMessage={error} onVerifyStatus={frozen?verify:undefined} onConfirm={submit}/>
 </section>;
}
