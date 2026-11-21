import Decimal from 'decimal.js';
import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { TotpActionModal } from '../TotpActionModal';
import { ApiError } from '../../api/errors';
import {
  fetchExitConfiguration,
  previewExitConfiguration,
  activateExitConfiguration,
  fetchExitConfigurationReceipt,
  previewExitSizing,
  type ExitSizingView,
  type ExitConfigurationIntent,
  type ExitConfigurationPreview,
  type ExitConfigurationBody,
} from '../../api/exitConfigurationApi';
import {
  SlidersHorizontal,
  RefreshCw,
  Lock,
  AlertTriangle,
  CheckCircle2,
  Calculator,
  Clock,
} from 'lucide-react';

const pendingKey = 'brc:exit-configuration:pending';
type Pending = Omit<ExitConfigurationBody, 'totp_code'>;

function readPending(): Pending | null {
  try {
    return JSON.parse(sessionStorage.getItem(pendingKey) ?? 'null');
  } catch {
    return null;
  }
}

const standaloneLong = 'event_spec:SOR-1H-LONG-001:SOR-1H-LONG:v1';
const standaloneShort = 'event_spec:SOR-1H-SHORT-001:SOR-1H-SHORT:v1';

function label(event: string) {
  if (event === standaloneLong) return 'SOR-多';
  if (event === standaloneShort) return 'SOR-空';
  const parts = event.split(':');
  return `${parts[1]} · ${parts[2].endsWith('SHORT') ? 'SHORT' : 'LONG'}`;
}

function formatPctHelper(decimalStr: string): string | null {
  try {
    const trimmed = decimalStr.trim();
    if (!trimmed) return null;
    const d = new Decimal(trimmed);
    if (!d.isFinite()) return null;
    return `${d.mul(100).toDecimalPlaces(2).toString()}%`;
  } catch {
    return null;
  }
}

function getEventFlags(eventSpecId: string) {
  const requiredMa50 = eventSpecId === standaloneLong;
  const sor = eventSpecId.includes('SOR-1H-001') || requiredMa50 || eventSpecId === standaloneShort;
  const ma =
    eventSpecId.includes('CPM-RO-001') ||
    eventSpecId.includes('MI-001') ||
    eventSpecId.includes('MPG-001');
  return { sor, ma, requiredMa50 };
}

