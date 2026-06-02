import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  AlertCircle,
  BarChart3,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FileSearch,
  GitBranch,
  HelpCircle,
  Info,
  ListChecks,
  PlayCircle,
  Route,
  RotateCcw,
  ShieldCheck,
  Star,
  Users,
  Wallet,
  Zap,
} from 'lucide-react';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import {
  AccountFactsResponse,
  AdmissionDecision,
  AdmissionTrialBinding,
  brcApi,
  Mi001SolReadinessResponse,
  Mi001BnbTrialReadinessGapResponse,
  ObservationCaseQueueResponse,
  BoundedLiveTrialAuthorization,
  BnbLiveExecutionBridgeResponse,
  OwnerRiskAcknowledgement,
  OwnerTrialFlowCurrentResponse,
  ReadinessResponse,
  MultiCarrierBudgetAuthorizationCurrentResponse,
  SecondCarrierExpansionResponse,
  StrategyGroupLiveReadOnlyObservationResponse,
  StrategyGroupReviewabilityResponse,
  StrategyTrialArchitectureGovernanceResponse,
  StrategyTrialReadinessResponse,
  StrategyFamily,
} from '@/src/services/api';
import { ErrorState, JsonDetails } from './ConsolePrimitives';

type ConsoleData = {
  readiness: ReadinessResponse | null;
  accountFacts: AccountFactsResponse | null;
  mi001: Mi001SolReadinessResponse | null;
  strategyGroupReviewability: StrategyGroupReviewabilityResponse | null;
  liveObservation: StrategyGroupLiveReadOnlyObservationResponse | null;
  observationCaseQueue: ObservationCaseQueueResponse | null;
  bnbTrialGap: Mi001BnbTrialReadinessGapResponse | null;
  strategyTrialReadiness: StrategyTrialReadinessResponse | null;
  strategyTrialGovernance: StrategyTrialArchitectureGovernanceResponse | null;
  secondCarrierExpansion: SecondCarrierExpansionResponse | null;
  budgetAuthorizationFoundation: MultiCarrierBudgetAuthorizationCurrentResponse | null;
  ownerTrialFlow: OwnerTrialFlowCurrentResponse | null;
  bnbLiveExecutionBridge: BnbLiveExecutionBridgeResponse | null;
  families: StrategyFamily[];
  decisions: AdmissionDecision[];
  bindings: AdmissionTrialBinding[];
  currentCampaign: Record<string, unknown> | null;
  reviewPacket: Record<string, unknown> | null;
  evidence: Record<string, unknown> | null;
  operations: Array<Record<string, unknown>>;
  gaps: string[];
};

type ViewState = {
  data: ConsoleData | null;
  error: unknown;
};

type Tone = 'teal' | 'indigo' | 'amber' | 'rose' | 'slate';
type DataSource = 'backend_api' | 'derived_from_backend' | 'frontend_local_state' | 'static_product_copy' | 'sample_data' | 'unavailable';

type FieldValue<T> = {
  value: T;
  source: DataSource;
};

type MarketViewInput = {
  symbol: string;
  regime: string;
  direction: string;
  riskMode: string;
};

type OwnerFlowState = {
  marketView: MarketViewInput;
  selectedCarrierId: string;
  riskAcknowledgements: Record<string, Record<string, boolean>>;
};

const OWNER_FLOW_STORAGE_KEY = 'brc-owner-console-main-flow-v1';
const DEFAULT_MARKET_VIEW: MarketViewInput = {
  symbol: 'BNB',
  regime: '震荡',
  direction: '都可',
  riskMode: '极小资金试错',
};

type StrategyGroupShelfItem = {
  strategy_group_id: string;
  strategy_group_name: string;
  plain_language_summary: string;
  market_regime_it_eats: string;
  market_regime_it_hates: string;
  representative_candidates: string[];
  current_status: string;
  status_tone: Tone;
  evidence_summary: string;
  key_risks: string[];
  owner_action_options: string[];
  next_recommended_action: string;
  not_allowed_now: string[];
  confidence_flags?: string[];
  evidence_reviewability?: string;
  live_readonly_observation_readiness?: string;
  bounded_trial_readiness?: string;
  main_blockers?: string[];
  source_refs?: string[];
  display_model_only?: boolean;
  not_runtime_source_of_truth?: boolean;
  no_execution_permission?: boolean;
  no_order_permission?: boolean;
  no_runtime_start?: boolean;
  no_automatic_strategy_routing?: boolean;
  shelf_section?: 'primary' | 'secondary';
};

type CarrierDecisionView = {
  carrierId: string;
  strategyFamily: string;
  strategyId: string;
  candidateId: string;
  symbol: string;
  runtimeSymbol: string;
  side: string;
  quantity: string;
  maxNotional: string;
  leverage: string;
  protectionPlan: string;
  testnetState: string;
  authorizationState: string;
  pendingOwnerLiveAuthorization: boolean;
  liveReady: boolean;
  hardBlockers: string[];
  strategyWarnings: string[];
  hardBlockerCount: number;
  warningCount: number;
  primaryAction: string;
  liveAuthorizationEffect: string;
  executionIntentState: string;
  orderState: string;
  testnetEvidence: Array<[string, string]>;
  canAuthorizeLiveTrial: boolean;
  authorizationButtonDisabledReason: string;
  evidenceSource: DataSource;
  safetyGateSource: DataSource;
  accountFactsSource: DataSource;
  provenance: Record<string, DataSource>;
  timeline: Array<{
    id: string;
    title: string;
    status: string;
    desc: string;
    tech: string;
    tone: Tone;
  }>;
};

const EMPTY_DATA: ConsoleData = {
  readiness: null,
  accountFacts: null,
  mi001: null,
  strategyGroupReviewability: null,
  liveObservation: null,
  observationCaseQueue: null,
  bnbTrialGap: null,
  strategyTrialReadiness: null,
  strategyTrialGovernance: null,
  secondCarrierExpansion: null,
  budgetAuthorizationFoundation: null,
  ownerTrialFlow: null,
  bnbLiveExecutionBridge: null,
  families: [],
  decisions: [],
  bindings: [],
  currentCampaign: null,
  reviewPacket: null,
  evidence: null,
  operations: [],
  gaps: [],
};

const blockerCopy = '启动保护未预检';
const blockerLongCopy = '运行时启动保护未预检';
const strategyGroupName = 'MI-001 动量冲击';
const strategySol = 'MI-001 SOL 多头';

export function HomeV2() {
  const { data, error } = useConsoleData();
  if (error) return <ErrorState error={error} />;
  if (!data) return <Loading label="加载首页..." />;

  const carrierDecision = carrierDecisionView(data);
  const workbench = ownerWorkbenchView(carrierDecision);

  return (
    <PageShell title="Owner 工作台" subtitle="一句话看清当前进展与下一步。">
      <section className="rounded-2xl border border-amber-500/15 bg-slate-950/85 p-6 shadow-lg shadow-black/20">
        <div className="flex items-center gap-5">
          <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-100">
            <Star className="h-8 w-8" />
          </div>
          <div>
            <p className="text-sm font-bold text-slate-500 dark:text-slate-400">当前最重要的事</p>
            <h2 className="mt-2 text-2xl font-bold text-slate-950 dark:text-slate-50">{workbench.priority}</h2>
          </div>
        </div>
      </section>

      <FlowProgress currentStep={workbench.currentStep} />

      <section className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <WorkbenchCard
          icon={<Users className="h-7 w-7" />}
          title="当前候选"
          body={workbench.candidateName}
          facts={[
            ['方向', workbench.direction],
            ['仓位上限', workbench.cap],
            ['试验类型', 'BNB 小额试验'],
          ]}
          to="/strategy-candidates"
          linkText="重新选择候选"
        />
        <WorkbenchCard
          icon={<ShieldCheck className="h-7 w-7" />}
          title="当前能否执行"
          body={workbench.canExecute}
          centered
          facts={[
            ['原因', workbench.readinessReason],
          ]}
          to="/trial-confirmation"
          linkText="查看原因"
        />
        <WorkbenchCard
          icon={<PlayCircle className="h-7 w-7" />}
          title="下一步动作"
          body="进入授权前确认"
          facts={[
            ['完成度', '2 / 5 步'],
          ]}
          to="/trial-confirmation"
          linkText="继续"
        />
      </section>

      <section className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <PlainListPanel
          icon={<AlertCircle className="h-5 w-5" />}
          title="为什么现在还不能实盘"
          items={workbench.plainBlockers}
          link="/trial-confirmation"
          linkText="查看全部原因"
        />
        <PlainListPanel
          icon={<Info className="h-5 w-5" />}
          title="需要你知情的风险"
          items={workbench.plainRisks}
          link="/trial-confirmation"
          linkText="查看全部风险"
        />
      </section>

      <section className="flex flex-col gap-4 md:flex-row">
        <Link
          to="/trial-confirmation"
          className="inline-flex min-h-14 items-center justify-center gap-3 rounded-xl bg-slate-950 px-8 py-4 text-base font-bold text-white shadow-lg shadow-slate-900/15 transition hover:bg-slate-800 dark:bg-slate-100 dark:text-slate-950 dark:hover:bg-white"
        >
          <Wallet className="h-5 w-5" />
          进入授权前确认
        </Link>
        <Link
          to="/strategy-candidates"
          className="inline-flex min-h-14 items-center justify-center gap-3 rounded-xl border border-slate-300 bg-white px-8 py-4 text-base font-bold text-slate-900 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:hover:bg-slate-900"
        >
          <RotateCcw className="h-5 w-5" />
          重新选择候选
        </Link>
      </section>

      <details className="rounded-xl border border-slate-200 bg-white p-5 text-sm shadow-sm dark:border-slate-800 dark:bg-slate-950">
        <summary className="cursor-pointer font-bold text-slate-800 dark:text-slate-100">查看详细证据 / 技术详情</summary>
        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <CarrierAuthorizationPanel view={carrierDecision} />
          <DecisionBoundaryPanel view={carrierDecision} />
        </div>
        <TechnicalDetails data={technicalPayload(data)} />
      </details>
    </PageShell>
  );
}

