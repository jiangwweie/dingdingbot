import { useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  CirclePause,
  ClipboardCheck,
  DatabaseZap,
  FileSearch,
  Lock,
  RefreshCw,
  ShieldCheck,
  ShieldQuestion,
  TimerReset,
  WalletCards,
} from 'lucide-react';
import { Badge, Card, EnvelopeStatus, PageHeader, TechnicalDetails } from '@/components/ui';
import { asArray, displayValue, formatTimestampMs, useReadModel } from '@/lib/tradingConsoleApi';
import { cn } from '@/lib/utils';
import { blockingReasonLabel, formatMoney, protectionStatusLabel, sideLabel } from '@/lib/ownerViewModel';

type Control = {
  control_id: string;
  label: string;
  enabled: boolean;
  kind: string;
  route?: string | null;
  operation_type?: string;
  preflight_endpoint?: string;
  confirm_endpoint?: string;
  confirmation_required?: boolean;
  disabled_reason?: string | null;
  risk_impact?: string;
  scope?: Record<string, any>;
  confirmation_summary?: string[];
  post_action_result?: string;
};

type OperationState = {
  control: Control;
  loading: boolean;
  error: string | null;
  preflight: any | null;
  result: any | null;
  confirmationPhrase: string;
};

const statusTone: Record<string, { panel: string; badge: 'normal' | 'warning' | 'danger' | 'caution' | 'muted'; icon: any }> = {
  safe: {
    panel: 'border-emerald-200 bg-emerald-50 text-emerald-950 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-100',
    badge: 'normal',
    icon: CheckCircle2,
  },
  warning: {
    panel: 'border-amber-200 bg-amber-50 text-amber-950 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-100',
    badge: 'warning',
    icon: AlertTriangle,
  },
  blocked: {
    panel: 'border-rose-200 bg-rose-50 text-rose-950 dark:border-rose-900/50 dark:bg-rose-950/20 dark:text-rose-100',
    badge: 'danger',
    icon: Lock,
  },
  active_position: {
    panel: 'border-blue-200 bg-blue-50 text-blue-950 dark:border-blue-900/50 dark:bg-blue-950/20 dark:text-blue-100',
    badge: 'caution',
    icon: Activity,
  },
  review_required: {
    panel: 'border-amber-200 bg-amber-50 text-amber-950 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-100',
    badge: 'warning',
    icon: ClipboardCheck,
  },
  recovery_required: {
    panel: 'border-rose-200 bg-rose-50 text-rose-950 dark:border-rose-900/50 dark:bg-rose-950/20 dark:text-rose-100',
    badge: 'danger',
    icon: DatabaseZap,
  },
  paused: {
    panel: 'border-slate-200 bg-slate-100 text-slate-900 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100',
    badge: 'muted',
    icon: CirclePause,
  },
  revoked: {
    panel: 'border-rose-200 bg-rose-50 text-rose-950 dark:border-rose-900/50 dark:bg-rose-950/20 dark:text-rose-100',
    badge: 'danger',
    icon: Lock,
  },
};

function controlIcon(id: string) {
  if (id === 'refresh_status') return RefreshCw;
  if (id === 'reconcile_now') return DatabaseZap;
  if (id === 'pause_autonomy') return CirclePause;
  if (id === 'revoke_budget') return Lock;
  if (id === 'open_review_item') return ClipboardCheck;
  return FileSearch;
}

function statusCopy(status?: string): string {
  const map: Record<string, string> = {
    safe: '安全',
    warning: '需关注',
    blocked: '阻断',
    active_position: '持仓中',
    review_required: '待复盘',
    recovery_required: '需恢复',
    paused: '已暂停',
    revoked: '已撤销',
  };
  return map[String(status || '')] || '无法确认';
}

function controlDisabledReason(control: Control): string {
  if (!control.disabled_reason) return '当前不可操作';
  if (control.disabled_reason.includes('Operation Layer POST')) return '控制台尚未接入 Operation Layer 提交入口';
  if (control.disabled_reason.includes('budget-revoke')) return '预算撤销 API 尚未接入当前预算读模型';
  return control.disabled_reason;
}

