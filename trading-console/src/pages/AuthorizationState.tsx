import { useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  FileSearch,
  Layers3,
  ShieldAlert,
  ShieldCheck,
  XCircle,
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
import { Badge, DeferredActionSlot, TechnicalDetails } from '@/components/ui';
import { actionSlotEntries, asArray, displayValue, formatTimestampMs, useReadModel } from '@/lib/tradingConsoleApi';
import { cn } from '@/lib/utils';
import { authorizationStatusLabel, blockingReasonLabel, formatMoney, sideLabel } from '@/lib/ownerViewModel';

type RuntimeView = {
  runtime_instance_id: string;
  strategy_family_id?: string;
  strategy_family_version_id?: string;
  trial_binding_id?: string;
  admission_decision_id?: string;
  carrier_id?: string | null;
  symbol?: string;
  side?: string;
  status?: string;
  boundary?: Record<string, any>;
  review_requirement?: string;
  execution_enabled?: boolean;
  execution_mode?: string;
  shadow_mode?: boolean;
  updated_at_ms?: number;
  expires_at_ms?: number | null;
};

type RuntimeLivePositionMonitorView = {
  monitor_id?: string;
  runtime_instance_id?: string;
  symbol?: string;
  side?: string;
  status?: string;
  protection_status?: string;
  runtime_status?: string;
  runtime_execution_enabled?: boolean;
  runtime_shadow_mode?: boolean;
  active_position_present?: boolean;
  local_active_position_count?: number;
  exchange_active_position_count?: number;
  local_open_order_count?: number;
  exchange_open_stop_order_count?: number;
  sl_protection_present?: boolean;
  tp_protection_present?: boolean;
  hard_stop_boundary_present?: boolean;
  current_qty?: string | number | null;
  entry_price?: string | number | null;
  mark_price?: string | number | null;
  unrealized_pnl?: string | number | null;
  liquidation_price?: string | number | null;
  attempts_used?: number;
  attempts_remaining?: number;
  max_attempts?: number;
  budget_reserved?: string | number | null;
  budget_remaining?: string | number | null;
  max_active_positions?: number;
  reconciliation_severe_count?: number;
  reconciliation_warning_count?: number;
  reconciliation_mismatch_types?: string[];
  blocks_new_entries_until_resolved?: boolean;
  can_continue_holding?: boolean;
  review_required_before_next_attempt?: boolean;
  owner_action_required?: boolean;
  blockers?: string[];
  warnings?: string[];
  not_execution_authority?: boolean;
  order_created?: boolean;
  exchange_order_submitted?: boolean;
  order_lifecycle_called?: boolean;
  withdrawal_instruction_created?: boolean;
  transfer_instruction_created?: boolean;
  created_at_ms?: number;
};

type SignalEvaluationView = {
  signal_evaluation_id: string;
  runtime_instance_id?: string | null;
  strategy_family_id?: string | null;
  strategy_family_version_id?: string | null;
  symbol?: string;
  side?: string;
  status?: string;
  decision?: string;
  rationale?: string;
  shadow_mode?: boolean;
  execution_enabled?: boolean;
  not_order?: boolean;
  not_execution_intent?: boolean;
  evaluated_at_ms?: number;
};

type OrderCandidateView = {
  order_candidate_id: string;
  signal_evaluation_id?: string;
  runtime_instance_id?: string | null;
  strategy_family_id?: string | null;
  strategy_family_version_id?: string | null;
  symbol?: string;
  side?: string;
  status?: string;
  candidate_order_type?: string;
  intended_notional?: string | null;
  proposed_quantity?: string | null;
  rationale?: string;
  shadow_mode?: boolean;
  execution_enabled?: boolean;
  candidate_executable?: boolean;
  not_order?: boolean;
  not_execution_intent?: boolean;
};

type PromotionGateView = {
  status?: string;
  scope?: string;
  blockers?: string[];
  warnings?: string[];
  missing_owner_decisions?: string[];
  binding_candidate_mode?: string;
  implementation_kind?: string;
  proven_alpha?: boolean;
  not_execution_authority?: boolean;
  execution_intent_created?: boolean;
  order_created?: boolean;
  exchange_called?: boolean;
};

type PromotionConfirmationView = {
  confirmation_id: string;
  runtime_instance_id?: string | null;
  strategy_family_id?: string;
  strategy_family_version_id?: string;
  scope?: string;
  recorded_by?: string;
  reason?: string;
  created_at_ms?: number;
  promotion_gate_result_snapshot?: PromotionGateView | null;
  not_execution_authority?: boolean;
  execution_intent_created?: boolean;
  order_created?: boolean;
  exchange_called?: boolean;
  owner_bounded_execution_called?: boolean;
  order_lifecycle_called?: boolean;
  runtime_mutation_created?: boolean;
  withdrawal_instruction_created?: boolean;
  transfer_instruction_created?: boolean;
};

type RuntimeSafetyTone = 'normal' | 'warning' | 'danger' | 'muted';

export default function AuthorizationState() {
  const authState = useReadModel<any>('/api/trading-console/authorization-state');
  const runtimeState = useReadModel<any>('/api/trading-console/strategy-runtimes?limit=10');
  const signalState = useReadModel<any>('/api/trading-console/signal-evaluations?limit=5');
  const candidateState = useReadModel<any>('/api/trading-console/order-candidates?limit=5');
  const rightTailState = useReadModel<any>('/api/trading-console/right-tail-review');

  const authData = authState.envelope?.data || {};
  const runtimes = readList<RuntimeView>(runtimeState.envelope);
  const signals = readList<SignalEvaluationView>(signalState.envelope);
  const candidates = readList<OrderCandidateView>(candidateState.envelope);
  const selectedRuntime = runtimes[0] || null;
  const rightTail = rightTailState.envelope?.data || {};
  const pageErrors = [
    authState.error,
    runtimeState.error,
    signalState.error,
    candidateState.error,
    rightTailState.error,
  ].filter(Boolean) as string[];
  const loading = authState.loading && runtimeState.loading;
  const runtimeTone = selectedRuntime ? runtimeStatusTone(selectedRuntime.status) : 'attention';
  const pageTone: ConsoleTone = pageErrors.length > 0 ? 'intervention' : runtimeTone;
  const runtimeBoundary = selectedRuntime?.boundary || {};
  const attemptsRemaining = selectedRuntime
    ? displayValue(runtimeBoundary.attempts_remaining, '暂无')
    : '0';
  const maxAttempts = selectedRuntime
    ? displayValue(runtimeBoundary.max_attempts, '暂无')
    : '暂无';
  const budgetRemaining = selectedRuntime
    ? formatMoney(runtimeBoundary.budget_remaining)
    : '暂无数据';

  if (loading) {
    return (
      <div className="flex min-h-[480px] items-center justify-center rounded-md border border-slate-800 bg-slate-900/50 text-sm text-slate-400">
        正在读取运行治理状态...
      </div>
    );
  }

  const inspectorItems = [
    {
      title: selectedRuntime ? 'Runtime 边界已进入治理面' : '运行实例尚未启动',
      body: selectedRuntime
        ? '当前页面只展示 Runtime 边界、候选与 readiness 事实；执行仍必须通过后续 Owner/Codex gate 和官方路径。'
        : '当前没有策略运行实例。单次授权可以保留查看，但不能被解释为 Runtime 执行授权。',
      tone: selectedRuntime ? runtimeTone : 'attention' as ConsoleTone,
    },
    {
      title: authData.authorization_id ? '单次授权保留为历史短路径' : '暂无单次授权',
      body: authData.authorization_id
        ? '该授权状态用于解释旧路径是否可继续，不会自动转换为 Runtime 尝试、ExecutionIntent 或订单。'
        : '当前 readmodel 没有返回可展示的 OwnerBoundedExecution 授权。',
      tone: authData.authorization_id ? 'attention' as ConsoleTone : 'unavailable' as ConsoleTone,
    },
    {
      title: candidates.length > 0 ? '候选需要继续过 gate' : '候选尚未出现',
      body: candidates.length > 0
        ? 'OrderCandidate 是策略信号后的候选对象，不是订单，也不是执行意图。'
        : '当前没有 OrderCandidate。策略语义和信号链路可以 shadow，但不能从空数据推断可行动。',
      tone: candidates.length > 0 ? 'attention' as ConsoleTone : 'unavailable' as ConsoleTone,
    },
    {
      title: '右尾复盘保持独立',
      body: rightTail.trade_count
        ? '分析页会展示右尾、MFE、MAE、R multiple 等指标；这些指标不创建提现、预算或订单指令。'
        : '当前没有显式 right-tail trade-path 事实；系统不会用账户权益或提现记录猜测策略表现。',
      tone: rightTail.trade_count ? 'normal' as ConsoleTone : 'unavailable' as ConsoleTone,
      action: <RuntimeSoftButton to="/analysis">查看分析</RuntimeSoftButton>,
    },
  ];

  return (
    <div className="mx-auto max-w-[1500px] space-y-4">
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusChip tone={pageTone}>{runtimePageStatusLabel(selectedRuntime, pageErrors)}</StatusChip>
            {authState.envelope?.freshness_status && (
              <StatusChip tone={authState.envelope.freshness_status === 'fresh' ? 'normal' : 'attention'}>
                {authState.envelope.freshness_status === 'fresh' ? '已同步' : '部分同步'}
              </StatusChip>
            )}
          </div>
          <h1 className="mt-4 text-3xl font-semibold text-slate-100">运行治理</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
            先确认 Runtime 边界、尝试预算、保护和策略候选，再讨论任何受控执行。当前页面只读，不提供买卖或提交订单入口。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <RuntimeSoftButton to="/strategy">
            <Layers3 className="h-4 w-4" />
            策略库
          </RuntimeSoftButton>
          <RuntimeSoftButton to="/evidence">
            <FileSearch className="h-4 w-4" />
            证据
          </RuntimeSoftButton>
        </div>
      </header>

      {pageErrors.length > 0 && (
        <ActionNudge
          tone="intervention"
          text={`运行治理读模型暂不可用：${pageErrors[0]}`}
          action={<RuntimeSoftButton to="/incident">进入异常介入</RuntimeSoftButton>}
        />
      )}

      {!selectedRuntime && (
        <ActionNudge
          tone="attention"
          text="当前没有策略运行实例。单次授权仍可查看，但不会被提升为 Runtime 执行权限。"
          action={<RuntimeSoftButton to="/strategy">查看策略资产</RuntimeSoftButton>}
        />
      )}

      <ConsolePanel>
        <div className="grid grid-cols-1 md:grid-cols-4">
          <MetricRailItem label="运行实例" value={runtimes.length} tone={runtimeTone} sub={selectedRuntime ? displayValue(selectedRuntime.status, '状态待确认') : '暂无实例'} />
          <MetricRailItem label="尝试" value={`${attemptsRemaining}/${maxAttempts}`} tone={selectedRuntime ? 'attention' : 'unavailable'} sub="剩余 / 上限" />
          <MetricRailItem label="预算" value={budgetRemaining} tone={selectedRuntime ? 'attention' : 'unavailable'} sub="剩余试错资本" />
          <MetricRailItem label="候选" value={candidates.length} tone={candidates.length > 0 ? 'attention' : 'unavailable'} sub={`${signals.length} 个信号评估`} />
        </div>
      </ConsolePanel>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-4">
          <RuntimeShelfPanel runtimes={runtimes} />
          <RuntimeBoundaryPanel runtime={selectedRuntime} />
          <RuntimeActivityPanel signals={signals} candidates={candidates} />
          <AuthorizationBridgePanel envelope={authState.envelope} data={authData} error={authState.error} />
          <RuntimeSafetyReadinessPanel runtimes={runtimes} />
          <RuntimeLivePositionMonitorPanel runtime={selectedRuntime} />
          <RuntimePromotionGatePanel runtimes={runtimes} />
          <RuntimePromotionConfirmationLedger runtime={selectedRuntime} />
        </div>

        <InspectorPanel
          items={inspectorItems}
          footer={
            <div className="text-xs leading-5 text-slate-500">
              说明：运行治理页不创建 ExecutionIntent、不登记订单、不调用 OrderLifecycle、不触碰交易所。Runtime 缺失时保持 BLOCK/观察语义。
            </div>
          }
        />
      </div>
    </div>
  );
}

function readList<T>(value: unknown): T[] {
  if (Array.isArray(value)) return value as T[];
  if (value && typeof value === 'object') return asArray<T>((value as any).data);
  return [];
}

function RuntimeShelfPanel({ runtimes }: { runtimes: RuntimeView[] }) {
  return (
    <ConsolePanel title="运行实例" caption="策略运行实例是受边界约束的策略实例，不是订单权限">
      <div className="divide-y divide-slate-800/90">
        {runtimes.length === 0 ? (
          <EntityRow
            title="暂无策略运行实例"
            subtitle="先完成策略语义、试错预算和 Owner/Codex 边界确认"
            tone="attention"
            cells={[
              { label: '状态', value: '未启动' },
              { label: '执行', value: '未授予' },
              { label: '策略信号', value: '等待 shadow' },
              { label: '下一步', value: '策略库 / 证据' },
            ]}
            action={<RuntimeSoftButton to="/strategy">查看策略库</RuntimeSoftButton>}
          />
        ) : (
          runtimes.map((runtime) => (
            <div key={runtime.runtime_instance_id}>
              <EntityRow
                title={displayValue(runtime.carrier_id || runtime.strategy_family_id, 'Runtime')}
                subtitle={displayValue(runtime.runtime_instance_id, '暂无 runtime id')}
                tone={runtimeStatusTone(runtime.status)}
                active
                cells={[
                  { label: '市场', value: displayValue(runtime.symbol, '暂无') },
                  { label: '方向', value: sideLabel(runtime.side) },
                  { label: '模式', value: displayValue(runtime.execution_mode, '暂无') },
                  { label: '执行', value: runtime.execution_enabled ? '已授权' : '未授予' },
                ]}
                action={<StatusChip tone={runtime.execution_enabled ? 'attention' : 'unavailable'}>{runtime.execution_enabled ? '需 gate' : '只读'}</StatusChip>}
              />
            </div>
          ))
        )}
      </div>
    </ConsolePanel>
  );
}

function RuntimeBoundaryPanel({ runtime }: { runtime: RuntimeView | null }) {
  const boundary = runtime?.boundary || {};
  return (
    <ConsolePanel title="运行边界" caption="亏损可以在预算内发生，失控不能发生">
      <div className="grid grid-cols-1 gap-px bg-slate-800/80 md:grid-cols-3 xl:grid-cols-4">
        <BoundaryCell label="尝试次数" value={runtime ? `${displayValue(boundary.attempts_used, '0')} / ${displayValue(boundary.max_attempts, '暂无')}` : '暂无'} />
        <BoundaryCell label="试错预算" value={runtime ? formatMoney(boundary.budget_remaining) : '暂无'} />
        <BoundaryCell label="单次名义金额" value={runtime ? formatMoney(boundary.max_notional_per_attempt) : '暂无'} />
        <BoundaryCell label="最大活跃仓位" value={runtime ? displayValue(boundary.max_active_positions, '暂无') : '暂无'} />
        <BoundaryCell label="最大杠杆" value={runtime ? displayValue(boundary.max_leverage, '暂无') : '暂无'} />
        <BoundaryCell label="保护要求" value={runtime ? (boundary.requires_protection ? '必须有硬保护' : '未要求') : '暂无'} />
        <BoundaryCell label="复盘要求" value={runtime ? (boundary.requires_review ? '必须复盘' : '未要求') : '暂无'} />
        <BoundaryCell label="有效期" value={runtime ? formatTimestampMs(runtime.expires_at_ms) : '暂无'} />
      </div>
      <div className="border-t border-slate-800 px-4 py-3 text-xs leading-5 text-slate-500">
        杠杆、名义金额和尝试次数只表达边界。页面不会把“可亏损”误读成“可无限尝试”。
      </div>
    </ConsolePanel>
  );
}

function RuntimeActivityPanel({
  signals,
  candidates,
}: {
  signals: SignalEvaluationView[];
  candidates: OrderCandidateView[];
}) {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <ConsolePanel title="信号评估" caption="策略信号评估，仍不是订单">
        <PipelineList
          emptyTitle="暂无信号评估记录"
          emptySubtitle="价格行为或其他策略事实进入主流程后会出现在这里"
          rows={signals.map((signal) => ({
            id: signal.signal_evaluation_id,
            title: displayValue(signal.strategy_family_id, '策略族待确认'),
            subtitle: displayValue(signal.rationale, '暂无 rationale'),
            tone: signal.execution_enabled ? 'attention' : 'unavailable',
            cells: [
              { label: '市场', value: displayValue(signal.symbol, '暂无') },
              { label: '方向', value: sideLabel(signal.side) },
              { label: '决策', value: displayValue(signal.decision, '暂无') },
              { label: '评估', value: displayValue(signal.status, '暂无') },
            ],
          }))}
        />
      </ConsolePanel>

      <ConsolePanel title="订单候选" caption="候选可进入 preview，但不是 ExecutionIntent">
        <PipelineList
          emptyTitle="暂无订单候选"
          emptySubtitle="没有候选时不能从授权状态推断可执行"
          rows={candidates.map((candidate) => ({
            id: candidate.order_candidate_id,
            title: displayValue(candidate.strategy_family_id, '策略族待确认'),
            subtitle: displayValue(candidate.rationale, '暂无 rationale'),
            tone: candidate.candidate_executable ? 'attention' : 'unavailable',
            cells: [
              { label: '市场', value: displayValue(candidate.symbol, '暂无') },
              { label: '方向', value: sideLabel(candidate.side) },
              { label: '名义', value: formatMoney(candidate.intended_notional) },
              { label: '状态', value: displayValue(candidate.status, '暂无') },
            ],
          }))}
        />
      </ConsolePanel>
    </div>
  );
}

