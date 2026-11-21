import { useRef, useState } from 'react';
import Decimal from 'decimal.js';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  fetchRiskBudget,
  previewRiskBudget,
  changeRiskBudget,
  fetchRiskBudgetReceipt,
} from '../../api/riskBudgetApi';
import type { RiskBudgetBody, RiskBudgetView } from '../../api/riskBudgetApi';
import { TotpActionModal } from '../TotpActionModal';
import { ApiError } from '../../api/errors';
import { SlidersHorizontal, AlertTriangle, Minus, Plus } from 'lucide-react';

const pct = (v: string) => new Decimal(v).mul(100).toString() + '%';
const storageKey = 'brc-risk-budget-request';
type Frozen = Omit<RiskBudgetBody, 'totp_code'> & { scopeKey: string };

function restore(): Frozen | null {
  try {
    const v = JSON.parse(sessionStorage.getItem(storageKey) || 'null');
    return v &&
      typeof v.scopeKey === 'string' &&
      typeof v.baseline === 'string' &&
      typeof v.idempotency_key === 'string' &&
      typeof v.reason === 'string' &&
      Number.isInteger(v.expected_version) &&
      Number.isInteger(v.expected_directional_version)
      ? v
      : null;
  } catch {
    return null;
  }
}

const errorText = (error: unknown) => {
  if (error instanceof ApiError) {
    if (error.status === 409) return '配置版本已变化或已有变更正在处理，请刷新后重新预览。';
    if (error.status === 401) return '登录已过期，请重新登录后核验原请求。';
    if (error.status === 403) return '身份验证未通过，请核对验证码和当前登录状态。';
    if (error.status === 422) return '参数不合法，请使用 2.0%～3.0%，步长 0.1 个百分点。';
    return '服务暂不可用，请核验原请求结果后再操作。';
  }
  return error instanceof Error ? error.message : '请求结果尚未确认';
};

function RiskLimitTile({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="rounded border border-border bg-surface-subtle px-3 py-2">
      <div className="text-[11px] text-text-muted">{label}</div>
      <div className="mt-0.5 flex items-baseline gap-1.5">
        <span className="font-mono text-sm font-bold tabular-nums text-text-primary">
          {value}
        </span>
        {hint && <span className="text-[10px] text-text-muted">{hint}</span>}
      </div>
    </div>
  );
}