export function StrategyCandidatesV2() {
  const { data, error } = useConsoleData();
  const [batch, setBatch] = useState(0);
  const navigate = useNavigate();
  const { flowState, updateFlowState } = useOwnerFlowState();

  if (error) return <ErrorState error={error} />;
  if (!data) return <Loading label="加载策略候选..." />;

  const carrierDecision = carrierDecisionView(data);
  const marketView = flowState.marketView;
  const candidates = strategyCandidateView(carrierDecision, { ...marketView, batch });
  const updateMarketView = (patch: Partial<MarketViewInput>) => {
    updateFlowState((current) => ({
      ...current,
      marketView: { ...current.marketView, ...patch },
    }));
  };
  const selectForConfirmation = (candidate: RecommendedCandidate) => {
    updateFlowState((current) => ({
      ...current,
      selectedCarrierId: candidate.id,
    }));
    navigate('/trial-confirmation');
  };

  return (
    <PageShell title="策略候选" subtitle="先说你的判断，系统只给候选建议；不会自动选择，也不会创建执行计划。">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
        <div className="mb-4 flex items-center gap-3">
          <StepBadge value="1" />
          <div>
            <h3 className="text-xl font-bold text-slate-950 dark:text-slate-50">先说你的判断</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400">越清晰的判断，推荐越容易复盘。随时可以调整后重新生成。</p>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-4 rounded-xl border border-slate-200 p-4 dark:border-slate-800 lg:grid-cols-[1fr_1fr_1fr_1fr_auto] lg:items-end">
          <SegmentedControl label="币种" value={marketView.symbol} options={['BTC', 'ETH', 'SOL', 'BNB']} onChange={(value) => updateMarketView({ symbol: value })} />
          <SegmentedControl label="行情判断" value={marketView.regime} options={['下跌趋势', '震荡', '反弹', '不确定']} onChange={(value) => updateMarketView({ regime: value })} />
          <SegmentedControl label="方向" value={marketView.direction} options={['只做多', '只做空', '都可']} onChange={(value) => updateMarketView({ direction: value })} />
          <label className="space-y-2">
            <span className="text-sm font-bold text-slate-800 dark:text-slate-100">风险模式</span>
            <select
              value={marketView.riskMode}
              onChange={(event) => updateMarketView({ riskMode: event.target.value })}
              className="h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            >
              <option>极小资金试错</option>
            </select>
          </label>
          <button
            type="button"
            onClick={() => setBatch((value) => value + 1)}
            className="h-11 rounded-lg bg-slate-950 px-5 text-sm font-bold text-white transition hover:bg-slate-800 dark:bg-slate-100 dark:text-slate-950"
          >
            生成候选
          </button>
        </div>
        <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
          基于你的判断：{marketView.symbol} + {marketView.regime} + {marketView.direction} + {marketView.riskMode}。系统给出以下候选。这是候选建议，不是执行授权。
        </div>
      </section>

      <section>
        <div className="mb-4 flex items-center gap-3">
          <StepBadge value="2" />
          <div>
            <h3 className="text-xl font-bold text-slate-950 dark:text-slate-50">系统推荐候选</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400">基于你的判断，为你挑选最匹配的候选。</p>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {candidates.map((candidate, index) => (
            <CandidateCard
              key={`${candidate.id}-${batch}`}
              candidate={candidate}
              rank={index + 1}
              onConfirm={selectForConfirmation}
            />
          ))}
        </div>
        <button
          type="button"
          onClick={() => setBatch((value) => value + 1)}
          className="mx-auto mt-4 flex items-center gap-2 text-sm font-bold text-slate-700 hover:text-slate-950 dark:text-slate-300 dark:hover:text-white"
        >
          换一批候选 <RotateCcw className="h-4 w-4" />
        </button>
      </section>

      <section className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_0.72fr]">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
          <div className="mb-4 flex items-center gap-3">
            <StepBadge value="3" />
            <h3 className="text-xl font-bold text-slate-950 dark:text-slate-50">全部策略类型</h3>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {strategyTypeShelf().map((item) => (
              <div key={item.title} className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-slate-100 dark:bg-slate-900">
                  <GitBranch className="h-5 w-5" />
                </div>
                <h4 className="font-bold text-slate-950 dark:text-slate-50">{item.title}</h4>
                <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{item.desc}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
          <div className="mb-4 flex items-center gap-3">
            <StepBadge value="4" />
            <div>
              <h3 className="text-xl font-bold text-slate-950 dark:text-slate-50">看不懂术语？</h3>
              <p className="text-sm text-slate-500 dark:text-slate-400">用大白话解释给你听。</p>
            </div>
          </div>
          <PlainTerm term="策略类型" desc="不同的赚钱思路或打法，比如趋势类、波动类。" />
          <PlainTerm term="候选" desc="系统为你挑选的具体币种和方向，可以先看看再决定。" />
          <PlainTerm term="试验" desc="用极小资金先跑一段时间，看效果再加大资金。" />
        </section>
      </section>

      <TechnicalDetails data={{ currentCandidate: carrierDecision, marketView, selectedCarrierId: flowState.selectedCarrierId, rawGovernance: data.strategyTrialGovernance }} />
    </PageShell>
  );
}

export function TrialConfirmationV2() {
  const { data, error } = useConsoleData();
  const { flowState, updateFlowState } = useOwnerFlowState();
  const [backendAcknowledgement, setBackendAcknowledgement] = useState<OwnerRiskAcknowledgement | null>(null);
  const [backendDraftId, setBackendDraftId] = useState<string | null>(null);
  const [backendLiveAuthorization, setBackendLiveAuthorization] = useState<BoundedLiveTrialAuthorization | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [activationError, setActivationError] = useState<string | null>(null);
  const [submittingMetadata, setSubmittingMetadata] = useState(false);
  const [activatingAuthorization, setActivatingAuthorization] = useState(false);
  if (error) return <ErrorState error={error} />;
  if (!data) return <Loading label="加载授权前确认单..." />;

  const carrierDecision = carrierDecisionView(data);
  const selectedCarrierId = flowState.selectedCarrierId || carrierDecision.carrierId;
  const confirmationCarrier = selectedCarrierId === carrierDecision.carrierId
    ? carrierDecision
    : selectedCarrierFallback(carrierDecision, selectedCarrierId);
  const localAcknowledgements = flowState.riskAcknowledgements[selectedCarrierId] || {};
  const persistedAcknowledgement = backendAcknowledgement?.carrier_id === selectedCarrierId
    ? backendAcknowledgement
    : data.ownerTrialFlow?.latest_acknowledgement?.carrier_id === selectedCarrierId
      ? data.ownerTrialFlow.latest_acknowledgement
      : null;
  const backendAcknowledgements = Object.fromEntries(
    (persistedAcknowledgement?.acknowledged_warning_codes || []).map((code) => [code, true]),
  );
  const acknowledgements = {
    ...localAcknowledgements,
    ...backendAcknowledgements,
  };
  const persistedDraft = data.ownerTrialFlow?.authorization_draft?.carrier_id === selectedCarrierId
    ? data.ownerTrialFlow.authorization_draft
    : null;
  const activeDraft = persistedDraft || (backendDraftId ? {
    draft_id: backendDraftId,
    carrier_id: selectedCarrierId,
    symbol: confirmationCarrier.runtimeSymbol || confirmationCarrier.symbol,
    side: confirmationCarrier.side === 'short' ? 'short' as const : 'long' as const,
    max_notional: confirmationCarrier.maxNotional,
    quantity: confirmationCarrier.quantity,
    leverage: confirmationCarrier.leverage,
    protection_plan_type: 'single_tp_plus_sl' as const,
  } : null);
  const persistedLiveAuthorization = backendLiveAuthorization?.carrier_id === selectedCarrierId
    ? backendLiveAuthorization
    : data.ownerTrialFlow?.live_authorization?.carrier_id === selectedCarrierId
      ? data.ownerTrialFlow.live_authorization
      : null;
  const confirmation = trialConfirmationView(confirmationCarrier, data, acknowledgements);
  const allRisksAcknowledged = confirmation.risks.every((risk) => acknowledgements[risk.id]);
  const canPersistMetadata = selectedCarrierId === carrierDecision.carrierId && allRisksAcknowledged;
  const scopeMatchesSelectedCarrier = selectedCarrierId === carrierDecision.carrierId;
  const riskMetadataComplete = Boolean(persistedAcknowledgement && activeDraft);
  const activationBlockers = [
    ...(!scopeMatchesSelectedCarrier ? ['授权范围不匹配'] : []),
    ...(!persistedAcknowledgement ? ['风险确认尚未由后端记录'] : []),
    ...(!activeDraft ? ['授权草案尚未生成'] : []),
    ...(persistedLiveAuthorization ? ['这一次真实小额试验已授权'] : []),
  ];
  const authorizationStateCopy = persistedLiveAuthorization
    ? '已授权，等待最终执行前检查'
    : '等待 Owner 授权';
  const metadataStatusRows = [
    {
      label: '风险确认',
      value: persistedAcknowledgement ? `已记录：${persistedAcknowledgement.acknowledgement_id}` : allRisksAcknowledged ? '已勾选，可写入后端' : '等待勾选风险',
      tone: persistedAcknowledgement ? 'teal' as Tone : allRisksAcknowledged ? 'amber' as Tone : 'rose' as Tone,
    },
    {
      label: '授权草案',
      value: activeDraft ? `已生成：${activeDraft.draft_id}` : allRisksAcknowledged ? '可生成草案' : '尚未生成',
      tone: activeDraft ? 'teal' as Tone : 'amber' as Tone,
    },
    {
      label: '授权状态',
      value: persistedLiveAuthorization ? '已授权但尚未执行' : scopeMatchesSelectedCarrier ? '尚未授权' : '授权范围不匹配',
      tone: persistedLiveAuthorization ? 'teal' as Tone : scopeMatchesSelectedCarrier ? 'amber' as Tone : 'rose' as Tone,
    },
  ];
  const canActivateLiveAuthorization = scopeMatchesSelectedCarrier
    && Boolean(persistedAcknowledgement)
    && Boolean(activeDraft)
    && !persistedLiveAuthorization;
  const setRiskAcknowledged = (riskId: string, acknowledged: boolean) => {
    updateFlowState((current) => ({
      ...current,
      selectedCarrierId,
      riskAcknowledgements: {
        ...current.riskAcknowledgements,
        [selectedCarrierId]: {
          ...(current.riskAcknowledgements[selectedCarrierId] || {}),
          [riskId]: acknowledged,
        },
      },
    }));
  };
  const submitBackendMetadata = async () => {
    setSubmittingMetadata(true);
    setSubmitError(null);
    try {
      const ack = await brcApi.createOwnerRiskAcknowledgement({
        carrier_id: selectedCarrierId,
        acknowledged_warning_codes: confirmation.risks.map((risk) => risk.id),
        acknowledgement_scope: 'strategy_trial_warnings',
      });
      setBackendAcknowledgement(ack);
      const side = confirmationCarrier.side === 'short' ? 'short' : 'long';
      const draft = await brcApi.createOwnerAuthorizationDraft({
        carrier_id: selectedCarrierId,
        linked_acknowledgement_id: ack.acknowledgement_id,
        symbol: confirmationCarrier.runtimeSymbol || confirmationCarrier.symbol,
        side,
        max_notional: confirmationCarrier.maxNotional,
        quantity: confirmationCarrier.quantity,
        leverage: confirmationCarrier.leverage,
        protection_plan_type: 'single_tp_plus_sl',
      });
      setBackendDraftId(draft.draft_id);
    } catch (error) {
      setSubmitError(message(error));
    } finally {
      setSubmittingMetadata(false);
    }
  };
  const activateLiveAuthorization = async () => {
    if (!activeDraft) return;
    setActivatingAuthorization(true);
    setActivationError(null);
    try {
      const authorization = await brcApi.activateOwnerLiveAuthorization(activeDraft.draft_id, {
        carrier_id: selectedCarrierId,
        symbol: activeDraft.symbol,
        side: activeDraft.side,
        max_notional: activeDraft.max_notional,
        quantity: activeDraft.quantity,
        leverage: activeDraft.leverage,
        protection_plan_type: activeDraft.protection_plan_type,
      });
      setBackendLiveAuthorization(authorization);
    } catch (error) {
      setActivationError(message(error));
    } finally {
      setActivatingAuthorization(false);
    }
  };
  const renderLiveAuthorizationButton = (spacingClass = 'mb-4') => (
    <button
      type="button"
      onClick={activateLiveAuthorization}
      disabled={!canActivateLiveAuthorization || activatingAuthorization}
      className={`${spacingClass} flex w-full items-center justify-center gap-3 rounded-xl px-5 py-4 text-base font-bold transition ${
        canActivateLiveAuthorization && !activatingAuthorization
          ? 'bg-slate-950 text-white hover:bg-slate-800 dark:bg-slate-100 dark:text-slate-950 dark:hover:bg-white'
          : 'cursor-not-allowed bg-slate-300 text-white dark:bg-slate-700 dark:text-slate-300'
      }`}
    >
      <Wallet className="h-5 w-5" />
      {persistedLiveAuthorization ? '已授权这一次真实小额试验' : '确认授权这一次真实小额试验'}
    </button>
  );

  return (
    <PageShell title="Owner 授权确认" subtitle="这页只记录本次 Owner 授权；授权不会立即下单。">
      <FlowStepper currentStep={3} />

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <StatePill tone={persistedLiveAuthorization ? 'teal' : 'amber'}>{authorizationStateCopy}</StatePill>
              <StatePill tone="slate">Carrier: MI-001-BNB-LONG</StatePill>
            </div>
            <h2 className="text-2xl font-bold text-slate-950 dark:text-slate-50">授权这一次 BNB 小额试验</h2>
            <p className="mt-2 text-base font-semibold text-slate-700 dark:text-slate-200">点击授权只记录本次授权，不会立即下单。</p>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600 dark:text-slate-300">
              风险确认、授权草案和 Owner 授权是 metadata 记录。启动保护、GKS、账户事实、持仓和挂单检查会在授权后、执行前继续阻断。
            </p>
          </div>
          <div className="grid min-w-[260px] grid-cols-1 gap-2 text-sm sm:grid-cols-3 lg:grid-cols-1">
            <StatePill tone="amber">尚未创建执行计划</StatePill>
            <StatePill tone="amber">尚未下单</StatePill>
            <StatePill tone="slate">自动执行关闭</StatePill>
          </div>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
        <div className="mb-4 flex items-center gap-3">
          <StepBadge value="1" />
          <h3 className="text-xl font-bold text-slate-950 dark:text-slate-50">本次我要授权什么</h3>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <TrialFact label="Carrier" value="MI-001-BNB-LONG" />
          <TrialFact label="Symbol" value="BNB/USDT" />
          <TrialFact label="方向" value="long / 做多" />
          <TrialFact label="数量" value="0.01 BNB" />
          <TrialFact label="最大名义本金" value="20 USDT" />
          <TrialFact label="杠杆" value="1x" />
          <TrialFact label="保护" value="单止盈 + 止损" />
          <TrialFact label="模式" value="一次性授权" />
        </div>
      </section>

      <section className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
          <div className="mb-4 flex items-center gap-3">
            <StepBadge value="2" />
            <div>
              <h3 className="text-xl font-bold text-slate-950 dark:text-slate-50">我是否已确认风险</h3>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">风险确认和真实资金授权分开记录。</p>
            </div>
          </div>
          <div className="space-y-3">
            {confirmation.risks.map((risk) => (
              <label key={risk.id} className="flex cursor-pointer items-center justify-between gap-4 rounded-xl border border-slate-200 p-4 transition hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-900">
                <span className="flex items-start gap-4">
                  <AlertCircle className="mt-1 h-5 w-5 text-slate-600 dark:text-slate-300" />
                  <span>
                    <span className="block font-bold text-slate-950 dark:text-slate-50">{risk.title}</span>
                    <span className="mt-1 block text-sm text-slate-600 dark:text-slate-300">{risk.desc}</span>
                    <StatePill tone={acknowledgements[risk.id] ? 'teal' : 'amber'}>
                      {backendAcknowledgements[risk.id] ? '已由后端记录' : acknowledgements[risk.id] ? '已在本地确认' : '未确认'}
                    </StatePill>
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
                  <input
                    type="checkbox"
                    checked={Boolean(acknowledgements[risk.id])}
                    onChange={(event) => setRiskAcknowledged(risk.id, event.target.checked)}
                    className="h-5 w-5 rounded border-slate-300"
                  />
                  我已知晓
                </span>
              </label>
            ))}
          </div>
          {persistedAcknowledgement ? (
            <div className="mt-4 rounded-lg border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-800 dark:border-teal-900/50 dark:bg-teal-950/30 dark:text-teal-300">
              风险确认已由后端记录：{persistedAcknowledgement.acknowledgement_id}。这不是真实资金授权。
              {activeDraft ? ' 授权草案已生成，下一步请在真实资金授权区确认本次授权。' : ''}
            </div>
          ) : (
            <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300">
              当前风险确认仍是本地勾选。全部勾选后可写入后端，并生成等待 Owner 授权的草案。
            </div>
          )}
          {!riskMetadataComplete ? (
            <button
              type="button"
              onClick={submitBackendMetadata}
              disabled={!canPersistMetadata || submittingMetadata}
              className={`mt-4 flex w-full items-center justify-center gap-2 rounded-xl px-5 py-3 text-sm font-bold transition ${
                canPersistMetadata && !submittingMetadata
                  ? 'bg-slate-950 text-white hover:bg-slate-800 dark:bg-slate-100 dark:text-slate-950 dark:hover:bg-white'
                  : 'cursor-not-allowed bg-slate-300 text-white dark:bg-slate-700 dark:text-slate-300'
              }`}
            >
              <ShieldCheck className="h-4 w-4" />
              {persistedAcknowledgement ? '生成授权草案' : '后端记录风险确认并生成授权草案'}
            </button>
          ) : null}
          {submitError ? (
            <p className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-300">
              {submitError}
            </p>
          ) : null}
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
          <div className="mb-4 flex items-center gap-3">
            <StepBadge value="3" />
            <div>
              <h3 className="text-xl font-bold text-slate-950 dark:text-slate-50">真实资金授权</h3>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">我现在能否点击授权：只看风险确认、授权草案、授权范围和是否已授权。</p>
            </div>
          </div>
          {renderLiveAuthorizationButton('mb-4')}
          <div className="space-y-3">
            {metadataStatusRows.map((row) => (
              <AuthorizationStatusLine key={row.label} label={row.label} value={row.value} tone={row.tone} />
            ))}
          </div>
          {activeDraft ? (
            <div className="mt-4 rounded-lg border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-800 dark:border-teal-900/50 dark:bg-teal-950/30 dark:text-teal-300">
              授权草案已生成：{activeDraft.draft_id}。状态为 pending_owner_live_authorization；不会下单，不会创建 live ExecutionIntent。
            </div>
          ) : (
            <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
              尚未生成后端授权草案。风险确认写入后端后，草案会保持等待真实资金授权。
            </div>
          )}
          <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
            风险确认 ≠ 真实资金授权；真实资金授权 ≠ 立即下单。授权后仍需最终硬安全检查。
          </div>
          {persistedLiveAuthorization ? (
            <div className="mb-3 rounded-lg border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-800 dark:border-teal-900/50 dark:bg-teal-950/30 dark:text-teal-300">
              已授权这一次真实小额试验，等待最终硬安全检查。尚未创建执行计划，尚未下单。
            </div>
          ) : null}
          {activationError ? (
            <p className="mb-3 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-300">
              {activationError}
            </p>
          ) : null}
          <p className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300">
            {persistedLiveAuthorization
              ? '真实资金授权已记录，但它不是执行计划或订单；最终硬安全检查仍未完成。'
              : activationBlockers.length
                ? activationBlockers.join('；')
                : '可以记录 Owner 对这一次 bounded live trial 的显式授权。记录后仍不会下单。'}
          </p>
          {!persistedLiveAuthorization ? renderLiveAuthorizationButton('mb-3') : null}
          {activationBlockers.length && !persistedLiveAuthorization ? (
            <div className="mb-3 rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm dark:border-slate-800 dark:bg-slate-900">
              <p className="mb-2 font-bold text-slate-900 dark:text-slate-100">暂不能授权真实资金，还差：</p>
              <ol className="list-decimal space-y-1 pl-5 text-slate-700 dark:text-slate-300">
                {activationBlockers.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ol>
            </div>
          ) : null}
          <Link
            to="/strategy-candidates"
            className="flex w-full items-center justify-center rounded-xl border border-slate-300 px-5 py-3 font-bold text-slate-800 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-100 dark:hover:bg-slate-900"
          >
            返回重新选候选
          </Link>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
          <div className="mb-3 flex items-center gap-2">
            <HelpCircle className="h-5 w-5" />
            <h3 className="font-bold text-slate-950 dark:text-slate-50">为什么按钮是灰色的？</h3>
          </div>
          <p className="text-sm leading-6 text-slate-600 dark:text-slate-300">
            {persistedLiveAuthorization
              ? '按钮已完成本次授权记录，但授权记录不是订单，也不会自动创建执行计划。'
              : activationBlockers.length
                ? activationBlockers.join('；')
                : '真实资金授权只记录本次 bounded live trial 的 Owner 授权，后续仍需最终硬安全检查。'}
          </p>
        </section>
      </section>

      <details className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950" open={Boolean(persistedLiveAuthorization)}>
        <summary className="cursor-pointer text-lg font-bold text-slate-950 dark:text-slate-50">授权后执行前仍需通过</summary>
        <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
          这些状态只决定是否能进入执行边界，不决定上面的 Owner 授权按钮是否可点击。
        </p>
        <div className="mt-4 overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800">
          {confirmation.gates.map((gate) => (
            <div key={gate.label} className="grid grid-cols-[1fr_auto] border-b border-slate-200 px-4 py-3 text-sm last:border-b-0 dark:border-slate-800">
              <span className="text-slate-700 dark:text-slate-300">{gate.label}</span>
              <span className={`inline-flex items-center gap-2 font-bold ${gate.tone === 'teal' ? 'text-emerald-600' : gate.tone === 'rose' ? 'text-rose-600' : 'text-amber-600'}`}>
                {gate.tone === 'teal' ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
                {gate.result}
              </span>
            </div>
          ))}
        </div>
        <div className="mt-4">
          <FinalGateReadModelPanel bridge={data.bnbLiveExecutionBridge} />
        </div>
      </details>

      <details className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
        <summary className="cursor-pointer text-lg font-bold text-slate-950 dark:text-slate-50">测试网验证结果</summary>
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-5">
          {confirmation.testnet.map((item) => (
            <div key={item.label} className="flex items-center justify-center gap-2 rounded-xl border border-slate-200 px-4 py-4 text-sm dark:border-slate-800">
              {item.result === '通过'
                ? <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                : <AlertCircle className="h-4 w-4 text-amber-600" />}
              <span className="font-bold text-slate-950 dark:text-slate-50">{item.label}</span>
              <span className="text-slate-500">{item.result}</span>
            </div>
          ))}
        </div>
      </details>

      <details className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
        <summary className="cursor-pointer text-lg font-bold text-slate-950 dark:text-slate-50">其他载体 / 预算基础（非本次授权）</summary>
        <div className="mt-4">
          <CarrierExpansionBudgetPanel
            expansion={data.secondCarrierExpansion}
            budget={data.budgetAuthorizationFoundation}
          />
        </div>
      </details>

      <TechnicalDetails data={{ trialConfirmation: confirmation, selectedCarrierId, localRiskAcknowledgements: localAcknowledgements, backendAcknowledgement: persistedAcknowledgement, backendDraft: activeDraft, liveAuthorization: persistedLiveAuthorization, ownerTrialFlow: data.ownerTrialFlow, bnbLiveExecutionBridge: data.bnbLiveExecutionBridge, rawGovernance: data.strategyTrialGovernance }} />
    </PageShell>
  );
}

function AuthorizationStatusLine({ label, value, tone }: { label: string; value: string; tone: Tone }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-xl border border-slate-200 px-4 py-3 text-sm dark:border-slate-800">
      <span className="font-semibold text-slate-700 dark:text-slate-300">{label}</span>
      <StatePill tone={tone}>{value}</StatePill>
    </div>
  );
}

function FinalGateReadModelPanel({ bridge }: { bridge: BnbLiveExecutionBridgeResponse | null }) {
  const gate = bridge?.final_gate_read_model || null;
  const authorization = bridge?.authorization_state || null;
  const persistence = gate?.persistence_readiness || null;
  const preview = bridge?.execution_plan_preview || null;
  const authorizedLabel = authorization?.exists && authorization.live_authorized
    ? '已授权但尚未执行'
    : '尚未记录 Owner 授权';
  const gateLabel = gate
    ? gate.result === 'passed' ? '最终硬安全检查通过（仅预览）' : '等待最终硬安全检查'
    : '等待最终硬安全检查';
  const boundaryLabel = gate?.execution_boundary_status === 'dry_run_reached_execution_boundary'
    ? '已到达执行边界预览'
    : '阻断在执行边界之前';

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <StepBadge value="3C" />
          <div>
            <h3 className="text-xl font-bold text-slate-950 dark:text-slate-50">最终硬安全检查</h3>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Owner 可见的最终 gate 状态；这里不会创建执行计划或订单。</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatePill tone={authorization?.exists ? 'teal' : 'amber'}>{authorizedLabel}</StatePill>
          <StatePill tone={gate?.result === 'passed' ? 'teal' : 'amber'}>{gateLabel}</StatePill>
        </div>
      </div>

      <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-5">
        <ReviewCard title="执行边界" value={bridge ? boundaryLabel : '数据未接入'} />
        <ReviewCard title="运行时安全" value={gate ? runtimeSafetyCopy(gate.runtime_safety_state) : '数据未接入'} />
        <ReviewCard title="执行计划" value={gate?.no_executable_execution_intent_created ? '尚未创建执行计划' : '状态异常'} />
        <ReviewCard title="订单" value={gate?.no_order_created ? '尚未下单' : '状态异常'} />
        <ReviewCard title="权限" value={gate?.no_permission_granted ? '未授予执行/下单权限' : '状态异常'} />
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <GateFactTile label="Startup Guard" fact={gate?.startup_guard} />
        <GateFactTile label="GKS" fact={gate?.gks} />
        <GateFactTile label="账户事实新鲜度" fact={gate?.account_facts} />
        <GateFactTile label="BNB 持仓" fact={gate?.bnb_position} />
        <GateFactTile label="BNB 挂单" fact={gate?.bnb_open_order} />
        <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
          <p className="text-xs font-bold uppercase text-slate-500">Persistence</p>
          <div className="mt-3 space-y-2 text-sm">
            <PersistenceLine label="execution_intents" ready={persistence?.execution_intents} />
            <PersistenceLine label="orders" ready={persistence?.orders} />
            <PersistenceLine label="result/review logging" ready={persistence?.result_review_logging} />
          </div>
        </div>
      </div>

      {preview ? (
        <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-900">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-xs font-bold uppercase text-slate-500">Execution Plan Preview</p>
              <h4 className="mt-1 text-base font-bold text-slate-950 dark:text-slate-50">执行计划预览</h4>
            </div>
            <div className="flex flex-wrap gap-2">
              <StatePill tone="amber">仅预览，不可执行</StatePill>
              <StatePill tone={preview.status === 'preview_ready' ? 'teal' : 'amber'}>{planPreviewStatusCopy(preview.status)}</StatePill>
            </div>
          </div>

          <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">仅展示最终门通过后系统会准备的动作；不会创建执行计划或订单。</p>
          <div className="grid grid-cols-1 gap-3 text-sm md:grid-cols-2 xl:grid-cols-3">
            <PreviewLine label="授权 / 草稿" value={`${preview.authorization_id || '未接入'} / ${preview.draft_id || '未接入'}`} />
            <PreviewLine label="Carrier" value={preview.carrier_id} />
            <PreviewLine label="交易对 / 方向" value={`${preview.symbol} / ${preview.side === 'long' ? '多' : '空'}`} />
            <PreviewLine label="最大名义本金" value={`${preview.max_notional} USDT`} />
            <PreviewLine label="数量 / 杠杆" value={`${preview.quantity} / ${preview.leverage}x`} />
            <PreviewLine label="入场" value={`${preview.entry_order.order_type.toUpperCase()}，最终门通过后才允许进入边界`} />
            <PreviewLine label="保护计划" value={`单止盈 + 止损；TP ${preview.protection_plan.take_profit_quantity} / SL ${preview.protection_plan.stop_loss_quantity}`} />
            <PreviewLine label="记录路径" value={preview.expected_record_path.join(' -> ')} />
            <PreviewLine label="复盘状态" value={preview.expected_review_state} />
          </div>
          <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">保护挂载失败处理：{preview.cleanup_behavior_if_protection_attach_fails}</p>
          <p className="mt-2 text-sm font-semibold text-slate-700 dark:text-slate-200">尚未创建执行计划，尚未下单，未授予执行/下单权限。</p>
        </div>
      ) : null}

      <details className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm dark:border-slate-800 dark:bg-slate-900">
        <summary className="cursor-pointer font-bold text-slate-800 dark:text-slate-100">查看技术 blocker codes</summary>
        <div className="mt-3 flex flex-wrap gap-2">
          {(gate?.exact_blockers.length ? gate.exact_blockers : ['no_blocker_codes']).map((code) => (
            <StatePill key={code} tone={gate?.exact_blockers.length ? 'rose' : 'teal'}>{code}</StatePill>
          ))}
        </div>
      </details>
    </section>
  );
}

function PreviewLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-lg bg-white px-3 py-2 dark:bg-slate-950">
      <p className="text-xs font-semibold text-slate-500">{label}</p>
      <p className="mt-1 break-words font-semibold text-slate-900 dark:text-slate-100">{value}</p>
    </div>
  );
}

function GateFactTile({ label, fact }: { label: string; fact?: BnbLiveExecutionBridgeResponse['final_gate_read_model']['startup_guard'] }) {
  const displayState = fact ? gateStateCopy(fact.state) : '数据未接入';
  const tone: Tone = !fact ? 'amber' : fact.state === 'clear' ? 'teal' : fact.state === 'missing' || fact.state === 'unavailable' ? 'amber' : 'rose';
  return (
    <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="text-xs font-bold uppercase text-slate-500">{label}</p>
        <StatePill tone={tone}>{displayState}</StatePill>
      </div>
      <p className="text-sm text-slate-600 dark:text-slate-300">{fact ? `source: ${fact.source}` : '后端 dry-run read model 未接入。'}</p>
    </div>
  );
}