function AuthorizationBridgePanel({
  envelope,
  data,
  error,
}: {
  envelope: any;
  data: any;
  error: string | null;
}) {
  const futureActionSlots = actionSlotEntries(data.future_action_slots);
  const statusTone = data.is_actionable === true ? 'attention' : 'blocked';
  return (
    <ConsolePanel title="单次授权短路径" caption="历史 OwnerBoundedExecution 状态，保留但不伪装成 Runtime">
      <div className="grid grid-cols-1 gap-px bg-slate-800/80 md:grid-cols-4">
        <BoundaryCell label="授权对象" value={displayValue(data.carrier_id, '暂无')} />
        <BoundaryCell label="授权状态" value={authorizationStatusLabel(data.status)} />
        <BoundaryCell label="范围核验" value={scopeMatchLabel(data.scope_match)} />
        <BoundaryCell label="是否可行动" value={data.is_actionable === true ? '是' : '否'} tone={statusTone} />
      </div>

      {(error || data.blocking_reason || asArray(envelope?.unavailable).length > 0) && (
        <div className="border-t border-slate-800 bg-slate-950/45 p-4 text-sm">
          {error && <GuidanceLine tone="intervention" title="读模型暂不可用" body={error} />}
          {data.blocking_reason && (
            <GuidanceLine
              tone="blocked"
              title="不能继续的原因"
              body={blockingReasonLabel(data.blocking_reason)}
            />
          )}
          {asArray(envelope?.unavailable).length > 0 && (
            <GuidanceLine
              tone="attention"
              title="缺失事实"
              body="部分账户、审计、信号或运行控制事实不可用。控制台不会据此放行执行。"
            />
          )}
        </div>
      )}

      <div className="border-t border-slate-800 px-4 py-4">
        <div className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <ScopeFact label="标的" value={displayValue(data.scope?.symbol, '未知')} />
          <ScopeFact label="方向" value={sideLabel(data.scope?.side)} />
          <ScopeFact label="最大名义金额" value={displayValue(data.scope?.max_notional, '未知')} />
          <ScopeFact label="数量" value={displayValue(data.scope?.quantity, '未知')} />
        </div>
      </div>

      <TechnicalDetails title="后续可开放的授权动作">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {futureActionSlots.map((slot) => (
            <DeferredActionSlot
              key={slot.name}
              actionName={slot.name === 'void_authorization' ? '作废授权' : slot.name === 'cancel_authorization' ? '变更授权' : slot.name}
              reason="当前不可操作"
            />
          ))}
          {futureActionSlots.length === 0 && (
            <div className="col-span-2 text-sm text-slate-500">当前无开放动作槽位</div>
          )}
        </div>
      </TechnicalDetails>
    </ConsolePanel>
  );
}

