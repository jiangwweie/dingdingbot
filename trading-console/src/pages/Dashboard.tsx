import { useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CirclePause,
  DatabaseZap,
  FileSearch,
  FolderSearch,
  Lock,
  RefreshCw,
  ShieldCheck,
  WalletCards,
} from 'lucide-react';
import {
  ActionNudge,
  ConsolePanel,
  EntityRow,
  InspectorPanel,
  MetricRailItem,
  StatusChip,
  type ConsoleTone,
} from '@/components/console/ConsolePrimitives';
import { TechnicalDetails } from '@/components/ui';
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

const statusTone: Record<string, ConsoleTone> = {
  safe: 'normal',
  warning: 'attention',
  active_position: 'normal',
  review_required: 'attention',
  recovery_required: 'intervention',
  blocked: 'blocked',
  paused: 'attention',
  revoked: 'blocked',
};

const statusCopy: Record<string, string> = {
  safe: '当前无需操作',
  warning: '有待关注项',
  blocked: '需要介入',
  active_position: '持仓监控中',
  review_required: '需要分析确认',
  recovery_required: '需要介入',
  paused: '已暂停',
  revoked: '预算已撤销',
};

function productRoute(route?: string | null): string {
  const map: Record<string, string> = {
    '/ledger': '/trades',
    '/protection': '/trades',
    '/review': '/analysis',
    '/recovery': '/incident',
    '/audit': '/evidence',
    '/carrier': '/strategy',
    '/authorization': '/runtime',
    '/execution': '/runtime',
    '/action-entry': '/runtime',
  };
  return route ? map[route] || route : '/';
}

function controlIcon(id: string) {
  if (id === 'refresh_status') return RefreshCw;
  if (id === 'reconcile_now') return DatabaseZap;
  if (id === 'pause_autonomy') return CirclePause;
  if (id === 'revoke_budget') return Lock;
  if (id === 'view_evidence') return FolderSearch;
  return FileSearch;
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
  return 'Operation Layer 会先预检，再要求 Owner 输入确认短语；不会下单、撤单、平仓、转账或提现。';
}

function ownerStatusTone(status?: string): ConsoleTone {
  return statusTone[String(status || '')] || 'attention';
}

function ownerStatusCopy(status?: string): string {
  return statusCopy[String(status || '')] || '状态待确认';
}

function resultTone(status?: string): ConsoleTone {
  const text = String(status || '').toLowerCase();
  if (text.includes('block') || text.includes('revoked')) return 'blocked';
  if (text.includes('required') || text.includes('warning') || text.includes('pending')) return 'attention';
  if (text.includes('safe') || text.includes('protected') || text.includes('available')) return 'normal';
  return 'unavailable';
}

function SoftButton({
  children,
  to,
  onClick,
  disabled = false,
  tone = 'neutral',
}: {
  children: ReactNode;
  to?: string;
  onClick?: () => void;
  disabled?: boolean;
  tone?: 'neutral' | 'attention' | 'danger';
}) {
  const classes = cn(
    'inline-flex min-h-9 cursor-pointer items-center justify-center gap-2 rounded-md border px-3 py-2 text-sm font-medium transition focus:outline-none focus:ring-2 focus:ring-blue-500',
    tone === 'danger'
      ? 'border-rose-500/40 bg-rose-500/10 text-rose-200 hover:bg-rose-500/20'
      : tone === 'attention'
        ? 'border-amber-500/40 bg-amber-500/10 text-amber-100 hover:bg-amber-500/20'
        : 'border-slate-700 bg-slate-800/70 text-slate-200 hover:bg-slate-800',
    disabled && 'cursor-not-allowed opacity-50 hover:bg-slate-800/70',
  );
  if (to && !disabled) return <Link to={to} className={classes}>{children}</Link>;
  return (
    <button type="button" onClick={onClick} disabled={disabled} className={classes}>
      {children}
    </button>
  );
}