function PersistenceLine({ label, ready }: { label: string; ready?: boolean }) {
  return (
    <div className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-900/80">
      <span className="text-slate-600 dark:text-slate-300">{label}</span>
      <StatePill tone={ready ? 'teal' : ready === false ? 'rose' : 'amber'}>{ready === undefined ? '未接入' : ready ? 'ready' : 'missing'}</StatePill>
    </div>
  );
}

function gateStateCopy(state: string) {
  const copy: Record<string, string> = {
    clear: '已通过',
    unavailable: '不可用',
    missing: '未上报',
    blocked: '阻断',
    stale: '已过期',
    conflict: '有冲突',
    not_armed: '未 armed',
    not_started: '未启动',
  };
  return copy[state] || state;
}

function runtimeSafetyCopy(state: string) {
  const copy: Record<string, string> = {
    clear: '已通过',
    startup_guard_not_started: '启动保护未启动',
    startup_guard_not_armed: '启动保护未 armed',
    startup_guard_blocked: '启动保护阻断',
    startup_guard_unavailable: '启动保护不可用',
    startup_guard_missing: '启动保护未上报',
    gks_unavailable: 'GKS 不可用',
    gks_blocked: 'GKS 阻断',
  };
  return copy[state] || state;
}

function planPreviewStatusCopy(status: string) {
  const copy: Record<string, string> = {
    preview_ready: '预览可生成',
    preview_blocked_by_hard_gates: '硬安全门阻断，仅展示预览',
    preview_unavailable_invalid_scope: '授权范围不匹配',
  };
  return copy[status] || status;
}