function RuntimeSafetyReadinessPanel({ runtimes }: { runtimes: RuntimeView[] }) {
  const runtime = runtimes[0];

  if (!runtime?.runtime_instance_id) {
    return (
      <ConsolePanel title="Runtime 安全边界" caption="执行前必须确认的边界事实">
        <div className="grid grid-cols-1 gap-px bg-slate-800/80 md:grid-cols-3">
          <BoundaryCell label="运行实例" value="暂无实例" tone="blocked" />
          <BoundaryCell label="授权类型" value="单次授权" tone="attention" />
          <BoundaryCell label="执行权限" value="未授予" tone="unavailable" />
        </div>
      </ConsolePanel>
    );
  }

  return <RuntimeSafetyReadinessDetail runtimeId={String(runtime.runtime_instance_id)} />;
}

function RuntimeLivePositionMonitorPanel({ runtime }: { runtime: RuntimeView | null }) {
  const runtimeId = runtime?.runtime_instance_id ? String(runtime.runtime_instance_id) : null;

  if (!runtimeId) {
    return (
      <ConsolePanel title="实盘持仓监控" caption="本地 / 交易所持仓与保护事实">
        <div className="grid grid-cols-1 gap-px bg-slate-800/80 md:grid-cols-4">
          <BoundaryCell label="运行实例" value="暂无实例" tone="blocked" />
          <BoundaryCell label="持仓" value="未读取" tone="unavailable" />
          <BoundaryCell label="保护" value="未确认" tone="unavailable" />
          <BoundaryCell label="新尝试" value="不可评估" tone="blocked" />
        </div>
      </ConsolePanel>
    );
  }

  return <RuntimeLivePositionMonitorDetail runtimeId={runtimeId} />;
}