export default function Dashboard() {
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [nudgeVisible, setNudgeVisible] = useState(true);
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
            reason: `${control.control_id} from trading console control overview`,
            control_id: control.control_id,
            budget_authorization_id: control.scope?.budget_authorization_id,
          },
          source: { kind: 'trading_console_control_overview', ref: control.control_id },
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

  if (loading) {
    return (
      <div className="flex min-h-[480px] items-center justify-center rounded-md border border-slate-800 bg-slate-900/50 text-sm text-slate-400">
        正在读取控制总览...
      </div>
    );
  }

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
  const postAction = data.evidence?.post_action_state || {};
  const controls = asArray<Control>(data.controls);
  const blockers = asArray<any>(data.blockers);
  const warnings = asArray<any>(data.warnings);
  const unavailable = asArray<any>(envelope?.unavailable);
  const tone = ownerStatusTone(overall.status);
  const attentionCount = warnings.length + unavailable.length + (review.review_required_before_next_action ? 1 : 0);
  const interventionCount = blockers.length + (recovery.required ? 1 : 0);
  const recentTradeCount = Number(postAction.completed_intent_count ?? postAction.intent_count ?? 0);
  const runtimeCount = autonomy.state || budget.status || position.exists ? 1 : 0;
  const selected = candidate.selected || {};

  const inspectorItems = [
    {
      title: '边界内',
      body: budget.another_action_allowed
        ? '预算和尝试仍显示可评审；真正行动仍需要授权、FinalGate、保护和审计链路。'
        : displayValue(budget.message || budget.retry_condition, '预算或尝试状态不可确认，系统不会从前端推断可行动。'),
      tone: budget.another_action_allowed ? 'normal' as ConsoleTone : 'attention' as ConsoleTone,
      action: <SoftButton to="/runtime">查看运行治理</SoftButton>,
    },
    {
      title: protection.status === 'protected' ? '保护正常' : '保护待确认',
      body: position.exists
        ? `当前仓位保护状态：${protectionStatusLabel(protection.status)}。新尝试应等待仓位关闭或保护重新确认。`
        : '当前没有活跃仓位；进入新尝试前仍需要保护计划和账户事实通过。',
      tone: protection.status === 'protected' || !position.exists ? 'normal' as ConsoleTone : 'attention' as ConsoleTone,
      action: <SoftButton to="/trades">查看交易与仓位</SoftButton>,
    },
    {
      title: interventionCount > 0 ? '存在介入项' : '无异常介入',
      body: interventionCount > 0
        ? displayValue(blockers[0]?.what || blockers[0]?.message || recovery.summary, '需要查看异常介入面板。')
        : '当前未看到需要 Owner 立即介入的异常事件。',
      tone: interventionCount > 0 ? 'intervention' as ConsoleTone : 'normal' as ConsoleTone,
      action: <SoftButton to="/incident" tone={interventionCount > 0 ? 'danger' : 'neutral'}>进入异常介入</SoftButton>,
    },
    {
      title: attentionCount > 0 ? '保持关注' : '暂无关注项',
      body: attentionCount > 0
        ? '存在警告、缺失事实或待分析事项；这些不是自动执行授权。'
        : '当前没有额外警告；证据仍可随时展开核对。',
      tone: attentionCount > 0 ? 'attention' as ConsoleTone : 'normal' as ConsoleTone,
      action: <SoftButton onClick={openEvidence}>查看证据</SoftButton>,
    },
  ];

  return (
    <div className="mx-auto max-w-[1500px] space-y-4">
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusChip tone={tone}>{ownerStatusCopy(overall.status)}</StatusChip>
            {error && <StatusChip tone="intervention">内容暂不可用</StatusChip>}
          </div>
          <h1 className="mt-4 text-3xl font-semibold text-slate-100">控制总览</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
            {displayValue(data.primary_message || overall.message, '当前系统状态无法确认。')}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SoftButton onClick={() => setRefreshNonce((value) => value + 1)}>
            <RefreshCw className="h-4 w-4" />
            刷新
          </SoftButton>
          <SoftButton to={productRoute(nextAction.route)} tone={nextAction.owner_action_required ? 'attention' : 'neutral'}>
            {displayValue(nextAction.label, '查看状态')}
          </SoftButton>
        </div>
      </header>

      <ConsolePanel>
        <div className="grid grid-cols-1 md:grid-cols-4">
          <MetricRailItem label="Runtime" value={runtimeCount} tone={tone} sub={displayValue(autonomy.label, '状态待确认')} />
          <MetricRailItem label="Attention" value={attentionCount} tone={attentionCount > 0 ? 'attention' : 'normal'} sub="待关注" />
          <MetricRailItem label="Intervention" value={interventionCount} tone={interventionCount > 0 ? 'intervention' : 'normal'} sub="需介入" />
          <MetricRailItem label="Recent Trades" value={recentTradeCount} tone="unavailable" sub="最近交易事实" />
        </div>
      </ConsolePanel>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-4">
          <ConsolePanel title="运行实例概览" caption="优先展示边界、尝试、保护和候选上下文">
            <EntityRow
              title={displayValue(selected.carrier_id || selected.family, '当前无候选策略')}
              subtitle={displayValue(selected.reason_selected, '策略候选和运行绑定由后端 readmodel 决定')}
              tone={resultTone(autonomy.state)}
              active={Boolean(selected.carrier_id)}
              cells={[
                { label: '市场', value: displayValue(selected.symbol || position.symbol, '暂无') },
                { label: '方向', value: sideLabel(selected.side || position.side) },
                { label: '模式', value: displayValue(autonomy.label, '无法确认') },
                { label: '状态', value: displayValue(budget.label || overall.label, '待确认'), className: 'text-emerald-200' },
              ]}
              action={<SoftButton to="/runtime">治理</SoftButton>}
            />
            <EntityRow
              title="运行边界"
              subtitle="预算、尝试和杠杆是边界，不是收益承诺"
              tone={budget.another_action_allowed ? 'normal' : 'attention'}
              cells={[
                { label: '预算剩余', value: formatMoney(budget.remaining_budget) },
                { label: '总预算', value: formatMoney(budget.total_budget) },
                { label: '尝试', value: `${displayValue(budget.daily_attempts_used, '0')} / ${displayValue(budget.daily_max_attempts, '暂无')}` },
                { label: '最大杠杆', value: displayValue(budget.authorized_scope?.max_leverage, '暂无') },
              ]}
              action={<SoftButton to="/runtime">边界</SoftButton>}
            />
            <EntityRow
              title={position.exists ? `${displayValue(position.symbol, '未知')} ${sideLabel(position.side)}` : '当前无活跃仓位'}
              subtitle={position.exists ? '仓位存在时不展示新买卖入口' : '没有仓位不等于可直接执行'}
              tone={position.exists ? resultTone(protection.status) : 'normal'}
              cells={[
                { label: '名义', value: formatMoney(position.notional) },
                { label: '未实现 PnL', value: formatMoney(position.unrealized_pnl) },
                { label: '保护', value: protectionStatusLabel(protection.status) },
                { label: 'TP / SL', value: `${displayValue(protection.tp_count, '0')} / ${displayValue(protection.sl_count, '0')}` },
              ]}
              action={<SoftButton to="/trades">仓位</SoftButton>}
            />
          </ConsolePanel>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <ConsolePanel title="策略表现" caption="右尾复盘指标待接入；缺失时不推断收益质量">
              <div className="divide-y divide-slate-800/90">
                <StrategyMetricRow
                  name={displayValue(selected.family, '策略族待选择')}
                  subtitle={displayValue(selected.carrier_id, '当前 readmodel 未提供策略表现序列')}
                  pnl={formatMoney(review.latest_closed_trade?.realized_pnl)}
                  status={selected.carrier_id ? '保持观察' : '数据待补'}
                />
                <StrategyMetricRow
                  name="右尾指标"
                  subtitle="MFE / MAE / R multiple / runner giveback"
                  pnl="待接入"
                  status="分析"
                />
              </div>
            </ConsolePanel>

            <ConsolePanel title="最近交易" caption="交易事实连接到策略 / runtime 后再进入分析">
              <div className="divide-y divide-slate-800/90">
                <TradeFactRow
                  time={formatTimestampMs(review.latest_closed_trade?.closed_at_ms)}
                  strategy={displayValue(review.latest_closed_trade?.strategy_family_id || selected.family, '暂无策略')}
                  result={displayValue(review.latest_closed_trade?.strategy_outcome, '暂无关闭交易')}
                  pnl={formatMoney(review.latest_closed_trade?.realized_pnl)}
                />
                <TradeFactRow
                  time={formatTimestampMs(envelope?.generated_at_ms)}
                  strategy="Review Ledger"
                  result={displayValue(review.review_status || review.status, '等待分析事实')}
                  pnl="待核对"
                />
              </div>
              <div className="border-t border-slate-800 px-4 py-3">
                <SoftButton to="/analysis">查看分析</SoftButton>
              </div>
            </ConsolePanel>
          </div>

          <ConsolePanel title="治理动作" caption="只展示当前后端已暴露的控制和导航；不提供买卖按钮">
            <div className="grid grid-cols-1 gap-px bg-slate-800/80 md:grid-cols-2 xl:grid-cols-4">
              {controls.map((control) => (
                <div key={control.control_id}>
                  <ControlTile
                    control={control}
                    loading={operationState?.loading}
                    onPreflight={() => void runOperationPreflight(control)}
                    onRefresh={() => setRefreshNonce((value) => value + 1)}
                    onEvidence={openEvidence}
                  />
                </div>
              ))}
            </div>
            {operationState && (
              <OperationPreflightPanel
                state={operationState}
                setState={setOperationState}
                onConfirm={() => void confirmOperation()}
              />
            )}
          </ConsolePanel>
        </div>

        <InspectorPanel
          items={inspectorItems}
          footer={
            <div className="text-xs leading-5 text-slate-500">
              说明：控制台只呈现官方 readmodel / Operation Layer 路径。FinalGate preview、shadow runtime、候选和授权状态都不会自动变成下单权限。
            </div>
          }
        />
      </div>

      {nudgeVisible && (attentionCount > 0 || interventionCount > 0) && (
        <ActionNudge
          tone={interventionCount > 0 ? 'intervention' : 'attention'}
          text={
            interventionCount > 0
              ? displayValue(blockers[0]?.what || blockers[0]?.message || recovery.summary, '存在需要介入的事项')
              : displayValue(warnings[0]?.message || unavailable[0]?.error, '存在待关注或待补数据')
          }
          action={<SoftButton to={interventionCount > 0 ? '/incident' : '/evidence'}>查看</SoftButton>}
          onDismiss={() => setNudgeVisible(false)}
        />
      )}

      <div id="cockpit-evidence">
        <TechnicalDetails title="证据与技术细节">
          <pre className="overflow-auto font-mono text-xs leading-5">{JSON.stringify(data.evidence || data, null, 2)}</pre>
        </TechnicalDetails>
      </div>
    </div>
  );
}