export function RiskBudgetCard() {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ['owner', 'risk-budget'],
    queryFn: fetchRiskBudget,
    refetchInterval: 5000,
  });
  const [input, setInput] = useState('');
  const [preview, setPreview] = useState<RiskBudgetView | null>(null);
  const [frozen, setFrozen] = useState<Frozen | null>(restore);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const state = query.data;
  const pending = Boolean(state?.pending_baseline || state?.pending_directional_view);
  const currentPercentStr = state ? new Decimal(state.baseline).mul(100).toString() : '';
  const displayedPercent = input || currentPercentStr;
  const isEditingDisabled = pending || busy || Boolean(frozen) || query.isError;

  const refresh = async () => {
    await query.refetch();
    await client.invalidateQueries({ queryKey: ['owner', 'directional-risk'] });
  };

  const stepBaseline = (delta: string) => {
    if (!state || isEditingDisabled) return;
    try {
      const next = new Decimal(displayedPercent || currentPercentStr).plus(delta);
      const clamped = Decimal.min(new Decimal('3'), Decimal.max(new Decimal('2'), next));
      setInput(clamped.toDecimalPlaces(1).toString());
    } catch {
      setInput(currentPercentStr);
    }
  };

  const prepare = async () => {
    if (lock.current || !state || query.isError || pending || frozen) return;
    lock.current = true;
    setBusy(true);
    setError(null);
    try {
      const value = new Decimal(input || currentPercentStr).div(100);
      if (!value.gte('.02') || !value.lte('.03') || !value.mod('.001').isZero()) {
        throw new Error('请输入 2.0% 至 3.0%，步长 0.1 个百分点。');
      }
      setPreview(await previewRiskBudget(value.toFixed(3)));
    } catch (e) {
      setError(errorText(e));
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };

  const verify = async () => {
    if (!frozen || lock.current) return;
    lock.current = true;
    setBusy(true);
    try {
      const current = await fetchRiskBudget();
      if (`${current.venue_id}:${current.account_id}` !== frozen.scopeKey) {
        throw new Error('当前账户与原请求不同。');
      }
      const receipt = await fetchRiskBudgetReceipt(frozen.idempotency_key);
      if (
        receipt ||
        current.policy_version > frozen.expected_version ||
        current.directional_version > frozen.expected_directional_version
      ) {
        sessionStorage.removeItem(storageKey);
        setFrozen(null);
        setPreview(null);
        setError(null);
        setMessage(
          receipt?.status === 'pending'
            ? '请求已保存，等待生效。'
            : receipt
            ? '原请求结果已确认。'
            : '原请求未记录，配置版本已变化，需重新预览。'
        );
        await refresh();
      } else {
        setError('尚未查到回执，保留同一请求身份后重试。');
      }
    } catch (e) {
      setError(errorText(e));
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };

  const submit = async ({ totp, reason }: { totp: string; reason: string }) => {
    if (lock.current || !state || query.isError || (!frozen && !preview)) return;
    const scopeKey = `${state.venue_id}:${state.account_id}`;
    if (frozen && frozen.scopeKey !== scopeKey) {
      setError('当前账户与原请求不同。');
      return;
    }
    const operation =
      frozen ?? {
        scopeKey,
        baseline: preview!.baseline,
        expected_version: preview!.policy_version,
        expected_directional_version: preview!.directional_version,
        reason,
        idempotency_key: crypto.randomUUID(),
      };
    lock.current = true;
    setBusy(true);
    setFrozen(operation);
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(operation));
      const { scopeKey: _scope, ...body } = operation;
      const result = await changeRiskBudget({ ...body, totp_code: totp });
      setMessage(
        result.status === 'pending'
          ? '请求已保存，等待生效。'
          : result.status === 'unchanged'
          ? '配置未变化。'
          : '风险预算已生效。'
      );
      sessionStorage.removeItem(storageKey);
      setFrozen(null);
      setPreview(null);
      setInput('');
      setError(null);
      await refresh();
    } catch (e) {
      setError(errorText(e));
      if (e instanceof ApiError && e.status < 500 && !frozen) {
        sessionStorage.removeItem(storageKey);
        setFrozen(null);
        if (e.status === 409) {
          setPreview(null);
          await refresh();
        }
      }
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };

  const hasSnapshotBalance = Boolean(
    state?.wallet_balance_at_last_admission && state?.balance_captured_at_ms
  );
  const snapshotExceeded = Boolean(
    state &&
      hasSnapshotBalance &&
      (new Decimal(state.long_risk_at_stop).gt(
        new Decimal(state.wallet_balance_at_last_admission!).mul(state.long_limit)
      ) ||
        new Decimal(state.short_risk_at_stop).gt(
          new Decimal(state.wallet_balance_at_last_admission!).mul(state.short_limit)
        ))
  );

  return (
    <section
      aria-label="风险预算"
      data-testid="risk-budget-card"
      className="rounded border border-border bg-surface shadow-xs"
    >
      {/* Header + Inline Baseline Adjustment */}
      <div className="flex flex-col gap-3 border-b border-border px-4 sm:px-5 py-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="h-4 w-4 text-brand flex-none" />
            <h2 className="text-xs font-bold uppercase tracking-wider text-text-primary">
              风险预算
            </h2>
          </div>
          {state && (
            <p
              role="status"
              className="inline-flex flex-wrap items-center gap-2 text-xs text-text-secondary"
            >
              <span className="rounded bg-surface-subtle border border-border px-2 py-0.5 font-mono text-[11px] font-semibold text-text-primary">
                当前单笔上限：{pct(state.baseline)}
              </span>
              {state.pending_baseline ? (
                <span className="rounded bg-amber-500/10 border border-amber-500/30 px-2 py-0.5 font-mono text-[11px] font-semibold text-amber-600 dark:text-amber-400">
                  {pct(state.pending_baseline)} 等待生效
                </span>
              ) : state.pending_directional_view ? (
                <span className="rounded bg-amber-500/10 border border-amber-500/30 px-2 py-0.5 text-[11px] font-semibold text-amber-600 dark:text-amber-400">
                  方向切换中
                </span>
              ) : null}
            </p>
          )}
        </div>

        {state && (
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor="risk-budget-input" className="text-[11px] text-text-muted">
              单笔风险上限
            </label>
            <div className="inline-flex items-center rounded border border-border bg-surface-subtle">
              <button
                type="button"
                aria-label="减少 0.1%"
                disabled={isEditingDisabled}
                onClick={() => stepBaseline('-0.1')}
                className="grid h-7 w-7 place-items-center text-text-muted hover:text-text-primary disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
              >
                <Minus className="h-3 w-3" />
              </button>
              <input
                id="risk-budget-input"
                type="number"
                min="2"
                max="3"
                step="0.1"
                value={displayedPercent}
                onChange={(e) => setInput(e.target.value)}
                disabled={isEditingDisabled}
                className="h-7 w-14 bg-transparent text-center font-mono text-xs font-semibold text-text-primary focus:outline-none disabled:opacity-50"
              />
              <span className="pr-1.5 font-mono text-[11px] text-text-muted">%</span>
              <button
                type="button"
                aria-label="增加 0.1%"
                disabled={isEditingDisabled}
                onClick={() => stepBaseline('0.1')}
                className="grid h-7 w-7 place-items-center border-l border-border text-text-muted hover:text-text-primary disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
              >
                <Plus className="h-3 w-3" />
              </button>
            </div>

            <button
              type="button"
              disabled={isEditingDisabled}
              onClick={() => void prepare()}
              className="inline-flex h-7 items-center rounded border border-brand/40 bg-brand/10 px-3 text-xs font-semibold text-brand hover:bg-brand/20 transition-colors disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
            >
              预览修改
            </button>
          </div>
        )}
      </div>

      {/* Body */}
      <div className="px-4 sm:px-5 py-3 space-y-2.5">
        {query.isError ? (
          <p role="alert" className="text-xs text-status-red">
            无法读取风险预算，暂不能修改。
          </p>
        ) : !state ? (
          <p className="text-xs text-text-muted">正在读取风险预算…</p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
              <RiskLimitTile label="总风险上限" value={pct(state.gross_limit)} />
              <RiskLimitTile label="多头上限" value={pct(state.long_limit)} />
              <RiskLimitTile label="空头上限" value={pct(state.short_limit)} />
              <RiskLimitTile
                label="最低单笔风险量"
                value={pct(state.minimum_risk)}
                hint="目标的 50%"
              />
            </div>

            {snapshotExceeded && (
              <div className="flex items-center gap-2 rounded border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-[11px] text-amber-700 dark:text-amber-300">
                <AlertTriangle className="h-3.5 w-3.5 flex-none text-amber-500" />
                <span>
                  按最近准入余额快照（{state.wallet_balance_at_last_admission} USDT），存量超过方向上限；新增开仓受限。
                </span>
              </div>
            )}

            <details className="text-[11px] text-text-muted">
              <summary className="cursor-pointer hover:text-text-secondary">
                规则与快照说明
              </summary>
              <div className="mt-1.5 space-y-1 leading-relaxed pl-2 border-l border-border">
                <p>
                  作用于本账户已授权策略的共享风险预算（非持仓市值比例）；总风险与方向额度自动联动，保证金限制和杠杆保持不变。上调可能因最低实现门槛过滤更多窄止损交易。
                </p>
                <p>
                  修改仅影响新开仓准入，不改变已有交易管理权。
                  {state.entry_enabled
                    ? '当前全局配置已开启，修改不会额外授予交易权限。'
                    : '当前全局 ENTRY 已暂停，修改后仍保持暂停。'}
                </p>
                {hasSnapshotBalance && (
                  <p>
                    最近准入余额：{state.wallet_balance_at_last_admission} USDT（
                    {new Date(state.balance_captured_at_ms!).toLocaleString('zh-CN', {
                      timeZone: 'Asia/Shanghai',
                    })}
                    ），非实时余额；实际额度在开仓前核验。
                  </p>
                )}
              </div>
            </details>
          </>
        )}

        {message && (
          <p role="status" className="text-xs font-medium text-status-green">
            {message}
          </p>
        )}
        {error && !preview && !frozen && (
          <p role="alert" className="text-xs text-status-red">
            {error}
          </p>
        )}
      </div>

      <TotpActionModal
        open={Boolean(preview || frozen)}
        onOpenChange={(open) => {
          if (!open && !frozen && !lock.current) setPreview(null);
        }}
        title="确认风险预算"
        description={
          preview
            ? `单笔 ${pct(state?.baseline || preview.baseline)} → ${pct(
                preview.baseline
              )}；总计 ${pct(preview.gross_limit)}；多头 ${pct(
                preview.long_limit
              )}、空头 ${pct(preview.short_limit)}；最低单笔 ${pct(
                preview.minimum_risk
              )}。已有交易管理权不变，生效可能等待已授权入场完成。`
            : '核验原请求，不能把未确认的请求当作失败重新提交。'
        }
        confirmLabel={frozen ? '核验并重试原请求' : '确认修改'}
        expectedVersion={frozen?.expected_version ?? preview?.policy_version ?? null}
        requireTotp
        defaultReason={frozen?.reason ?? 'Owner 调整风险预算'}
        isReasonFrozen={Boolean(frozen)}
        isSubmitting={busy}
        errorMessage={error}
        onVerifyStatus={frozen ? verify : undefined}
        onConfirm={submit}
      />
    </section>
  );
}