function RuntimePromotionGatePanel({ runtimes }: { runtimes: RuntimeView[] }) {
  const runtime = runtimes[0];

  if (!runtime?.runtime_instance_id) {
    return (
      <ConsolePanel title="首次实盘门禁" caption="进入真实 submit 前必须显式补齐的 Owner / Codex 决策">
        <div className="grid grid-cols-1 gap-px bg-slate-800/80 md:grid-cols-3">
          <BoundaryCell label="运行实例" value="暂无实例" tone="blocked" />
          <BoundaryCell label="门禁状态" value="等待 Runtime" tone="attention" />
          <BoundaryCell label="执行权限" value="未授予" tone="unavailable" />
        </div>
        <div className="border-t border-slate-800 px-4 py-3 text-xs leading-5 text-slate-500">
          没有 Runtime 时不会请求 promotion gate，也不会从单次授权推断真实 submit 准备度。
        </div>
      </ConsolePanel>
    );
  }

  return <RuntimePromotionGateDetail runtimeId={String(runtime.runtime_instance_id)} />;
}

function RuntimePromotionGateDetail({ runtimeId }: { runtimeId: string }) {
  const path = `/api/trading-console/strategy-runtimes/${encodeURIComponent(runtimeId)}/promotion-gate?scope=first_real_submit_gate_review`;
  const { gate, loading, error } = usePromotionGatePreview(path);
  const blockers = asArray<string>(gate.blockers);
  const warnings = asArray<string>(gate.warnings);
  const decisions = asArray<string>(gate.missing_owner_decisions);
  const blocked = Boolean(error || blockers.length > 0 || gate.not_execution_authority !== true);

  return (
    <ConsolePanel
      title="首次实盘门禁"
      caption="真实 submit 前的只读 promotion gate；显示缺口，不授权交易"
      action={<StatusChip tone={blocked ? 'blocked' : 'attention'}>{loading ? '读取中' : promotionGateStatusLabel(error ? 'unavailable' : gate.status)}</StatusChip>}
    >
      {loading ? (
        <div className="px-4 py-6 text-sm text-slate-500">正在读取首次实盘门禁...</div>
      ) : error ? (
        <div className="px-4 py-4">
          <GuidanceLine tone="intervention" title="promotion gate 暂不可用" body={error} />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-px bg-slate-800/80 md:grid-cols-4">
            <BoundaryCell label="门禁状态" value={promotionGateStatusLabel(gate.status)} tone={blockers.length > 0 ? 'blocked' : 'attention'} />
            <BoundaryCell label="阻断" value={String(blockers.length)} tone={blockers.length > 0 ? 'blocked' : 'normal'} />
            <BoundaryCell label="待决策" value={String(decisions.length)} tone={decisions.length > 0 ? 'attention' : 'normal'} />
            <BoundaryCell label="执行权限" value={gate.not_execution_authority ? '未授予' : '异常'} tone={gate.not_execution_authority ? 'unavailable' : 'blocked'} />
          </div>

          <div className="grid grid-cols-1 gap-4 border-t border-slate-800 p-4 lg:grid-cols-2">
            <RuntimeSafetyList
              title="当前阻断"
              empty="已具备进入门禁审查的前置事实"
              items={blockers}
              tone="danger"
              mapLabel={promotionGateBlockerLabel}
            />
            <RuntimeSafetyList
              title="Owner / Codex 待确认"
              empty="暂无待确认项"
              items={decisions}
              tone="warning"
              mapLabel={promotionGateDecisionLabel}
            />
          </div>

          <div className="border-t border-slate-800 px-4 py-3 text-xs leading-5 text-slate-500">
            这个面板只回答“离首次真实 submit 门禁还缺什么”。即使状态变为可审查，也仍然不是下单、撤单、平仓、提现或自动复利权限。
          </div>

          <TechnicalDetails title="First real submit gate facts">
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              <ScopeFact label="Scope" value={displayValue(gate.scope, 'first_real_submit_gate_review')} />
              <ScopeFact label="Strategy mode" value={displayValue(gate.binding_candidate_mode, '暂无')} />
              <ScopeFact label="Implementation" value={displayValue(gate.implementation_kind, '暂无')} />
              <ScopeFact label="Proven alpha" value={gate.proven_alpha === true ? '已证明' : '未证明 / 限制预算与自动化'} />
              <ScopeFact label="ExecutionIntent" value={gate.execution_intent_created ? '已创建' : '未创建'} />
              <ScopeFact label="Order" value={gate.order_created ? '已创建' : '未创建'} />
              <ScopeFact label="Exchange" value={gate.exchange_called ? '已调用' : '未调用'} />
              <ScopeFact label="Authority" value={gate.not_execution_authority ? '非执行授权' : '需核查'} />
            </div>
            {warnings.length > 0 && (
              <div className="mt-3 text-amber-700 dark:text-amber-300">
                {warnings.map(promotionGateBlockerLabel).join(' / ')}
              </div>
            )}
          </TechnicalDetails>
        </>
      )}
    </ConsolePanel>
  );
}