function StrategyMetricRow({
  name,
  subtitle,
  pnl,
  status,
}: {
  name: string;
  subtitle: string;
  pnl: string;
  status: string;
}) {
  return (
    <div className="grid min-h-16 grid-cols-[minmax(0,1fr)_120px_88px] items-center gap-3 px-4 py-3 text-sm">
      <div className="min-w-0">
        <div className="truncate font-medium text-slate-100">{name}</div>
        <div className="mt-1 truncate text-xs text-slate-500">{subtitle}</div>
      </div>
      <div className="font-mono text-slate-300">{pnl}</div>
      <div className="text-right text-xs text-slate-400">{status}</div>
    </div>
  );
}

function TradeFactRow({
  time,
  strategy,
  result,
  pnl,
}: {
  time: string;
  strategy: string;
  result: string;
  pnl: string;
}) {
  return (
    <div className="grid min-h-16 grid-cols-[92px_minmax(0,1fr)_100px_88px] items-center gap-3 px-4 py-3 text-sm">
      <div className="truncate font-mono text-xs text-slate-500">{time}</div>
      <div className="truncate text-slate-200">{strategy}</div>
      <div className="truncate text-xs text-slate-400">{result}</div>
      <div className="truncate text-right font-mono text-slate-300">{pnl}</div>
    </div>
  );
}

