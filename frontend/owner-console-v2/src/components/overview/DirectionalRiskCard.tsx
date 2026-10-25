import { useRef, useState } from 'react';
import Decimal from 'decimal.js';
import { useQuery } from '@tanstack/react-query';
import { changeDirectionalRisk, fetchDirectionalRisk, fetchDirectionalReceipt } from '../../api/directionalRiskApi';
import type { DirectionalRiskBody } from '../../api/directionalRiskApi';
import { TotpActionModal } from '../TotpActionModal';
import { ApiError } from '../../api/errors';

const labels = { unset: '未设置', bullish: '偏多', neutral: '中性', bearish: '偏空' };
type View = 'bullish' | 'neutral' | 'bearish';
type FrozenRequest = Omit<DirectionalRiskBody, 'totp_code'> & { scopeKey: string };
const storageKey = 'brc-directional-risk-pending';
function restore(): FrozenRequest | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(storageKey) || 'null');
    return value && ['bullish','neutral','bearish'].includes(value.view) && typeof value.scopeKey === 'string' && typeof value.idempotency_key === 'string' && typeof value.reason === 'string' && Number.isInteger(value.expected_version) ? value : null;
  } catch { return null; }
}
const pct = (value: string) => new Decimal(value).mul(100).toDecimalPlaces(4).toString() + '%';