function RuntimePromotionConfirmationLedger({ runtime }: { runtime: RuntimeView | null }) {
  const runtimeId = runtime?.runtime_instance_id ? String(runtime.runtime_instance_id) : null;
  const { records, loading, error } = usePromotionConfirmationLedger(runtimeId);

  if (!runtimeId) {
    return (
      <ConsolePanel title="门禁确认账本" caption="Owner / Codex promotion-gate 确认事实">
        <div className="grid grid-cols-1 gap-px bg-slate-800/80 md:grid-cols-3">
          <BoundaryCell label="运行实例" value="暂无实例" tone="blocked" />
          <BoundaryCell label="账本记录" value="等待 Runtime" tone="attention" />
          <BoundaryCell label="执行权限" value="未授予" tone="unavailable" />
        </div>
      </ConsolePanel>
    );
  }

  const latest = records[0];
  const unsafe = records.some((record) => promotionConfirmationUnsafe(record));

  return (
    <ConsolePanel
      title="门禁确认账本"
      caption="持久化的 promotion-gate 确认事实；不是 submit 授权"
      action={<StatusChip tone={error || unsafe ? 'blocked' : records.length > 0 ? 'attention' : 'unavailable'}>{loading ? '读取中' : records.length > 0 ? `${records.length} 条` : '暂无记录'}</StatusChip>}
    >
      {loading ? (
        <div className="px-4 py-6 text-sm text-slate-500">正在读取门禁确认账本...</div>
      ) : error ? (
        <div className="px-4 py-4">
          <GuidanceLine tone="intervention" title="confirmation ledger 暂不可用" body={error} />
        </div>
      ) : records.length === 0 ? (
        <div className="grid grid-cols-1 gap-px bg-slate-800/80 md:grid-cols-3">
          <BoundaryCell label="运行实例" value={runtimeId} tone="attention" />
          <BoundaryCell label="账本记录" value="暂无记录" tone="unavailable" />
          <BoundaryCell label="执行权限" value="未授予" tone="unavailable" />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-px bg-slate-800/80 md:grid-cols-4">
            <BoundaryCell label="最新记录" value={displayValue(latest.confirmation_id, '暂无')} tone="attention" />
            <BoundaryCell label="门禁快照" value={promotionGateStatusLabel(latest.promotion_gate_result_snapshot?.status)} tone={latest.promotion_gate_result_snapshot?.status === 'blocked' ? 'blocked' : 'attention'} />
            <BoundaryCell label="记录人" value={displayValue(latest.recorded_by, '暂无')} tone="unavailable" />
            <BoundaryCell label="执行权限" value={latest.not_execution_authority ? '未授予' : '异常'} tone={latest.not_execution_authority ? 'unavailable' : 'blocked'} />
          </div>

          <div className="divide-y divide-slate-800/90 border-t border-slate-800">
            {records.slice(0, 4).map((record) => (
              <div key={record.confirmation_id}>
                <EntityRow
                  title={record.confirmation_id}
                  subtitle={displayValue(record.reason, '暂无原因')}
                  tone={promotionConfirmationUnsafe(record) ? 'blocked' : 'attention'}
                  cells={[
                    { label: 'Scope', value: displayValue(record.scope, '暂无') },
                    { label: 'Gate', value: promotionGateStatusLabel(record.promotion_gate_result_snapshot?.status) },
                    { label: '记录时间', value: formatTimestampMs(record.created_at_ms) },
                    { label: 'No action', value: promotionConfirmationUnsafe(record) ? '需核查' : '保持' },
                  ]}
                  action={<StatusChip tone={promotionConfirmationUnsafe(record) ? 'blocked' : 'unavailable'}>{record.order_created || record.exchange_called ? '异常' : '非执行'}</StatusChip>}
                />
              </div>
            ))}
          </div>
        </>
      )}
    </ConsolePanel>
  );
}

function usePromotionGatePreview(path: string): {
  gate: PromotionGateView;
  loading: boolean;
  error: string | null;
} {
  const [gate, setGate] = useState<PromotionGateView>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(path, {
          method: 'GET',
          credentials: 'include',
        });
        if (response.status === 401) {
          window.dispatchEvent(new Event('trading-console:unauthorized'));
        }
        if (!response.ok) throw new Error(`GET ${path} returned HTTP ${response.status}`);
        const payload = await response.json();
        if (active) setGate(payload || {});
      } catch (err) {
        console.error('Trading Console promotion gate API error', { path, error: err });
        if (active) {
          setGate({});
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    if (!path.startsWith('/api/trading-console/')) {
      setGate({});
      setError(`Forbidden Trading Console API path: ${path}`);
      setLoading(false);
      return;
    }

    load();
    return () => {
      active = false;
    };
  }, [path]);

  return { gate, loading, error };
}

function usePromotionConfirmationLedger(runtimeId: string | null): {
  records: PromotionConfirmationView[];
  loading: boolean;
  error: string | null;
} {
  const [records, setRecords] = useState<PromotionConfirmationView[]>([]);
  const [loading, setLoading] = useState(Boolean(runtimeId));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function load() {
      if (!runtimeId) {
        setRecords([]);
        setLoading(false);
        setError(null);
        return;
      }
      const path = `/api/brc/strategy-runtime-promotion-confirmations?runtime_instance_id=${encodeURIComponent(runtimeId)}&limit=5`;
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(path, {
          method: 'GET',
          credentials: 'include',
        });
        if (response.status === 401) {
          window.dispatchEvent(new Event('trading-console:unauthorized'));
        }
        if (!response.ok) throw new Error(`GET ${path} returned HTTP ${response.status}`);
        const payload = await response.json();
        if (active) setRecords(asArray<PromotionConfirmationView>(payload?.confirmations));
      } catch (err) {
        console.error('Trading Console promotion confirmation API error', { runtimeId, error: err });
        if (active) {
          setRecords([]);
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    load();
    return () => {
      active = false;
    };
  }, [runtimeId]);

  return { records, loading, error };
}