function ControlTile({
  control,
  loading,
  onPreflight,
  onRefresh,
  onEvidence,
}: {
  control: Control;
  loading?: boolean;
  onPreflight: () => void;
  onRefresh: () => void;
  onEvidence: () => void;
}) {
  const Icon = controlIcon(control.control_id);
  const disabled = !control.enabled || loading;
  const content = (
    <div className={cn(
      'min-h-28 w-full bg-slate-900 px-4 py-3 text-left transition',
      control.enabled ? 'hover:bg-slate-800/80' : 'opacity-60',
    )}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <Icon className="h-4 w-4 shrink-0 text-slate-400" />
          <span className="truncate text-sm font-medium text-slate-100">{control.label}</span>
        </div>
        <StatusChip tone={control.enabled ? 'normal' : 'unavailable'} className="h-6 px-2">
          {control.enabled ? '可用' : '不可用'}
        </StatusChip>
      </div>
      <p className="mt-3 line-clamp-3 text-xs leading-5 text-slate-500">
        {control.enabled
          ? displayValue(control.risk_impact || control.post_action_result || control.kind, '可查看')
          : controlDisabledReason(control)}
      </p>
    </div>
  );

  if (control.kind === 'operation_layer_preflight') {
    return (
      <button type="button" onClick={onPreflight} disabled={disabled} className="w-full cursor-pointer disabled:cursor-not-allowed">
        {content}
      </button>
    );
  }
  if (control.control_id === 'refresh_status') {
    return (
      <button type="button" onClick={onRefresh} disabled={loading} className="w-full cursor-pointer disabled:cursor-not-allowed">
        {content}
      </button>
    );
  }
  if (control.control_id === 'view_evidence') {
    return (
      <button type="button" onClick={onEvidence} className="w-full cursor-pointer">
        {content}
      </button>
    );
  }
  if (control.route && control.enabled) return <Link to={productRoute(control.route)} className="block w-full">{content}</Link>;
  return <div className="w-full">{content}</div>;
}