export function ExitConfigurationPanel() {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ['exit-configuration'],
    queryFn: fetchExitConfiguration,
  });
  const [draft, setDraft] = useState<ExitConfigurationIntent | null>(null);
  const [preview, setPreview] = useState<ExitConfigurationPreview | null>(null);
  const [pending, setPending] = useState<Pending | null>(readPending);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [sizing, setSizing] = useState<ExitSizingView | null>(null);
  const [sizingInputs, setSizingInputs] = useState({
    event: '',
    symbol: 'BTCUSDT',
    quantity: '0.007',
    entry: '65000',
    stop: '64000',
  });
  const [error, setError] = useState<string | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    if (query.data && !pending) {
      setDraft(query.data.intent);
      setPreview(null);
    }
  }, [query.data, pending]);

  useEffect(() => {
    if (!preview) return;
    const current = Date.now();
    setNowMs(current);
    const remaining = preview.valid_until_ms - current;
    if (remaining <= 0) return;
    const delay = Math.min(remaining + 20, 2_147_483_647);
    const timer = setTimeout(() => setNowMs(Date.now()), delay);
    return () => clearTimeout(timer);
  }, [preview]);

  const update = (event: string, field: string, value: string | boolean) => {
    setDraft((current) =>
      current
        ? {
            ...current,
            events: current.events.map((e) =>
              e.event_spec_id === event ? { ...e, [field]: value } : e
            ),
          }
        : null
    );
    setPreview(null);
    setSizing(null);
    setError(null);
  };

  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ['exit-configuration'] });
  };

  const verify = async () => {
    if (!pending) return;
    setBusy(true);
    try {
      const receipt = await fetchExitConfigurationReceipt(pending.idempotency_key);
      if (
        receipt &&
        receipt.intent.account_id === pending.intent.account_id &&
        receipt.intent.product_id === pending.intent.product_id &&
        receipt.revision === pending.expected_version + 1 &&
        receipt.preview_digest === pending.preview_digest
      ) {
        sessionStorage.removeItem(pendingKey);
        setPending(null);
        setOpen(false);
        setError(null);
        await refresh();
      } else {
        setError('该请求尚无已提交结果；保留原请求，请继续核实。');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '结果核实失败');
    } finally {
      setBusy(false);
    }
  };

  const submit = async ({ totp, reason }: { totp: string; reason: string }) => {
    if (!preview || pending) return;
    const current = Date.now();
    if (current > preview.valid_until_ms) {
      setNowMs(current);
      setOpen(false);
      setError('预览已失效，请重新生成预览');
      return;
    }
    const operation: Pending = {
      intent: preview.intent,
      expected_version: preview.intent.expected_revision,
      preview_digest: preview.preview_digest,
      preview_valid_until_ms: preview.valid_until_ms,
      idempotency_key: `exit-config:${crypto.randomUUID()}`,
      reason,
    };
    sessionStorage.setItem(pendingKey, JSON.stringify(operation));
    setPending(operation);
    setBusy(true);
    setError(null);
    try {
      const result = await activateExitConfiguration({
        ...operation,
        totp_code: totp,
      });
      if (
        result.revision !== operation.expected_version + 1 ||
        result.intent.account_id !== operation.intent.account_id ||
        result.preview_digest !== operation.preview_digest
      ) {
        throw new Error('提交回执身份不一致，需核实');
      }
      sessionStorage.removeItem(pendingKey);
      setPending(null);
      setOpen(false);
      setPreview(null);
      await refresh();
    } catch (e) {
      if (e instanceof ApiError && e.status >= 400 && e.status < 500 && e.status !== 408) {
        sessionStorage.removeItem(pendingKey);
        setPending(null);
        setPreview(null);
      }
      setError(e instanceof Error ? e.message : '提交结果未知，请核实原请求');
    } finally {
      setBusy(false);
    }
  };

  const isFirstActivation = !query.data?.current;
  const isActionBlocked = query.isError || busy || Boolean(pending);
  const splitTransfer = Boolean(draft?.events.some(e => e.event_spec_id === standaloneLong) && query.data?.current?.intent?.events?.some(e => e.event_spec_id.includes('SOR-1H-001')));
  const isFieldLocked = isFirstActivation || isActionBlocked || splitTransfer;
  const isPreviewExpired = Boolean(preview && nowMs > preview.valid_until_ms);

  const handleOpenConfirm = () => {
    if (!preview || isActionBlocked) return;
    const current = Date.now();
    if (current > preview.valid_until_ms) {
      setNowMs(current);
      setError('预览已失效，请重新生成预览');
      return;
    }
    setOpen(true);
  };

  const handleGeneratePreview = async () => {
    if (!draft || isActionBlocked) return;
    setBusy(true);
    setError(null);
    try {
      setPreview(await previewExitConfiguration(draft));
    } catch (e) {
      setError(e instanceof Error ? e.message : '预览失败');
    } finally {
      setBusy(false);
    }
  };

  const handleSizingPreview = async () => {
    if (!draft || isActionBlocked) return;
    const selected = draft.events.find(
      (e) => e.event_spec_id === (sizingInputs.event || draft.events[0]?.event_spec_id)
    );
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      setSizing(
        await previewExitSizing({
          event_spec_id: selected.event_spec_id,
          parameters: selected,
          exchange_instrument_id: `binance-usdm:${sizingInputs.symbol.toUpperCase()}:perpetual`,
          quantity: sizingInputs.quantity,
          entry_price: sizingInputs.entry,
          initial_stop: sizingInputs.stop,
        })
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : '数量预览失败');
    } finally {
      setBusy(false);
    }
  };

  const inputCls =
    'h-7 rounded border border-border bg-surface-subtle px-2 font-mono text-xs text-text-primary focus:border-brand focus:bg-surface focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed';

  return (
    <section
      className="rounded border border-border bg-surface shadow-xs"
      aria-label="TP1 与 MA50 参数"
      data-testid="exit-configuration-panel"
    >
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 sm:px-5 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <SlidersHorizontal className="h-4 w-4 text-brand flex-none" />
          <h2 className="text-xs font-bold uppercase tracking-wider text-text-primary">
            TP1 与 MA50 参数
          </h2>
          {query.data && (
            <span
              className={`rounded px-2 py-0.5 font-mono text-[11px] font-semibold border ${
                query.data.current
                  ? 'bg-surface-subtle text-text-primary border-border'
                  : 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30'
              }`}
            >
              {query.data.current
                ? `当前版本 v${query.data.current.revision}`
                : '首次待激活 · 采用已确认基线'}
            </span>
          )}
        </div>

        <button
          type="button"
          disabled={busy}
          onClick={() => void query.refetch()}
          className="inline-flex h-7 items-center gap-1.5 rounded border border-border bg-surface px-2.5 text-xs font-medium text-text-primary hover:bg-surface-elevated transition-colors cursor-pointer disabled:opacity-50"
        >
          <RefreshCw className={`h-3 w-3 text-text-muted ${query.isFetching ? 'animate-spin text-brand' : ''}`} />
          <span>刷新配置</span>
        </button>
      </div>

      {/* Body */}
      <div className="p-4 sm:p-5 space-y-3">
        {query.isLoading && (
          <p className="text-xs text-text-muted">读取退出配置中…</p>
        )}

        {query.isError && (
          <div
            role="alert"
            className="flex items-center gap-2 rounded border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-600 dark:text-rose-400"
          >
            <AlertTriangle className="h-4 w-4 flex-none" />
            <span>退出配置读取失败，当前无法编辑或生成预览</span>
          </div>
        )}

        {pending && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
            <div className="flex items-center gap-2 font-medium">
              <AlertTriangle className="h-4 w-4 flex-none text-amber-500" />
              <span>存在提交结果未知的激活请求，已锁定编辑；请先核实原请求。</span>
            </div>
            <button
              type="button"
              disabled={busy}
              onClick={() => void verify()}
              className="rounded border border-amber-500/40 bg-surface px-2.5 py-1 text-xs font-semibold text-amber-700 dark:text-amber-300 hover:bg-amber-500/20 cursor-pointer disabled:opacity-50"
            >
              核实原激活请求
            </button>
          </div>
        )}

        {draft && (
          <>
            {splitTransfer && <p className="text-xs text-text-secondary">首次切换继承当前退出参数。完成切换后可按原流程调整。</p>}
            {/* Mobile Card List (< 768px) */}
            <div className="md:hidden space-y-2.5" data-testid="exit-config-mobile-list">
              {draft.events.map((e) => {
                const { sor, ma, requiredMa50 } = getEventFlags(e.event_spec_id);
                const eventLabel = label(e.event_spec_id);
                const targetPct = formatPctHelper(e.target_fraction);
                const maxPct = formatPctHelper(e.max_actual_fraction);

                return (
                  <div
                    key={e.event_spec_id}
                    className="rounded border border-border bg-surface-subtle/60 p-3 space-y-2.5 text-xs"
                  >
                    <div className="flex items-center justify-between gap-2 border-b border-border/60 pb-2">
                      <span className="font-mono font-bold text-text-primary">{eventLabel}</span>
                      {sor && (
                        <span className="inline-flex items-center gap-1 rounded bg-surface px-1.5 py-0.5 text-[10px] text-text-muted border border-border">
                          <Lock className="h-2.5 w-2.5" />
                          原比例锁定
                        </span>
                      )}
                    </div>

                    <div className="grid grid-cols-2 gap-2.5">
                      <label className="space-y-1">
                        <span className="block text-[11px] text-text-muted">TP1 倍数 (R)</span>
                        <input
                          aria-label={`移动端 ${eventLabel} TP1倍数`}
                          type="number"
                          min="0.1"
                          max="5"
                          step="0.1"
                          value={e.reward_multiple}
                          disabled={isFieldLocked}
                          onChange={(v) => update(e.event_spec_id, 'reward_multiple', v.target.value)}
                          className={`${inputCls} w-full`}
                        />
                      </label>

                      <label className="space-y-1">
                        <span className="block text-[11px] text-text-muted">
                          目标比例 {targetPct ? `(${targetPct})` : ''}
                        </span>
                        <input
                          aria-label={`移动端 ${eventLabel} 目标比例`}
                          type="number"
                          min="0.001"
                          max="0.5"
                          step="0.01"
                          value={e.target_fraction}
                          disabled={isFieldLocked || sor}
                          onChange={(v) => update(e.event_spec_id, 'target_fraction', v.target.value)}
                          className={`${inputCls} w-full`}
                        />
                      </label>

                      <label className="space-y-1">
                        <span className="block text-[11px] text-text-muted">
                          实际比例上限 {maxPct ? `(${maxPct})` : ''}
                        </span>
                        <input
                          aria-label={`移动端 ${eventLabel} 实际比例上限`}
                          type="number"
                          min="0.001"
                          max="0.5"
                          step="0.01"
                          value={e.max_actual_fraction}
                          disabled={isFieldLocked || sor}
                          onChange={(v) => update(e.event_spec_id, 'max_actual_fraction', v.target.value)}
                          className={`${inputCls} w-full`}
                        />
                      </label>

                      <div className="flex flex-col justify-end gap-1.5">
                        <label className="inline-flex items-center gap-1.5 text-[11px] text-text-secondary">
                          <input
                            aria-label={`移动端 ${eventLabel} 最小量提升`}
                            type="checkbox"
                            checked={e.minimum_lift}
                            disabled={isFieldLocked || sor}
                            onChange={(v) => update(e.event_spec_id, 'minimum_lift', v.target.checked)}
                            className="h-3.5 w-3.5 rounded border-border accent-brand"
                          />
                          <span>最小量提升{sor ? ' (原规则)' : ''}</span>
                        </label>
                        <div className="text-[11px] text-text-secondary">
                          {requiredMa50 ? <span className="text-[11px] text-text-secondary">强制开启</span> : ma ? (
                            <label className="inline-flex items-center gap-1.5">
                              <input
                                aria-label={`移动端 ${eventLabel} MA50`}
                                type="checkbox"
                                checked={e.ma50_enabled}
                                disabled={isFieldLocked}
                                onChange={(v) => update(e.event_spec_id, 'ma50_enabled', v.target.checked)}
                                className="h-3.5 w-3.5 rounded border-border accent-brand"
                              />
                              <span>BTC 4h &gt; SMA50</span>
                            </label>
                          ) : (
                            <span className="text-text-muted">MA50: 不适用</span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Desktop Table (>= 768px) */}
            <div className="hidden md:block overflow-x-auto rounded border border-border">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-border bg-surface-subtle text-[11px] font-semibold text-text-muted">
                    <th className="px-3 py-2.5">策略／方向</th>
                    <th className="px-3 py-2.5">TP1 倍数 (R)</th>
                    <th className="px-3 py-2.5">目标比例 (小数)</th>
                    <th className="px-3 py-2.5">最小量提升</th>
                    <th className="px-3 py-2.5">实际比例上限</th>
                    <th className="px-3 py-2.5">BTC 4h &gt; SMA50</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {draft.events.map((e) => {
                    const { sor, ma, requiredMa50 } = getEventFlags(e.event_spec_id);
                    const eventLabel = label(e.event_spec_id);
                    const targetPct = formatPctHelper(e.target_fraction);
                    const maxPct = formatPctHelper(e.max_actual_fraction);

                    return (
                      <tr key={e.event_spec_id} className="hover:bg-surface-subtle/50 transition-colors">
                        <th className="px-3 py-2 text-left font-mono font-semibold text-text-primary whitespace-nowrap">
                          <span>{eventLabel}</span>
                          {sor && (
                            <span className="ml-2 inline-flex items-center gap-0.5 rounded bg-surface-subtle px-1.5 py-0.5 font-sans text-[10px] font-normal text-text-muted border border-border">
                              <Lock className="h-2.5 w-2.5" />
                              原比例锁定
                            </span>
                          )}
                        </th>
                        <td className="px-3 py-2 whitespace-nowrap">
                          <div className="inline-flex items-center gap-1">
                            <input
                              aria-label={`${eventLabel} TP1倍数`}
                              type="number"
                              min="0.1"
                              max="5"
                              step="0.1"
                              value={e.reward_multiple}
                              disabled={isFieldLocked}
                              onChange={(v) => update(e.event_spec_id, 'reward_multiple', v.target.value)}
                              className={`${inputCls} w-20`}
                            />
                            <span className="font-mono text-[11px] text-text-muted">R</span>
                          </div>
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap">
                          <div className="inline-flex items-center gap-1.5">
                            <input
                              aria-label={`${eventLabel} 目标比例`}
                              type="number"
                              min="0.001"
                              max="0.5"
                              step="0.01"
                              value={e.target_fraction}
                              disabled={isFieldLocked || sor}
                              onChange={(v) => update(e.event_spec_id, 'target_fraction', v.target.value)}
                              className={`${inputCls} w-20`}
                            />
                            {targetPct && (
                              <span className="font-mono text-[10px] text-text-muted w-11">
                                ({targetPct})
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap">
                          <label className="inline-flex items-center gap-1.5 text-text-secondary">
                            <input
                              aria-label={`${eventLabel} 最小量提升`}
                              type="checkbox"
                              checked={e.minimum_lift}
                              disabled={isFieldLocked || sor}
                              onChange={(v) => update(e.event_spec_id, 'minimum_lift', v.target.checked)}
                              className="h-3.5 w-3.5 rounded border-border accent-brand"
                            />
                            {sor && <span className="text-[11px] text-text-muted">原规则</span>}
                          </label>
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap">
                          <div className="inline-flex items-center gap-1.5">
                            <input
                              aria-label={`${eventLabel} 实际比例上限`}
                              type="number"
                              min="0.001"
                              max="0.5"
                              step="0.01"
                              value={e.max_actual_fraction}
                              disabled={isFieldLocked || sor}
                              onChange={(v) => update(e.event_spec_id, 'max_actual_fraction', v.target.value)}
                              className={`${inputCls} w-20`}
                            />
                            {maxPct && (
                              <span className="font-mono text-[10px] text-text-muted w-11">
                                ({maxPct})
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap">
                          {requiredMa50 ? <span className="text-[11px] text-text-secondary">强制开启</span> : ma ? (
                            <input
                              aria-label={`${eventLabel} MA50`}
                              type="checkbox"
                              checked={e.ma50_enabled}
                              disabled={isFieldLocked}
                              onChange={(v) => update(e.event_spec_id, 'ma50_enabled', v.target.checked)}
                              className="h-3.5 w-3.5 rounded border-border accent-brand"
                            />
                          ) : (
                            <span className="text-[11px] text-text-muted">不适用</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Action Bar & Rules Toggle */}
            <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
              <details className="text-[11px] text-text-muted">
                <summary className="cursor-pointer hover:text-text-secondary">
                  参数与生效规则说明
                </summary>
                <div className="mt-1.5 space-y-1 pl-2 border-l border-border max-w-2xl leading-relaxed">
                  <p>
                    六个退出绑定一次激活，SOR-多固定检查 BTC MA50，CPM、MI 和 MPG 的 MA50 可单独配置，仅作用于新交易；旧交易保持冻结方案，人工接管永久有效。
                  </p>
                  <p>
                    比例以小数填写（如 0.05 表示 5%）。Runner、保本、保护与时间规则从原策略继承；激活不改变策略暂停状态或全局开仓开关。
                  </p>
                </div>
              </details>

              <button
                type="button"
                disabled={isActionBlocked}
                onClick={() => void handleGeneratePreview()}
                className="inline-flex h-8 items-center rounded border border-brand/40 bg-brand/10 px-3.5 text-xs font-semibold text-brand hover:bg-brand/20 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              >
                生成服务端预览
              </button>
            </div>

            {/* Collapsible Sizing Example Calculator */}
            <details className="rounded border border-border bg-surface-subtle/40 px-3.5 py-2.5 text-xs">
              <summary className="cursor-pointer font-medium text-text-secondary hover:text-text-primary inline-flex items-center gap-1.5">
                <Calculator className="h-3.5 w-3.5 text-text-muted" />
                <span>按当前已采集规则核实数量示例（仅试算，非真实仓位）</span>
              </summary>
              <div className="mt-2.5 space-y-2.5 border-t border-border/60 pt-2.5">
                <p className="text-[11px] text-text-muted">
                  仅作参数示例计算，不代表当前持仓或可执行订单；规则缺失或过期会明确拒绝，不保证成交。
                </p>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-6 items-end">
                  <label className="space-y-1 sm:col-span-2">
                    <span className="block text-[11px] text-text-muted">示例策略</span>
                    <select
                      aria-label="数量示例策略"
                      value={sizingInputs.event || draft.events[0]?.event_spec_id || ''}
                      onChange={(e) => {
                        setSizingInputs((v) => ({ ...v, event: e.target.value }));
                        setSizing(null);
                      }}
                      className={`${inputCls} w-full font-sans`}
                    >
                      {draft.events.map((e) => (
                        <option key={e.event_spec_id} value={e.event_spec_id}>
                          {label(e.event_spec_id)}
                        </option>
                      ))}
                    </select>
                  </label>
                  {(
                    [
                      ['symbol', '标的'],
                      ['quantity', '入场数量'],
                      ['entry', '入场均价'],
                      ['stop', '初始止损'],
                    ] as const
                  ).map(([field, fieldLabel]) => (
                    <label key={field} className="space-y-1">
                      <span className="block text-[11px] text-text-muted">{fieldLabel}</span>
                      <input
                        aria-label={`数量示例${field}`}
                        value={sizingInputs[field]}
                        onChange={(e) => {
                          setSizingInputs((v) => ({ ...v, [field]: e.target.value }));
                          setSizing(null);
                        }}
                        className={`${inputCls} w-full`}
                      />
                    </label>
                  ))}
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  {sizing ? (
                    <p
                      className={`text-xs font-mono ${
                        sizing.blocker ? 'text-amber-600 dark:text-amber-400' : 'text-text-primary'
                      }`}
                      role="status"
                    >
                      {sizing.blocker
                        ? `不可计算：${sizing.blocker}`
                        : sizing.quantities
                        ? `TP ${sizing.quantities.tp_quantity} · 实际 ${new Decimal(
                            sizing.quantities.actual_fraction
                          )
                            .mul(100)
                            .toFixed(3)}% · Runner ${sizing.quantities.runner_quantity}${
                            sizing.quantities.minimum_lifted ? '（最小量提升）' : ''
                          }`
                        : '数量结果不可得'}
                    </p>
                  ) : (
                    <span className="text-[11px] text-text-muted">填写示例参数后点击核实</span>
                  )}
                  <button
                    type="button"
                    disabled={isActionBlocked}
                    onClick={() => void handleSizingPreview()}
                    className="inline-flex h-7 items-center rounded border border-border bg-surface px-3 text-xs font-medium text-brand hover:bg-surface-elevated cursor-pointer disabled:opacity-40"
                  >
                    核实数量
                  </button>
                </div>
              </div>
            </details>

            {/* Structured Server Diff Preview */}
            {preview && (
              <div
                data-testid="exit-config-preview"
                className="rounded border border-brand/40 bg-brand/5 p-3.5 space-y-2.5 text-xs"
              >
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-brand/20 pb-2">
                  <div className="flex items-center gap-2 font-bold text-text-primary">
                    <CheckCircle2 className="h-4 w-4 text-brand" />
                    <span>新旧配置差异 · 待确认</span>
                  </div>
                  <div className="flex items-center gap-1.5 font-mono text-[11px]">
                    <Clock className="h-3 w-3 text-text-muted" />
                    <span className={isPreviewExpired ? 'text-rose-500 font-semibold' : 'text-text-muted'}>
                      {isPreviewExpired
                        ? '预览已失效，请重新生成预览'
                        : `有效期至 ${new Date(preview.valid_until_ms).toLocaleTimeString('zh-CN', {
                            hour12: false,
                          })}`}
                    </span>
                  </div>
                </div>

                {preview.profiles.length > 0 && (
                  <div className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
                    {preview.profiles.map((p) => {
                      const oldProfile = query.data?.sources.find(
                        (s) => s.event_spec_id === p.event_spec_id
                      )?.profile;
                      const oldEvent = query.data?.intent.events.find(
                        (ev) => ev.event_spec_id === p.event_spec_id
                      );
                      const newEvent = preview.intent.events.find(
                        (ev) => ev.event_spec_id === p.event_spec_id
                      );
                      const { ma } = getEventFlags(p.event_spec_id);

                      const changes: Array<{ name: string; from: string; to: string }> = [];
                      const oldR = oldProfile?.tp1.reward_multiple ?? oldEvent?.reward_multiple;
                      const newR = p.profile.tp1.reward_multiple;
                      if (oldR != null && String(oldR) !== String(newR)) {
                        changes.push({ name: 'TP1 倍数', from: `${oldR}R`, to: `${newR}R` });
                      }
                      const oldFrac = oldProfile?.tp1.quantity_fraction ?? oldEvent?.target_fraction;
                      const newFrac = p.profile.tp1.quantity_fraction;
                      if (oldFrac != null && String(oldFrac) !== String(newFrac)) {
                        changes.push({ name: '目标比例', from: String(oldFrac), to: String(newFrac) });
                      }
                      const oldLift =
                        oldProfile?.execution?.quantity_policy != null
                          ? oldProfile.execution.quantity_policy === 'target_floor_then_minimum'
                          : oldEvent?.minimum_lift;
                      const newLift =
                        p.profile.execution?.quantity_policy != null
                          ? p.profile.execution.quantity_policy === 'target_floor_then_minimum'
                          : newEvent?.minimum_lift;
                      if (oldLift != null && newLift != null && oldLift !== newLift) {
                        changes.push({
                          name: '最小量提升',
                          from: oldLift ? '开启' : '关闭',
                          to: newLift ? '开启' : '关闭',
                        });
                      }
                      const oldMaxFrac = oldEvent?.max_actual_fraction;
                      const newMaxFrac = newEvent?.max_actual_fraction;
                      if (oldMaxFrac != null && newMaxFrac != null && String(oldMaxFrac) !== String(newMaxFrac)) {
                        changes.push({
                          name: '实际比例上限',
                          from: String(oldMaxFrac),
                          to: String(newMaxFrac),
                        });
                      }
                      if (
                        ma &&
                        oldEvent?.ma50_enabled != null &&
                        newEvent?.ma50_enabled != null &&
                        oldEvent.ma50_enabled !== newEvent.ma50_enabled
                      ) {
                        changes.push({
                          name: 'MA50 门槛',
                          from: oldEvent.ma50_enabled ? '开启' : '关闭',
                          to: newEvent.ma50_enabled ? '开启' : '关闭',
                        });
                      }

                      return (
                        <div
                          key={p.event_spec_id}
                          className="rounded border border-border bg-surface px-3 py-2 space-y-1"
                        >
                          <div className="flex items-center justify-between gap-1">
                            <span className="font-mono font-semibold text-text-primary">
                              {label(p.event_spec_id)}
                            </span>
                            {changes.length > 0 ? (
                              <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-amber-600 dark:text-amber-400">
                                {changes.length} 项变更
                              </span>
                            ) : (
                              <span className="text-[10px] text-text-muted">参数未变化</span>
                            )}
                          </div>
                          {changes.length > 0 ? (
                            <div className="space-y-0.5 font-mono text-[11px] text-text-secondary">
                              {changes.map((c) => (
                                <div key={c.name}>
                                  {c.name}: {c.from} →{' '}
                                  <span className="text-brand font-semibold">{c.to}</span>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="font-mono text-[10px] text-text-muted">
                              TP1 {newR}R · 目标 {newFrac} · 上限 {newMaxFrac ?? '—'}
                              {ma && newEvent ? ` · MA50 ${newEvent.ma50_enabled ? '开' : '关'}` : ''}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}

                <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                  <span className="text-[11px] text-text-muted">
                    执行按实际完整入场均价计算 R；实际 TP 比例在每笔成交计划中显示。
                  </span>
                  <button
                    type="button"
                    disabled={isActionBlocked || isPreviewExpired}
                    onClick={handleOpenConfirm}
                    className="inline-flex h-8 items-center rounded bg-brand px-3.5 text-xs font-semibold text-white hover:bg-brand/90 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    TOTP 确认激活
                  </button>
                </div>
              </div>
            )}
          </>
        )}

        {error && (
          <p role="alert" className="text-xs text-amber-600 dark:text-amber-400">
            {error}
          </p>
        )}
      </div>

      <TotpActionModal
        open={open}
        onOpenChange={setOpen}
        title="激活退出配置"
        description="仅影响新交易；不恢复暂停策略，不恢复人工票自动管理。"
        confirmLabel="确认激活六退出及三门槛"
        expectedVersion={preview?.source_configuration_revision}
        isSubmitting={busy}
        isUnknownResult={!!pending}
        onConfirm={submit}
        onVerifyStatus={verify}
        errorMessage={error}
      />
    </section>
  );
}