function RuntimeLivePositionMonitorDetail({ runtimeId }: { runtimeId: string }) {
  const { envelope, loading, error } = useReadModel<RuntimeLivePositionMonitorView>(
    `/api/trading-console/strategy-runtimes/${encodeURIComponent(runtimeId)}/live-position-monitor`,
  );
  const packet = (envelope || {}) as RuntimeLivePositionMonitorView;
  const blockers = asArray<string>(packet.blockers);
  const warnings = asArray<string>(packet.warnings);
  const mismatches = asArray<string>(packet.reconciliation_mismatch_types);
  const tone = liveMonitorTone(error ? 'blocked' : packet.status);
  const Icon = tone === 'normal' ? ShieldCheck : tone === 'attention' ? ShieldAlert : XCircle;
  const activeCount = `${displayValue(packet.local_active_position_count, '0')} / ${displayValue(packet.exchange_active_position_count, '0')}`;
  const protectionText = liveProtectionStatusLabel(packet.protection_status);
  const nextAttemptText = packet.blocks_new_entries_until_resolved ? '暂停' : '可评估';
  const holdingText = packet.can_continue_holding ? '可继续持有' : packet.active_position_present ? '需介入' : '无持仓';

  return (
    <ConsolePanel
      title="实盘持仓监控"
      caption="本地 / 交易所持仓与保护事实"
      action={(
        <StatusChip tone={tone}>
          <span className="inline-flex items-center gap-1">
            <Icon className="h-3.5 w-3.5" />
            {loading ? '读取中' : liveMonitorStatusLabel(error ? 'blocked' : packet.status)}
          </span>
        </StatusChip>
      )}
    >
      {loading ? (
        <div className="px-4 py-6 text-sm text-slate-500">正在读取实盘持仓监控...</div>
      ) : error ? (
        <div className="px-4 py-4">
          <GuidanceLine tone="intervention" title="live monitor 暂不可用" body={error} />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-px bg-slate-800/80 md:grid-cols-4">
            <BoundaryCell label="持仓 本地/交易所" value={activeCount} tone={packet.active_position_present ? 'attention' : 'unavailable'} />
            <BoundaryCell label="保护" value={protectionText} tone={packet.hard_stop_boundary_present ? (packet.tp_protection_present ? 'normal' : 'attention') : 'blocked'} />
            <BoundaryCell label="未实现PnL" value={formatMoney(packet.unrealized_pnl)} tone={Number(packet.unrealized_pnl || 0) < 0 ? 'attention' : 'normal'} />
            <BoundaryCell label="持仓动作" value={holdingText} tone={packet.can_continue_holding ? 'normal' : packet.active_position_present ? 'blocked' : 'unavailable'} />
          </div>

          <div className="grid grid-cols-1 gap-px border-t border-slate-800 bg-slate-800/80 md:grid-cols-4">
            <BoundaryCell label="尝试" value={`${displayValue(packet.attempts_remaining, '0')}/${displayValue(packet.max_attempts, '0')}`} tone="attention" />
            <BoundaryCell label="预算剩余" value={formatMoney(packet.budget_remaining)} tone="attention" />
            <BoundaryCell label="新尝试" value={nextAttemptText} tone={packet.blocks_new_entries_until_resolved ? 'blocked' : 'normal'} />
            <BoundaryCell label="交易所写入" value={packet.exchange_order_submitted ? '异常' : '无'} tone={packet.exchange_order_submitted ? 'blocked' : 'unavailable'} />
          </div>

          {(blockers.length > 0 || warnings.length > 0) && (
            <div className="grid grid-cols-1 gap-4 border-t border-slate-800 p-4 lg:grid-cols-2">
              <RuntimeSafetyList
                title="阻止下一次尝试"
                empty="当前没有下一次尝试阻断"
                items={blockers}
                tone="danger"
                mapLabel={liveMonitorReasonLabel}
              />
              <RuntimeSafetyList
                title="持仓 / 出场提醒"
                empty="暂无持仓提醒"
                items={warnings}
                tone="warning"
                mapLabel={liveMonitorReasonLabel}
              />
            </div>
          )}

          <div className="border-t border-slate-800 px-4 py-3 text-xs leading-5 text-slate-500">
            当前面板只读取 facts。SL 存在时，小额浮亏和缺少 TP 属于可复盘的持仓 / 出场状态；新尝试会在 active-position slot 释放前暂停。
          </div>

          <TechnicalDetails title="Live monitor facts">
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              <ScopeFact label="Runtime" value={displayValue(packet.runtime_instance_id, runtimeId)} />
              <ScopeFact label="Symbol / side" value={`${displayValue(packet.symbol, '暂无')} / ${sideLabel(packet.side)}`} />
              <ScopeFact label="Entry / mark" value={`${formatMoney(packet.entry_price)} / ${formatMoney(packet.mark_price)}`} />
              <ScopeFact label="Qty / liq" value={`${formatMoney(packet.current_qty)} / ${formatMoney(packet.liquidation_price)}`} />
              <ScopeFact label="Local open orders" value={displayValue(packet.local_open_order_count, '0')} />
              <ScopeFact label="Exchange stop orders" value={displayValue(packet.exchange_open_stop_order_count, '0')} />
              <ScopeFact label="Reconciliation" value={`${displayValue(packet.reconciliation_severe_count, '0')} severe / ${displayValue(packet.reconciliation_warning_count, '0')} warning`} />
              <ScopeFact label="Created" value={formatTimestampMs(packet.created_at_ms)} />
              <ScopeFact label="No OrderLifecycle" value={packet.order_lifecycle_called ? '异常' : '保持'} />
              <ScopeFact label="No withdrawal" value={packet.withdrawal_instruction_created || packet.transfer_instruction_created ? '异常' : '保持'} />
            </div>
            {mismatches.length > 0 && (
              <div className="mt-3 text-amber-700 dark:text-amber-300">
                {mismatches.map(liveMonitorReasonLabel).join(' / ')}
              </div>
            )}
          </TechnicalDetails>
        </>
      )}
    </ConsolePanel>
  );
}

function RuntimeSafetyReadinessDetail({ runtimeId }: { runtimeId: string }) {
  const { envelope, loading, error } = useReadModel<any>(`/api/trading-console/strategy-runtimes/${encodeURIComponent(runtimeId)}/safety-readiness`);
  const readiness: any = envelope || {};
  const blockers = asArray<string>(readiness.blockers);
  const warnings = asArray<string>(readiness.warnings);
  const confirmations = asArray<string>(readiness.required_owner_confirmations);
  const requirements = asArray<any>(readiness.requirements);

  return (
    <ConsolePanel
      title="Runtime 安全边界"
      caption="执行前必须确认的边界事实"
      action={<StatusChip tone={error || blockers.length > 0 ? 'blocked' : 'attention'}>{loading ? '读取中' : runtimeSafetyStatusLabel(error ? 'unavailable' : readiness.status)}</StatusChip>}
    >
      {loading ? (
        <div className="px-4 py-6 text-sm text-slate-500">正在读取 runtime 安全边界...</div>
      ) : error ? (
        <div className="px-4 py-4">
          <GuidanceLine tone="intervention" title="readiness 暂不可用" body={error} />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-px bg-slate-800/80 md:grid-cols-4">
            <BoundaryCell label="运行实例" value={displayValue(readiness.runtime_instance_id, '暂无')} />
            <BoundaryCell label="状态" value={runtimeSafetyStatusLabel(readiness.status)} tone={blockers.length > 0 ? 'blocked' : 'attention'} />
            <BoundaryCell label="阻断" value={String(blockers.length)} tone={blockers.length > 0 ? 'blocked' : 'normal'} />
            <BoundaryCell label="需确认" value={String(confirmations.length)} tone={confirmations.length > 0 ? 'attention' : 'normal'} />
          </div>

          <div className="grid grid-cols-1 gap-4 border-t border-slate-800 p-4 lg:grid-cols-2">
            <RuntimeSafetyList title="阻断项" empty="当前边界事实完整" items={blockers} tone="danger" />
            <RuntimeSafetyList
              title="Owner / Codex 确认"
              empty="暂无待确认项"
              items={confirmations}
              tone="warning"
              mapLabel={runtimeSafetyConfirmationLabel}
            />
          </div>

          <TechnicalDetails title="Runtime safety facts">
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              {requirements.slice(0, 12).map((requirement) => (
                <div key={requirement.code} className="rounded border border-slate-200 bg-white p-2 dark:border-slate-800 dark:bg-slate-950">
                  <div className="flex items-center justify-between gap-2">
                    <span>{runtimeSafetyRequirementLabel(requirement.code)}</span>
                    <Badge variant={requirement.status === 'pass' ? 'normal' : requirement.status === 'warn' ? 'warning' : 'danger'}>
                      {runtimeSafetyRequirementStatusLabel(requirement.status)}
                    </Badge>
                  </div>
                  {requirement.confirmation_key && (
                    <div className="mt-1 text-slate-500">
                      {runtimeSafetyConfirmationLabel(requirement.confirmation_key)}
                    </div>
                  )}
                </div>
              ))}
            </div>
            {warnings.length > 0 && (
              <div className="mt-3 text-amber-700 dark:text-amber-300">
                {warnings.map(runtimeSafetyRequirementLabel).join(' / ')}
              </div>
            )}
          </TechnicalDetails>
        </>
      )}
    </ConsolePanel>
  );
}