function CarrierExpansionBudgetPanel({
  expansion,
  budget,
}: {
  expansion: SecondCarrierExpansionResponse | null;
  budget: MultiCarrierBudgetAuthorizationCurrentResponse | null;
}) {
  const secondCarrier = expansion?.carriers.find((carrier) => carrier.carrier_id === expansion.selected_second_carrier_id) || null;
  const budgetAuthorization = budget?.latest_budget_authorization || null;
  const budgetCarrierIds = budgetAuthorization?.allowed_carriers.map((carrier) => carrier.carrier_id) || [];
  const disabledState = budget?.disabled_execution_state || expansion?.non_permissions || {};

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <StepBadge value="4B" />
          <h3 className="text-xl font-bold text-slate-950 dark:text-slate-50">Second Carrier / Budget</h3>
        </div>
        <StatePill tone="slate">non-live metadata</StatePill>
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_0.9fr]">
        <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <StatePill tone={secondCarrier ? 'teal' : 'amber'}>
              {secondCarrier ? secondCarrier.carrier_id : '数据未接入'}
            </StatePill>
            <StatePill tone="amber">
              {secondCarrier?.testnet_rehearsal_gap_summary.length ? 'rehearsal gap' : 'no rehearsal data'}
            </StatePill>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <TrialFact label="Family" value={secondCarrier?.strategy_family || '数据未接入'} />
            <TrialFact label="Symbol / Side" value={secondCarrier ? `${secondCarrier.runtime_symbol} ${secondCarrier.side}` : '数据未接入'} />
            <TrialFact label="Risk cap" value={secondCarrier ? `${secondCarrier.risk_cap_draft.per_carrier_cap} USDT` : '数据未接入'} />
            <TrialFact label="Protection" value={secondCarrier?.protection_feasibility.protection_plan_type || '数据未接入'} />
          </div>
          <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
            {secondCarrier?.regime_fit || 'Second carrier bootstrap data is unavailable.'}
          </p>
        </div>

        <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <StatePill tone={budgetAuthorization ? 'teal' : 'amber'}>
              {budgetAuthorization ? budgetAuthorization.status : 'no PG budget object'}
            </StatePill>
            <StatePill tone="slate">auto off</StatePill>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <TrialFact label="Budget ID" value={budgetAuthorization?.budget_authorization_id || '未创建'} />
            <TrialFact label="Allowed carriers" value={budgetCarrierIds.length ? budgetCarrierIds.join(', ') : (budget?.eligible_carrier_ids || []).join(', ') || '数据未接入'} />
            <TrialFact label="Global budget" value={budgetAuthorization ? `${budgetAuthorization.global_budget} USDT` : '未创建'} />
            <TrialFact label="Daily loss" value={budgetAuthorization ? `${budgetAuthorization.daily_loss_limit} USDT` : '未创建'} />
          </div>
          <div className="mt-3 grid grid-cols-1 gap-2 text-sm sm:grid-cols-3">
            {[
              { label: 'live_ready', value: disabledState.live_ready },
              { label: 'auto_execution', value: disabledState.auto_execution_enabled },
              { label: 'order_created', value: disabledState.order_created },
            ].map(({ label, value }) => (
              <div key={label} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-900">
                <span className="text-slate-600 dark:text-slate-300">{label}</span>
                <span className="font-bold text-slate-950 dark:text-slate-50">{String(Boolean(value))}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

export function StrategyGroupsV2() {
  const [selectedGroupId, setSelectedGroupId] = useState('MI-001');
  const { data, error } = useConsoleData();
  if (error) return <ErrorState error={error} />;
  if (!data) return <Loading label="加载策略组..." />;

  const rows = buildStrategyRows(data);
  const { primaryShelf, secondaryShelf, allShelf, apiUnavailable } = strategyGroupShelves(data);
  const shelf = allShelf;
  const selectedGroup = shelf.find((item) => item.strategy_group_id === selectedGroupId) || shelf[0]!;
  const carrierDecision = carrierDecisionView(data);
  return (
    <PageShell title="策略组" subtitle="StrategyFamily / Carrier 货架。这里只用于 Owner 观察、比较和复盘，不会自动选择策略。">
      {apiUnavailable ? (
        <section className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 shadow-sm dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300">
          display_model_only / api_unavailable：当前使用前端回退模型。回退模型不是 runtime source of truth，也不授予任何执行或订单权限。
        </section>
      ) : null}

      <StrategyShelfHero
        selectedGroup={selectedGroup}
        primaryCount={primaryShelf.length}
        secondaryCount={secondaryShelf.length}
      />

      <CarrierHierarchyPanel view={carrierDecision} />

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="space-y-5">
          <ShelfSection
            title="主策略族"
            subtitle="MI / VI / CPM / TB / PC / VB。BNB 只是首个 Carrier，不是全部架构。"
            items={primaryShelf}
            selectedGroupId={selectedGroup.strategy_group_id}
            onSelect={setSelectedGroupId}
          />
          <ShelfSection
            title="扩展观察层"
            subtitle="MR/RB 与 Tier 1 数据族保持可见，但未 admission。"
            items={secondaryShelf}
            selectedGroupId={selectedGroup.strategy_group_id}
            onSelect={setSelectedGroupId}
          />
        </div>

        <StrategyGroupDetail item={selectedGroup} />
      </section>

      <details className="rounded-2xl border border-amber-500/15 bg-slate-950/85 shadow-lg shadow-black/20">
        <summary className="flex cursor-pointer items-center justify-between gap-3 px-5 py-4 text-sm font-bold text-slate-800 transition-colors hover:bg-slate-900/70 dark:text-slate-100 dark:hover:bg-slate-800/40">
          <span className="flex items-center gap-2">
            <FileSearch className="h-4 w-4 text-indigo-500" />
            证据与技术面板
          </span>
          <span className="text-xs font-medium text-slate-400">默认折叠，不影响 Owner 首屏判断</span>
        </summary>
        <div className="space-y-5 border-t border-slate-100 p-5 ">
          <section className="rounded-2xl border border-amber-500/15 bg-slate-950/85 p-5 shadow-lg shadow-black/20">
            <h3 className="mb-4 text-base font-bold text-slate-50">策略组列表</h3>
            <DataTable
              columns={['strategy_group_id', '策略组', '代表候选', '状态', '证据强度', '下一步']}
              rows={shelf.map((item) => [
                item.strategy_group_id,
                item.strategy_group_name,
                item.representative_candidates.join(' / '),
                <StatePill key={`${item.strategy_group_id}-status`} tone={item.status_tone}>{item.current_status}</StatePill>,
                item.evidence_summary,
                item.next_recommended_action,
              ])}
            />
          </section>

          <CandidateEvidenceComparison data={data.strategyGroupReviewability} />
          <ObservationReadinessPanel
            data={data.strategyGroupReviewability}
            liveObservation={data.liveObservation}
            caseQueue={data.observationCaseQueue}
          />
          <BnbTrialReadinessGapPanel data={data.bnbTrialGap} />
          <StrategyTrialReadinessPanel data={data.strategyTrialReadiness} />

          <DataTable
            columns={['策略组', '具体策略', '状态', '标的', '方向', '最近信号', '最近意图', '下一步']}
            rows={rows.map((row) => [
              row.group,
              row.strategy,
              <StatePill key="status" tone={row.tone}>{row.status}</StatePill>,
              row.symbol,
              row.side,
              row.signal,
              row.intent,
              row.next,
            ])}
          />

          <TechnicalDetails data={{
            strategy_group_reviewability: data.strategyGroupReviewability,
            live_observation_v1: data.liveObservation,
            strategy_group_shelf: shelf,
            families: data.families,
            decisions: data.decisions,
            bindings: data.bindings,
            mi001: data.mi001,
          }} />
        </div>
      </details>
    </PageShell>
  );
}

export function IntentsV2() {
  const { data, error } = useConsoleData();
  const { flowState } = useOwnerFlowState();
  if (error) return <ErrorState error={error} />;
  if (!data) return <Loading label="加载执行意图..." />;

  const rows = buildIntentRows(data);
  const carrierDecision = carrierDecisionView(data);
  const selectedCarrierId = flowState.selectedCarrierId || carrierDecision.carrierId;
  const selectedAcknowledgements = flowState.riskAcknowledgements[selectedCarrierId] || {};
  const backendAcknowledgedCount = data.ownerTrialFlow?.latest_acknowledgement?.carrier_id === selectedCarrierId
    ? data.ownerTrialFlow.latest_acknowledgement.acknowledged_warning_codes.length
    : 0;
  const acknowledgedCount = Math.max(Object.values(selectedAcknowledgements).filter(Boolean).length, backendAcknowledgedCount);
  const draft = data.ownerTrialFlow?.authorization_draft?.carrier_id === selectedCarrierId
    ? data.ownerTrialFlow.authorization_draft
    : null;
  const liveAuthorization = data.ownerTrialFlow?.live_authorization?.carrier_id === selectedCarrierId
    ? data.ownerTrialFlow.live_authorization
    : null;
  const noIntentText = carrierDecision.provenance.executionIntentState === 'unavailable'
    ? '执行计划状态数据未接入，无法判断是否存在真实资金执行计划。'
    : liveAuthorization
      ? 'Owner 已授权一笔 bounded live trial，但尚未创建执行计划；最终硬安全检查仍未完成 / 等待启动保护确认。执行计划不是订单，不会触发交易。'
      : draft
      ? `当前有后端授权草案 ${draft.draft_id}，但仍等待真实资金授权；没有 live ExecutionIntent，没有订单。`
      : `当前还没有真实资金执行计划，因为你尚未完成真实资金授权。当前等待确认的候选是 ${selectedCarrierId}；执行计划不是订单，不会触发交易。`;
  return (
    <PageShell title="执行计划" subtitle="这里展示策略想做什么；执行计划不是订单，不会触发交易。">
      <section className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <ReviewCard title="当前待确认候选" value={selectedCarrierId} />
        <ReviewCard title="真实资金授权" value={liveAuthorization ? '已授权，待硬检查' : draft ? '等待真实资金授权' : '尚未生成草案'} />
        <ReviewCard title={backendAcknowledgedCount ? '后端风险确认' : '本地风险确认'} value={`${acknowledgedCount} / ${data.ownerTrialFlow?.strategy_warnings.length || 5} 项`} />
      </section>
      {rows.length ? (
        <DataTable
          columns={['时间', '策略', '标的', '方向', '意图', '状态', '原因', '后续表现']}
          rows={rows}
        />
      ) : (
        <EmptyState
          icon={<Zap className="h-6 w-6" />}
          title={carrierDecision.provenance.executionIntentState === 'unavailable' ? '执行计划状态未接入' : '暂无执行计划记录'}
          subtitle={noIntentText}
        />
      )}
      <section className="rounded-2xl border border-amber-500/15 bg-slate-950/85 p-5 shadow-lg shadow-black/20">
        <div className="mb-4 flex flex-col justify-between gap-3 md:flex-row md:items-center">
          <div>
            <h3 className="text-base font-bold text-slate-50">授权链路状态</h3>
            <p className="mt-1 text-sm text-slate-400">
              {carrierDecision.provenance.executionIntentState === 'unavailable'
                ? '执行链路状态必须以后端为准；当前数据未接入，无法用于真实授权。'
                : liveAuthorization
                  ? 'Owner 已授权一笔 bounded live trial，但尚未创建执行计划；最终硬安全检查仍未完成 / 等待启动保护确认。'
                  : draft
                  ? '当前有授权草案，但尚未获得真实资金授权；当前没有 live ExecutionIntent 或订单。'
                  : '当前停在“等待授权”。只有你明确授权后，才可能进入后续链路；当前没有真实资金执行计划或订单。'}
            </p>
          </div>
          <StatePill tone={liveAuthorization ? 'teal' : 'amber'}>
            {liveAuthorization ? '已授权，等待最终硬安全检查' : humanAuthorizationState(carrierDecision.authorizationState)}
          </StatePill>
        </div>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-5">
          {['等待授权', '执行计划', '入场订单', '保护订单', '退出 / 复盘'].map((step, index) => (
            <div key={step} className="rounded-xl border border-amber-500/10 bg-slate-900/70 p-3">
              <div className="mb-2 text-xs font-bold text-amber-200/60">Step {index + 1}</div>
              <div className="text-sm font-semibold text-slate-100">{step}</div>
              <div className="mt-2">
                <StatePill tone={index === 0 ? liveAuthorization ? 'teal' : 'amber' : 'slate'}>{index === 0 ? liveAuthorization ? '已授权' : '当前' : '未创建'}</StatePill>
              </div>
            </div>
          ))}
        </div>
      </section>
      <section className="rounded-2xl border border-amber-500/15 bg-slate-950/85 p-5 shadow-lg shadow-black/20">
        <h3 className="mb-2 text-sm font-bold text-slate-100">图表复盘</h3>
        <p className="text-sm text-slate-400">TradingView 类图表稍后支持。当前仅保留只读复盘位置。</p>
      </section>
      <TechnicalDetails data={{ selectedCarrierId, localRiskAcknowledgements: selectedAcknowledgements, ownerTrialFlow: data.ownerTrialFlow, authorizationDraft: draft, liveAuthorization, evidence: data.evidence, currentCampaign: data.currentCampaign }} />
    </PageShell>
  );
}

export function AccountOrdersV2() {
  const { data, error } = useConsoleData();
  if (error) return <ErrorState error={error} />;
  if (!data) return <Loading label="加载账户订单..." />;

  const account = data.accountFacts?.account_summary || {};
  const accountFactsAvailable = Boolean(data.accountFacts);
  const unknown = data.accountFacts?.unknown_unmanaged_counts || {};
  const positions = accountFactsAvailable ? data.accountFacts?.positions || [] : [];
  const openOrders = accountFactsAvailable ? data.accountFacts?.open_orders || [] : [];
  const abnormal = accountFactsAvailable ? Number(unknown.orders || 0) + Number(unknown.positions || 0) : null;
  const carrierDecision = carrierDecisionView(data);
  const bnbPositions = recordsForSymbol(positions, 'BNB');
  const bnbOrders = recordsForSymbol(openOrders, 'BNB');
  const accountUnavailable = '账户事实数据未接入';

  return (
    <PageShell title="账户订单" subtitle="当前只读取账户信息，不提供交易操作，禁止下单。">
      <section className="rounded-2xl border border-amber-500/15 bg-slate-950/85 p-5 shadow-lg shadow-black/20">
        <div className="mb-4 flex flex-col justify-between gap-3 md:flex-row md:items-center">
          <div>
            <h3 className="text-base font-bold text-slate-50">当前候选账户上下文</h3>
            <p className="mt-1 text-sm text-slate-400">
              {carrierDecision.carrierId} 只用于只读核对。这里显示 BNB 持仓、挂单、账户事实和对账状态，不提供交易动作。
            </p>
          </div>
          <StatePill tone={carrierDecision.pendingOwnerLiveAuthorization ? 'amber' : 'slate'}>{humanAuthorizationState(carrierDecision.authorizationState)}</StatePill>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
          <ShelfMiniFact label="Carrier" value={carrierDecision.carrierId} />
          <ShelfMiniFact label="BNB 持仓" value={accountFactsAvailable ? bnbPositions.length ? `${bnbPositions.length} 条` : '后端确认暂无 BNB 持仓' : accountUnavailable} />
          <ShelfMiniFact label="BNB 挂单" value={accountFactsAvailable ? bnbOrders.length ? `${bnbOrders.length} 条` : '后端确认暂无 BNB 挂单' : accountUnavailable} />
          <ShelfMiniFact label="Reconciliation" value={accountFactsAvailable ? String(recordAt(data.accountFacts?.reconciliation_status, 'status').status || data.accountFacts?.reconciliation_status?.status || '暂未上报') : accountUnavailable} />
          <ShelfMiniFact label="source" value={data.accountFacts?.source || '暂未上报'} />
          <ShelfMiniFact label="truth level" value={data.accountFacts?.truth_level || '暂未上报'} />
          <ShelfMiniFact label="facts freshness" value={data.accountFacts?.generated_at_ms ? new Date(data.accountFacts.generated_at_ms).toISOString() : '暂未上报'} />
          <ShelfMiniFact label="reconciled at" value={data.accountFacts?.reconciliation_checked_at_ms ? new Date(data.accountFacts.reconciliation_checked_at_ms).toISOString() : '暂未上报'} />
        </div>
      </section>

      <section className="rounded-2xl border border-amber-500/15 bg-slate-950/85 p-6 shadow-lg shadow-black/20">
        <div className="grid grid-cols-1 gap-6 md:grid-cols-4 md:gap-8">
          <Metric bordered label="总权益" value={accountFactsAvailable ? withUsdt(firstText(account.total_equity, account.equity)) : accountUnavailable} />
          <Metric bordered label="可用余额" value={accountFactsAvailable ? withUsdt(firstText(account.available_balance, account.available_margin)) : accountUnavailable} />
          <Metric bordered label="保证金占用" value={accountFactsAvailable ? withUsdt(firstText(account.margin_balance, account.available_margin)) : accountUnavailable} />
          <Metric label="未实现盈亏" value={accountFactsAvailable ? withUsdt(firstText(account.unrealized_pnl, account.unrealized_profit)) : accountUnavailable} />
        </div>
      </section>

      <section className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <RecordPanel title="持仓" items={positions} empty={accountFactsAvailable ? '后端确认暂无持仓' : accountUnavailable} />
        <RecordPanel title="挂单" items={openOrders} empty={accountFactsAvailable ? '后端确认暂无挂单' : accountUnavailable} />
      </section>

      <section className="rounded-2xl border border-amber-500/15 bg-slate-950/85 p-6 shadow-lg shadow-black/20">
        <h3 className="mb-2 text-sm font-bold text-slate-100">异常敞口</h3>
        <div className={toneBox(abnormal === null || abnormal > 0 ? 'rose' : 'teal')}>
          <span className="h-2 w-2 flex-shrink-0 rounded-full bg-current" />
          {abnormal === null ? '账户事实数据未接入，无法判断异常敞口。' : abnormal > 0 ? `发现 ${abnormal} 个异常敞口` : '后端确认未发现异常敞口。'}
        </div>
      </section>

      <TechnicalDetails data={{
        source: data.accountFacts?.source,
        truth_level: data.accountFacts?.truth_level,
        reconciliation: data.accountFacts?.reconciliation_status,
        unknown_exposure: unknown,
        connection_health: data.accountFacts?.connection_health,
      }} label="数据来源详情" />
    </PageShell>
  );
}

export function AnalysisV2() {
  const { data, error } = useConsoleData();
  if (error) return <ErrorState error={error} />;
  if (!data) return <Loading label="加载复盘分析..." />;

  const latestDecision = (data.decisions[0] || {}) as Record<string, unknown>;
  const latestBinding = (data.bindings[0] || {}) as Record<string, unknown>;
  const carrierDecision = carrierDecisionView(data);
  return (
    <PageShell title="复盘分析" subtitle={`${carrierDecision.carrierId} 是当前候选复盘对象；复盘证据不授权真实资金执行计划或订单。`}>
      <section className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <ReviewCard title="试验前复核" value={data.reviewPacket || data.strategyTrialGovernance ? '后端已上报' : '数据未接入'} />
        <ReviewCard title="风险披露" value={latestDecision.risk_disclosure_json ? '已完成' : '暂未上报'} />
        <ReviewCard title="Owner 接受" value={firstText(latestDecision.owner_risk_acceptance_id, latestBinding.owner_risk_acceptance_id, '数据未接入')} />
      </section>

      <section className="rounded-2xl border border-amber-500/15 bg-slate-950/85 p-6 shadow-lg shadow-black/20">
        <h3 className="mb-4 flex items-center gap-2 text-base font-bold text-slate-50">
          <AlertCircle className="h-4.5 w-4.5 text-amber-500" />
          当前结论
        </h3>
        <div className="space-y-3 rounded-lg border border-slate-100 bg-slate-900/70 p-5 text-sm text-slate-700 dark:border-slate-700/50 dark:bg-slate-800/50 dark:text-slate-300">
          <p className="font-medium text-slate-50">BNB 测试网保护演练已完成；当前必须解决的问题是真实资金尚未授权。</p>
          <p>复盘证据只用于授权前检查，不创建真实资金执行计划或订单。</p>
        </div>
      </section>

      <section className="rounded-2xl border border-amber-500/15 bg-slate-950/85 p-6 shadow-lg shadow-black/20">
        <h3 className="mb-4 text-base font-bold text-slate-50">BNB 测试网证据</h3>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {carrierDecision.testnetEvidence.map(([label, value]) => (
            <ShelfMiniFact key={label} label={label} value={value} />
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-amber-500/15 bg-slate-950/85 p-6 shadow-lg shadow-black/20">
        <h3 className="mb-4 text-base font-bold text-slate-50">证据摘要</h3>
        <ul className="space-y-3">
          <EvidenceItem label="broad smoke" value={data.mi001 ? '已完成' : '暂未上报'} />
          <EvidenceItem label="Owner acceptance" value={firstText(latestDecision.owner_risk_acceptance_id, latestBinding.owner_risk_acceptance_id, '数据未接入')} />
          <EvidenceItem label="PG 注册" value={data.mi001?.source_refs.some((ref) => ref.includes('brc_')) ? '已完成' : '暂未上报'} />
          <EvidenceItem label="final review" value={data.reviewPacket || data.strategyTrialGovernance ? '后端已上报' : '数据未接入'} />
          <EvidenceItem label="trial_trade_intent evidence" value={intentEvidenceText(data)} />
          <EvidenceItem label="订单" value={carrierDecision.orderState} />
        </ul>
      </section>

      <TechnicalDetails data={{ strategyTrialGovernance: data.strategyTrialGovernance, reviewPacket: data.reviewPacket, evidence: data.evidence, decisions: data.decisions, bindings: data.bindings }} />
    </PageShell>
  );
}

export function TraceV2() {
  const [expandedNode, setExpandedNode] = useState<string | null>(null);
  const { data, error } = useConsoleData();
  if (error) return <ErrorState error={error} />;
  if (!data) return <Loading label="加载链路追踪..." />;

  const carrierDecision = carrierDecisionView(data);
  const steps = carrierDecision.timeline;

  return (
    <PageShell title="链路追踪" subtitle={`查看 ${carrierDecision.carrierId} 从观察、测试网保护演练到等待真实资金授权的完整过程。`}>
      <section className="rounded-2xl border border-amber-500/15 bg-slate-950/85 p-6 shadow-lg shadow-black/20">
        <div className="relative ml-5 space-y-10 border-l-2 border-slate-200 py-4 ">
          {steps.map((step) => (
            <div key={step.id} className="relative pl-8">
              <div className={timelineDot(step.tone)}>
                {step.tone === 'teal' ? <Check className="h-3.5 w-3.5" strokeWidth={3} /> : <AlertCircle className="h-3.5 w-3.5" />}
              </div>
              <button
                type="button"
                onClick={() => setExpandedNode((current) => current === step.id ? null : step.id)}
                className="w-full rounded-xl border border-slate-100 bg-slate-900/70 p-4 text-left transition-colors hover:bg-slate-100 dark:border-slate-700/50 dark:bg-slate-800/30 dark:hover:bg-slate-800/50"
              >
                <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
                  <div className="flex items-center gap-3">
                    <h3 className="text-base font-bold text-slate-50">{step.title}</h3>
                    <StatePill tone={step.tone}>{step.status}</StatePill>
                  </div>
                  {expandedNode === step.id ? <ChevronDown className="h-4 w-4 text-slate-400" /> : <ChevronRight className="h-4 w-4 text-slate-400" />}
                </div>
                <p className="mt-2 text-sm text-slate-400">{step.desc}</p>
                {expandedNode === step.id ? (
                  <div className="mt-4 rounded-lg border border-amber-500/15 bg-slate-950/85 p-4 dark:border-slate-700 ">
                    <p className="text-sm text-slate-600 dark:text-slate-300">
                      说明：{step.desc}
                    </p>
                    <div className="mt-4 rounded border border-slate-200 bg-slate-100/50 p-3  dark:bg-slate-950">
                      <p className="mb-1 text-[11px] font-bold uppercase text-slate-500 dark:text-slate-500">技术状态</p>
                      <p className="break-all font-mono text-xs text-amber-600 dark:text-amber-400">
                        {step.tech}
                      </p>
                    </div>
                  </div>
                ) : null}
              </button>
            </div>
          ))}
        </div>
      </section>
      <TechnicalDetails data={{
        readiness: data.readiness,
        accountFacts: data.accountFacts,
        mi001: data.mi001,
        families: data.families,
        decisions: data.decisions,
        bindings: data.bindings,
        currentCampaign: data.currentCampaign,
        reviewPacket: data.reviewPacket,
        evidence: data.evidence,
        strategyTrialGovernance: data.strategyTrialGovernance,
        operations: data.operations,
        gaps: data.gaps,
      }} />
    </PageShell>
  );
}

function useConsoleData(): ViewState {
  const { refreshCount } = useRefreshContext();
  const [state, setState] = useState<ViewState>({ data: null, error: null });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const gaps: string[] = [];
      const [
        readiness,
        accountFacts,
        mi001,
        strategyGroupReviewability,
        liveObservation,
        observationCaseQueue,
        bnbTrialGap,
        strategyTrialReadiness,
        strategyTrialGovernance,
        secondCarrierExpansion,
        budgetAuthorizationFoundation,
        ownerTrialFlow,
        bnbLiveExecutionBridge,
        families,
        decisions,
        bindings,
        currentCampaign,
        reviewPacket,
        evidence,
        operationsPayload,
      ] = await Promise.all([
        brcApi.readiness().catch((error) => {
          gaps.push(`readiness: ${message(error)}`);
          return null;
        }),
        brcApi.accountFacts().catch((error) => {
          gaps.push(`account facts: ${message(error)}`);
          return null;
        }),
        brcApi.mi001SolReadiness().catch((error) => {
          gaps.push(`MI-001: ${message(error)}`);
          return null;
        }),
        brcApi.strategyGroupReviewability().catch((error) => {
          gaps.push(`strategy group reviewability: ${message(error)}`);
          return null;
        }),
        brcApi.strategyGroupLiveObservationV1().catch((error) => {
          gaps.push(`live read-only observation v1: ${message(error)}`);
          return null;
        }),
        brcApi.strategyGroupObservationCasesV1().catch((error) => {
          gaps.push(`observation case queue v1: ${message(error)}`);
          return null;
        }),
        brcApi.mi001BnbTrialReadinessGap().catch((error) => {
          gaps.push(`MI-001 BNB trial gap: ${message(error)}`);
          return null;
        }),
        brcApi.strategyTrialReadinessV1().catch((error) => {
          gaps.push(`strategy trial readiness v1: ${message(error)}`);
          return null;
        }),
        brcApi.strategyTrialArchitectureGovernance().catch((error) => {
          gaps.push(`strategy trial architecture governance: ${message(error)}`);
          return null;
        }),
        brcApi.secondCarrierExpansion().catch((error) => {
          gaps.push(`second carrier expansion: ${message(error)}`);
          return null;
        }),
        brcApi.multiCarrierBudgetAuthorizationCurrent().catch((error) => {
          gaps.push(`budget authorization foundation: ${message(error)}`);
          return null;
        }),
        brcApi.ownerTrialFlowCurrent().catch((error) => {
          gaps.push(`owner trial flow: ${message(error)}`);
          return null;
        }),
        brcApi.bnbLiveExecutionBridgeDryRun().catch((error) => {
          gaps.push(`BNB live execution bridge dry-run: ${message(error)}`);
          return null;
        }),
        brcApi.listStrategyFamilies().catch((error) => {
          gaps.push(`strategy families: ${message(error)}`);
          return [];
        }),
        brcApi.listAdmissionDecisions().catch((error) => {
          gaps.push(`admission decisions: ${message(error)}`);
          return [];
        }),
        brcApi.listTrialBindings().catch((error) => {
          gaps.push(`trial bindings: ${message(error)}`);
          return [];
        }),
        brcApi.currentCampaign().then((payload) => payload.campaign || null).catch((error) => {
          gaps.push(`campaign: ${message(error)}`);
          return null;
        }),
        brcApi.reviewPacket().catch((error) => {
          gaps.push(`review packet: ${message(error)}`);
          return null;
        }),
        brcApi.evidence().catch((error) => {
          gaps.push(`evidence: ${message(error)}`);
          return null;
        }),
        brcApi.listOperations().catch((error) => {
          gaps.push(`operations: ${message(error)}`);
          return { operations: [] };
        }),
      ]);
      if (!cancelled) {
        setState({
          data: {
            ...EMPTY_DATA,
            readiness,
            accountFacts,
            mi001,
            strategyGroupReviewability,
            liveObservation,
            observationCaseQueue,
            bnbTrialGap,
            strategyTrialReadiness,
            strategyTrialGovernance,
            secondCarrierExpansion,
            budgetAuthorizationFoundation,
            ownerTrialFlow,
            bnbLiveExecutionBridge,
            families,
            decisions,
            bindings,
            currentCampaign,
            reviewPacket,
            evidence,
            operations: operationsPayload.operations || [],
            gaps,
          },
          error: null,
        });
      }
    }
    load().catch((error) => {
      if (!cancelled) setState({ data: null, error });
    });
    return () => {
      cancelled = true;
    };
  }, [refreshCount]);

  return state;
}

function useOwnerFlowState(defaultCarrierId = '') {
  const [flowState, setFlowState] = useState<OwnerFlowState>(() => readOwnerFlowState(defaultCarrierId));

  useEffect(() => {
    if (!flowState.selectedCarrierId && defaultCarrierId) {
      setFlowState((current) => ({ ...current, selectedCarrierId: defaultCarrierId }));
    }
  }, [defaultCarrierId, flowState.selectedCarrierId]);

  const updateFlowState = (updater: (current: OwnerFlowState) => OwnerFlowState) => {
    setFlowState((current) => {
      const next = updater(current);
      writeOwnerFlowState(next);
      return next;
    });
  };

  return { flowState, updateFlowState };
}

function readOwnerFlowState(defaultCarrierId: string): OwnerFlowState {
  const fallback: OwnerFlowState = {
    marketView: DEFAULT_MARKET_VIEW,
    selectedCarrierId: defaultCarrierId,
    riskAcknowledgements: {},
  };
  try {
    const raw = window.localStorage.getItem(OWNER_FLOW_STORAGE_KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<OwnerFlowState>;
    return {
      marketView: {
        ...DEFAULT_MARKET_VIEW,
        ...(parsed.marketView || {}),
      },
      selectedCarrierId: parsed.selectedCarrierId || defaultCarrierId,
      riskAcknowledgements: parsed.riskAcknowledgements || {},
    };
  } catch {
    return fallback;
  }
}

function writeOwnerFlowState(state: OwnerFlowState) {
  try {
    window.localStorage.setItem(OWNER_FLOW_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Local persistence is best-effort UI state only.
  }
}

function PageShell({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <>
      <section className="overflow-hidden rounded-2xl border border-amber-500/20 bg-slate-950 p-6 text-white shadow-xl shadow-black/20">
        <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
          <div>
            <p className="mb-2 text-xs font-bold uppercase tracking-[0.18em] text-amber-300">Owner Console</p>
            <h2 className="text-3xl font-bold tracking-tight text-slate-50">{title}</h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-300">{subtitle}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatePill tone="teal">环境可见</StatePill>
            <StatePill tone="indigo">证据优先</StatePill>
            <StatePill tone="rose">无交易入口</StatePill>
          </div>
        </div>
      </section>
      {children}
    </>
  );
}

function Panel({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="flex h-full flex-col overflow-hidden rounded-2xl border border-amber-500/15 bg-slate-950/85 shadow-lg shadow-black/20">
      <div className="flex items-center justify-between border-b border-amber-500/10 bg-slate-900/70 px-5 py-4">
        <h3 className="text-sm font-bold text-slate-100">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  );
}

function StatusCard({ title, value, note, tone, accent }: { title: string; value: string; note: string; tone: Tone; accent?: boolean }) {
  return (
    <section className={`rounded-2xl border border-amber-500/15 bg-slate-950/85 p-5 shadow-lg shadow-black/20 ${accent ? 'border-l-4 border-l-amber-400' : ''}`}>
      <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wider text-amber-200/80">{title}</h3>
      <div className="mb-1 flex items-center gap-2 text-xl font-bold text-slate-50">
        {value}
        {tone === 'teal' ? <span className="h-2 w-2 rounded-full bg-teal-500 shadow-[0_0_8px_rgba(20,184,166,0.65)]" /> : null}
      </div>
      <StatePill tone={tone}>{note}</StatePill>
    </section>
  );
}

function Metric({ label, value, bordered }: { label: string; value: unknown; bordered?: boolean }) {
  return (
    <div className={`space-y-1 ${bordered ? "relative md:after:absolute md:after:right-[-16px] md:after:top-2 md:after:bottom-2 md:after:w-px md:after:bg-amber-500/10 md:after:content-['']" : ''}`}>
      <p className="text-xs font-medium text-slate-400">{label}</p>
      <p className="break-words text-2xl font-bold text-slate-50">{display(value)}</p>
    </div>
  );
}

function DataTable({ columns, rows, compact = false }: { columns: string[]; rows: Array<Array<React.ReactNode>>; compact?: boolean }) {
  return (
    <section className="overflow-hidden rounded-2xl border border-amber-500/15 bg-slate-950/85 shadow-lg shadow-black/20">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse text-left">
          <thead>
            <tr className="border-b border-amber-500/10 bg-slate-900/80">
              {columns.map((column) => (
                <th key={column} className={`${compact ? 'px-4 py-3 text-xs' : 'px-5 py-4 text-[13px]'} font-bold uppercase tracking-wider text-amber-200/75`}>
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-amber-500/10">
            {rows.map((row, index) => (
              <tr key={index} className="transition-colors duration-200 hover:bg-slate-900/70">
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex} className={`${compact ? 'px-4 py-3' : 'px-5 py-4'} text-sm text-slate-300`}>
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function StepBadge({ value }: { value: string }) {
  return (
    <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-800 text-sm font-bold text-white dark:bg-slate-100 dark:text-slate-950">
      {value}
    </span>
  );
}

function FlowProgress({ currentStep }: { currentStep: number }) {
  const steps = ['市场判断', '选择候选', '风险确认', '授权', '执行/复盘'];
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-950">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-5">
        {steps.map((step, index) => {
          const stepIndex = index + 1;
          const completed = stepIndex < currentStep;
          const active = stepIndex === currentStep;
          return (
            <div key={step} className="relative flex flex-col items-center text-center">
              {index > 0 ? <div className="absolute right-1/2 top-5 hidden h-px w-full bg-slate-300 md:block dark:bg-slate-700" /> : null}
              <div className={`relative z-10 flex h-10 w-10 items-center justify-center rounded-full border text-sm font-bold ${
                active
                  ? 'border-slate-800 bg-slate-800 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950'
                  : completed
                    ? 'border-slate-300 bg-slate-100 text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200'
                    : 'border-slate-300 bg-white text-slate-600 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300'
              }`}>
                {completed ? <Check className="h-4 w-4" /> : stepIndex}
              </div>
              <h3 className="mt-3 font-bold text-slate-950 dark:text-slate-50">{step}</h3>
              <p className="mt-1 text-sm text-slate-500">{active ? '当前步骤' : completed ? '已完成' : '待进行'}</p>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function FlowStepper({ currentStep }: { currentStep: number }) {
  const steps = ['市场判断', '已选候选', '风险确认', '授权草案', '执行/复盘'];
  return (
    <section className="grid grid-cols-1 gap-2 md:grid-cols-5">
      {steps.map((step, index) => {
        const active = index + 1 === currentStep;
        return (
          <div
            key={step}
            className={`flex items-center justify-center gap-3 rounded-xl border px-4 py-3 text-sm font-bold ${
              active
                ? 'border-slate-800 bg-slate-800 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950'
                : 'border-slate-300 bg-white text-slate-700 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200'
            }`}
          >
            <span className="inline-flex h-6 w-6 items-center justify-center rounded-full border border-current">{index + 1}</span>
            {step}
          </div>
        );
      })}
    </section>
  );
}

function WorkbenchCard({
  icon,
  title,
  body,
  facts,
  to,
  linkText,
  centered,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
  facts: Array<[string, string]>;
  to: string;
  linkText: string;
  centered?: boolean;
}) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
      <div className="mb-5 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100 text-slate-700 dark:bg-slate-900 dark:text-slate-200">
            {icon}
          </div>
          <h3 className="text-lg font-bold text-slate-950 dark:text-slate-50">{title}</h3>
        </div>
        <ChevronRight className="h-5 w-5 text-slate-500" />
      </div>
      <div className={centered ? 'py-4 text-center' : ''}>
        <p className="text-2xl font-bold text-slate-950 dark:text-slate-50">{body}</p>
      </div>
      <div className="mt-4 space-y-2 text-sm">
        {facts.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-4">
            <span className="text-slate-500">{label}</span>
            <span className="font-medium text-slate-800 dark:text-slate-200">{value}</span>
          </div>
        ))}
      </div>
      <Link to={to} className="mt-5 inline-flex items-center gap-2 text-sm font-bold text-slate-800 hover:text-slate-950 dark:text-slate-200 dark:hover:text-white">
        {linkText} <ChevronRight className="h-4 w-4" />
      </Link>
    </section>
  );
}

function PlainListPanel({
  icon,
  title,
  items,
  link,
  linkText,
}: {
  icon: React.ReactNode;
  title: string;
  items: string[];
  link: string;
  linkText: string;
}) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
      <div className="mb-4 flex items-center gap-3">
        {icon}
        <h3 className="text-lg font-bold text-slate-950 dark:text-slate-50">{title}</h3>
      </div>
      <ul className="space-y-3 text-sm leading-6 text-slate-700 dark:text-slate-300">
        {items.map((item) => (
          <li key={item} className="flex gap-3">
            <span className="mt-2 h-1.5 w-1.5 rounded-full bg-slate-700 dark:bg-slate-300" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
      <Link to={link} className="mt-4 inline-flex items-center gap-2 text-sm font-bold text-slate-800 hover:text-slate-950 dark:text-slate-200 dark:hover:text-white">
        {linkText} <ChevronRight className="h-4 w-4" />
      </Link>
    </section>
  );
}

function SegmentedControl({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-2">
      <p className="text-sm font-bold text-slate-800 dark:text-slate-100">{label}</p>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => onChange(option)}
            className={`rounded-lg border px-4 py-2 text-sm font-medium transition ${
              value === option
                ? 'border-slate-800 bg-slate-800 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950'
                : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-900'
            }`}
          >
            {option}
          </button>
        ))}
      </div>
    </div>
  );
}

type RecommendedCandidate = {
  id: string;
  name: string;
  category: string;
  summary: string;
  reason: string;
  status: string;
  risk: string;
  source: DataSource;
  sourceLabel: string;
  action: 'confirm' | 'observe' | 'details' | 'not_recommended';
  actionLabel: string;
};

function CandidateCard({
  candidate,
  rank,
  onConfirm,
}: {
  candidate: RecommendedCandidate;
  rank: number;
  onConfirm: (candidate: RecommendedCandidate) => void;
}) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
      <div className="mb-4 flex items-start gap-4">
        <StepBadge value={String(rank)} />
        <div className="flex min-w-0 flex-1 items-start justify-between gap-3">
          <div>
            <h3 className="text-lg font-bold text-slate-950 dark:text-slate-50">{candidate.name}</h3>
            <StatePill tone="slate">{candidate.category}</StatePill>
            <StatePill tone={candidate.source === 'sample_data' ? 'amber' : 'teal'}>{candidate.sourceLabel}</StatePill>
          </div>
        </div>
      </div>
      <p className="mb-4 text-sm leading-6 text-slate-700 dark:text-slate-300">{candidate.summary}</p>
      <div className="space-y-3 border-t border-dashed border-slate-300 pt-4 text-sm dark:border-slate-700">
        <MiniReason label="适合当前判断的原因" value={candidate.reason} />
        <MiniReason label="当前状态" value={candidate.status} dot />
        <MiniReason label="主要风险" value={candidate.risk} />
      </div>
      <button
        type="button"
        onClick={() => candidate.action === 'confirm' ? onConfirm(candidate) : undefined}
        disabled={candidate.action !== 'confirm'}
        className={`mt-5 flex h-11 w-full items-center justify-center rounded-lg border text-sm font-bold transition ${
          candidate.action === 'confirm'
            ? 'cursor-pointer border-slate-800 text-slate-900 hover:bg-slate-50 dark:border-slate-200 dark:text-slate-100 dark:hover:bg-slate-900'
            : 'cursor-not-allowed border-slate-300 bg-slate-100 text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-500'
        }`}
      >
        {candidate.actionLabel}
      </button>
      <p className="mt-3 text-xs leading-5 text-slate-500 dark:text-slate-400">
        候选建议不是执行授权，不会自动选择策略，也不会创建执行计划或订单。
      </p>
    </section>
  );
}

function MiniReason({ label, value, dot }: { label: string; value: string; dot?: boolean }) {
  return (
    <div className="grid grid-cols-[auto_1fr] gap-3">
      {dot ? <span className="mt-2 h-2 w-2 rounded-full bg-emerald-500" /> : <Info className="mt-0.5 h-4 w-4 text-slate-500" />}
      <div>
        <p className="font-bold text-slate-800 dark:text-slate-100">{label}</p>
        <p className="mt-1 text-slate-600 dark:text-slate-300">{value}</p>
      </div>
    </div>
  );
}

function PlainTerm({ term, desc }: { term: string; desc: string }) {
  return (
    <div className="mb-3 grid grid-cols-[44px_1fr] gap-4 rounded-xl border border-slate-200 p-4 last:mb-0 dark:border-slate-800">
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-900">
        <Info className="h-5 w-5" />
      </div>
      <div>
        <h4 className="font-bold text-slate-950 dark:text-slate-50">{term}</h4>
        <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-300">{desc}</p>
      </div>
    </div>
  );
}

function TrialFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[44px_1fr] gap-4 rounded-xl p-3">
      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-100 dark:bg-slate-900">
        <Star className="h-5 w-5" />
      </div>
      <div>
        <p className="text-sm text-slate-500">{label}</p>
        <p className="font-bold text-slate-950 dark:text-slate-50">{value}</p>
      </div>
    </div>
  );
}

function CarrierAuthorizationPanel({ view }: { view: CarrierDecisionView }) {
  return (
    <section className="rounded-2xl border border-amber-500/15 bg-slate-950/85 p-5 shadow-lg shadow-black/20">
      <div className="mb-5 flex flex-col justify-between gap-3 md:flex-row md:items-start">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.18em] text-amber-200/75">Carrier Trial Authorization</p>
          <h3 className="text-xl font-bold text-slate-50">{view.carrierId}</h3>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
            {view.strategyFamily} 是策略逻辑本身；Carrier 才是策略族 + 标的 + 方向 + 风险上限。当前 Carrier 已完成 testnet 保护演练，但仍等待 Owner live authorization。
          </p>
        </div>
        <StatePill tone="amber">{view.authorizationState}</StatePill>
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <ShelfMiniFact label="StrategyFamily" value={view.strategyFamily} />
        <ShelfMiniFact label="Carrier" value={view.carrierId} />
        <ShelfMiniFact label="Candidate" value={view.candidateId} />
        <ShelfMiniFact label="标的 / 方向" value={`${view.symbol} / ${view.side}`} />
        <ShelfMiniFact label="数量 / cap" value={`${view.quantity} / ${view.maxNotional}`} />
        <ShelfMiniFact label="杠杆 / 保护" value={`${view.leverage} / ${view.protectionPlan}`} />
        <ShelfMiniFact label="Testnet result" value={view.testnetState} />
        <ShelfMiniFact label="ExecutionIntent" value={view.executionIntentState} />
        <ShelfMiniFact label="Order" value={view.orderState} />
      </div>
      <div className="mt-4 rounded-xl border border-indigo-500/20 bg-indigo-500/10 p-4 text-sm text-indigo-100">
        <span className="font-bold">Owner 主动作：</span>
        {view.primaryAction}
      </div>
    </section>
  );
}

function DecisionBoundaryPanel({ view }: { view: CarrierDecisionView }) {
  return (
    <section className="rounded-2xl border border-amber-500/15 bg-slate-950/85 p-5 shadow-lg shadow-black/20">
      <h3 className="mb-2 text-base font-bold text-slate-50">阻断与警告</h3>
      <p className="mb-4 text-sm leading-6 text-slate-400">
        Warning 可以被 Owner 确认；Hard Blocker 不能绕过。确认 Warning 不等于 live authorization。
      </p>
      <div className="space-y-4">
        <ChipBlock
          label={`Hard Blocker (${view.hardBlockerCount})`}
          values={view.hardBlockers.length ? view.hardBlockers : ['none_reported']}
          tone={view.hardBlockers.length ? 'rose' : 'teal'}
        />
        <ChipBlock
          label={`Strategy Warning (${view.warningCount})`}
          values={view.strategyWarnings.length ? view.strategyWarnings : ['none_reported']}
          tone={view.strategyWarnings.length ? 'amber' : 'teal'}
        />
        <ChipBlock
          label="当前不可做"
          values={['create live ExecutionIntent', 'place order', 'start runtime', 'auto-select strategy']}
          tone="rose"
        />
      </div>
    </section>
  );
}

function CarrierHierarchyPanel({ view }: { view: CarrierDecisionView }) {
  return (
    <section className="rounded-2xl border border-amber-500/15 bg-slate-950/85 p-5 shadow-lg shadow-black/20">
      <div className="mb-4 flex flex-col justify-between gap-3 md:flex-row md:items-center">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.18em] text-amber-200/75">StrategyFamily → Carrier</p>
          <h3 className="text-xl font-bold text-slate-50">MI-001 Carrier 架构</h3>
          <p className="mt-2 text-sm leading-6 text-slate-300">
            BNB 是 first execution Carrier；SOL 是同一 StrategyFamily 下的历史主链路候选。BNB 不是整个架构。
          </p>
        </div>
        <StatePill tone="rose">无交易入口</StatePill>
      </div>
      <DataTable
        compact
        columns={['StrategyFamily', 'Carrier', '角色', '状态', '证据', '授权']}
        rows={[
          [
            view.strategyFamily,
            view.carrierId,
            <StatePill key="role" tone="teal">first execution Carrier</StatePill>,
            'pending Owner live authorization',
            view.testnetState,
            'live_ready=false',
          ],
          [
            view.strategyFamily,
            'MI-001-SOL-LONG',
            <StatePill key="role" tone="slate">same family candidate</StatePill>,
            'historical primary chain evidence',
            'final review / PG metadata available',
            'not current live authorization target',
          ],
        ]}
      />
    </section>
  );
}

function StrategyShelfHero({
  selectedGroup,
  primaryCount,
  secondaryCount,
}: {
  selectedGroup: StrategyGroupShelfItem;
  primaryCount: number;
  secondaryCount: number;
}) {
  const hardBlockers = selectedGroup.main_blockers?.length ? selectedGroup.main_blockers : ['当前未授予执行 / 下单 / runtime start 权限'];
  const warnings = selectedGroup.confidence_flags?.length ? selectedGroup.confidence_flags : selectedGroup.key_risks.slice(0, 3);
  return (
    <section className="grid grid-cols-1 gap-4 xl:grid-cols-[1.5fr_1fr]">
      <div className="rounded-2xl border border-amber-500/15 bg-slate-950/85 p-5 shadow-lg shadow-black/20">
        <div className="mb-5 flex flex-col justify-between gap-4 md:flex-row md:items-start">
          <div>
            <p className="mb-2 text-xs font-bold uppercase tracking-[0.18em] text-indigo-500 dark:text-indigo-400">Owner 决策货架</p>
            <h3 className="text-2xl font-bold text-slate-50">先看策略族，再看 Carrier</h3>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
              当前页面用于比较 StrategyFamily / Carrier 的证据、风险和下一步。它不是自动路由，不会启动 trial，也不会创建执行指令或订单。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatePill tone="teal">实盘只读</StatePill>
            <StatePill tone="indigo">记录意图</StatePill>
            <StatePill tone="rose">禁止下单</StatePill>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StrategyInsightCard label="主策略族" value={`${primaryCount} 个`} note="可比较，不自动选择" />
          <StrategyInsightCard label="扩展观察" value={`${secondaryCount} 个`} note="未 admission" />
          <StrategyInsightCard label="当前选中" value={selectedGroup.strategy_group_id} note={selectedGroup.current_status} />
          <StrategyInsightCard label="下一步" value="Owner 判断" note="查看证据 / 风险 / 阻断" />
        </div>
      </div>

      <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-5 shadow-lg shadow-black/20">
        <div className="mb-4 flex items-center gap-2">
          <AlertCircle className="h-5 w-5 text-amber-300" />
          <h3 className="text-base font-bold text-amber-100">阻断与警告分开看</h3>
        </div>
        <div className="space-y-4">
          <div>
            <p className="mb-2 text-xs font-bold text-amber-200">Hard Blocker</p>
            <div className="flex flex-wrap gap-1.5">
              {hardBlockers.slice(0, 3).map((blocker) => (
                <StatePill key={blocker} tone="rose">{blocker}</StatePill>
              ))}
            </div>
          </div>
          <div>
            <p className="mb-2 text-xs font-bold text-amber-200">Warning</p>
            <div className="flex flex-wrap gap-1.5">
              {warnings.slice(0, 3).map((warning) => (
                <StatePill key={warning} tone="amber">{warning}</StatePill>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function StrategyInsightCard({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="rounded-xl border border-amber-500/10 bg-slate-900/70 p-4">
      <p className="text-xs font-medium text-slate-400">{label}</p>
      <p className="mt-2 truncate text-xl font-bold text-slate-50">{value}</p>
      <p className="mt-1 truncate text-xs text-slate-400">{note}</p>
    </div>
  );
}

function ShelfSection({
  title,
  subtitle,
  items,
  selectedGroupId,
  onSelect,
}: {
  title: string;
  subtitle: string;
  items: StrategyGroupShelfItem[];
  selectedGroupId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <section>
      <div className="mb-3">
        <h3 className="text-sm font-bold text-slate-100">{title}</h3>
        <p className="mt-1 text-xs text-slate-400">{subtitle}</p>
      </div>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {items.map((item) => (
          <StrategyGroupCard
            key={item.strategy_group_id}
            item={item}
            selected={selectedGroupId === item.strategy_group_id}
            onSelect={onSelect}
          />
        ))}
      </div>
    </section>
  );
}

function StrategyGroupCard({
  item,
  selected,
  onSelect,
}: {
  item: StrategyGroupShelfItem;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(item.strategy_group_id)}
      className={`cursor-pointer rounded-2xl border bg-slate-950/85 p-4 text-left shadow-lg shadow-black/20 transition-colors duration-200 hover:bg-slate-900/90 focus:outline-none focus:ring-2 focus:ring-amber-400/50 ${
        selected
          ? 'border-amber-400/60 ring-2 ring-purple-500/25'
          : 'border-amber-500/15'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold text-amber-200/75">{item.strategy_group_id}</p>
          <h3 className="mt-1 text-base font-bold text-slate-50">{item.strategy_group_name}</h3>
        </div>
        <StatePill tone={item.status_tone}>{item.shelf_section === 'primary' ? '主策略族' : '扩展层'}</StatePill>
      </div>
      <p className="mt-3 text-sm text-slate-300">{item.plain_language_summary}</p>
      <div className="mt-4 grid grid-cols-1 gap-2 text-xs text-slate-400">
        <ShelfMiniFact label="吃什么行情" value={item.market_regime_it_eats} />
        <ShelfMiniFact label="下一步" value={item.next_recommended_action} />
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {item.representative_candidates.slice(0, 4).map((candidate) => (
          <StatePill key={candidate} tone="slate">{candidate}</StatePill>
        ))}
      </div>
    </button>
  );
}

function RecordPanel({ title, items, empty }: { title: string; items: Array<Record<string, unknown>>; empty: string }) {
  return (
    <Panel title={title}>
      {items.length ? (
        <div className="space-y-2 p-5">
          {items.slice(0, 4).map((item, index) => (
            <div key={index} className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm ">
              <span>{firstText(item.symbol, item.display_symbol, `记录 ${index + 1}`)}</span>
              <StatePill tone="slate">{firstText(item.status, item.side, '已上报')}</StatePill>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex min-h-[160px] flex-grow flex-col items-center justify-center p-6 text-sm text-slate-400">
          <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800">
            <Info className="h-4 w-4" />
          </div>
          {empty}
        </div>
      )}
    </Panel>
  );
}

function EmptyState({ icon, title, subtitle }: { icon: React.ReactNode; title: string; subtitle: string }) {
  return (
    <section className="flex flex-col items-center justify-center rounded-xl border border-amber-500/15 bg-slate-950/85 p-10 text-center shadow-sm  ">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full border border-slate-200 bg-slate-900/70 text-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-500">
        {icon}
      </div>
      <h4 className="mb-2 text-lg font-bold text-slate-100">{title}</h4>
      <p className="max-w-sm text-sm text-slate-400">{subtitle}</p>
    </section>
  );
}

function ReviewCard({ title, value }: { title: string; value: string }) {
  return (
    <section className="flex items-center gap-4 rounded-2xl border border-amber-500/15 bg-slate-950/85 p-5 shadow-lg shadow-black/20">
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-teal-50 text-teal-600 dark:bg-teal-500/10 dark:text-teal-400">
        <CheckCircle2 className="h-6 w-6" />
      </div>
      <div>
        <h3 className="mb-1 text-[13px] font-bold tracking-wider text-slate-400">{title}</h3>
        <p className="text-base font-bold text-slate-50">{value}</p>
      </div>
    </section>
  );
}

function EvidenceItem({ label, value }: { label: string; value: string }) {
  return (
    <li className="flex items-center gap-3 text-sm">
      <CheckCircle2 className="h-4 w-4 text-teal-500" />
      <span className="w-44 font-mono text-slate-400">{label}</span>
      <span className="border-l border-slate-200 pl-3 font-medium text-slate-800 dark:border-slate-700 dark:text-slate-200">{value}</span>
    </li>
  );
}

function StrategyGroupDetail({ item }: { item: StrategyGroupShelfItem }) {
  return (
    <section className="rounded-2xl border border-amber-500/15 bg-slate-950/85 p-5 shadow-lg shadow-black/20">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold text-amber-200/75">{item.strategy_group_id}</p>
          <h3 className="mt-1 text-xl font-bold text-slate-50">{item.strategy_group_name}</h3>
        </div>
        <StatePill tone={item.status_tone}>{item.current_status}</StatePill>
      </div>

      <div className="mt-5 space-y-5">
        <div className="rounded-xl border border-purple-500/20 bg-purple-500/10 p-4">
          <p className="mb-1 text-xs font-bold uppercase tracking-[0.16em] text-purple-200">Next Action</p>
          <p className="text-sm leading-6 text-slate-100">{item.next_recommended_action}</p>
        </div>
        <DetailBlock label="Owner 总结" value={item.plain_language_summary} />
        <DetailBlock label="吃什么行情" value={item.market_regime_it_eats} />
        <DetailBlock label="怕什么行情" value={item.market_regime_it_hates} />
        <DetailBlock label="证据摘要" value={item.evidence_summary} />
        <DetailBlock label="准入边界" value={item.bounded_trial_readiness || 'display_model_only'} />
        <ChipBlock label="代表候选" values={item.representative_candidates} />
        <ChipBlock label="关键风险" values={item.key_risks} tone="amber" />
        <ChipBlock label="可确认警告" values={item.confidence_flags || ['display_model_only']} tone="amber" />
        <ChipBlock label="Main blockers" values={item.main_blockers || ['api_unavailable']} tone="rose" />
        <ChipBlock label="Owner 可选动作" values={item.owner_action_options} tone="indigo" />
        <ChipBlock label="当前禁止" values={item.not_allowed_now} tone="rose" />
        <details className="rounded-xl border border-amber-500/10 bg-slate-900/60 p-3">
          <summary className="cursor-pointer text-xs font-bold text-slate-300">技术详情</summary>
          <div className="mt-3 space-y-3">
            <DetailBlock label="Evidence reviewability" value={item.evidence_reviewability || 'display_model_only'} />
            <DetailBlock label="Live read-only observation readiness" value={item.live_readonly_observation_readiness || 'display_model_only'} />
            <DetailBlock label="Bounded-trial readiness" value={item.bounded_trial_readiness || 'display_model_only'} />
            <ChipBlock
              label="Non-permissions"
              values={[
                item.no_execution_permission ? 'no execution permission' : 'execution permission not asserted',
                item.no_order_permission ? 'no order permission' : 'order permission not asserted',
                item.no_runtime_start ? 'no runtime start' : 'runtime start not asserted',
                item.no_automatic_strategy_routing ? 'no automatic strategy routing' : 'routing not asserted',
              ]}
              tone="rose"
            />
          </div>
        </details>
      </div>
    </section>
  );
}

function CandidateEvidenceComparison({ data }: { data: StrategyGroupReviewabilityResponse | null }) {
  const candidates = data?.candidate_evidence || [];
  if (!candidates.length) {
    return (
      <section className="rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-800 shadow-sm dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300">
        Candidate evidence comparison is display_model_only / api_unavailable.
      </section>
    );
  }
  return (
    <section className="rounded-2xl border border-amber-500/15 bg-slate-950/85 p-5 shadow-lg shadow-black/20">
      <h3 className="mb-4 text-base font-bold text-slate-50">Candidate Evidence Comparison</h3>
      <DataTable
        compact
        columns={['candidate', 'group', 'status', '72h mean', '72h positive', '7d mean', 'flags']}
        rows={candidates.map((candidate) => [
          candidate.candidate_id,
          candidate.strategy_group_id,
          candidate.review_status,
          candidate.metrics.mean_72h || candidate.metrics.historical_oos_2021_2022 || 'n/a',
          candidate.metrics.positive_rate_72h || 'n/a',
          candidate.metrics.mean_7d || 'n/a',
          candidate.confidence_flags.join(' / '),
        ])}
      />
    </section>
  );
}

function ObservationReadinessPanel({
  data,
  liveObservation,
  caseQueue,
}: {
  data: StrategyGroupReviewabilityResponse | null;
  liveObservation: StrategyGroupLiveReadOnlyObservationResponse | null;
  caseQueue: ObservationCaseQueueResponse | null;
}) {
  const summary = data?.observation_chain_summary || {};
  const candidates = liveObservation?.candidates || [];
  const currentSignals = liveObservation?.current_signals || [];
  const signalHistory = liveObservation?.signal_history || [];
  const cases = caseQueue?.cases || [];
  const sinkSummary = liveObservation?.sink_summary || {};
  const inputSource = liveObservation?.input_source_summary || {};
  return (
    <section className="rounded-2xl border border-amber-500/15 bg-slate-950/85 p-5 shadow-lg shadow-black/20">
      <h3 className="mb-4 text-base font-bold text-slate-50">Live Read-only Observation Readiness</h3>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <ShelfMiniFact label="Existing runner" value={firstText(summary.existing_runner, 'api_unavailable')} />
        <ShelfMiniFact label="Active observation" value={String(Boolean(summary.active_live_readonly_observation))} />
        <ShelfMiniFact label="Signal glue" value={String(Boolean(summary.strategy_specific_signal_evaluator_glue_wired))} />
        <ShelfMiniFact label="Evidence without order" value={String(Boolean(summary.can_record_metadata_and_evidence_without_orders))} />
        <ShelfMiniFact label="Market source" value={String(inputSource.source_id || 'api_unavailable')} />
        <ShelfMiniFact label="Sink status" value={String(sinkSummary.sink_status || 'api_unavailable')} />
        <ShelfMiniFact label="Execution intent" value={String(Boolean(summary.execution_intent_created))} />
        <ShelfMiniFact label="Order created" value={String(Boolean(summary.order_created))} />
      </div>
      {candidates.length ? (
        <DataTable
          compact
          columns={['candidate', 'contract', 'glue', 'preview', 'readiness', 'blockers']}
          rows={candidates.map((candidate) => [
            candidate.candidate_id,
            candidate.signal_contract.join(' / '),
            candidate.evaluator_glue_status,
            String(candidate.latest_signal_preview.signal_type || 'not_checked'),
            candidate.readiness_status,
            candidate.blockers.join(' / '),
          ])}
        />
      ) : null}
      {currentSignals.length ? (
        <div className="mt-4">
          <DataTable
            compact
            columns={['current signal', 'symbol', 'type', 'bar time', 'review hook', 'sink']}
            rows={currentSignals.map((record) => [
              record.candidate_id,
              record.symbol,
              record.signal_type,
              new Date(record.market_bar_timestamp_ms).toISOString(),
              record.review_windows.join(' / '),
              record.sink_status,
            ])}
          />
        </div>
      ) : null}
      {signalHistory.length ? (
        <div className="mt-4">
          <DataTable
            compact
            columns={['history record', 'candidate', 'type', 'recorded', 'non-permission']}
            rows={signalHistory.slice(0, 5).map((record) => [
              record.record_id,
              record.candidate_id,
              record.signal_type,
              record.recorded_at_ms ? new Date(record.recorded_at_ms).toISOString() : 'preview',
              record.no_execution_permission && record.no_order_permission ? 'no execution / no order' : 'invalid',
            ])}
          />
        </div>
      ) : null}
      <div className="mt-4">
        <div className="mb-2 flex items-center justify-between gap-3">
          <h4 className="text-sm font-semibold text-slate-800 dark:text-slate-100">Observation Case Queue v1</h4>
          <StatePill tone={caseQueue?.queue_status === 'available' ? 'teal' : 'amber'}>
            {caseQueue?.queue_status || 'api_unavailable'}
          </StatePill>
        </div>
        {cases.length ? (
          <DataTable
            compact
            columns={['case', 'candidate', 'status', 'completed', 'pending', 'risk tags', 'non-permission']}
            rows={cases.map((item) => [
              item.case_id,
              item.candidate_id,
              item.case_status,
              item.completed_review_windows.join(' / ') || 'none',
              item.pending_review_windows.join(' / ') || 'none',
              item.risk_tags.join(' / '),
              item.no_execution_permission && item.no_order_permission ? 'no execution / no order' : 'invalid',
            ])}
          />
        ) : (
          <p className="rounded-lg border border-slate-200 bg-slate-900/70 px-4 py-3 text-sm text-slate-600  dark:bg-slate-950/40 dark:text-slate-300">
            No would-enter case is currently queued from the API. No-action and invalid observations stay excluded from Owner case review.
          </p>
        )}
        {caseQueue?.supported_future_cases?.['CPM-RO-001'] ? (
          <p className="mt-2 text-xs text-slate-400">
            CPM: {caseQueue.supported_future_cases['CPM-RO-001']}
          </p>
        ) : null}
      </div>
      <div className="mt-4 rounded-lg border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300">
        Existing runner can record metadata/evidence without order creation. MI/CPM evaluator glue now produces read-only current signal records from closed candle snapshots. The case queue only promotes would-enter observations into Owner review; it does not start runtime or create execution intent.
      </div>
      <ChipBlock
        label="Non-permissions"
        values={[
          'no trial start',
          'no execution intent',
          'no order permission',
          'no runtime start',
          'no automatic strategy routing',
        ]}
        tone="rose"
      />
    </section>
  );
}

function BnbTrialReadinessGapPanel({ data }: { data: Mi001BnbTrialReadinessGapResponse | null }) {
  const gates = data?.gap_matrix || [];
  const blockers = gates.filter((gate) => gate.required_for_testnet_rehearsal || gate.required_for_small_live_trial);
  return (
    <section className="rounded-2xl border border-amber-500/15 bg-slate-950/85 p-5 shadow-lg shadow-black/20">
      <div className="mb-4 flex flex-col justify-between gap-3 md:flex-row md:items-center">
        <div>
          <h3 className="text-base font-bold text-slate-50">MI-001 BNB Trial Readiness Gap</h3>
          <p className="mt-1 text-sm text-slate-400">
            Read-only Owner review map for testnet/manual-live prerequisites. This panel is not authorization.
          </p>
        </div>
        <StatePill tone={data ? 'amber' : 'slate'}>{data?.readiness_verdict || 'api_unavailable'}</StatePill>
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
        <ShelfMiniFact label="Candidate" value={data?.candidate_id || '数据未接入'} />
        <ShelfMiniFact label="Current phase" value={data?.current_phase || 'api_unavailable'} />
        <ShelfMiniFact label="Testnet design" value={data?.testnet_rehearsal_design.status.join(' / ') || 'api_unavailable'} />
        <ShelfMiniFact label="Small live draft" value={data?.small_live_trial_readiness_draft.status.join(' / ') || 'api_unavailable'} />
      </div>
      {gates.length ? (
        <DataTable
          compact
          columns={['gate', 'status', 'testnet', 'small live', 'gap', 'owner']}
          rows={gates.slice(0, 8).map((gate) => [
            `${gate.gate_id} ${gate.gate_name}`,
            gate.current_status,
            gate.required_for_testnet_rehearsal ? 'required' : 'not required',
            gate.required_for_small_live_trial ? 'required' : 'not required',
            gate.gap,
            gate.owner_decision_required ? 'required' : 'not required',
          ])}
        />
      ) : (
        <p className="rounded-lg border border-slate-200 bg-slate-900/70 px-4 py-3 text-sm text-slate-600  dark:bg-slate-950/40 dark:text-slate-300">
          BNB readiness gap API is unavailable; keep BNB in observation/design-only state.
        </p>
      )}
      <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
        <ChipBlock
          label="Key blockers"
          values={blockers.slice(0, 8).map((gate) => `${gate.gate_id}: ${gate.current_status}`)}
          tone="amber"
        />
        <ChipBlock
          label="Non-permissions"
          values={[
            'no trial start',
            'no execution intent',
            'no order permission',
            'no runtime start',
            'no live authorization',
          ]}
          tone="rose"
        />
      </div>
    </section>
  );
}

function StrategyTrialReadinessPanel({ data }: { data: StrategyTrialReadinessResponse | null }) {
  const profile = data?.strategy_profile;
  const cap = data?.risk_cap_profile;
  const preflight = data?.preflight_result;
  const factValues = data?.fact_checks?.facts?.length
    ? data.fact_checks.facts.map((fact) => `${fact.fact_id}: ${fact.status}${fact.blocker ? ` (${fact.blocker})` : ''}`)
    : ['api_unavailable'];
  return (
    <section className="rounded-2xl border border-amber-500/15 bg-slate-950/85 p-5 shadow-lg shadow-black/20">
      <div className="mb-4 flex flex-col justify-between gap-3 md:flex-row md:items-center">
        <div>
          <h3 className="text-base font-bold text-slate-50">Strategy Trial Readiness Framework</h3>
          <p className="mt-1 text-sm text-slate-400">
            Generic readiness surface using MI-001 BNB as first carrier. Observation remains review-only.
          </p>
        </div>
        <StatePill tone={data?.readiness_verdict === 'testnet_rehearsal_ready' ? 'teal' : 'amber'}>
          {data?.readiness_verdict || 'api_unavailable'}
        </StatePill>
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
        <ShelfMiniFact label="Strategy" value={profile ? `${profile.strategy_id} ${profile.symbol} ${profile.side}` : 'api_unavailable'} />
        <ShelfMiniFact label="Mode" value={profile?.execution_mode || 'api_unavailable'} />
        <ShelfMiniFact label="Latest signal" value={String(data?.observation_case.latest_signal || 'missing')} />
        <ShelfMiniFact label="Preflight" value={preflight?.status || 'api_unavailable'} />
        <ShelfMiniFact label="Cap profile" value={cap?.profile_status || 'api_unavailable'} />
        <ShelfMiniFact label="Max notional" value={cap?.max_notional_usdt || 'api_unavailable'} />
        <ShelfMiniFact label="Testnet" value={String(data?.rehearsal_readiness_state.testnet_rehearsal_status || 'api_unavailable')} />
        <ShelfMiniFact label="Live" value={data?.live_ready === false ? 'blocked' : 'api_unavailable'} />
      </div>
      <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
        <ChipBlock label="Blockers" values={(data?.blockers.length ? data.blockers : ['none_reported']).slice(0, 10)} tone="amber" />
        <ChipBlock label="Warnings" values={(data?.warnings.length ? data.warnings : ['none_reported']).slice(0, 10)} tone="slate" />
        <ChipBlock label="Preflight facts" values={factValues.slice(0, 10)} tone="amber" />
        <ChipBlock
          label="Non-permissions"
          values={[
            'no live order',
            'no execution intent',
            'no order creation',
            'no runtime start',
            'no auto execution',
          ]}
          tone="rose"
        />
        <ChipBlock
          label="Market data"
          values={[
            String(data?.market_data_architecture.current_provider || 'api_unavailable'),
            data?.market_data_architecture.websocket_required_for_this_sprint === false ? 'websocket not required' : 'websocket unknown',
          ]}
          tone="teal"
        />
      </div>
    </section>
  );
}

function DetailBlock({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="mb-1 text-xs font-semibold text-amber-200/70">{label}</p>
      <p className="text-sm leading-6 text-slate-300">{value}</p>
    </div>
  );
}

function ChipBlock({ label, values, tone = 'slate' }: { label: string; values: string[]; tone?: Tone }) {
  return (
    <div>
      <p className="mb-2 text-xs font-semibold text-amber-200/70">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {values.map((value) => (
          <StatePill key={value} tone={tone}>{value}</StatePill>
        ))}
      </div>
    </div>
  );
}

function ShelfMiniFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-amber-500/10 bg-slate-900/70 px-3 py-2">
      <div className="text-[11px] font-semibold text-amber-200/60">{label}</div>
      <div className="mt-1 text-sm font-medium text-slate-300">{value}</div>
    </div>
  );
}

function TechnicalDetails({ data, label = '技术详情' }: { data: unknown; label?: string }) {
  return (
    <details className="text-sm">
      <summary className="inline-flex cursor-pointer items-center gap-1.5 rounded-md px-3 py-2 text-xs font-medium text-slate-400 transition-colors duration-200 hover:bg-slate-900 hover:text-amber-100 focus:outline-none focus:ring-2 focus:ring-amber-400/50">
        {label}
      </summary>
      <div className="mt-2 rounded-lg border border-amber-500/15 bg-slate-950 p-5 text-[13px] text-slate-300 shadow-inner">
        <JsonDetails data={data} label="JSON" />
      </div>
    </details>
  );
}

function SoftLink({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <Link
      to={to}
      className="rounded-lg border border-purple-400/30 bg-purple-500 px-4 py-2 text-sm font-semibold text-white shadow-sm shadow-purple-950/30 transition-colors duration-200 hover:bg-purple-400 focus:outline-none focus:ring-2 focus:ring-amber-400/50"
    >
      {children}
    </Link>
  );
}

function StatePill({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  const classes = {
    teal: 'bg-teal-500/10 text-teal-300 border-teal-400/25',
    indigo: 'bg-purple-500/15 text-purple-200 border-purple-400/30',
    amber: 'bg-amber-500/10 text-amber-200 border-amber-400/30',
    rose: 'bg-rose-500/10 text-rose-300 border-rose-400/25',
    slate: 'bg-slate-900 text-slate-300 border-slate-700',
  };
  return <span className={`inline-flex items-center rounded border px-2.5 py-0.5 text-xs font-medium ${classes[tone]}`}>{children}</span>;
}

function DotText({ tone, text }: { tone: 'teal' | 'indigo' | 'rose'; text: string }) {
  const colors = {
    teal: 'bg-teal-400',
    indigo: 'bg-indigo-400',
    rose: 'bg-red-400',
  };
  return (
    <span className="flex items-center gap-1.5 font-medium">
      <span className={`h-1.5 w-1.5 rounded-full ${colors[tone]}`} />
      {text}
    </span>
  );
}

function toneBox(tone: 'teal' | 'rose') {
  return tone === 'teal'
    ? 'flex items-center gap-2 rounded-md border border-teal-100 bg-teal-50 px-4 py-3 text-sm text-teal-600 dark:border-teal-900/50 dark:bg-teal-500/10 dark:text-teal-400'
    : 'flex items-center gap-2 rounded-md border border-rose-100 bg-rose-50 px-4 py-3 text-sm text-rose-600 dark:border-rose-900/50 dark:bg-rose-500/10 dark:text-rose-400';
}

function timelineDot(tone: Tone) {
  const colors = {
    teal: 'bg-teal-100 text-teal-600 dark:bg-teal-900/50 dark:text-teal-400',
    amber: 'bg-amber-100 text-amber-600 dark:bg-amber-900/50 dark:text-amber-400',
    rose: 'bg-rose-100 text-rose-600 dark:bg-rose-900/50 dark:text-rose-400',
    indigo: 'bg-purple-100 text-purple-600 dark:bg-purple-900/50 dark:text-purple-300',
    slate: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
  };
  return `absolute -left-[17px] top-1 flex h-8 w-8 items-center justify-center rounded-full border-4 border-white dark:border-slate-900 ${colors[tone]}`;
}

function Loading({ label }: { label: string }) {
  return <div className="text-sm text-slate-500">{label}</div>;
}

function ownerWorkbenchView(view: CarrierDecisionView) {
  const hasCarrier = view.carrierId !== '数据未接入';
  const plainBlockers = view.safetyGateSource === 'unavailable'
    ? ['授权门槛数据未接入', '无法用于真实授权']
    : view.hardBlockers.length
      ? view.hardBlockers.map(ownerSafeText).slice(0, 3)
      : view.pendingOwnerLiveAuthorization
        ? ['真实资金尚未授权']
        : ['后端未报告硬阻断'];
  const plainRisks = view.strategyWarnings.length
    ? view.strategyWarnings.map(ownerSafeText).slice(0, 3)
    : ['策略不保证盈利', '市场波动可能导致回撤扩大', '这是极小资金试验，结果可能与真实交易表现不同'];
  return {
    priority: hasCarrier
      ? `${shortSymbol(view.symbol)} 小额试验准备已完成，等待你的真实资金授权`
      : '当前候选数据未接入，无法用于真实授权',
    currentStep: view.safetyGateSource === 'unavailable' ? 2 : 3,
    candidateName: hasCarrier ? `${view.strategyId} ${shortSymbol(view.symbol)} ${humanSide(view.side)}` : '数据未接入',
    direction: `${humanSide(view.side)}（做多）`,
    cap: `${view.quantity} / ${plainCap(view.maxNotional, view.symbol)}`,
    canExecute: view.canAuthorizeLiveTrial ? '可授权' : '未就绪',
    readinessReason: view.canAuthorizeLiveTrial ? '后端已确认授权门槛' : view.authorizationButtonDisabledReason,
    plainBlockers,
    plainRisks,
    provenance: view.provenance,
  };
}

function strategyCandidateView(
  current: CarrierDecisionView,
  marketView: { symbol: string; regime: string; direction: string; batch: number },
): RecommendedCandidate[] {
  const primary: RecommendedCandidate = {
    id: current.carrierId,
    name: current.carrierId,
    category: '趋势类',
    summary: `${shortSymbol(current.symbol)} 处于当前小额试验候选，测试网保护路径已验证。`,
    reason: `${marketView.regime} 判断下，优先选择已经完成测试网保护演练的候选。`,
    status: '可进入授权前确认',
    risk: '小样本试验不代表长期盈利。',
    source: current.provenance.carrierId === 'unavailable' ? 'unavailable' : 'derived_from_backend',
    sourceLabel: current.provenance.carrierId === 'unavailable' ? '数据未接入' : '后端候选',
    action: current.provenance.carrierId === 'unavailable' ? 'not_recommended' : 'confirm',
    actionLabel: current.provenance.carrierId === 'unavailable' ? '暂不建议' : '查看确认单',
  };
  const pool: RecommendedCandidate[] = [
    primary,
    {
      id: 'MI-001-SOL-LONG',
      name: 'MI-001-SOL-LONG',
      category: '趋势类',
      summary: 'SOL 动量候选，适合强趋势延续时继续观察。',
      reason: '当行情偏强或反弹延续时，可作为同策略族对照候选。',
      status: '可复盘，暂不作为当前授权对象',
      risk: '波动较大，追高后可能快速回撤。',
      source: 'sample_data',
      sourceLabel: '示例候选',
      action: 'observe',
      actionLabel: '加入观察',
    },
    {
      id: 'TB-BTC-SHORT',
      name: 'TB-BTC-SHORT',
      category: '突破跟随类',
      summary: 'BTC 下破后顺势跟随的研究候选。',
      reason: marketView.regime === '下跌趋势' ? '与你选择的下跌趋势更匹配。' : '可作为方向变化后的备用候选。',
      status: '研究池，不能直接试验',
      risk: '假突破可能导致止损。',
      source: 'sample_data',
      sourceLabel: '示例候选',
      action: 'details',
      actionLabel: '查看候选详情',
    },
    {
      id: 'VB-SOL-SHORT',
      name: 'VB-SOL-SHORT',
      category: '波动类',
      summary: '波动扩张后的方向候选，只适合后续复盘。',
      reason: '如果波动放大，可观察是否出现更明确方向。',
      status: '研究池',
      risk: '波动放大末端容易反转。',
      source: 'sample_data',
      sourceLabel: '示例候选',
      action: 'not_recommended',
      actionLabel: '暂不建议',
    },
    {
      id: 'VI-001-ETH-LONG',
      name: 'VI-001-ETH-LONG',
      category: '量价冲击类',
      summary: 'ETH 量价冲击后的温和延续候选。',
      reason: '比高 beta 候选更温和，可作为备用观察。',
      status: '备用候选',
      risk: '成交量尖峰后可能回落。',
      source: 'sample_data',
      sourceLabel: '示例候选',
      action: 'observe',
      actionLabel: '加入观察',
    },
  ];
  if (marketView.symbol === 'SOL') return [pool[1], primary, pool[3]];
  if (marketView.symbol === 'ETH') return [pool[4], primary, pool[1]];
  if (marketView.regime === '下跌趋势') return [pool[2], pool[3], primary];
  return marketView.batch % 2 === 0 ? pool.slice(0, 3) : [primary, pool[4], pool[1]];
}

function strategyTypeShelf() {
  return [
    { title: '趋势类', desc: '顺着趋势，跟随上涨或下跌获取收益。' },
    { title: '波动类', desc: '利用价格波动，在区间内反复操作。' },
    { title: '回调类', desc: '在趋势中的回调位置，寻找反弹机会。' },
    { title: '均值回归类', desc: '价格偏离均值时，等待回归均值获利。' },
    { title: '相对强弱类', desc: '比较不同资产强弱，选择更强的做多。' },
  ];
}

function trialConfirmationView(
  view: CarrierDecisionView,
  data: ConsoleData,
  acknowledgements: Record<string, boolean>,
) {
  const unavailableGates = view.safetyGateSource === 'unavailable';
  const hasHardBlockers = view.hardBlockers.length > 0;
  const gateTone = (passed: boolean): Tone => unavailableGates ? 'amber' : passed ? 'teal' : 'rose';
  const gateResult = (passed: boolean) => unavailableGates ? '未接入' : passed ? '通过' : '阻断';
  const gateToneFromResult = (result: string): Tone => result === '通过' ? 'teal' : result === '阻断' ? 'rose' : 'amber';
  const noExecutionIntent = view.executionIntentState.includes('未创建');
  const noOrder = view.orderState.includes('未创建');
  const accountFactsAvailable = Boolean(data.accountFacts);
  const accountPositions = data.accountFacts?.positions || [];
  const accountOrders = data.accountFacts?.open_orders || [];
  const candidateSymbol = shortSymbol(view.symbol);
  const noConflictPositions = accountFactsAvailable ? recordsForSymbol(accountPositions, candidateSymbol).length === 0 : null;
  const noConflictOrders = accountFactsAvailable ? recordsForSymbol(accountOrders, candidateSymbol).length === 0 : null;
  const liveEnv = stringAt(data.readiness?.environment_boundary, 'trading_env', '');
  const liveEnvVisible = Boolean(liveEnv);
  const risks = data.ownerTrialFlow?.strategy_warnings.length
    ? data.ownerTrialFlow.strategy_warnings.map((warning) => ({
        id: String(warning.warning_id),
        title: ownerSafeText(String(warning.warning_id)),
        desc: String(warning.description || '策略风险需要 Owner 知情确认。'),
      }))
    : [
        { id: 'strategy_not_proven_profitable', title: '策略不保证盈利', desc: '即使过去表现良好，未来仍可能亏损。' },
        { id: 'limited_live_observation_sample', title: '实盘观察样本有限', desc: 'live read-only observation 样本仍小，不能证明长期有效。' },
        { id: 'regime_may_be_unfavorable', title: '行情环境可能不利', desc: '当前行情可能不同于历史高质量样本。' },
        { id: 'forward_review_incomplete', title: '前向复核尚不完整', desc: '前向复核是披露证据，不是确认后仍永久阻断的硬门槛。' },
        { id: 'historical_fragility_known', title: '历史脆弱性已知', desc: '历史样本存在脆弱性和不利早期路径风险。' },
      ];
  const allRisksAcknowledged = risks.every((risk) => acknowledgements[risk.id]);
  const accountGateResult = (value: boolean | null) => value === null ? '未接入' : value ? '通过' : '阻断';
  const remainingConditions = [
    ...(!allRisksAcknowledged ? ['策略风险仍未全部确认'] : []),
    ...(!view.liveReady ? ['尚未完成正式 Owner live 授权'] : []),
    ...(hasHardBlockers ? ['最终硬安全门未全部通过'] : []),
    ...(!accountFactsAvailable ? ['账户事实未接入，无法检查余额、持仓和挂单'] : []),
    ...(noConflictPositions === false ? [`${candidateSymbol} 仍存在冲突持仓，需后端确认`] : []),
    ...(noConflictOrders === false ? [`${candidateSymbol} 仍存在冲突挂单，需后端确认`] : []),
    ...(!liveEnvVisible ? ['服务器 / live 环境状态未接入'] : []),
    'live key / IP 白名单状态未接入',
  ];
  return {
    content: [
      ['候选', view.carrierId],
      ['币种', view.runtimeSymbol],
      ['方向', humanSide(view.side)],
      ['资金上限', plainCap(view.maxNotional, view.symbol)],
      ['杠杆', view.leverage],
      ['保护方案', '单止盈 + 止损'],
    ] as Array<[string, string]>,
    reasons: view.evidenceSource === 'backend_api'
      ? ['测试网链路已验证', '保护单和退出路径已验证', '适合极小资金试验']
      : ['测试网证据未接入，无法用于真实授权', '仅可作为页面流程预览', '必须等待后端证据上报'],
    risks,
    gates: [
      { label: '真实资金授权是否已通过', result: gateResult(view.liveReady), tone: gateTone(view.liveReady) },
      { label: '硬安全门是否全部通过', result: gateResult(!hasHardBlockers), tone: gateTone(!hasHardBlockers) },
      { label: '测试网验证是否全部通过', result: view.evidenceSource === 'backend_api' ? '通过' : '未接入', tone: view.evidenceSource === 'backend_api' ? 'teal' as Tone : 'amber' as Tone },
      { label: '账户事实是否可用', result: accountFactsAvailable ? '通过' : '未接入', tone: accountFactsAvailable ? 'teal' as Tone : 'amber' as Tone },
      { label: `${candidateSymbol} 是否无冲突持仓`, result: accountGateResult(noConflictPositions), tone: gateToneFromResult(accountGateResult(noConflictPositions)) },
      { label: `${candidateSymbol} 是否无冲突挂单`, result: accountGateResult(noConflictOrders), tone: gateToneFromResult(accountGateResult(noConflictOrders)) },
      { label: 'GKS / key / IP 白名单是否正常', result: '未接入', tone: 'amber' as Tone },
      { label: 'live 环境是否可见', result: liveEnvVisible ? '通过' : '未接入', tone: liveEnvVisible ? 'teal' as Tone : 'amber' as Tone },
      { label: '是否尚未创建真实资金执行计划', result: gateResult(noExecutionIntent), tone: gateTone(noExecutionIntent) },
      { label: '是否尚未创建订单', result: gateResult(noOrder), tone: gateTone(noOrder) },
    ],
    testnet: [
      { label: '入场', result: view.evidenceSource === 'backend_api' ? '通过' : '数据未接入' },
      { label: '保护单', result: view.evidenceSource === 'backend_api' ? '通过' : '数据未接入' },
      { label: '平仓', result: view.evidenceSource === 'backend_api' ? '通过' : '数据未接入' },
      { label: '最终空仓', result: view.evidenceSource === 'backend_api' ? '通过' : '数据未接入' },
      { label: '对账一致', result: view.evidenceSource === 'backend_api' ? '通过' : '数据未接入' },
    ],
    disabledReason: view.authorizationButtonDisabledReason,
    remainingConditions: uniqueTexts(remainingConditions).length
      ? uniqueTexts(remainingConditions)
      : ['等待后端确认所有真实资金授权门槛通过'],
  };
}

function selectedCarrierFallback(base: CarrierDecisionView, selectedCarrierId: string): CarrierDecisionView {
  const symbol = symbolFromCarrierId(selectedCarrierId);
  const strategyId = selectedCarrierId.split('-').slice(0, 2).join('-') || selectedCarrierId;
  return {
    ...base,
    carrierId: selectedCarrierId,
    strategyFamily: strategyId,
    strategyId,
    candidateId: selectedCarrierId,
    symbol: symbol ? `${symbol}/USDT:USDT` : '数据未接入',
    runtimeSymbol: symbol ? `${symbol}USDT` : '数据未接入',
    side: selectedCarrierId.toUpperCase().includes('SHORT') ? 'short' : 'long',
    quantity: '数据未接入',
    maxNotional: '数据未接入',
    leverage: '数据未接入',
    protectionPlan: '数据未接入',
    testnetState: '当前选择不是后端确认的可授权候选',
    authorizationState: 'local_selection_not_backend_authorized',
    pendingOwnerLiveAuthorization: false,
    liveReady: false,
    hardBlockers: ['当前选择不是后端确认的可授权候选，不能用于真实资金授权'],
    hardBlockerCount: 1,
    primaryAction: '返回策略候选，选择后端确认的候选进入授权前确认。',
    executionIntentState: '后端确认未创建真实资金执行计划',
    orderState: '后端确认未创建订单',
    testnetEvidence: [
      ['state', '未接入'],
      ['entry filled', '未接入'],
      ['TP accepted', '未接入'],
      ['SL accepted', '未接入'],
      ['cleanup close filled', '未接入'],
      ['final position flat', '未接入'],
      ['local positions', '未接入'],
      ['local open orders', '未接入'],
      ['reconciliation', '未接入'],
    ],
    canAuthorizeLiveTrial: false,
    authorizationButtonDisabledReason: '当前选择不是后端确认的可授权候选，不能授权真实资金试验。',
    evidenceSource: 'unavailable',
    safetyGateSource: 'unavailable',
    provenance: {
      ...base.provenance,
      carrierId: 'frontend_local_state',
      strategyFamily: 'frontend_local_state',
      strategyId: 'frontend_local_state',
      candidateId: 'frontend_local_state',
      symbol: 'frontend_local_state',
      runtimeSymbol: 'frontend_local_state',
      side: 'frontend_local_state',
      quantity: 'unavailable',
      maxNotional: 'unavailable',
      leverage: 'unavailable',
      protectionPlan: 'unavailable',
      testnetState: 'unavailable',
      liveReady: 'unavailable',
      hardBlockers: 'unavailable',
      executionIntentState: 'derived_from_backend',
      orderState: 'derived_from_backend',
    },
    timeline: carrierTimeline(selectedCarrierId, 'unavailable'),
  };
}

function symbolFromCarrierId(carrierId: string) {
  const upper = carrierId.toUpperCase();
  for (const symbol of ['BTC', 'ETH', 'SOL', 'BNB']) {
    if (upper.includes(`-${symbol}-`) || upper.includes(`${symbol}-`) || upper.includes(symbol)) return symbol;
  }
  return '';
}

function carrierDecisionView(data: ConsoleData): CarrierDecisionView {
  const governance = data.strategyTrialGovernance;
  const packet = governance?.owner_review_packet;
  const carrier = packet?.carrier;
  const auth = governance?.authorization_draft || {};
  const persistedDraft = data.ownerTrialFlow?.authorization_draft || null;
  const gate = governance?.minimal_live_trial_gate;
  const activeHardFromPacket = (packet?.hard_safety_blockers || [])
    .filter((blocker) => blocker.active)
    .map((blocker) => `${blocker.blocker_id}: ${blocker.description}`);
  const activeHardFromGate = gate?.hard_blockers || [];
  const activeHard = [
    ...activeHardFromPacket,
    ...activeHardFromGate,
  ];
  const warnings = [
    ...(packet?.strategy_warnings || []).map((warning) => `${warning.warning_id}: ${warning.description}`),
    ...(gate?.warnings || []),
    ...(gate?.acknowledgement_blockers || []),
  ];
  const evidence = packet?.testnet_rehearsal_evidence || {};
  const evidenceValue = (key: string) => evidence[key] === undefined || evidence[key] === null || evidence[key] === ''
    ? '数据未接入'
    : display(evidence[key]);
  const carrierId = provenanceText([
    [carrier?.carrier_id, 'backend_api'],
    [data.strategyTrialReadiness?.strategy_profile.candidate_id, 'backend_api'],
  ], '数据未接入');
  const strategyFamily = provenanceText([
    [carrier?.strategy_family, 'backend_api'],
    [data.strategyTrialReadiness?.strategy_profile.strategy_group, 'backend_api'],
  ], '数据未接入');
  const strategyId = provenanceText([
    [carrier?.strategy_id, 'backend_api'],
    [data.strategyTrialReadiness?.strategy_profile.strategy_id, 'backend_api'],
  ], '数据未接入');
  const candidateId = provenanceText([
    [carrier?.candidate_id, 'backend_api'],
    [data.strategyTrialReadiness?.strategy_profile.candidate_id, 'backend_api'],
  ], '数据未接入');
  const symbol = provenanceText([
    [carrier?.symbol, 'backend_api'],
    [data.strategyTrialReadiness?.strategy_profile.symbol, 'backend_api'],
  ], '数据未接入');
  const runtimeSymbol = provenanceText([[carrier?.runtime_symbol, 'backend_api']], '数据未接入');
  const side = provenanceText([
    [carrier?.side, 'backend_api'],
    [data.strategyTrialReadiness?.strategy_profile.side, 'backend_api'],
  ], '数据未接入');
  const quantity = provenanceText([[carrier?.quantity, 'backend_api']], '数据未接入');
  const maxNotional = provenanceText([
    [carrier?.max_notional, 'backend_api'],
    [data.strategyTrialReadiness?.risk_cap_profile.max_notional_usdt, 'backend_api'],
  ], '数据未接入');
  const leverage = provenanceText([
    [carrier?.leverage, 'backend_api'],
    [data.strategyTrialReadiness?.risk_cap_profile.leverage, 'backend_api'],
  ], '数据未接入');
  const protectionPlan = provenanceText([[carrier?.protection_plan_type, 'backend_api']], '数据未接入');
  const testnetState = provenanceText([
    [packet?.testnet_rehearsal_result, 'backend_api'],
    [evidence.result, 'backend_api'],
  ], '数据未接入');
  const liveReady = Boolean(carrier?.live_ready || packet?.live_ready || gate?.live_ready);
  const hasSafetyBackend = Boolean(packet || gate);
  const hardBlockers = hasSafetyBackend
    ? uniqueTexts(activeHard)
    : ['硬安全门数据未接入，无法用于真实授权'];
  const strategyWarnings = hasSafetyBackend
    ? uniqueTexts(warnings)
    : ['策略风险数据未接入，无法用于真实授权'];
  const authorizationStateField: FieldValue<string> = persistedDraft
    ? { value: persistedDraft.status, source: 'backend_api' }
    : Boolean(auth.pending_owner_live_authorization)
    ? { value: 'pending_owner_live_authorization', source: 'backend_api' }
    : provenanceText([
        [auth.authorization_status, 'backend_api'],
        [auth.status, 'backend_api'],
        [gate?.final_state, 'backend_api'],
      ], '数据未接入');
  const authorizationState = authorizationStateField.value;
  const canAuthorizeLiveTrial = Boolean(gate?.can_execute_bounded_live_trial && liveReady && hardBlockers.length === 0);
  const authorizationButtonDisabledReason = gate
    ? '后端未确认真实资金授权、执行权限和硬安全门全部通过，暂不可授权真实资金试验。'
    : '授权门槛数据未接入，无法用于真实授权。';
  const executionIntentState = gate
    ? gate.execution_intent_created
      ? '后端报告已创建执行计划'
      : '后端确认未创建真实资金执行计划'
    : '执行计划状态数据未接入，无法判断';
  const orderState = gate
    ? gate.order_created
      ? '后端报告已创建订单'
      : '后端确认未创建订单'
    : '订单状态数据未接入，无法判断';
  const evidenceSource: DataSource = packet ? 'backend_api' : 'unavailable';
  const safetyGateSource: DataSource = gate ? 'backend_api' : 'unavailable';
  const accountFactsSource: DataSource = data.accountFacts ? 'backend_api' : 'unavailable';
  return {
    carrierId: carrierId.value,
    strategyFamily: strategyFamily.value,
    strategyId: strategyId.value,
    candidateId: candidateId.value,
    symbol: symbol.value,
    runtimeSymbol: runtimeSymbol.value,
    side: side.value,
    quantity: quantity.value,
    maxNotional: maxNotional.value,
    leverage: leverage.value,
    protectionPlan: protectionPlan.value,
    testnetState: testnetState.value,
    authorizationState,
    pendingOwnerLiveAuthorization: authorizationState.includes('pending'),
    liveReady,
    hardBlockers,
    strategyWarnings,
    hardBlockerCount: hardBlockers.length,
    warningCount: strategyWarnings.length,
    primaryAction: '查看授权前确认单；确认策略风险与硬安全门的区别。',
    liveAuthorizationEffect: packet?.live_authorization_effect || '真实资金授权效果数据未接入，无法用于真实授权。',
    executionIntentState,
    orderState,
    testnetEvidence: [
      ['状态', testnetState.value === 'completed_with_valid_protection' ? '测试网保护演练已通过' : ownerSafeText(testnetState.value)],
      ['入场', `${plainEvidenceValue(evidence.entry_status)} / 数量 ${evidenceValue('entry_filled_quantity')}`],
      ['止盈保护', plainEvidenceValue(evidence.tp_status)],
      ['止损保护', plainEvidenceValue(evidence.sl_status)],
      ['清理平仓', evidence.cleanup_close_order_id ? '已完成' : '暂未上报'],
      ['最终空仓', plainEvidenceValue(evidence.final_position_flat)],
      ['本地 BNB 持仓', `${plainEvidenceValue(evidence.final_local_active_bnb_positions)} 条`],
      ['本地 BNB 挂单', `${plainEvidenceValue(evidence.final_local_open_bnb_orders)} 条`],
      ['对账', plainEvidenceValue(evidence.periodic_reconciliation)],
    ],
    canAuthorizeLiveTrial,
    authorizationButtonDisabledReason,
    evidenceSource,
    safetyGateSource,
    accountFactsSource,
    provenance: {
      carrierId: carrierId.source,
      strategyFamily: strategyFamily.source,
      strategyId: strategyId.source,
      candidateId: candidateId.source,
      symbol: symbol.source,
      runtimeSymbol: runtimeSymbol.source,
      side: side.source,
      quantity: quantity.source,
      maxNotional: maxNotional.source,
      leverage: leverage.source,
      protectionPlan: protectionPlan.source,
      testnetState: testnetState.source,
      authorizationState: authorizationStateField.source,
      liveReady: hasSafetyBackend ? 'backend_api' : 'unavailable',
      hardBlockers: hasSafetyBackend ? 'backend_api' : 'unavailable',
      strategyWarnings: hasSafetyBackend ? 'backend_api' : 'unavailable',
      executionIntentState: gate ? 'backend_api' : 'unavailable',
      orderState: gate ? 'backend_api' : 'unavailable',
      candidateRecommendations: 'derived_from_backend',
      marketInput: 'frontend_local_state',
      plainCopy: 'static_product_copy',
      accountFacts: accountFactsSource,
    },
    timeline: carrierTimeline(carrierId.value, evidenceSource),
  };
}

function carrierTimeline(carrierId: string, source: DataSource): CarrierDecisionView['timeline'] {
  const unavailable = source === 'unavailable';
  return [
    {
      id: 'live-observation',
      title: '实盘只读观察',
      status: unavailable ? '数据未接入' : '已完成',
      desc: unavailable ? '链路证据数据未接入，无法作为真实授权依据。' : `${carrierId} 先作为 live read-only observation case 被记录；signal 不是订单。`,
      tech: 'live_read_only_observation_case_recorded',
      tone: unavailable ? 'amber' : 'teal',
    },
    {
      id: 'readiness-framework',
      title: '就绪框架',
      status: '已完成',
      desc: '策略逻辑、具体候选、可知情风险、必须解决的问题、授权草案已经拆分。',
      tech: 'strategy_trial_architecture_governance_complete',
      tone: 'teal',
    },
    {
      id: 'preflight-facts',
      title: '授权前事实检查',
      status: '已完成',
      desc: '授权前事实检查结构已就绪，仍不启动 runtime。',
      tech: 'preflight_facts_read_only_surface',
      tone: 'teal',
    },
    {
      id: 'account-facts',
      title: '账户事实新鲜度',
      status: '已读取',
      desc: '账户事实和对账状态只用于核对，不给订单权限。',
      tech: 'account_facts_read_only',
      tone: 'teal',
    },
    {
      id: 'first-testnet-path',
      title: '受控测试网路径',
      status: '已演练',
      desc: 'BNB 同路径测试网演练覆盖入场与保护单路径。',
      tech: 'controlled_testnet_carrier_path',
      tone: 'teal',
    },
    {
      id: 'protection-defect',
      title: '首轮保护缺陷',
      status: '已发现',
      desc: '第一轮演练暴露 protection defect，未进入 live。',
      tech: 'first_rehearsal_protection_defect_found',
      tone: 'amber',
    },
    {
      id: 'protection-fixed',
      title: '保护规划已修复',
      status: '已修复',
      desc: '保护单规划修复后重新演练。',
      tech: 'protection_planner_fixed',
      tone: 'teal',
    },
    {
      id: 'valid-protection',
      title: '第二轮有效保护',
      status: unavailable ? '数据未接入' : '已完成',
      desc: unavailable ? '测试网保护证据未接入。' : 'entry filled、TP accepted、SL accepted、cleanup close filled、final position flat。',
      tech: 'completed_with_valid_protection',
      tone: unavailable ? 'amber' : 'teal',
    },
    {
      id: 'pending-live-auth',
      title: '等待真实资金授权',
      status: '阻断',
      desc: '架构治理已完成；当前缺少你的真实资金授权，所以没有真实资金执行计划或订单。',
      tech: 'not_live_ready_until_explicit_owner_live_authorization',
      tone: 'rose',
    },
  ];
}

function uniqueTexts(values: string[]) {
  return Array.from(new Set(values.filter(Boolean)));
}

function recordsForSymbol(items: Array<Record<string, unknown>>, symbol: string) {
  return items.filter((item) => JSON.stringify(item).toUpperCase().includes(symbol.toUpperCase()));
}

function buildStrategyRows(data: ConsoleData) {
  const mi001 = data.mi001;
  const carrierDecision = carrierDecisionView(data);
  return [
    {
      group: strategyGroupName,
      strategy: `${carrierDecision.carrierId} first execution Carrier`,
      symbol: carrierDecision.symbol,
      side: '多头',
      status: '等待 Owner live authorization',
      tone: 'amber' as Tone,
      signal: 'testnet 保护演练已完成',
      intent: 'no live ExecutionIntent',
      next: '查看 Carrier Authorization packet',
    },
    {
      group: strategyGroupName,
      strategy: strategySol,
      symbol: firstText(mi001?.candidate.symbol, 'SOL/USDT'),
      side: '多头',
      status: '准备完成',
      tone: 'amber' as Tone,
      signal: signalText(data),
      intent: intentEvidenceText(data),
      next: '查看详情',
    },
    {
      group: strategyGroupName,
      strategy: 'MI-001 BNB 多头',
      symbol: 'BNB/USDT',
      side: '多头',
      status: '候选',
      tone: 'slate' as Tone,
      signal: '暂未上报',
      intent: '暂无',
      next: '准备观察',
    },
    {
      group: 'VI-001 波动扩张',
      strategy: 'VI-001 ETH 多头',
      symbol: 'ETH/USDT',
      side: '多头',
      status: '候选',
      tone: 'slate' as Tone,
      signal: '暂未上报',
      intent: '暂无',
      next: '查看证据',
    },
  ];
}

function strategyGroupShelves(data: ConsoleData) {
  const carrierDecision = carrierDecisionView(data);
  if (data.strategyGroupReviewability) {
    const primaryShelf = data.strategyGroupReviewability.primary_groups.map((item) => ({
      ...carrierAdjustedShelfItem(item, carrierDecision),
      status_tone: toneForStrategyStatus(item.current_status),
      shelf_section: 'primary' as const,
    }));
    const secondaryShelf = data.strategyGroupReviewability.secondary_groups.map((item) => ({
      ...item,
      status_tone: toneForStrategyStatus(item.current_status),
      shelf_section: 'secondary' as const,
    }));
    return {
      primaryShelf,
      secondaryShelf,
      allShelf: [...primaryShelf, ...secondaryShelf],
      apiUnavailable: false,
    };
  }

  const fallback = buildStrategyGroupShelf(data).map((item, index) => ({
    ...item,
    display_model_only: true,
    not_runtime_source_of_truth: true,
    no_execution_permission: true,
    no_order_permission: true,
    no_runtime_start: true,
    no_automatic_strategy_routing: true,
    shelf_section: index < 6 ? 'primary' as const : 'secondary' as const,
  }));
  return {
    primaryShelf: fallback.slice(0, 6),
    secondaryShelf: fallback.slice(6),
    allShelf: fallback,
    apiUnavailable: true,
  };
}

function toneForStrategyStatus(status: string): Tone {
  const value = status.toLowerCase();
  if (value.includes('owner_special') || value.includes('coverage') || value.includes('cost')) return 'amber';
  if (value.includes('primary') || value.includes('strong')) return 'teal';
  if (value.includes('backup') || value.includes('data_request')) return 'indigo';
  if (value.includes('blocked') || value.includes('negative')) return 'rose';
  return 'slate';
}

function carrierAdjustedShelfItem(
  item: Omit<StrategyGroupShelfItem, 'status_tone'> & Partial<Pick<StrategyGroupShelfItem, 'status_tone'>>,
  carrierDecision: CarrierDecisionView,
): Omit<StrategyGroupShelfItem, 'status_tone'> & Partial<Pick<StrategyGroupShelfItem, 'status_tone'>> {
  if (item.strategy_group_id !== 'MI-001') return item;
  return {
    ...item,
    representative_candidates: uniqueTexts([carrierDecision.carrierId, 'MI-001 SOL long', ...item.representative_candidates]),
    current_status: 'BNB first execution Carrier / pending Owner live authorization',
    evidence_summary: `${carrierDecision.carrierId}: ${carrierDecision.testnetState}; SOL keeps historical primary-chain evidence. BNB is a Carrier, not the whole architecture.`,
    confidence_flags: uniqueTexts([
      ...(item.confidence_flags || []),
      'BNB pending explicit Owner live authorization',
      'Warning acknowledgement is not live authorization',
    ]),
    main_blockers: carrierDecision.hardBlockers,
    bounded_trial_readiness: 'BNB protected testnet same-path rehearsal completed; live_ready=false',
    next_recommended_action: '查看 Carrier Trial Authorization packet；不要自动选择或自动提升策略。',
    not_allowed_now: uniqueTexts([...item.not_allowed_now, 'create live ExecutionIntent', 'place order', 'start runtime']),
  };
}

function buildStrategyGroupShelf(data: ConsoleData): StrategyGroupShelfItem[] {
  const miSignalText = data.mi001 ? `${data.mi001.evidence.signal_count} 条 SOL 信号；BNB broad smoke rank #1，但本地历史覆盖短` : 'SOL readiness 暂未上报；BNB strong smoke 已纳入货架';
  return [
    {
      strategy_group_id: 'MI-001',
      strategy_group_name: 'Momentum Impulse',
      plain_language_summary: '强动量出现后，观察高 beta 标的是否继续向右尾延伸。',
      market_regime_it_eats: '强趋势、动量冲击后延续、right-tail continuation、市场愿意追高。',
      market_regime_it_hates: '动量耗尽、冲高回落、单边拥挤后的快速反转、低流动性假突破。',
      representative_candidates: ['MI-001 SOL long', 'MI-001 BNB long'],
      current_status: 'primary_chain_candidate / strong_smoke_candidate',
      status_tone: 'teal',
      evidence_summary: `${miSignalText}。BNB 数字强，历史覆盖短只是 confidence flag，不是淘汰理由。`,
      key_risks: ['高波动', 'MAE 大', '右尾依赖', '动量耗尽', 'BNB 覆盖期较短'],
      owner_action_options: ['查看 MI-001 SOL 主链路', '对比 MI-001 BNB 证据', '保留 BNB 作为强候选观察'],
      next_recommended_action: '继续完成 MI-001 SOL 的 Owner 控制台验收；BNB 保留为强 smoke 备选。',
      not_allowed_now: ['启动 trial', '创建 execution intent', '下单', '自动提升 BNB'],
    },
    {
      strategy_group_id: 'VI-001',
      strategy_group_name: 'Volume Impulse',
      plain_language_summary: '量价同时冲击后，观察更温和的延续机会。',
      market_regime_it_eats: '成交量明显放大、价格跟随、延续但不极端的趋势环境。',
      market_regime_it_hates: '消息尖峰后回落、放量滞涨、流动性扫单后的假延续。',
      representative_candidates: ['VI-001 ETH long'],
      current_status: 'backup_trial_candidate',
      status_tone: 'indigo',
      evidence_summary: 'ETH long broad smoke positive: signal_count 1277; 72h mean 1.1164; positive_rate 0.5348；相对 SOL 更温和。',
      key_risks: ['volume spike chasing', '成交量质量未知', '缺 taker/OI/funding 确认', '事件驱动假信号'],
      owner_action_options: ['查看 VI-001 ETH 证据', '作为 MI 暂停时的备用复盘对象', '等待 Owner 指令再做接受表'],
      next_recommended_action: '保留为 backup trial candidate，不进入当前主链路。',
      not_allowed_now: ['启动 trial', '下载新数据', '创建执行链路', '自动替换 MI-001 SOL'],
    },
    {
      strategy_group_id: 'CPM-RO-001',
      strategy_group_name: 'Owner Special Observation',
      plain_language_summary: '温和回调 / 趋势内回调观察对象，用于 Owner 主观认为更温和的市场验证和复盘优化。',
      market_regime_it_eats: '趋势内回调、波动较温和、回撤后继续沿原趋势修复。',
      market_regime_it_hates: '高波动下杀、趋势失效、EMA 滞后、区间破位后继续扩散。',
      representative_candidates: ['CPM read-only observation'],
      current_status: 'owner_special_observation',
      status_tone: 'amber',
      evidence_summary: 'CPM historical OOS 2021/2022 negative；不作为 proven alpha。Owner 认为其较温和，适合当前市场 validation 和 bounded review。',
      key_risks: ['2021/2022 OOS negative', '不是 proven alpha', '适用边界未验证', '不能自动 runtime eligible'],
      owner_action_options: ['只读 observation', 'market validation', 'bounded review', '复盘优化假设'],
      next_recommended_action: '建立只读观察记录，不自动提升为 runtime eligible。',
      not_allowed_now: ['宣称 proven alpha', '自动提升 runtime eligible', '启动 trial', '下单'],
    },
    {
      strategy_group_id: 'TB',
      strategy_group_name: 'Trend Breakout',
      plain_language_summary: '趋势突破后观察是否延续。',
      market_regime_it_eats: '趋势突破、区间上沿被有效突破、持续性资金追随。',
      market_regime_it_hates: '假突破、突破后快速回落、震荡市来回扫损。',
      representative_candidates: ['TB-001', 'TB-002'],
      current_status: 'research_pool / keep_for_later',
      status_tone: 'slate',
      evidence_summary: 'TB-002 BNB broad smoke rank #2；SOL/ETH 也有正向参考，但当前不进入 trial。',
      key_risks: ['false breakout', 'late entry', 'BNB coverage comparability', '缺成本/滑点/资金费率确认'],
      owner_action_options: ['保留为趋势参考', '以后与 MI/VI 对比', '需要时生成 breakout family sheet'],
      next_recommended_action: 'keep_for_later，等待 MI/VI 路径决策后再复盘。',
      not_allowed_now: ['参数优化', 'trial start', 'runtime 接入', '策略自我提升'],
    },
    {
      strategy_group_id: 'PC',
      strategy_group_name: 'Pullback Continuation',
      plain_language_summary: '趋势回踩后观察是否继续原趋势。',
      market_regime_it_eats: '趋势仍在、回踩不破结构、修复后继续延伸。',
      market_regime_it_hates: '趋势转弱、回踩变反转、EMA 触碰过密、宽幅震荡。',
      representative_candidates: ['PC-001', 'PC-002'],
      current_status: 'research_pool',
      status_tone: 'slate',
      evidence_summary: 'PC-002 SOL rank #8；保留 pullback-continuation family，不重新打开 CPM rescue。',
      key_risks: ['泛化成 long-beta continuation', 'MAE 大', '入场时点模糊', '可能与 CPM 问题重叠'],
      owner_action_options: ['作为 later family review candidate', '仅做证据复盘', '等待新的冻结假设'],
      next_recommended_action: 'park in research_pool，不做 trial。',
      not_allowed_now: ['CPM rescue', 'trial start', '自动接入执行', '参数扫'],
    },
    {
      strategy_group_id: 'VB',
      strategy_group_name: 'Volatility Breakout',
      plain_language_summary: '波动压缩后观察扩张方向是否延续。',
      market_regime_it_eats: '波动收缩后的扩张、突破初段、能量释放。',
      market_regime_it_hates: '扩张末端追高、假 squeeze、低质量波动放大。',
      representative_candidates: ['VB-001'],
      current_status: 'research_pool',
      status_tone: 'slate',
      evidence_summary: 'Broad smoke 有正向 long rows，但排名低于 MI/VI/TB 参考线。',
      key_risks: ['追在扩张尾部', '缺 volatility-quality filter', '缺 funding/OI/cost replay'],
      owner_action_options: ['保留为非纯动量比较组', '以后补质量过滤', '查看 broad smoke 行'],
      next_recommended_action: 'keep_for_later，当前不新增变体。',
      not_allowed_now: ['新增 runtime 策略', 'trial start', '下载 Tier 1 数据', '执行路径接入'],
    },
    {
      strategy_group_id: 'MR/RB',
      strategy_group_name: 'Mean Reversion / Range Boundary',
      plain_language_summary: '均值回归 / 区间边界拒绝，暂时作为弱或次级研究线。',
      market_regime_it_eats: '高质量区间、边界拒绝、过度偏离后回归。',
      market_regime_it_hates: '强趋势突破、边界失效、趋势延续碾压均值回归。',
      representative_candidates: ['MR-001', 'RB-001'],
      current_status: 'weak_or_secondary / needs better variant',
      status_tone: 'slate',
      evidence_summary: 'RB-001 SOL/ETH 有次级正向行；MR 当前没有 trial candidate，需要更好的变体假设。',
      key_risks: ['逆趋势接刀', '边界质量差', 'adverse path risk', 'short rows broadly weak'],
      owner_action_options: ['park', '等待新假设', '只做 secondary review'],
      next_recommended_action: 'parked until better variant is proposed。',
      not_allowed_now: ['trial start', 'averaging down', 'add-to-loser', '执行接入'],
    },
    {
      strategy_group_id: 'Tier1-Data-Families',
      strategy_group_name: 'Tier 1 Data Families',
      plain_language_summary: 'Funding、OI、taker flow、long-short、basis/premium、attention/search 等数据增强族。',
      market_regime_it_eats: '需要 crowding、carry、participation、premium、attention context 才能判断的行情。',
      market_regime_it_hates: '数据缺失、时间戳不齐、source semantics 不稳定、lookahead 风险。',
      representative_candidates: ['Funding', 'OI', 'Taker flow', 'Long-short ratio', 'Basis / premium', 'Attention / search'],
      current_status: 'data_request_ready / not downloaded / not admitted',
      status_tone: 'indigo',
      evidence_summary: '数据请求已在 tier1_data_requests.md 准备；未下载，未入库，未 admission。',
      key_risks: ['provider semantics', 'timestamp alignment', 'lookahead', 'normalization/revision risk'],
      owner_action_options: ['查看数据请求', 'Owner 单独授权下载', '保持 unavailable risk 标记'],
      next_recommended_action: '等待 Owner 单独确认是否下载 Tier 1 数据。',
      not_allowed_now: ['下载数据', '新增 adapter', '写 DB', 'admit strategy', '接 execution'],
    },
  ];
}

function buildIntentRows(data: ConsoleData): Array<Array<React.ReactNode>> {
  const metadata = recordAt(data.currentCampaign, 'metadata_json');
  const intent = stringAt(metadata, 'trial_trade_intent', '');
  if (!intent) return [];
  return [[
    '暂未上报',
    strategySol,
    'SOL',
    <StatePill key="direction" tone="teal">多</StatePill>,
    intent,
    <StatePill key="status" tone="teal">已记录未执行</StatePill>,
    '当前是只读观察模式',
    '暂未上报',
  ]];
}

function signalText(data: ConsoleData) {
  if (!data.evidence && !data.mi001) return '暂未上报';
  if (data.mi001) return `${data.mi001.evidence.signal_count} 条`;
  return '已上报';
}

function intentEvidenceText(data: ConsoleData) {
  const metadata = recordAt(data.currentCampaign, 'metadata_json');
  const intent = stringAt(metadata, 'trial_trade_intent', '');
  return intent ? '已记录，不是订单' : '暂无';
}

function technicalPayload(data: ConsoleData) {
  return {
    terminal_state: data.mi001?.readiness.verdict || data.mi001?.terminal_state,
    runtime_status: data.readiness?.runtime_state,
    source_refs: data.mi001?.source_refs,
    permission: data.readiness?.environment_boundary,
    strategy_trial_governance: data.strategyTrialGovernance,
    gaps: data.gaps,
  };
}

function plainEvidenceValue(value: unknown) {
  if (value === undefined || value === null || value === '') return '暂未上报';
  if (value === true) return '是';
  if (value === false) return '否';
  const text = String(value);
  const dictionary: Record<string, string> = {
    FILLED: '已成交',
    ACCEPTED: '已接受',
    consistent: '一致',
    completed_with_valid_protection: '测试网保护演练已通过',
  };
  return dictionary[text] || ownerSafeText(text);
}

function firstText(...values: unknown[]) {
  for (const value of values) {
    if (value !== undefined && value !== null && value !== '') {
      const text = String(value);
      if (['not_available', 'unknown', 'undefined', 'null', 'nan'].includes(text.toLowerCase())) continue;
      return text;
    }
  }
  return '暂未上报';
}

function provenanceText(values: Array<[unknown, DataSource]>, fallback: string): FieldValue<string> {
  for (const [value, source] of values) {
    if (value !== undefined && value !== null && value !== '') {
      const text = String(value);
      if (['not_available', 'unknown', 'undefined', 'null', 'nan'].includes(text.toLowerCase())) continue;
      return { value: text, source };
    }
  }
  return { value: fallback, source: 'unavailable' };
}

function withUsdt(value: string) {
  if (value === '暂未上报' || value === '数据未接入') return value;
  if (value.toUpperCase().includes('USDT')) return value;
  const numeric = Number(value);
  if (Number.isFinite(numeric)) return `${numeric.toFixed(2)} USDT`;
  return `${value} USDT`;
}

function shortSymbol(symbol: string) {
  return symbol.split('/')[0].replace('USDT', '') || symbol;
}

function humanSide(side: string) {
  if (side === '数据未接入' || side === '暂未上报') return side;
  return side.toLowerCase() === 'short' ? '空' : '多';
}

function humanAuthorizationState(state: string) {
  if (state === 'owner_live_authorized_pending_final_preflight') return '已授权，等待最终硬安全检查';
  return state.includes('pending') ? '等待真实资金授权' : state;
}

function ownerSafeText(value: string) {
  return value
    .replace(/^live_authorization_missing$/, '真实资金授权缺失')
    .replace('live_authorization_missing:', '真实资金授权缺失：')
    .replace(/^strategy_not_proven_profitable$/, '策略不保证盈利')
    .replace('strategy_not_proven_profitable:', '策略不保证盈利：')
    .replace(/^limited_live_observation_sample$/, '实盘观察样本有限')
    .replace('limited_live_observation_sample:', '实盘观察样本有限：')
    .replace(/^regime_may_be_unfavorable$/, '当前行情可能不利')
    .replace('regime_may_be_unfavorable:', '当前行情可能不利：')
    .replace(/^forward_review_incomplete$/, '前向复盘仍需继续')
    .replace('forward_review_incomplete:', '前向复盘仍需继续：')
    .replace(/^historical_fragility_known$/, '历史脆弱性已知')
    .replace('historical_fragility_known:', '历史脆弱性已知：');
}

function plainCap(maxNotional: string, symbol: string) {
  if (maxNotional === '数据未接入' || maxNotional === '暂未上报') return maxNotional;
  const numeric = Number(maxNotional);
  if (Number.isFinite(numeric)) return `${numeric.toFixed(0)} USDT`;
  if (maxNotional.includes('USDT')) return maxNotional;
  if (maxNotional && !maxNotional.includes('owner_authorization')) return `${maxNotional} USDT`;
  return '数据未接入';
}

function display(value: unknown) {
  if (value === undefined || value === null || value === '') return '暂未上报';
  if (typeof value === 'string' && ['not_available', 'unknown', 'undefined', 'null', 'nan'].includes(value.toLowerCase())) return '暂未上报';
  if (typeof value === 'object') return '已上报';
  return String(value);
}

function recordAt(source: Record<string, unknown> | undefined | null, key: string): Record<string, unknown> {
  const value = source?.[key];
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function stringAt(source: Record<string, unknown> | undefined | null, key: string, fallback: string): string {
  const value = source?.[key];
  return value === undefined || value === null || value === '' ? fallback : String(value);
}

function message(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}