function controlConfirmLabel(control: Control): string {
  if (control.control_id === 'pause_autonomy') return '确认暂停自治';
  if (control.control_id === 'revoke_budget') return '确认撤销预算';
  return `确认${control.label}`;
}

function controlImpactCopy(control: Control): string {
  if (control.risk_impact) return control.risk_impact;
  return 'Operation Layer 会先预检，再要求 Owner 输入确认短语；该控制不会下单、撤单、平仓、转账或提现。';
}

function MetricTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
      <div className="text-xs font-medium text-slate-500">{label}</div>
      <div className="mt-1 min-h-7 break-words font-mono text-lg font-semibold text-slate-950 dark:text-slate-100">{value}</div>
      {sub && <div className="mt-1 min-h-4 text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

function SectionTitle({ icon: Icon, title, action }: { icon: any; title: string; action?: ReactNode }) {
  return (
    <div className="mb-4 flex items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 text-slate-500" />
        <h2 className="text-base font-semibold">{title}</h2>
      </div>
      {action}
    </div>
  );
}

export default function Dashboard() {
  const [refreshNonce, setRefreshNonce] = useState(0);
  const endpoint = useMemo(
    () => `/api/trading-console/operations-cockpit?include_exchange=true&_=${refreshNonce}`,
    [refreshNonce],
  );
  const { envelope, loading, error } = useReadModel<any>(endpoint);
  const [operationState, setOperationState] = useState<OperationState | null>(null);

  async function runOperationPreflight(control: Control) {
    if (!control.operation_type) return;
    setOperationState({
      control,
      loading: true,
      error: null,
      preflight: null,
      result: null,
      confirmationPhrase: '',
    });
    try {
      const response = await fetch('/api/brc/operations/preflight', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          operation_type: control.operation_type,
          requested_by: 'owner',
          input_params: {
            reason: `${control.control_id} from trading console cockpit`,
            control_id: control.control_id,
            budget_authorization_id: control.scope?.budget_authorization_id,
          },
          source: { kind: 'trading_console_cockpit', ref: control.control_id },
        }),
      });
      if (response.status === 401) {
        window.dispatchEvent(new Event('trading-console:unauthorized'));
      }
      if (!response.ok) throw new Error(`POST /api/brc/operations/preflight returned HTTP ${response.status}`);
      const payload = await response.json();
      setOperationState({
        control,
        loading: false,
        error: null,
        preflight: payload,
        result: null,
        confirmationPhrase: '',
      });
    } catch (err) {
      setOperationState({
        control,
        loading: false,
        error: err instanceof Error ? err.message : String(err),
        preflight: null,
        result: null,
        confirmationPhrase: '',
      });
    }
  }

  async function confirmOperation() {
    if (!operationState?.preflight) return;
    const preflight = operationState.preflight;
    setOperationState({ ...operationState, loading: true, error: null });
    try {
      const response = await fetch(`/api/brc/operations/${preflight.operation_id}/confirm`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          preflight_id: preflight.preflight_id,
          confirmation_phrase: operationState.confirmationPhrase,
          idempotency_key: preflight.idempotency_key,
          confirmed_by: 'owner',
        }),
      });
      if (response.status === 401) {
        window.dispatchEvent(new Event('trading-console:unauthorized'));
      }
      if (!response.ok) throw new Error(`POST /api/brc/operations/${preflight.operation_id}/confirm returned HTTP ${response.status}`);
      const payload = await response.json();
      setOperationState({
        ...operationState,
        loading: false,
        error: null,
        result: payload,
      });
      setRefreshNonce((value) => value + 1);
    } catch (err) {
      setOperationState({
        ...operationState,
        loading: false,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }

  function openEvidence() {
    const evidence = document.getElementById('cockpit-evidence');
    const details = evidence?.querySelector('details');
    if (details instanceof HTMLDetailsElement) details.open = true;
    evidence?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  if (loading) return <div className="p-4 text-sm text-slate-500">正在读取当前内容...</div>;

  const data = envelope?.data || {};
  const overall = data.overall_status || {};
  const nextAction = data.primary_next_action || {};
  const autonomy = data.autonomy || {};
  const budget = data.budget || {};
  const position = data.active_position || {};
  const protection = data.protection || {};
  const candidate = data.candidate || {};
  const review = data.review || {};
  const recovery = data.recovery || {};
  const controls = asArray<Control>(data.controls);
  const blockers = asArray<any>(data.blockers);
  const warnings = asArray<any>(data.warnings);
  const tone = statusTone[String(overall.status || 'warning')] || statusTone.warning;
  const StatusIcon = tone.icon;

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <PageHeader
        title="Autonomy Operations Cockpit"
        subtitle="Owner 打开后先看安全、自治、仓位保护、预算和下一步动作。"
        status={envelope?.freshness_status}
      >
        <button
          type="button"
          onClick={() => setRefreshNonce((value) => value + 1)}
          className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          <RefreshCw className="h-4 w-4" />
          刷新
        </button>
      </PageHeader>

      <section className={cn('rounded-lg border p-5', tone.panel)}>
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <StatusIcon className="h-6 w-6 shrink-0" />
              <Badge variant={tone.badge}>{statusCopy(overall.status)}</Badge>
              <span className="text-xs opacity-75">更新：{formatTimestampMs(envelope?.generated_at_ms)}</span>
            </div>
            <h1 className="mt-4 max-w-4xl text-2xl font-semibold tracking-tight md:text-3xl">
              {displayValue(data.primary_message || overall.message, '当前系统状态无法确认')}
            </h1>
            <p className="mt-3 max-w-3xl text-sm opacity-80">
              自治状态：{displayValue(autonomy.label, '无法确认')} · {displayValue(autonomy.message, '暂无说明')}
            </p>
          </div>

          <div className="rounded-md border border-white/40 bg-white/70 p-4 text-slate-900 shadow-sm dark:border-slate-700 dark:bg-slate-950/60 dark:text-slate-100">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Primary Next Action</div>
            <div className="mt-2 text-lg font-semibold">{displayValue(nextAction.label, '刷新状态')}</div>
            <p className="mt-2 min-h-10 text-sm text-slate-600 dark:text-slate-400">{displayValue(nextAction.reason, '读取最新状态。')}</p>
            {nextAction.enabled && nextAction.route ? (
              <Link
                to={nextAction.route}
                className="mt-4 inline-flex w-full cursor-pointer items-center justify-center rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                打开查看
              </Link>
            ) : (
              <button
                type="button"
                disabled
                className="mt-4 w-full cursor-not-allowed rounded-md border border-slate-200 bg-slate-100 px-3 py-2 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900"
              >
                当前不可操作
              </button>
            )}
          </div>
        </div>
      </section>

      <EnvelopeStatus envelope={envelope} error={error} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
        <MetricTile
          label="预算剩余"
          value={formatMoney(budget.remaining_budget)}
          sub={`总预算 ${formatMoney(budget.total_budget)} · 单次 ${formatMoney(budget.per_action_max_notional)}`}
        />
        <MetricTile
          label="今日尝试"
          value={`${displayValue(budget.daily_attempts_used, '0')} / ${displayValue(budget.daily_max_attempts, '暂无')}`}
          sub={`剩余 ${displayValue(budget.daily_attempts_remaining, '暂无')} · ${budget.another_action_allowed ? '可继续评审' : '不可继续'}`}
        />
        <MetricTile
          label="仓位"
          value={position.exists ? `${displayValue(position.symbol, '未知')} ${sideLabel(position.side)}` : '无活跃仓位'}
          sub={position.exists ? `数量 ${displayValue(position.quantity, '暂无')} · 名义 ${formatMoney(position.notional)}` : 'PG/交易所未显示活跃仓位'}
        />
        <MetricTile
          label="保护"
          value={protectionStatusLabel(protection.status)}
          sub={`TP ${displayValue(protection.tp_count, '0')} · SL ${displayValue(protection.sl_count, '0')}`}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Card className="p-5">
          <SectionTitle icon={WalletCards} title="预算与自治" action={<Badge variant={budget.another_action_allowed ? 'normal' : 'warning'}>{budget.another_action_allowed ? '预算可评审' : '预算不可行动'}</Badge>} />
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <MetricTile label="状态" value={displayValue(budget.label, '无法确认')} />
            <MetricTile label="允许标的" value={asArray<string>(budget.authorized_scope?.symbols).join(', ') || '暂无'} />
            <MetricTile label="最大杠杆" value={displayValue(budget.authorized_scope?.max_leverage, '暂无')} />
          </div>
          <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm dark:border-slate-800 dark:bg-slate-950">
            <div className="font-medium">自治判断</div>
            <div className="mt-1 text-slate-600 dark:text-slate-400">
              {displayValue(autonomy.message, '暂无自治说明')}
            </div>
            <div className="mt-2 text-xs text-slate-500">
              Loop：{displayValue(autonomy.loop_outcome, 'unknown')} · 授权：{displayValue(autonomy.authorization_status, 'unknown')} · 自动执行：关闭
            </div>
          </div>
        </Card>

        <Card className="p-5">
          <SectionTitle icon={ShieldCheck} title="当前仓位 / 保护" />
          {position.exists ? (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-2">
                <MetricTile label="标的" value={displayValue(position.symbol, '未知')} />
                <MetricTile label="方向" value={sideLabel(position.side)} />
                <MetricTile label="入场" value={formatMoney(position.entry_price)} />
                <MetricTile label="标记价" value={formatMoney(position.current_mark_price)} />
                <MetricTile label="未实现 PnL" value={formatMoney(position.unrealized_pnl)} />
                <MetricTile label="一致性" value={displayValue(position.pg_exchange_consistency, '无法确认')} />
              </div>
              <Link to="/protection" className="inline-flex w-full items-center justify-center rounded-md border border-slate-200 px-3 py-2 text-sm font-medium hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800">
                查看保护健康
              </Link>
            </div>
          ) : (
            <div className="rounded-md border border-dashed border-slate-200 p-6 text-center text-sm text-slate-500 dark:border-slate-800">
              当前没有活跃仓位。若准备新动作，仍需预算、授权、FinalGate 和保护计划全部通过。
            </div>
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="p-5">
          <SectionTitle icon={TimerReset} title="恢复 / 清理" action={<Badge variant={recovery.required ? 'danger' : 'normal'}>{recovery.required ? '需处理' : '未发现'}</Badge>} />
          <p className="min-h-12 text-sm text-slate-600 dark:text-slate-400">{displayValue(recovery.summary, '暂无恢复状态')}</p>
          <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
            <MetricTile label="恢复任务" value={String(asArray(recovery.recovery_tasks).length)} />
            <MetricTile label="不一致" value={String(asArray(recovery.mismatches).length)} />
          </div>
          <Link to="/recovery" className="mt-4 inline-flex w-full items-center justify-center rounded-md border border-slate-200 px-3 py-2 text-sm font-medium hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800">
            查看恢复建议
          </Link>
        </Card>

        <Card className="p-5">
          <SectionTitle icon={ClipboardCheck} title="复盘" action={<Badge variant={review.review_required_before_next_action ? 'warning' : 'muted'}>{review.review_required_before_next_action ? '待复盘' : '无阻断'}</Badge>} />
          <div className="space-y-3 text-sm">
            <MetricTile label="待复盘" value={String(review.pending_review_count || 0)} />
            <div className="rounded-md border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-950">
              <div className="text-xs font-medium text-slate-500">最近交易状态</div>
              <div className="mt-1">{displayValue(review.latest_closed_trade?.status, '暂无关闭交易')}</div>
              <div className="mt-1 text-xs text-slate-500">结果：{displayValue(review.latest_closed_trade?.strategy_outcome, 'pending')}</div>
            </div>
          </div>
          <Link to="/review" className="mt-4 inline-flex w-full items-center justify-center rounded-md border border-slate-200 px-3 py-2 text-sm font-medium hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800">
            打开复盘
          </Link>
        </Card>

        <Card className="p-5">
          <SectionTitle icon={ShieldQuestion} title="候选 / 下一动作" />
          <div className="space-y-3 text-sm">
            <MetricTile label="候选" value={displayValue(candidate.selected?.carrier_id, '暂无候选')} sub={displayValue(candidate.selected?.family, '暂无策略族')} />
            <MetricTile label="标的 / 方向" value={`${displayValue(candidate.selected?.symbol, '暂无')} · ${sideLabel(candidate.selected?.side)}`} />
          </div>
          <Link to="/action-entry" className="mt-4 inline-flex w-full items-center justify-center rounded-md border border-slate-200 px-3 py-2 text-sm font-medium hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800">
            查看候选与预算
          </Link>
        </Card>
      </div>

      <Card className="p-5">
        <SectionTitle icon={Activity} title="控制" />
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          {controls.map((control) => {
            const Icon = controlIcon(control.control_id);
            const card = (
              <div className={cn(
                'min-h-28 rounded-md border p-3 text-left transition',
                control.enabled
                  ? 'cursor-pointer border-slate-200 bg-white hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:hover:bg-slate-800'
                  : 'cursor-not-allowed border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-800 dark:bg-slate-900/70',
              )}>
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 font-medium">
                    <Icon className="h-4 w-4 shrink-0" />
                    <span>{control.label}</span>
                  </div>
                  <Badge variant={control.enabled ? 'normal' : 'muted'}>{control.enabled ? '可用' : '禁用'}</Badge>
                </div>
                <p className="mt-2 line-clamp-3 text-xs text-slate-500">
                  {control.enabled ? displayValue(control.risk_impact || control.post_action_result || control.kind, '可执行控制') : controlDisabledReason(control)}
                </p>
                {control.confirmation_required && <div className="mt-2 text-xs font-medium text-amber-600">需要确认</div>}
              </div>
            );
            if (!control.enabled) return <div key={control.control_id}>{card}</div>;
            if (control.kind === 'operation_layer_preflight') {
              return (
                <button
                  key={control.control_id}
                  type="button"
                  onClick={() => void runOperationPreflight(control)}
                  disabled={operationState?.loading}
                  className="w-full disabled:opacity-70"
                >
                  {card}
                </button>
              );
            }
            if (control.control_id === 'refresh_status') {
              return (
                <button
                  key={control.control_id}
                  type="button"
                  onClick={() => setRefreshNonce((value) => value + 1)}
                  className="w-full"
                >
                  {card}
                </button>
              );
            }
            if (control.control_id === 'view_evidence') {
              return (
                <button key={control.control_id} type="button" onClick={openEvidence} className="w-full">
                  {card}
                </button>
              );
            }
            if (control.route) return <Link key={control.control_id} to={control.route}>{card}</Link>;
            return <div key={control.control_id}>{card}</div>;
          })}
        </div>
        {operationState && (
          <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-4 text-sm dark:border-slate-800 dark:bg-slate-950">
            <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
              <div>
                <div className="font-semibold">{operationState.control.label}</div>
                <p className="mt-1 text-slate-600 dark:text-slate-400">
                  {controlImpactCopy(operationState.control)}
                </p>
                {asArray<string>(operationState.control.confirmation_summary).length > 0 && (
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-slate-500 dark:text-slate-400">
                    {asArray<string>(operationState.control.confirmation_summary).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                )}
              </div>
              <button
                type="button"
                onClick={() => setOperationState(null)}
                className="rounded-md border border-slate-200 px-3 py-1.5 text-xs font-medium hover:bg-white dark:border-slate-800 dark:hover:bg-slate-900"
              >
                关闭
              </button>
            </div>
            {operationState.loading && <div className="mt-3 text-slate-500">正在执行 Operation Layer 请求...</div>}
            {operationState.error && (
              <div className="mt-3 rounded-md border border-rose-200 bg-rose-50 p-3 text-rose-900 dark:border-rose-900/50 dark:bg-rose-950/20 dark:text-rose-200">
                {operationState.error}
              </div>
            )}
            {operationState.preflight && (
              <div className="mt-4 space-y-3">
                <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                  <MetricTile label="预检状态" value={displayValue(operationState.preflight.status, '无法确认')} />
                  <MetricTile label="决策" value={displayValue(operationState.preflight.decision, '无法确认')} />
                  <MetricTile label="操作 ID" value={displayValue(operationState.preflight.operation_id, '暂无')} />
                </div>
                <div className="rounded-md border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
                  <div className="text-xs font-medium text-slate-500">预检摘要</div>
                  <p className="mt-1 text-slate-700 dark:text-slate-300">{displayValue(operationState.preflight.summary, '暂无摘要')}</p>
                  {asArray<string>(operationState.preflight.risk_summary?.blockers).length > 0 && (
                    <div className="mt-2 text-xs text-rose-600">
                      阻断：{asArray<string>(operationState.preflight.risk_summary?.blockers).join('；')}
                    </div>
                  )}
                  {asArray<string>(operationState.preflight.risk_summary?.warnings).length > 0 && (
                    <div className="mt-2 text-xs text-amber-600">
                      警告：{asArray<string>(operationState.preflight.risk_summary?.warnings).join('；')}
                    </div>
                  )}
                </div>
                {operationState.preflight.status === 'awaiting_confirmation' && operationState.preflight.confirmation_requirement?.phrase && !operationState.result && (
                  <div className="rounded-md border border-amber-200 bg-amber-50 p-3 dark:border-amber-900/40 dark:bg-amber-950/20">
                    <label className="block text-xs font-medium text-amber-800 dark:text-amber-200">
                      输入确认短语：{operationState.preflight.confirmation_requirement.phrase}
                    </label>
                    <input
                      value={operationState.confirmationPhrase}
                      onChange={(event) => setOperationState({ ...operationState, confirmationPhrase: event.target.value })}
                      className="mt-2 w-full rounded-md border border-amber-200 bg-white px-3 py-2 font-mono text-sm text-slate-900 outline-none focus:ring-2 focus:ring-amber-500 dark:border-amber-900/50 dark:bg-slate-950 dark:text-slate-100"
                    />
                    <button
                      type="button"
                      onClick={() => void confirmOperation()}
                      disabled={operationState.loading || operationState.confirmationPhrase !== operationState.preflight.confirmation_requirement.phrase}
                      className="mt-3 inline-flex cursor-pointer items-center rounded-md bg-amber-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-amber-700 disabled:cursor-not-allowed disabled:bg-amber-300"
                    >
                      {controlConfirmLabel(operationState.control)}
                    </button>
                  </div>
                )}
                {operationState.result && (
                  <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-emerald-900 dark:border-emerald-900/40 dark:bg-emerald-950/20 dark:text-emerald-200">
                    <div className="font-medium">执行结果：{displayValue(operationState.result.status, '无法确认')}</div>
                    <div className="mt-1 text-xs">{displayValue(operationState.result.result_summary?.message, 'Operation Layer 已返回结果。')}</div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </Card>

      <Card className="p-5">
        <SectionTitle icon={AlertTriangle} title="阻断与警告" />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div>
            <div className="mb-2 text-sm font-medium">阻断</div>
            {blockers.length === 0 ? (
              <div className="rounded-md border border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800">当前没有 cockpit 阻断。</div>
            ) : (
              <div className="space-y-2">
                {blockers.map((item, index) => (
                  <Link key={`${item.code}-${index}`} to={item.route || '/execution'} className="block rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900 hover:bg-rose-100 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-200">
                    <div className="font-medium">{displayValue(item.what, '存在阻断')}</div>
                    <div className="mt-1 text-xs opacity-80">{displayValue(item.clears_when, '等待条件清除')}</div>
                  </Link>
                ))}
              </div>
            )}
          </div>
          <div>
            <div className="mb-2 text-sm font-medium">警告</div>
            {warnings.length === 0 ? (
              <div className="rounded-md border border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800">当前没有额外警告。</div>
            ) : (
              <div className="space-y-2">
                {warnings.map((item, index) => (
                  <div key={`${item.code}-${index}`} className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200">
                    <div className="font-medium">{blockingReasonLabel(item.message || item.code)}</div>
                    <div className="mt-1 text-xs opacity-80">{displayValue(item.source, 'read_model')}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </Card>

      <div id="cockpit-evidence">
        <TechnicalDetails title="技术证据">
          <pre className="overflow-auto font-mono">{JSON.stringify(data.evidence || data, null, 2)}</pre>
        </TechnicalDetails>
      </div>
    </div>
  );
}