function PipelineList({
  rows,
  emptyTitle,
  emptySubtitle,
}: {
  rows: Array<{
    id: string;
    title: string;
    subtitle: string;
    tone: ConsoleTone;
    cells: Array<{ label: string; value: string }>;
  }>;
  emptyTitle: string;
  emptySubtitle: string;
}) {
  if (rows.length === 0) {
    return (
      <EntityRow
        title={emptyTitle}
        subtitle={emptySubtitle}
        tone="unavailable"
        cells={[
          { label: '状态', value: '暂无数据' },
          { label: '执行', value: '未授予' },
          { label: '来源', value: 'shadow / preview' },
          { label: '处理', value: '等待策略事实' },
        ]}
        action={<StatusChip tone="unavailable">空</StatusChip>}
      />
    );
  }
  return (
    <div className="divide-y divide-slate-800/90">
      {rows.map((row) => (
        <div key={row.id}>
          <EntityRow
            title={row.title}
            subtitle={row.subtitle}
            tone={row.tone}
            cells={row.cells}
            action={<StatusChip tone={row.tone}>只读</StatusChip>}
          />
        </div>
      ))}
    </div>
  );
}

function BoundaryCell({
  label,
  value,
  tone = 'unavailable',
}: {
  label: string;
  value: string;
  tone?: ConsoleTone;
}) {
  return (
    <div className="min-h-20 bg-slate-900 px-4 py-3">
      <div className="flex items-center gap-2 text-[11px] font-medium uppercase text-slate-500">
        <span className={cn('h-2 w-2 rounded-sm', toneDotClass(tone))} />
        {label}
      </div>
      <div className="mt-2 truncate text-sm font-medium text-slate-100">{value}</div>
    </div>
  );
}

function GuidanceLine({
  tone,
  title,
  body,
}: {
  tone: ConsoleTone;
  title: string;
  body: string;
}) {
  const Icon = tone === 'blocked' || tone === 'intervention' ? XCircle : AlertTriangle;
  return (
    <div className="flex gap-3 rounded-md border border-slate-800 bg-slate-900/70 p-3">
      <Icon className={cn('mt-0.5 h-4 w-4 shrink-0', toneTextClass(tone))} />
      <div>
        <div className="font-medium text-slate-100">{title}</div>
        <div className="mt-1 text-xs leading-5 text-slate-400">{body}</div>
      </div>
    </div>
  );
}

function ScopeFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/45 px-3 py-2">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="mt-1 truncate font-mono text-slate-200">{value}</div>
    </div>
  );
}

function RuntimeSoftButton({
  children,
  to,
  onClick,
  disabled = false,
}: {
  children: ReactNode;
  to?: string;
  onClick?: () => void;
  disabled?: boolean;
}) {
  const classes = cn(
    'inline-flex min-h-9 cursor-pointer items-center justify-center gap-2 rounded-md border border-slate-700 bg-slate-800/70 px-3 py-2 text-sm font-medium text-slate-200 transition hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500',
    disabled && 'cursor-not-allowed opacity-50 hover:bg-slate-800/70',
  );
  if (to && !disabled) return <Link to={to} className={classes}>{children}</Link>;
  return (
    <button type="button" onClick={onClick} disabled={disabled} className={classes}>
      {children}
    </button>
  );
}

