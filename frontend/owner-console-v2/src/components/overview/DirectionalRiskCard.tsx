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
    return value && ['bullish', 'neutral', 'bearish'].includes(value.view) && typeof value.scopeKey === 'string' && typeof value.idempotency_key === 'string' && typeof value.reason === 'string' && Number.isInteger(value.expected_version) ? value : null;
  } catch {
    return null;
  }
}

const pct = (value: string) => new Decimal(value).mul(100).toDecimalPlaces(4).toString() + '%';

export function computeRiskSlotSummary(
  limitStr: string,
  usedStr: string,
  balanceStr?: string | null
) {
  const used = new Decimal(usedStr);
  const usedFormatted = `${used.toFixed(2)} USDT`;
  const limitPctFormatted = pct(limitStr);

  if (balanceStr == null || balanceStr.trim() === '') {
    return {
      usedFormatted,
      limitPctFormatted,
      capFormatted: `快照上限未取得 (${limitPctFormatted})`,
      barPct: null as number | null,
      isUncomputable: true,
      hasPositiveRiskWithoutCap: used.gt(0),
    };
  }

  try {
    const bal = new Decimal(balanceStr);
    const lim = new Decimal(limitStr);
    const cap = bal.mul(lim);
    if (bal.lte(0) || lim.lte(0) || cap.lte(0)) {
      return {
        usedFormatted,
        limitPctFormatted,
        capFormatted: `快照上限无法计算 (${limitPctFormatted})`,
        barPct: null as number | null,
        isUncomputable: true,
        hasPositiveRiskWithoutCap: used.gt(0),
      };
    }
    const ratio = used.div(cap).mul(100).toNumber();
    const barPct = used.gt(0) ? Math.max(2, Math.min(100, Math.round(ratio))) : 0;
    return {
      usedFormatted,
      limitPctFormatted,
      capFormatted: `快照上限 ${cap.toFixed(2)} USDT (${limitPctFormatted})`,
      barPct,
      isUncomputable: false,
      hasPositiveRiskWithoutCap: false,
    };
  } catch {
    return {
      usedFormatted,
      limitPctFormatted,
      capFormatted: `快照上限无法计算 (${limitPctFormatted})`,
      barPct: null as number | null,
      isUncomputable: true,
      hasPositiveRiskWithoutCap: used.gt(0),
    };
  }
}

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

  const select = (view: View) => {
    if (!state || frozen || busyRef.current) return;
    setTarget(view);
    setBaseline(state.control.version);
    setError(null);
  };

  const submit = async ({ totp, reason }: { totp: string; reason: string }) => {
    if (busyRef.current || query.isError || !state || (!frozen && (!target || baseline === null))) return;
    const scopeKey = `${state.control.venue_id}:${state.control.account_id}`;
    if (frozen && frozen.scopeKey !== scopeKey) {
      setError('上次请求属于不同账户，不能在当前账户重试。');
      return;
    }
    const operation = frozen ?? { view: target!, expected_version: baseline!, reason, idempotency_key: crypto.randomUUID(), scopeKey };
    busyRef.current = true;
    setBusy(true);
    setFrozen(operation);
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(operation));
      const { scopeKey: _scope, ...body } = operation;
      const result = await changeDirectionalRisk({ ...body, totp_code: totp });
      setMessage(result.pending_view ? '请求已保存，正在等待已授权交易处理完成。' : '方向风险偏好已生效。');
      sessionStorage.removeItem(storageKey);
      setFrozen(null);
      setTarget(null);
      setError(null);
      await query.refetch();
    } catch (err) {
      setError(err instanceof Error ? err.message : '请求结果未确认');
      if (err instanceof ApiError && err.status < 500) {
        if (frozen) return;
        sessionStorage.removeItem(storageKey);
        setFrozen(null);
        if (err.status === 409) {
          setTarget(null);
          await query.refetch();
        }
      }
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const pending = Boolean(state?.control.pending_view || state?.control.pending_baseline);

  const verify = async () => {
    if (!frozen || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    try {
      const receipt = await fetchDirectionalReceipt(frozen.idempotency_key);
      if (`${receipt.current.venue_id}:${receipt.current.account_id}` !== frozen.scopeKey) {
        throw new Error('当前账户与原请求不同，不能核验。');
      }
      if (receipt.result || receipt.current.version > frozen.expected_version) {
        sessionStorage.removeItem(storageKey);
        setFrozen(null);
        setTarget(null);
        setError(null);
        setMessage(receipt.result ? '已核验：服务端记录了原请求，当前生效状态如下。' : '已核验：原请求未记录，控制版本已变化；原请求不能再生效。');
        await query.refetch();
      } else {
        setError('尚未查到原请求回执。保持原请求身份，可以使用新的验证码安全重试。');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '核验失败');
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const longSlot = state
    ? computeRiskSlotSummary(state.long_limit, state.long_risk_at_stop, state.wallet_balance_at_last_admission)
    : null;
  const shortSlot = state
    ? computeRiskSlotSummary(state.short_limit, state.short_risk_at_stop, state.wallet_balance_at_last_admission)
    : null;

  return (
    <section
      className="rounded-xl border border-border bg-surface p-4 shadow-xs transition-all"
      aria-label="方向风险偏好"
    >
      {query.isError ? (
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-bold tracking-tight text-text-primary">方向风险偏好</h2>
          <p role="alert" className="text-xs text-danger">无法读取方向风险控制，暂不能修改。</p>
          <button
            type="button"
            className="text-xs font-semibold text-brand hover:underline cursor-pointer"
            onClick={() => void query.refetch()}
          >
            刷新状态
          </button>
        </div>
      ) : !state || !longSlot || !shortSlot ? (
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-bold tracking-tight text-text-primary">方向风险偏好</h2>
          <p className="text-xs text-text-muted">正在读取方向风险控制…</p>
        </div>
      ) : (
        <details className="group">
          {/* Tier 1: Compact Single-Line Summary Bar */}
          <summary className="cursor-pointer select-none list-none flex flex-wrap items-center justify-between gap-3 text-xs focus-visible:outline-2 focus-visible:outline-brand rounded">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-bold tracking-tight text-text-primary">方向风险偏好</h2>
              <span
                role="status"
                className={`inline-flex items-center rounded-md px-2 py-0.5 font-semibold border ${
                  pending
                    ? 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/30'
                    : 'bg-surface-subtle text-text-primary border-border'
                }`}
              >
                {pending
                  ? `切换中：${state.control.pending_view ? labels[state.control.pending_view] : '风险预算'}，当前仍为${labels[state.control.view]}`
                  : `当前：${labels[state.control.view]} ›`}
              </span>

              <span className="inline-flex items-center rounded bg-surface-subtle px-1.5 py-0.5 text-[11px] text-text-muted border border-border">
                余额快照测算
              </span>

              {state.review_due && (
                <span className="inline-flex items-center rounded-md bg-amber-500/10 px-2 py-0.5 text-[11px] font-semibold text-amber-700 dark:text-amber-300 border border-amber-500/30">
                  建议复核当前判断，原选择持续有效
                </span>
              )}

              {(state.long_over_limit_at_last_balance || state.short_over_limit_at_last_balance) && (
                <span className="inline-flex items-center rounded-md bg-amber-500/10 px-2 py-0.5 text-[11px] font-semibold text-amber-700 dark:text-amber-300 border border-amber-500/30">
                  按上次余额快照测算已超限
                </span>
              )}

              {(longSlot.hasPositiveRiskWithoutCap || shortSlot.hasPositiveRiskWithoutCap) && (
                <span className="inline-flex items-center rounded-md bg-amber-500/10 px-2 py-0.5 text-[11px] font-semibold text-amber-700 dark:text-amber-300 border border-amber-500/30">
                  存在已占用风险 · 快照上限无法计算
                </span>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-3 font-mono text-xs">
              <span className="text-text-secondary">
                <strong className="font-sans text-text-muted font-medium">多头:</strong> 已用 {longSlot.usedFormatted} / {longSlot.capFormatted}
              </span>
              <span className="text-text-muted">·</span>
              <span className="text-text-secondary">
                <strong className="font-sans text-text-muted font-medium">空头:</strong> 已用 {shortSlot.usedFormatted} / {shortSlot.capFormatted}
              </span>
              <span className="font-sans text-[11px] font-semibold text-brand group-open:hidden">
                展开控制 ›
              </span>
              <span className="font-sans text-[11px] font-semibold text-text-muted hidden group-open:inline">
                收起 ‹
              </span>
            </div>
          </summary>

          {/* Tier 2 & Tier 3: Controls, Gauges, Snapshot Time, and Scope Rules */}
          <div className="mt-3.5 pt-3.5 border-t border-border/80 space-y-3 text-xs">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="inline-flex rounded-lg border border-border bg-surface-subtle p-0.5 gap-1" aria-label="选择市场立场">
                {(['bullish', 'neutral', 'bearish'] as const).map((view) => (
                  <button
                    type="button"
                    key={view}
                    aria-pressed={!pending && state.control.view === view}
                    disabled={pending || busy || Boolean(frozen)}
                    onClick={() => select(view)}
                    className="rounded-md px-3 py-1 text-xs font-semibold text-text-primary transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed aria-pressed:bg-brand aria-pressed:text-white hover:bg-surface-elevated focus-visible:ring-2 focus-visible:ring-brand"
                  >
                    {labels[view]}
                  </button>
                ))}
              </div>
              <button
                type="button"
                className="text-xs font-semibold text-brand hover:underline cursor-pointer px-1.5 py-1"
                onClick={() => void query.refetch()}
              >
                刷新状态
              </button>
            </div>

            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <div className="rounded-lg border border-border bg-surface-subtle/60 p-3 space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <dt className="text-text-muted font-medium">多头风险上限</dt>
                  <dd className="font-mono font-bold text-text-primary">
                    {longSlot.limitPctFormatted} · 已占用 {longSlot.usedFormatted} ({longSlot.capFormatted})
                  </dd>
                </div>
                {longSlot.barPct !== null ? (
                  <div data-testid="long-risk-bar" className="h-1.5 w-full overflow-hidden rounded-full bg-surface border border-border/60">
                    <div
                      className={`h-full transition-all ${state.long_over_limit_at_last_balance ? 'bg-amber-500' : 'bg-emerald-500'}`}
                      style={{ width: `${longSlot.barPct}%` }}
                    />
                  </div>
                ) : (
                  <p className="text-[11px] font-semibold text-amber-600 dark:text-amber-400">
                    快照上限无法计算{longSlot.hasPositiveRiskWithoutCap ? '（当前存在多头已占用风险）' : ''}
                  </p>
                )}
                {state.long_over_limit_at_last_balance && (
                  <p className="text-[11px] font-semibold text-amber-600 dark:text-amber-400">
                    按上次余额快照测算已超限（本控制不自动平仓，持仓管理权与保护状态见持仓详情）
                  </p>
                )}
              </div>

              <div className="rounded-lg border border-border bg-surface-subtle/60 p-3 space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <dt className="text-text-muted font-medium">空头风险上限</dt>
                  <dd className="font-mono font-bold text-text-primary">
                    {shortSlot.limitPctFormatted} · 已占用 {shortSlot.usedFormatted} ({shortSlot.capFormatted})
                  </dd>
                </div>
                {shortSlot.barPct !== null ? (
                  <div data-testid="short-risk-bar" className="h-1.5 w-full overflow-hidden rounded-full bg-surface border border-border/60">
                    <div
                      className={`h-full transition-all ${state.short_over_limit_at_last_balance ? 'bg-amber-500' : 'bg-rose-500'}`}
                      style={{ width: `${shortSlot.barPct}%` }}
                    />
                  </div>
                ) : (
                  <p className="text-[11px] font-semibold text-amber-600 dark:text-amber-400">
                    快照上限无法计算{shortSlot.hasPositiveRiskWithoutCap ? '（当前存在空头已占用风险）' : ''}
                  </p>
                )}
                {state.short_over_limit_at_last_balance && (
                  <p className="text-[11px] font-semibold text-amber-600 dark:text-amber-400">
                    按上次余额快照测算已超限（本控制不自动平仓，持仓管理权与保护状态见持仓详情）
                  </p>
                )}
              </div>
            </dl>

            <div className="rounded border border-border bg-surface-subtle p-2.5 space-y-1 text-text-secondary text-[11px]">
              <p className="leading-relaxed break-words">
                {state.balance_captured_at_ms
                  ? `最近准入余额快照：${state.wallet_balance_at_last_admission} USDT（${new Date(state.balance_captured_at_ms).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })}），非实时余额。${
                      state.long_over_limit_at_last_balance || state.short_over_limit_at_last_balance
                        ? '按此快照测算，已有方向占用超过当前上限；本控制不自动平仓，持仓管理权与保护状态见持仓详情。'
                        : '可新增额度仍以实际开仓前核验为准。'
                    }`
                  : '尚无准入余额快照，当前超限状态未知。实际开仓前核验最新余额。'}
              </p>
              <p className="leading-relaxed break-words text-text-muted">
                用于已授权的 Crypto 新开仓，不直接控制其他产品。上限按钱包余额的计划止损风险计算。本控制不自动平仓，持仓管理权与保护状态见持仓详情；实际持仓方向不由此按钮直接调整。新增交易仍需通过全部风险检查。
              </p>
              <p className="font-mono text-text-muted">
                生效时间：{new Date(state.control.effective_at_ms).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })}
              </p>
            </div>
          </div>
        </details>
      )}

      {message && <p role="status" className="mt-2 text-xs text-text-secondary">{message}</p>}
      {error && !target && !frozen && <p role="alert" className="mt-2 text-xs text-danger">{error}</p>}
      {frozen && <p className="mt-2 text-xs text-status-amber">上次请求尚待确认。重试将核验同一请求，不创建新的变更。</p>}

      <TotpActionModal
        open={Boolean(target || frozen)}
        onOpenChange={(open) => {
          if (!open && !frozen && !busyRef.current) setTarget(null);
        }}
        title={`确认${labels[frozen?.view ?? target ?? 'neutral']}风险偏好`}
        description={`新预设：多头上限 ${
          state
            ? pct(
                new Decimal(state.long_limit)
                  .div(state.control.view === 'bearish' ? 0.5 : 1)
                  .mul((frozen?.view ?? target) === 'bearish' ? 0.5 : 1)
                  .toString()
              )
            : '待核验'
        }，空头上限 ${
          state
            ? pct(
                new Decimal(state.short_limit)
                  .div(state.control.view === 'bullish' ? 0.5 : 1)
                  .mul((frozen?.view ?? target) === 'bullish' ? 0.5 : 1)
                  .toString()
              )
            : '待核验'
        }，基础风控更严格时取更低值。仅限制 Crypto 新开仓风险，不自动平仓，不解除维护暂停。逆向机会仍可交易；切换可能等待已授权交易处理完成。`}
        confirmLabel={frozen ? '核验并重试原请求' : '确认变更'}
        expectedVersion={frozen?.expected_version ?? baseline}
        requireTotp
        defaultReason={frozen?.reason ?? 'Owner 更新方向风险判断'}
        isReasonFrozen={Boolean(frozen)}
        isSubmitting={busy}
        onVerifyStatus={frozen ? verify : undefined}
        errorMessage={error}
        onConfirm={submit}
      />
    </section>
  );
}