export function DirectionalRiskCard() {
  const query = useQuery({ queryKey: ['owner', 'directional-risk'], queryFn: fetchDirectionalRisk, refetchInterval: 5000 });
  const [frozen, setFrozen] = useState<FrozenRequest | null>(restore);
  const [target, setTarget] = useState<View | null>(null);
  const [baseline, setBaseline] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const state = query.data;
  const select = (view: View) => { if (!state || frozen || busyRef.current) return; setTarget(view); setBaseline(state.control.version); setError(null); };
  const submit = async ({ totp, reason }: { totp: string; reason: string }) => {
    if (busyRef.current || query.isError || !state || (!frozen && (!target || baseline === null))) return;
    const scopeKey = `${state.control.venue_id}:${state.control.account_id}`;
    if (frozen && frozen.scopeKey !== scopeKey) { setError('上次请求属于不同账户，不能在当前账户重试。'); return; }
    const operation = frozen ?? { view: target!, expected_version: baseline!, reason, idempotency_key: crypto.randomUUID(), scopeKey };
    busyRef.current = true; setBusy(true); setFrozen(operation);
    // Store only request identity and rationale, never the authentication proof.
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(operation));
      const { scopeKey: _scope, ...body } = operation;
      const result = await changeDirectionalRisk({ ...body, totp_code: totp });
      setMessage(result.pending_view ? '请求已保存，正在等待已授权交易处理完成。' : '方向风险偏好已生效。');
      sessionStorage.removeItem(storageKey); setFrozen(null); setTarget(null); setError(null);
      await query.refetch();
    } catch (err) {
      setError(err instanceof Error ? err.message : '请求结果未确认');
      if (err instanceof ApiError && err.status < 500) {
        if (frozen) return; // A refused retry does not resolve the original unknown request.
        // Explicit server refusal is not an unknown transport result.
        sessionStorage.removeItem(storageKey); setFrozen(null);
        if (err.status === 409) { setTarget(null); await query.refetch(); }
      }
    } finally { busyRef.current = false; setBusy(false); }
  };
  const pending = Boolean(state?.control.pending_view);
  const verify = async () => {
    if (!frozen || busyRef.current) return;
    busyRef.current = true; setBusy(true);
    try {
      const receipt = await fetchDirectionalReceipt(frozen.idempotency_key);
      if (`${receipt.current.venue_id}:${receipt.current.account_id}` !== frozen.scopeKey) throw new Error('当前账户与原请求不同，不能核验。');
      if (receipt.result || receipt.current.version > frozen.expected_version) {
        sessionStorage.removeItem(storageKey); setFrozen(null); setTarget(null); setError(null);
        setMessage(receipt.result ? '已核验：服务端记录了原请求，当前生效状态如下。' : '已核验：原请求未记录，控制版本已变化；原请求不能再生效。');
        await query.refetch();
      } else setError('尚未查到原请求回执。保持原请求身份，可以使用新的验证码安全重试。');
    } catch (err) { setError(err instanceof Error ? err.message : '核验失败'); }
    finally { busyRef.current = false; setBusy(false); }
  };
  return <section className="rounded-xl border border-border bg-surface p-4 space-y-3" aria-label="方向风险偏好">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="text-sm font-semibold text-text-primary">方向风险偏好</h2>
      <button type="button" className="text-xs text-brand" onClick={() => void query.refetch()}>刷新状态</button>
    </div>
    {query.isError ? <p role="alert" className="text-sm text-danger">无法读取方向风险控制，暂不能修改。</p> : !state ? <p className="text-sm text-text-muted">正在读取方向风险控制…</p> : <>
      <p className="text-sm text-text-primary" role="status">{pending ? `切换中：${labels[state.control.pending_view!]}，当前仍为${labels[state.control.view]}` : `当前：${labels[state.control.view]}`}</p>
      <div className="flex flex-wrap gap-2" aria-label="选择市场立场">{(['bullish','neutral','bearish'] as const).map(view => <button type="button" key={view} aria-pressed={!pending && state.control.view === view} disabled={pending || busy || Boolean(frozen)} onClick={() => select(view)} className="rounded-md border border-border px-4 py-2 text-sm text-text-primary disabled:opacity-40 aria-pressed:bg-brand aria-pressed:text-white focus-visible:ring-2 focus-visible:ring-brand">{labels[view]}</button>)}</div>
      <dl className="grid grid-cols-2 gap-4 text-sm">
        <div><dt className="text-text-muted">多头风险上限</dt><dd className="font-semibold">{pct(state.long_limit)} · 已占用 {new Decimal(state.long_risk_at_stop).toFixed(2)} USDT</dd></div>
        <div><dt className="text-text-muted">空头风险上限</dt><dd className="font-semibold">{pct(state.short_limit)} · 已占用 {new Decimal(state.short_risk_at_stop).toFixed(2)} USDT</dd></div>
      </dl>
      <p className="text-xs text-text-muted">用于已授权的 Crypto 新开仓，不直接控制其他产品。上限按钱包余额的计划止损风险计算。已有持仓继续管理；实际持仓方向不由此按钮直接调整。新增交易仍需通过全部风险检查。</p>
      {state.balance_captured_at_ms ? <p className="text-xs text-text-muted">最近准入余额快照：{state.wallet_balance_at_last_admission} USDT（{new Date(state.balance_captured_at_ms).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}），非实时余额。{state.long_over_limit_at_last_balance || state.short_over_limit_at_last_balance ? '按此快照测算，已有方向占用超过当前上限；已有持仓继续受保护。' : '可新增额度仍以实际开仓前核验为准。'}</p> : <p className="text-xs text-text-muted">尚无准入余额快照，当前超限状态未知。实际开仓前核验最新余额。</p>}
      <p className="text-xs text-text-muted">生效时间：{new Date(state.control.effective_at_ms).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}</p>
      {state.review_due && <p className="text-xs text-status-amber">建议复核当前判断，原选择持续有效。</p>}
    </>}
    {message && <p role="status" className="text-xs text-text-secondary">{message}</p>}
    {error && !target && !frozen && <p role="alert" className="text-xs text-danger">{error}</p>}
    {frozen && <p className="text-xs text-status-amber">上次请求尚待确认。重试将核验同一请求，不创建新的变更。</p>}
    <TotpActionModal open={Boolean(target || frozen)} onOpenChange={open => { if (!open && !frozen && !busyRef.current) setTarget(null); }} title={`确认${labels[frozen?.view ?? target ?? 'neutral']}风险偏好`} description={`新预设：多头上限 ${(frozen?.view ?? target) === 'bearish' ? '2%' : '4%'}，空头上限 ${(frozen?.view ?? target) === 'bullish' ? '2%' : '4%'}，基础风控更严格时取更低值。仅限制 Crypto 新开仓风险，不自动平仓，不解除维护暂停。逆向机会仍可交易；切换可能等待已授权交易处理完成。`} confirmLabel={frozen ? '核验并重试原请求' : '确认变更'} expectedVersion={frozen?.expected_version ?? baseline} requireTotp defaultReason={frozen?.reason ?? 'Owner 更新方向风险判断'} isReasonFrozen={Boolean(frozen)} isSubmitting={busy} onVerifyStatus={frozen ? verify : undefined} errorMessage={error} onConfirm={submit} />
  </section>;
}
