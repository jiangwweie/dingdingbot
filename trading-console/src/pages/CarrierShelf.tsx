import { useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import {
  FileSearch,
  ShieldCheck,
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
import { asArray, displayValue, useReadModel } from '@/lib/tradingConsoleApi';
import { cn } from '@/lib/utils';
import { authorizationStatusLabel, blockingReasonLabel, carrierStatusLabel, sideLabel } from '@/lib/ownerViewModel';

type CarrierView = {
  carrier_id?: string;
  strategy_family_id?: string;
  symbol?: string;
  side?: string;
  status?: string;
  blocked_reasons?: string[];
  authorization?: Record<string, any>;
  protection?: Record<string, any>;
};

type StrategyCandidateView = {
  family?: string;
  strategy_family_id?: string;
  carrier_id?: string;
  admission_level?: string;
  candidate_state?: string;
  action_candidate_status?: string;
  action_registry_supported?: boolean;
  warning_count?: number;
  hard_blocker_count?: number;
  owner_decision_text?: string;
  research_quality_status?: string;
  risk_disclosure_classifications?: string[];
  owner_risk_acceptance_required?: boolean;
  frontend_action_enabled?: boolean;
  may_execute_live?: boolean;
};

type ObservationCandidateView = {
  candidate_id?: string;
  strategy_group_id?: string;
  strategy_family_version_id?: string | null;
  symbol?: string;
  side?: string;
  observation_role?: string;
  evaluator_glue_status?: string;
  signal_contract?: string[];
  review_windows?: string[];
  readiness_status?: string;
  blockers?: string[];
  not_allowed_now?: string[];
  runtime_signal_planning_readiness?: Record<string, any>;
};

type ObservationSignalView = {
  candidate_id?: string;
  strategy_group_id?: string;
  strategy_family_version_id?: string | null;
  symbol?: string;
  side?: string;
  signal_type?: string;
  confidence?: string;
  human_summary?: string;
  reason_codes?: string[];
  no_execution_permission?: boolean;
  no_order_permission?: boolean;
  no_runtime_start?: boolean;
};

type ReadOnlyObservationView = {
  generated_from?: string;
  candidates?: ObservationCandidateView[];
  current_signals?: ObservationSignalView[];
  runner_mapping?: Record<string, any>;
  observation_chain_summary?: Record<string, any>;
  runtime_signal_planning_summary?: Record<string, any>;
  non_permissions?: Record<string, boolean>;
  live_observation_active?: boolean;
  live_ready?: boolean;
};

export default function CarrierShelf() {
  const carrierState = useReadModel<any>('/api/trading-console/carrier-availability?include_exchange=false');
  const admissionState = useReadModel<any>('/api/trading-console/strategy-family-admission-state');
  const runtimeState = useReadModel<any>('/api/trading-console/strategy-runtimes?limit=10');
  const signalState = useReadModel<any>('/api/trading-console/signal-evaluations?limit=10');
  const candidateState = useReadModel<any>('/api/trading-console/order-candidates?limit=10');
  const observationState = useReadOnlyObservation();

  const carriers = asArray<CarrierView>(carrierState.envelope?.data?.carriers);
  const admission = admissionState.envelope?.data || {};
  const strategyCandidates = asArray<StrategyCandidateView>(
    admission.trading_console_candidate_output || admission.candidate_output,
  );
  const admissionBlockers = asArray<any>(admissionState.envelope?.blockers);
  const runtimes = asArray<any>(runtimeState.envelope);
  const signalEvaluations = asArray<any>(signalState.envelope);
  const orderCandidates = asArray<any>(candidateState.envelope);
  const observation = observationState.payload || {};
  const observationCandidates = asArray<ObservationCandidateView>(observation.candidates);
  const observationSignals = asArray<ObservationSignalView>(observation.current_signals);
  const pageErrors = [
    carrierState.error,
    admissionState.error,
    runtimeState.error,
    signalState.error,
    candidateState.error,
    observationState.error,
  ].filter(Boolean) as string[];
  const loading = carrierState.loading && admissionState.loading;

  if (loading) {
    return (
      <div className="flex min-h-[480px] items-center justify-center rounded-md border border-slate-800 bg-slate-900/50 text-sm text-slate-400">
        正在读取策略库...
      </div>
    );
  }

  const l3Count = strategyCandidates.filter((item) => item.admission_level === 'L3').length;
  const blockerCount = admissionBlockers.length + carriers.reduce((total, item) => total + asArray(item.blocked_reasons).length, 0);
  const activeBindingCount = carriers.filter((item) => item.authorization?.authorization_id || item.status).length;
  const shortObservationCount = observationCandidates.filter((item) => String(item.side || '').toLowerCase() === 'short').length;
  const pageTone: ConsoleTone = pageErrors.length > 0
    ? 'intervention'
    : blockerCount > 0
      ? 'attention'
      : strategyCandidates.length > 0
        ? 'normal'
        : 'unavailable';

  const inspectorItems = [
    {
      title: '准入不等于可执行',
      body: '策略可以进入展示或提案层，但只有完整范围、Owner 风险接受、FinalGate、保护和审计链路都满足时，才可能进入后续执行路径。',
      tone: 'attention' as ConsoleTone,
    },
    {
      title: '未证明 alpha 不是架构禁入条件',
      body: '策略弱证据会作为风险披露和预算限制，不会阻止语义建模；但它会限制预算、自动化强度和确认要求。',
      tone: 'normal' as ConsoleTone,
    },
    {
      title: observationCandidates.length > 0 ? '只读观察链已接入' : '只读观察链待接入',
      body: observationCandidates.length > 0
        ? `当前有 ${observationCandidates.length} 个观察候选，包含 ${shortObservationCount} 个短侧候选。它们可进入证据和复盘语义，但不是订单或 Runtime 启动权限。`
        : 'CPM / BRF 等策略观察链暂未返回候选；策略库不会从空数据推断可执行。',
      tone: observationCandidates.length > 0 ? 'normal' as ConsoleTone : 'unavailable' as ConsoleTone,
      action: <StrategySoftButton to="/runtime">查看运行治理</StrategySoftButton>,
    },
    {
      title: activeBindingCount > 0 ? '存在当前 Carrier 绑定' : '暂无运行绑定',
      body: activeBindingCount > 0
        ? '当前 Carrier 用于解释已存在的 Owner 授权和保护状态；它不会自动提升为 Runtime 或订单权限。'
        : '策略资产可以先完成语义和事实绑定，再进入 Runtime 治理。',
      tone: activeBindingCount > 0 ? 'attention' as ConsoleTone : 'unavailable' as ConsoleTone,
      action: <StrategySoftButton to="/runtime">查看运行治理</StrategySoftButton>,
    },
    {
      title: '缺失事实要保持可见',
      body: missingFactSummary(admissionState.envelope, carrierState.envelope),
      tone: blockerCount > 0 ? 'attention' as ConsoleTone : 'normal' as ConsoleTone,
      action: <StrategySoftButton to="/evidence">查看证据</StrategySoftButton>,
    },
  ];

  return (
    <div className="mx-auto max-w-[1500px] space-y-4">
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusChip tone={pageTone}>{strategyPageStatusLabel(strategyCandidates.length, blockerCount, pageErrors)}</StatusChip>
            {admissionState.envelope?.freshness_status && (
              <StatusChip tone={admissionState.envelope.freshness_status === 'fresh' ? 'normal' : 'attention'}>
                {admissionState.envelope.freshness_status === 'fresh' ? '已同步' : '部分同步'}
              </StatusChip>
            )}
          </div>
          <h1 className="mt-4 text-3xl font-semibold text-slate-100">策略库</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
            查看策略资产、准入层级、缺失事实和当前绑定。这里是治理面，不是下单终端；策略准入不会自动变成执行权限。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StrategySoftButton to="/runtime">
            <ShieldCheck className="h-4 w-4" />
            运行治理
          </StrategySoftButton>
          <StrategySoftButton to="/evidence">
            <FileSearch className="h-4 w-4" />
            证据
          </StrategySoftButton>
        </div>
      </header>

      {pageErrors.length > 0 && (
        <ActionNudge
          tone="intervention"
          text={`策略库读模型暂不可用：${pageErrors[0]}`}
          action={<StrategySoftButton to="/incident">进入异常介入</StrategySoftButton>}
        />
      )}

      {blockerCount > 0 && (
        <ActionNudge
          tone="attention"
          text="存在准入阻断或缺失事实。它们限制执行路径，但不阻止策略资产继续被表达和复盘。"
          action={<StrategySoftButton to="/evidence">查看缺失事实</StrategySoftButton>}
        />
      )}

      <ConsolePanel>
        <div className="grid grid-cols-1 md:grid-cols-4">
          <MetricRailItem label="策略资产" value={strategyCandidates.length} tone={strategyCandidates.length > 0 ? 'normal' : 'unavailable'} sub="可展示 / 提案 / 候选" />
          <MetricRailItem label="L3 候选" value={l3Count} tone={l3Count > 0 ? 'attention' : 'unavailable'} sub="仍需安全门禁" />
          <MetricRailItem label="当前绑定" value={activeBindingCount} tone={activeBindingCount > 0 ? 'attention' : 'unavailable'} sub="Carrier / 授权事实" />
          <MetricRailItem label="只读观察" value={observationCandidates.length} tone={observationCandidates.length > 0 ? 'normal' : 'unavailable'} sub={`${shortObservationCount} 个短侧候选`} />
        </div>
      </ConsolePanel>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-4">
          <ReadOnlyObservationPanel
            loading={observationState.loading}
            observation={observation}
            candidates={observationCandidates}
            signals={observationSignals}
          />
          <StrategyAssetPanel candidates={strategyCandidates} />
          <CurrentCarrierPanel carriers={carriers} />
          <AdmissionGatePanel blockers={admissionBlockers} scopeReview={admission.scope_review || {}} />
          <StrategyRuntimeLinkPanel
            runtimes={runtimes}
            signalEvaluations={signalEvaluations}
            orderCandidates={orderCandidates}
          />
        </div>

        <InspectorPanel
          items={inspectorItems}
          footer={
            <div className="text-xs leading-5 text-slate-500">
              说明：策略库只展示策略资产和准入状态。没有买卖按钮；没有 ExecutionIntent 创建；没有交易所调用。
            </div>
          }
        />
      </div>

      <TechnicalDetails title="策略准入证据">
        <pre className="overflow-auto font-mono text-xs leading-5">
          {JSON.stringify({
            candidate_output: strategyCandidates,
            live_readonly_observation: {
              candidates: observationCandidates,
              current_signals: observationSignals,
              runtime_signal_planning_summary: observation.runtime_signal_planning_summary,
              non_permissions: observation.non_permissions,
            },
            scope_review: admission.scope_review,
            blockers: admissionBlockers.slice(0, 20),
            no_action_guarantee: admissionState.envelope?.no_action_guarantee,
          }, null, 2)}
        </pre>
      </TechnicalDetails>
    </div>
  );
}

function useReadOnlyObservation(): {
  payload: ReadOnlyObservationView | null;
  loading: boolean;
  error: string | null;
} {
  const [payload, setPayload] = useState<ReadOnlyObservationView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const path = '/api/brc/strategy-groups/live-readonly-observation/v1';

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
        const data = await response.json();
        if (active) setPayload(data);
      } catch (err) {
        console.error('Trading Console strategy observation API error', { path, error: err });
        if (active) {
          setPayload(null);
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
  }, []);

  return { payload, loading, error };
}

function ReadOnlyObservationPanel({
  loading,
  observation,
  candidates,
  signals,
}: {
  loading: boolean;
  observation: ReadOnlyObservationView;
  candidates: ObservationCandidateView[];
  signals: ObservationSignalView[];
}) {
  const unsafe = observation.live_ready === true
    || observation.live_observation_active === true
    || Object.values(observation.non_permissions || {}).some((value) => value !== true);
  const planningSummary = observation.runtime_signal_planning_summary || {};
  const plannerUnexpectedlyCalled = planningSummary.planner_call_performed === true
    || planningSummary.signal_evaluation_created === true
    || planningSummary.order_candidate_created === true
    || planningSummary.execution_intent_created === true
    || planningSummary.order_created === true
    || planningSummary.exchange_called === true;

  return (
    <ConsolePanel
      title="只读观察链"
      caption="CPM / BRF 等策略语义可以进入证据和复盘，但不是执行权限"
      action={<StatusChip tone={unsafe || plannerUnexpectedlyCalled ? 'blocked' : candidates.length > 0 ? 'normal' : 'unavailable'}>{loading ? '读取中' : unsafe || plannerUnexpectedlyCalled ? '需核查' : '非执行'}</StatusChip>}
    >
      {loading ? (
        <div className="px-4 py-6 text-sm text-slate-500">正在读取策略观察链...</div>
      ) : candidates.length === 0 ? (
        <EntityRow
          title="暂无观察候选"
          subtitle="等待 read-only strategy observation API 返回候选"
          tone="unavailable"
          cells={[
            { label: 'CPM', value: '待接入' },
            { label: 'BRF', value: '待接入' },
            { label: '信号', value: '暂无' },
            { label: '执行', value: '未授予' },
          ]}
          action={<StatusChip tone="unavailable">空</StatusChip>}
        />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-px bg-slate-800/80 md:grid-cols-4">
            <GateCell label="观察候选" value={String(candidates.length)} tone="normal" />
            <GateCell label="规划预检" value={planningSummaryLabel(planningSummary)} tone={planningSummaryTone(planningSummary)} />
            <GateCell label="Shadow 创建" value={plannerUnexpectedlyCalled ? '异常' : '未创建'} tone={plannerUnexpectedlyCalled ? 'blocked' : 'unavailable'} />
            <GateCell label="执行权限" value={unsafe ? '需核查' : '未授予'} tone={unsafe ? 'blocked' : 'unavailable'} />
          </div>
          <div className="grid grid-cols-1 gap-px border-t border-slate-800 bg-slate-800/80 md:grid-cols-4">
            <GateCell label="当前信号" value={String(signals.length)} tone={signals.length > 0 ? 'attention' : 'unavailable'} />
            <GateCell label="Live ready" value={observation.live_ready ? '异常' : '否'} tone={observation.live_ready ? 'blocked' : 'normal'} />
            <GateCell label="Planner 调用" value={planningSummary.planner_call_performed ? '异常' : '未调用'} tone={planningSummary.planner_call_performed ? 'blocked' : 'unavailable'} />
            <GateCell label="Intent / Order" value={planningSummary.execution_intent_created || planningSummary.order_created ? '异常' : '未创建'} tone={planningSummary.execution_intent_created || planningSummary.order_created ? 'blocked' : 'unavailable'} />
          </div>
          <div className="divide-y divide-slate-800/90 border-t border-slate-800">
            {candidates.map((candidate) => {
              const signal = signals.find((item) => item.candidate_id === candidate.candidate_id);
              const readiness = candidate.runtime_signal_planning_readiness || {};
              return (
                <div key={candidate.candidate_id || `${candidate.strategy_group_id}-${candidate.symbol}`}>
                  <EntityRow
                    title={displayValue(candidate.candidate_id, '观察候选')}
                    subtitle={`${displayValue(candidate.strategy_group_id, '策略族')} · ${observationRoleLabel(candidate.observation_role)}`}
                    tone={observationCandidateTone(candidate, signal)}
                    cells={[
                      { label: '标的', value: displayValue(candidate.symbol, '暂无') },
                      { label: '方向', value: sideLabel(candidate.side) },
                      { label: '信号', value: signalTypeLabel(signal?.signal_type) },
                      { label: '规划', value: planningStatusLabel(readiness.status) },
                    ]}
                    action={<StatusChip tone={observationCandidateTone(candidate, signal)}>{signal?.no_execution_permission === false ? '需核查' : '非执行'}</StatusChip>}
                  />
                  <div className="border-t border-slate-800/70 bg-slate-950/30 px-4 py-3 text-xs leading-5 text-slate-500">
                    {planningLine(readiness)}
                    <span className="mx-2 text-slate-700">/</span>
                    {signal?.human_summary || observationBlockerSummary(candidate)}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </ConsolePanel>
  );
}

function StrategyAssetPanel({ candidates }: { candidates: StrategyCandidateView[] }) {
  return (
    <ConsolePanel title="策略资产" caption="按准入层级展示；研究弱点是披露和预算约束，不是语义禁入">
      <div className="divide-y divide-slate-800/90">
        {candidates.length === 0 ? (
          <EntityRow
            title="暂无策略资产"
            subtitle="等待 StrategyFamily / StrategyImplementation 进入治理面"
            tone="unavailable"
            cells={[
              { label: '准入', value: '暂无' },
              { label: '状态', value: '未接入' },
              { label: '风险', value: '待披露' },
              { label: '执行', value: '未授予' },
            ]}
            action={<StatusChip tone="unavailable">空</StatusChip>}
          />
        ) : (
          candidates.map((candidate) => (
            <div key={`${candidate.strategy_family_id}-${candidate.carrier_id}`}>
              <EntityRow
                title={displayValue(strategyFamilyLabel(candidate.family), '策略族')}
                subtitle={displayValue(candidate.strategy_family_id || candidate.carrier_id, '暂无版本')}
                tone={strategyCandidateTone(candidate)}
                cells={[
                  { label: '准入', value: admissionLevelLabel(candidate.admission_level) },
                  { label: '状态', value: candidateStateLabel(candidate.candidate_state) },
                  { label: '风险', value: researchQualityLabel(candidate.research_quality_status) },
                  { label: '执行', value: candidate.may_execute_live ? '可进入后续 gate' : '未开放' },
                ]}
                action={<StatusChip tone={strategyCandidateTone(candidate)}>{candidate.frontend_action_enabled ? '可操作' : '只读'}</StatusChip>}
              />
              <div className="border-t border-slate-800/70 bg-slate-950/30 px-4 py-3 text-xs leading-5 text-slate-500">
                {ownerDecisionLabel(candidate)}
              </div>
            </div>
          ))
        )}
      </div>
    </ConsolePanel>
  );
}

function CurrentCarrierPanel({ carriers }: { carriers: CarrierView[] }) {
  return (
    <ConsolePanel title="当前 Carrier 绑定" caption="Carrier 是策略 + 标的 + 方向 + 风险边界，不是订单">
      <div className="divide-y divide-slate-800/90">
        {carriers.length === 0 ? (
          <EntityRow
            title="暂无 Carrier"
            subtitle="策略资产尚未绑定到当前运行对象"
            tone="unavailable"
            cells={[
              { label: '市场', value: '暂无' },
              { label: '方向', value: '未知' },
              { label: '授权', value: '未授予' },
              { label: '保护', value: '暂无' },
            ]}
            action={<StatusChip tone="unavailable">空</StatusChip>}
          />
        ) : (
          carriers.map((carrier) => (
            <div key={carrier.carrier_id || `${carrier.symbol}-${carrier.side}`}>
              <EntityRow
                title={displayValue(carrier.carrier_id, 'Carrier')}
                subtitle={displayValue(carrier.strategy_family_id, '策略族待确认')}
                tone={carrierTone(carrier)}
                active={Boolean(carrier.authorization?.authorization_id)}
                cells={[
                  { label: '市场', value: displayValue(carrier.symbol, '暂无') },
                  { label: '方向', value: sideLabel(carrier.side) },
                  { label: '状态', value: carrierAvailabilityLabel(carrier.status) },
                  { label: '授权', value: authorizationStatusLabel(carrier.authorization?.status) },
                ]}
                action={<StatusChip tone={carrierTone(carrier)}>{carrier.authorization?.is_actionable ? '需预检' : '只读'}</StatusChip>}
              />
              {asArray<string>(carrier.blocked_reasons).length > 0 && (
                <div className="border-t border-slate-800/70 bg-slate-950/30 px-4 py-3 text-xs leading-5 text-rose-200">
                  {asArray<string>(carrier.blocked_reasons).map(blockingReasonLabel).join(' / ')}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </ConsolePanel>
  );
}

function AdmissionGatePanel({
  blockers,
  scopeReview,
}: {
  blockers: any[];
  scopeReview: Record<string, any>;
}) {
  const visibleBlockers = blockers.slice(0, 8);
  return (
    <ConsolePanel title="准入与缺失事实" caption="缺失事实会限制执行，但不会删除策略资产">
      <div className="grid grid-cols-1 gap-px bg-slate-800/80 md:grid-cols-4">
        <GateCell label="范围" value={scopeVerdictLabel(scopeReview.verdict)} tone={scopeReview.complete ? 'normal' : 'attention'} />
        <GateCell label="缺失字段" value={String(asArray(scopeReview.missing_fields).length)} tone={asArray(scopeReview.missing_fields).length > 0 ? 'attention' : 'normal'} />
        <GateCell label="不匹配" value={String(asArray(scopeReview.mismatches).length)} tone={asArray(scopeReview.mismatches).length > 0 ? 'blocked' : 'normal'} />
        <GateCell label="阻断" value={String(blockers.length)} tone={blockers.length > 0 ? 'attention' : 'normal'} />
      </div>
      <div className="divide-y divide-slate-800/90 border-t border-slate-800">
        {visibleBlockers.length === 0 ? (
          <div className="px-4 py-4 text-sm text-slate-500">暂无准入阻断。</div>
        ) : (
          visibleBlockers.map((blocker) => (
            <div key={`${blocker.code}-${blocker.stage}`} className="grid grid-cols-1 gap-2 px-4 py-3 text-sm md:grid-cols-[160px_minmax(0,1fr)_120px]">
              <div className="truncate text-slate-300">{admissionStageLabel(blocker.stage)}</div>
              <div className="min-w-0 text-slate-400">{admissionBlockerMessage(blocker.message)}</div>
              <div className="text-xs text-amber-300">{blockerSeverityLabel(blocker.severity)}</div>
            </div>
          ))
        )}
      </div>
    </ConsolePanel>
  );
}

function StrategyRuntimeLinkPanel({
  runtimes,
  signalEvaluations,
  orderCandidates,
}: {
  runtimes: any[];
  signalEvaluations: any[];
  orderCandidates: any[];
}) {
  return (
    <ConsolePanel title="进入运行治理前" caption="策略资产进入 Runtime 前必须绑定语义、事实和边界">
      <div className="grid grid-cols-1 gap-px bg-slate-800/80 md:grid-cols-3">
        <GateCell label="运行实例" value={String(runtimes.length)} tone={runtimes.length > 0 ? 'attention' : 'unavailable'} />
        <GateCell label="信号评估" value={String(signalEvaluations.length)} tone={signalEvaluations.length > 0 ? 'attention' : 'unavailable'} />
        <GateCell label="订单候选" value={String(orderCandidates.length)} tone={orderCandidates.length > 0 ? 'attention' : 'unavailable'} />
      </div>
      <div className="border-t border-slate-800 px-4 py-4">
        <ActionNudge
          tone="attention"
          text="先完成策略语义与边界绑定，再进入受控 Runtime 执行设计。"
          action={<StrategySoftButton to="/runtime">查看运行治理</StrategySoftButton>}
        />
      </div>
    </ConsolePanel>
  );
}

function GateCell({
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

function StrategySoftButton({
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

function strategyPageStatusLabel(assetCount: number, blockerCount: number, errors: string[]): string {
  if (errors.length > 0) return '需要介入';
  if (assetCount === 0) return '数据待补';
  if (blockerCount > 0) return '有待关注项';
  return '策略保持观察';
}

function strategyCandidateTone(candidate: StrategyCandidateView): ConsoleTone {
  if (candidate.frontend_action_enabled || candidate.may_execute_live) return 'attention';
  if (Number(candidate.hard_blocker_count || 0) > 0) return 'attention';
  if (candidate.admission_level === 'L0') return 'blocked';
  return 'normal';
}

function carrierTone(carrier: CarrierView): ConsoleTone {
  if (asArray(carrier.blocked_reasons).length > 0 || carrier.status === 'blocked') return 'blocked';
  if (carrier.authorization?.authorization_id) return 'attention';
  if (carrier.status) return 'normal';
  return 'unavailable';
}

function strategyFamilyLabel(value?: string): string {
  const map: Record<string, string> = {
    Trend: '趋势延续',
    'Volatility expansion': '波动扩张',
    'Mean reversion': '均值回归',
  };
  return map[String(value || '')] || displayValue(value, '策略族');
}

function admissionLevelLabel(value?: string): string {
  const map: Record<string, string> = {
    L0: 'L0 停用 / 归档',
    L1: 'L1 可展示',
    L2: 'L2 提案',
    L3: 'L3 Owner 确认候选',
    L4: 'L4 预算自治设计',
  };
  return map[String(value || '')] || displayValue(value, '暂无');
}

function candidateStateLabel(value?: string): string {
  const map: Record<string, string> = {
    bounded_live_candidate: '有界候选',
    proposal: '提案',
    displayable: '可展示',
    parked: '停放',
  };
  return map[String(value || '')] || displayValue(value, '暂无');
}

function researchQualityLabel(value?: string): string {
  const map: Record<string, string> = {
    fragile_evidence: '证据脆弱',
    insufficient_research: '研究不足',
    accepted_for_trial: '可小额试验',
  };
  return map[String(value || '')] || displayValue(value, '待确认');
}

function ownerDecisionLabel(candidate: StrategyCandidateView): string {
  if (candidate.admission_level === 'L3') {
    return 'Owner 可审查精确有界范围；只有在明确接受风险且所有执行安全门禁通过后，才可能进入后续路径。';
  }
  if (candidate.admission_level === 'L2') {
    return 'Owner 可以查看提案和风险披露；当前没有 live action 路径，也不会自动进入执行。';
  }
  if (candidate.owner_risk_acceptance_required) {
    return '需要 Owner 风险接受；接受风险只处理策略弱证据，不会绕过执行安全门禁。';
  }
  return displayValue(candidate.owner_decision_text, '暂无 Owner 处理说明。');
}

function observationCandidateTone(candidate: ObservationCandidateView, signal?: ObservationSignalView): ConsoleTone {
  if (signal?.no_execution_permission === false || signal?.no_order_permission === false || signal?.no_runtime_start === false) return 'blocked';
  if (asArray(candidate.blockers).length > 0 || asArray(candidate.not_allowed_now).length > 0) return 'attention';
  if (signal?.signal_type === 'would_enter') return 'attention';
  return 'normal';
}

function observationRoleLabel(value?: string): string {
  const map: Record<string, string> = {
    owner_special_observation: 'Owner 特别观察',
    short_side_bear_rally_failure_reference: '熊市反弹失败短侧',
    price_action_observation: '价格行为观察',
  };
  return map[String(value || '')] || displayValue(value, '观察');
}

function signalTypeLabel(value?: string): string {
  const map: Record<string, string> = {
    no_action: '无动作',
    would_enter: '会入场候选',
    invalid: '输入无效',
  };
  return map[String(value || '')] || displayValue(value, '暂无');
}

function planningStatusLabel(value?: unknown): string {
  const map: Record<string, string> = {
    observe_only: '观察',
    blocked: '阻断',
    ready_for_non_executing_planner: '可进非执行规划',
  };
  return map[String(value || '')] || displayValue(value, '暂无');
}

function planningSummaryLabel(summary: Record<string, any>): string {
  const statusCounts = summary.status_counts || {};
  const ready = Number(statusCounts.ready_for_non_executing_planner || 0);
  const blocked = Number(statusCounts.blocked || 0);
  const observeOnly = Number(statusCounts.observe_only || 0);
  if (ready > 0) return `${ready} 可规划`;
  if (blocked > 0) return `${blocked} 阻断`;
  if (observeOnly > 0) return `${observeOnly} 观察`;
  return '暂无';
}

function planningSummaryTone(summary: Record<string, any>): ConsoleTone {
  if (
    summary.planner_call_performed === true
    || summary.signal_evaluation_created === true
    || summary.order_candidate_created === true
    || summary.execution_intent_created === true
    || summary.order_created === true
    || summary.exchange_called === true
  ) return 'blocked';
  const statusCounts = summary.status_counts || {};
  if (Number(statusCounts.ready_for_non_executing_planner || 0) > 0) return 'attention';
  if (Number(statusCounts.blocked || 0) > 0) return 'attention';
  if (Number(statusCounts.observe_only || 0) > 0) return 'unavailable';
  return 'unavailable';
}

function planningLine(readiness: Record<string, any>): string {
  const created = [
    readiness.signal_evaluation_created === true ? 'SignalEvaluation' : null,
    readiness.order_candidate_created === true ? 'OrderCandidate' : null,
    readiness.execution_intent_created === true ? 'ExecutionIntent' : null,
    readiness.order_created === true ? 'Order' : null,
  ].filter(Boolean);
  if (created.length > 0) {
    return `规划预检异常：已创建 ${created.join(' / ')}`;
  }
  const blockers = asArray<string>(readiness.blockers);
  const warnings = asArray<string>(readiness.warnings);
  if (blockers.length > 0) {
    return `规划预检：${planningStatusLabel(readiness.status)}，阻断 ${blockers.slice(0, 2).join(' / ')}`;
  }
  if (warnings.length > 0) {
    return `规划预检：${planningStatusLabel(readiness.status)}，关注 ${warnings.slice(0, 2).join(' / ')}`;
  }
  return `规划预检：${planningStatusLabel(readiness.status)}，未创建 SignalEvaluation / OrderCandidate`;
}

function observationBlockerSummary(candidate: ObservationCandidateView): string {
  const blockers = [
    ...asArray<string>(candidate.blockers),
    ...asArray<string>(candidate.not_allowed_now),
  ];
  if (blockers.length === 0) return '观察链保持非执行；可用于证据、信号和后续复盘语义。';
  return blockers.slice(0, 3).join(' / ');
}

function carrierAvailabilityLabel(value?: string): string {
  const map: Record<string, string> = {
    candidate_available_for_review: '可评审',
    blocked: '暂不可用',
    read_only_available: '可查看',
    available: '可查看',
    unknown: '无法确认',
  };
  return map[String(value || 'unknown')] || carrierStatusLabel(value);
}

function scopeVerdictLabel(value?: string): string {
  const map: Record<string, string> = {
    not_provided: '未提供',
    incomplete: '不完整',
    complete_dry_run_only: '仅 dry-run 完整',
  };
  return map[String(value || '')] || displayValue(value, '无法确认');
}

function admissionStageLabel(value?: string): string {
  const map: Record<string, string> = {
    BoundedLiveAuthorization: '授权边界',
    AuthorizationDraft: '范围草案',
    PreExecutionBlockedReview: '执行前证据',
    'TP/SL': '保护计划',
    Review: '复盘',
  };
  return map[String(value || '')] || displayValue(value, '准入');
}

function admissionBlockerMessage(message?: string): string {
  const text = String(message || '');
  if (!text) return '缺失事实需要补齐。';
  if (text.includes('No candidate has complete')) return '没有候选具备完整范围、保护和复盘要求。';
  if (text.includes('Owner authorization')) return '缺少当前 Owner 授权或 live preflight 证据。';
  if (text.includes('Owner scope')) return 'Owner 范围未完整匹配。';
  if (text.includes('FinalGate') || text.toLowerCase().includes('final gate')) return 'FinalGate 尚未返回可行动。';
  if (text.includes('pre-action')) return '执行前 PG / 交易所证据尚未收集。';
  if (text.includes('TP/SL')) return '保护计划仍是草案，不可执行。';
  if (text.includes('review')) return '复盘契约仍缺少行动证据。';
  if (text.includes('official action API')) return '当前官方 action API 不支持该候选。';
  return text;
}

function blockerSeverityLabel(value?: string): string {
  const map: Record<string, string> = {
    hard_blocker: '硬阻断',
    deferred: '待后续',
    warning: '需关注',
  };
  return map[String(value || '')] || displayValue(value, '待确认');
}

function missingFactSummary(admissionEnvelope: any, carrierEnvelope: any): string {
  const unavailable = [
    ...asArray(admissionEnvelope?.unavailable),
    ...asArray(carrierEnvelope?.unavailable),
  ];
  if (unavailable.length === 0) return '当前没有显式缺失事实。';
  const labels = Array.from(new Set(unavailable.map((item: any) => missingSourceLabel(item.source || item.code)))).slice(0, 4);
  return `缺失或不可确认：${labels.join('、')}。缺失时只允许观察和证据核对。`;
}

function missingSourceLabel(value?: string): string {
  const map: Record<string, string> = {
    is_active: '全局开关',
    is_armed: '启动保护',
    order_audit_logs: '订单审计',
    review_state: '复盘事实',
    signals: '信号事实',
    runtime_control_state: '运行控制',
  };
  return map[String(value || '')] || displayValue(value, '未知事实');
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