function OperationPreflightPanel({
  state,
  setState,
  onConfirm,
}: {
  state: OperationState;
  setState: (state: OperationState | null) => void;
  onConfirm: () => void;
}) {
  return (
    <div className="border-t border-slate-800 bg-slate-950/45 p-4 text-sm">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="font-semibold text-slate-100">{state.control.label}</div>
          <p className="mt-1 max-w-3xl leading-6 text-slate-400">
            {controlImpactCopy(state.control)}
          </p>
          {asArray<string>(state.control.confirmation_summary).length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2">
              {asArray<string>(state.control.confirmation_summary).map((item) => (
                <span key={item}>
                  <StatusChip tone="unavailable">{item}</StatusChip>
                </span>
              ))}
            </div>
          )}
        </div>
        <SoftButton onClick={() => setState(null)}>关闭</SoftButton>
      </div>
      {state.loading && <div className="mt-3 text-slate-500">正在执行 Operation Layer 请求...</div>}
      {state.error && (
        <div className="mt-3 rounded-md border border-rose-500/35 bg-rose-500/10 p-3 text-rose-200">
          {state.error}
        </div>
      )}
      {state.preflight && (
        <div className="mt-4 space-y-3">
          <div className="grid grid-cols-1 gap-px overflow-hidden rounded-md border border-slate-800 bg-slate-800 md:grid-cols-3">
            <PreflightCell label="预检状态" value={displayValue(state.preflight.status, '无法确认')} />
            <PreflightCell label="决策" value={displayValue(state.preflight.decision, '无法确认')} />
            <PreflightCell label="操作 ID" value={displayValue(state.preflight.operation_id, '暂无')} />
          </div>
          <div className="rounded-md border border-slate-800 bg-slate-900 p-3">
            <div className="text-xs font-medium text-slate-500">预检摘要</div>
            <p className="mt-1 leading-6 text-slate-300">{displayValue(state.preflight.summary, '暂无摘要')}</p>
            {asArray<string>(state.preflight.risk_summary?.blockers).length > 0 && (
              <div className="mt-2 text-xs text-rose-300">
                阻断：{asArray<string>(state.preflight.risk_summary?.blockers).join('；')}
              </div>
            )}
            {asArray<string>(state.preflight.risk_summary?.warnings).length > 0 && (
              <div className="mt-2 text-xs text-amber-300">
                警告：{asArray<string>(state.preflight.risk_summary?.warnings).join('；')}
              </div>
            )}
          </div>
          {state.preflight.status === 'awaiting_confirmation' && state.preflight.confirmation_requirement?.phrase && !state.result && (
            <div className="rounded-md border border-amber-500/35 bg-amber-500/10 p-3">
              <label className="block text-xs font-medium text-amber-200">
                输入确认短语：{state.preflight.confirmation_requirement.phrase}
              </label>
              <input
                value={state.confirmationPhrase}
                onChange={(event) => setState({ ...state, confirmationPhrase: event.target.value })}
                className="mt-2 w-full rounded-md border border-amber-500/35 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 outline-none focus:ring-2 focus:ring-amber-500"
              />
              <SoftButton
                onClick={onConfirm}
                disabled={state.loading || state.confirmationPhrase !== state.preflight.confirmation_requirement.phrase}
                tone="attention"
              >
                {controlConfirmLabel(state.control)}
              </SoftButton>
            </div>
          )}
          {state.result && (
            <div className="rounded-md border border-emerald-500/35 bg-emerald-500/10 p-3 text-emerald-200">
              <div className="font-medium">执行结果：{displayValue(state.result.status, '无法确认')}</div>
              <div className="mt-1 text-xs">{displayValue(state.result.result_summary?.message, 'Operation Layer 已返回结果。')}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PreflightCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-slate-900 px-4 py-3">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="mt-1 truncate font-mono text-sm text-slate-200">{value}</div>
    </div>
  );
}