function RuntimeSafetyList({
  title,
  empty,
  items,
  tone,
  mapLabel = runtimeSafetyRequirementLabel,
}: {
  title: string;
  empty: string;
  items: string[];
  tone: 'warning' | 'danger';
  mapLabel?: (value: string) => string;
}) {
  const color = tone === 'danger'
    ? 'border-rose-500/35 text-rose-200'
    : 'border-amber-500/35 text-amber-200';
  return (
    <div className={`rounded-md border bg-slate-950/45 p-4 ${color}`}>
      <div className="mb-3 text-sm font-semibold">{title}</div>
      {items.length === 0 ? (
        <div className="text-sm opacity-75">{empty}</div>
      ) : (
        <div className="space-y-2 text-sm">
          {items.slice(0, 8).map((item) => (
            <div key={item} className="rounded bg-slate-900/80 px-2 py-1">
              {mapLabel(item)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function runtimePageStatusLabel(runtime: RuntimeView | null, errors: string[]): string {
  if (errors.length > 0) return '需要介入';
  if (!runtime) return '等待运行实例';
  if (runtime.execution_enabled) return '需 gate';
  return '只读治理';
}

function runtimeStatusTone(status?: string): ConsoleTone {
  const normalized = String(status || '').toLowerCase();
  if (normalized.includes('active')) return 'normal';
  if (normalized.includes('revoked') || normalized.includes('closed')) return 'blocked';
  if (normalized.includes('paused') || normalized.includes('pending')) return 'attention';
  return 'unavailable';
}

function scopeMatchLabel(value?: string): string {
  if (value === 'matched') return '已匹配';
  if (value === 'not_checked') return '未核验';
  if (value) return String(value);
  return '无法确认';
}

function toneDotClass(tone: ConsoleTone): string {
  const map: Record<ConsoleTone, string> = {
    normal: 'bg-emerald-400',
    attention: 'bg-amber-400',
    intervention: 'bg-rose-400',
    blocked: 'bg-red-400',
    unavailable: 'bg-slate-400',
  };
  return map[tone];
}

function toneTextClass(tone: ConsoleTone): string {
  const map: Record<ConsoleTone, string> = {
    normal: 'text-emerald-300',
    attention: 'text-amber-300',
    intervention: 'text-rose-300',
    blocked: 'text-red-300',
    unavailable: 'text-slate-300',
  };
  return map[tone];
}

function runtimeSafetyStatusLabel(status: string): string {
  const map: Record<string, string> = {
    blocked: '阻断',
    ready_for_owner_codex_confirmation: '待确认',
    not_available: '暂无 Runtime',
    unavailable: '不可用',
  };
  return map[status] || displayValue(status, '无法确认');
}

function liveMonitorTone(status?: string): ConsoleTone {
  const normalized = String(status || '').toLowerCase();
  if (normalized === 'active_protected') return 'normal';
  if (normalized === 'active_protection_warning') return 'attention';
  if (normalized === 'flat_review_required') return 'attention';
  if (normalized === 'flat_no_review_required') return 'unavailable';
  if (normalized === 'active_unprotected' || normalized === 'blocked') return 'blocked';
  return 'unavailable';
}

function liveMonitorStatusLabel(status?: string): string {
  const map: Record<string, string> = {
    active_protected: '保护完整',
    active_protection_warning: '保护提醒',
    active_unprotected: '未保护',
    flat_review_required: '平仓待复盘',
    flat_no_review_required: '无持仓',
    blocked: '阻断',
  };
  return map[String(status || '')] || displayValue(status, '无法确认');
}

function liveProtectionStatusLabel(status?: string): string {
  const map: Record<string, string> = {
    hard_stop_and_tp_present: 'SL + TP',
    hard_stop_only: '仅 SL',
    hard_stop_missing: '缺少 SL',
    no_active_position: '无持仓',
    unknown: '无法确认',
  };
  return map[String(status || 'unknown')] || displayValue(status, '无法确认');
}

function liveMonitorReasonLabel(value: string): string {
  const map: Record<string, string> = {
    runtime_not_active: 'Runtime 未处于 active',
    reconciliation_severe_mismatch: '本地 / 交易所存在严重不一致',
    exchange_facts_unavailable: '交易所事实暂不可用',
    runtime_max_active_positions_in_use: 'active-position slot 已占用，新尝试暂停',
    active_position_missing_hard_stop: '活跃仓位缺少硬止损',
    missing_tp_protection_right_tail_exit_not_mounted: '仅有 SL，TP / runner 出场尚未挂载',
    reconciliation_warning_present: '对账存在 warning',
    local_exchange_active_position_count_differs: '本地 / 交易所活跃仓位数不同',
    missing_tp_protection: '交易所存在 SL-only 保护提醒',
  };
  return map[value] || runtimeSafetyRequirementLabel(value);
}

function runtimeSafetyRequirementStatusLabel(status: string): string {
  const map: Record<string, string> = {
    pass: '已具备',
    warn: '需确认',
    block: '缺失',
  };
  return map[status] || displayValue(status, '未知');
}

function runtimeSafetyRequirementLabel(code: string): string {
  const map: Record<string, string> = {
    runtime_status_active: 'Runtime 状态',
    runtime_remains_non_executing_preview: '非执行预览边界',
    symbol_side_boundary_present: '标的 / 方向边界',
    attempt_limit_available: '尝试次数边界',
    max_loss_budget_present: '最大亏损预算',
    budget_reservation_basis_required: '预算预留规则',
    max_notional_boundary_present: '单次名义金额',
    max_active_positions_boundary_present: '最大活跃仓位',
    max_leverage_boundary_present: '最大杠杆',
    margin_usage_boundary_present: '保证金占用',
    liquidation_buffer_boundary_present: '强平缓冲',
    protection_required: '硬保护要求',
    review_required: '复盘要求',
    trusted_fact_sources_required: '可信仓位事实',
    trusted_account_facts_required: '可信账户事实',
    stale_fact_behavior_required: '过期事实处理',
  };
  return map[code] || code;
}

function runtimeSafetyConfirmationLabel(code: string): string {
  const map: Record<string, string> = {
    symbol_side_boundary_confirmed: '确认标的 / 方向边界',
    attempt_consumption_rule_confirmed: '确认 attempt 消耗规则',
    max_loss_budget_confirmed: '确认最大亏损预算',
    budget_reservation_rule_confirmed: '确认预算预留规则',
    max_notional_boundary_confirmed: '确认单次名义金额',
    max_active_positions_boundary_confirmed: '确认最大活跃仓位',
    max_leverage_boundary_confirmed: '确认最大杠杆',
    margin_usage_boundary_confirmed: '确认保证金边界',
    liquidation_buffer_boundary_confirmed: '确认强平缓冲',
    protection_readiness_source_confirmed: '确认保护事实来源',
    trusted_active_position_source_confirmed: '确认仓位事实来源',
    trusted_account_fact_source_confirmed: '确认账户事实来源',
    stale_fact_behavior_confirmed: '确认过期事实阻断',
  };
  return map[code] || code;
}

function promotionGateStatusLabel(status?: string): string {
  const map: Record<string, string> = {
    blocked: '阻断',
    ready_for_controlled_runtime_execution_design: '可进入受控执行设计审查',
    ready_for_first_real_submit_gate_review: '可进入首次实盘门禁审查',
    unavailable: '不可用',
  };
  return map[String(status || '')] || displayValue(status, '无法确认');
}

function promotionGateDecisionLabel(code: string): string {
  const map: Record<string, string> = {
    strategy_family_confirmed: '确认首批策略族',
    implementation_source_confirmed: '确认策略实现来源',
    required_facts_confirmed: '确认 RequiredFacts',
    entry_policy_confirmed: '确认入场策略',
    exit_policy_confirmed: '确认出场策略',
    protection_policy_confirmed: '确认保护策略',
    eligible_for_runtime_execution_confirmed: '确认可进入 runtime 执行候选',
    right_tail_review_metrics_confirmed: '确认右尾复盘指标',
    runtime_profile_confirmed: '确认 runtime profile',
    owner_confirmation_mode_confirmed: '确认 Owner 逐单 / 预算内自动模式',
    symbol_side_boundary_confirmed: '确认标的 / 方向边界',
    max_loss_budget_confirmed: '确认最大亏损预算',
    max_notional_boundary_confirmed: '确认单次名义金额',
    max_active_positions_boundary_confirmed: '确认最大活跃仓位',
    max_leverage_boundary_confirmed: '确认最大杠杆',
    margin_usage_boundary_confirmed: '确认保证金边界',
    liquidation_buffer_boundary_confirmed: '确认强平缓冲',
    protection_readiness_source_confirmed: '确认保护事实来源',
    stale_fact_behavior_confirmed: '确认过期事实阻断',
    attempt_consumption_rule_confirmed: '确认 attempt 消耗规则',
    budget_reservation_rule_confirmed: '确认预算预留规则',
    trusted_active_position_source_confirmed: '确认仓位事实来源',
    trusted_account_fact_source_confirmed: '确认账户事实来源',
    short_side_conservative_profile_confirmed: '确认短侧保守 profile',
    budget_release_or_consume_rule_confirmed: '确认预算释放 / 确认消耗规则',
    protection_creation_failure_policy_confirmed: '确认保护创建失败处理',
    duplicate_submit_policy_confirmed: '确认重复 submit 阻断策略',
    deployment_readiness_confirmed: '确认部署 readiness',
    explicit_owner_real_submit_authorization: 'Owner 明确授权首次真实 submit',
  };
  return map[code] || code;
}

function promotionConfirmationUnsafe(record: PromotionConfirmationView): boolean {
  return (
    record.not_execution_authority !== true
    || record.execution_intent_created === true
    || record.order_created === true
    || record.exchange_called === true
    || record.owner_bounded_execution_called === true
    || record.order_lifecycle_called === true
    || record.runtime_mutation_created === true
    || record.withdrawal_instruction_created === true
    || record.transfer_instruction_created === true
  );
}

function promotionGateBlockerLabel(code: string): string {
  const normalized = code
    .replace(/^semantic_/, '')
    .replace(/^runtime_/, '')
    .replace(/^first_real_submit_/, '')
    .replace(/_missing$/, '');
  const direct = promotionGateDecisionLabel(normalized);
  if (direct !== normalized) return direct;
  const map: Record<string, string> = {
    strategy_binding_not_trade_candidate: '策略绑定不是交易候选',
    regime_classifier_not_runtime_trade_strategy: 'RMR 仍是 regime classifier',
    data_backlog_not_runtime_trade_strategy: '数据依赖策略仍在 backlog',
    strategy_not_proven_alpha_limits_economic_and_autonomy_admission: '未证明 alpha：限制预算和自动化强度',
    reference_implementation_not_proven_production_strategy: '参考实现：不是 proven-alpha 生产策略',
    short_side_conservative_profile_confirmed: '短侧保守 profile 未确认',
  };
  return map[code] || map[normalized] || code;
}
