import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertCircle,
  BarChart3,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FileSearch,
  GitBranch,
  Info,
  ListChecks,
  Route,
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
  ReadinessResponse,
  StrategyGroupLiveReadOnlyObservationResponse,
  StrategyGroupReviewabilityResponse,
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

const EMPTY_DATA: ConsoleData = {
  readiness: null,
  accountFacts: null,
  mi001: null,
  strategyGroupReviewability: null,
  liveObservation: null,
  observationCaseQueue: null,
  bnbTrialGap: null,
  strategyTrialReadiness: null,
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

  const account = data.accountFacts?.account_summary || {};
  const positions = firstText(account.active_position_count, data.accountFacts?.positions.length, 0);
  const orders = firstText(account.open_order_count, data.accountFacts?.open_orders.length, 0);
  const totalEquity = withUsdt(firstText(data.mi001?.risk_policy.account_equity, account.total_equity, account.equity));
  const available = withUsdt(firstText(data.mi001?.risk_policy.available_margin, account.available_balance, account.available_margin));
  const margin = withUsdt(firstText(account.margin_balance, account.available_margin));
  const unrealized = withUsdt(firstText(account.unrealized_pnl, account.unrealized_profit));

  return (
    <>
      <section className="flex flex-col justify-between gap-4 rounded-xl border border-slate-800 bg-slate-900 p-6 text-white shadow-sm dark:bg-slate-800/80 md:flex-row md:items-center">
        <div className="flex flex-col gap-2">
          <div className="mb-1 flex items-center gap-2">
            <div className="flex h-5 w-5 items-center justify-center rounded-full border border-teal-500/30 bg-teal-500/20 text-xs font-bold text-teal-400">!</div>
            <h2 className="text-lg font-bold text-slate-50">
              MI-001 SOL 已完成试验前准备，当前因运行时启动保护未预检而阻断，试验未启动。
            </h2>
          </div>
          <div className="flex flex-wrap items-center gap-4 text-sm text-slate-300">
            <DotText tone="teal" text="实盘只读" />
            <span className="text-slate-600">·</span>
            <DotText tone="indigo" text="记录意图" />
            <span className="text-slate-600">·</span>
            <DotText tone="rose" text="禁止下单" />
          </div>
        </div>
        <button
          type="button"
          disabled
          className="whitespace-nowrap rounded-lg border border-white/10 bg-white/10 px-5 py-2.5 text-sm font-medium text-white opacity-60"
        >
          新建观察稍后开放
        </button>
      </section>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatusCard title="系统状态" value="安全" note="禁止下单" tone="teal" />
        <StatusCard title="账户状态" value={data.accountFacts ? '读取正常' : '暂未上报'} note={`持仓 ${positions} / 挂单 ${orders}`} tone="teal" />
        <StatusCard title="当前策略组" value="MI-001 SOL" note="MI-001 动量冲击 / 多头观察" tone="indigo" />
        <StatusCard title="当前阻断" value={blockerCopy} note="试验未启动" tone="amber" accent />
      </section>

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Panel title="全仓账户概览">
          <div className="grid flex-grow grid-cols-2 gap-6 p-5">
            <Metric label="总权益" value={totalEquity} />
            <Metric label="可用余额" value={available} />
            <Metric label="保证金占用" value={margin} />
            <div className="flex gap-8">
              <Metric label="持仓" value={positions} />
              <Metric label="挂单" value={orders} />
            </div>
            <Metric label="未实现盈亏" value={unrealized} />
          </div>
        </Panel>

        <Panel
          title="最近执行意图"
          action={<Link to="/intents" className="text-xs font-medium text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300">查看全部</Link>}
        >
          <div className="flex flex-grow flex-col items-center justify-center p-10 text-center">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800">
              <Zap className="h-6 w-6 text-slate-400 dark:text-slate-500" />
            </div>
            <h4 className="mb-2 font-bold text-slate-800 dark:text-slate-200">暂无新意图</h4>
            <p className="mb-5 max-w-xs text-sm leading-relaxed text-slate-500 dark:text-slate-400">
              策略还没有产生可记录的意图，或当前仍处于准备阶段。没有执行指令，没有订单。
            </p>
            <div className="flex gap-4 text-xs font-medium text-slate-400 dark:text-slate-500">
              <span>最近信号：{signalText(data)}</span>
              <span>最近阻断：启动保护</span>
            </div>
          </div>
        </Panel>
      </section>

      <section className="flex flex-col justify-between gap-4 rounded-xl border border-indigo-100 bg-indigo-50/80 p-6 dark:border-indigo-900/50 dark:bg-indigo-950/30 md:flex-row md:items-center">
        <div>
          <h3 className="mb-1 text-sm font-bold text-indigo-900 dark:text-indigo-300">当前可做</h3>
          <p className="text-xs text-indigo-700/80 dark:text-indigo-400/80">
            您可以继续查看详细信息。当前不可做：启动试验 / 创建执行指令 / 下单。
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <SoftLink to="/strategy-groups">查看策略组</SoftLink>
          <SoftLink to="/analysis">查看复盘证据</SoftLink>
          <SoftLink to="/trace">查看链路追踪</SoftLink>
        </div>
      </section>

      <TechnicalDetails data={technicalPayload(data)} />
    </>
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

      <details className="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <summary className="flex cursor-pointer items-center justify-between gap-3 px-5 py-4 text-sm font-bold text-slate-800 transition-colors hover:bg-slate-50 dark:text-slate-100 dark:hover:bg-slate-800/40">
          <span className="flex items-center gap-2">
            <FileSearch className="h-4 w-4 text-indigo-500" />
            证据与技术面板
          </span>
          <span className="text-xs font-medium text-slate-500 dark:text-slate-400">默认折叠，不影响 Owner 首屏判断</span>
        </summary>
        <div className="space-y-5 border-t border-slate-100 p-5 dark:border-slate-800">
          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <h3 className="mb-4 text-base font-bold text-slate-900 dark:text-slate-100">策略组列表</h3>
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
  if (error) return <ErrorState error={error} />;
  if (!data) return <Loading label="加载执行意图..." />;

  const rows = buildIntentRows(data);
  return (
    <PageShell title="执行意图" subtitle="这里只记录策略意图，不会触发交易。">
      {rows.length ? (
        <DataTable
          columns={['时间', '策略', '标的', '方向', '意图', '状态', '原因', '后续表现']}
          rows={rows}
        />
      ) : (
        <EmptyState
          icon={<Zap className="h-6 w-6" />}
          title="暂无执行意图记录"
          subtitle="策略还没有产生可记录的意图，或当前仍处于准备阶段。执行意图不是订单，不会触发交易。"
        />
      )}
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <h3 className="mb-2 text-sm font-bold text-slate-800 dark:text-slate-200">图表复盘</h3>
        <p className="text-sm text-slate-500 dark:text-slate-400">TradingView 类图表稍后支持。当前仅保留只读复盘位置。</p>
      </section>
      <TechnicalDetails data={{ evidence: data.evidence, currentCampaign: data.currentCampaign }} />
    </PageShell>
  );
}

export function AccountOrdersV2() {
  const { data, error } = useConsoleData();
  if (error) return <ErrorState error={error} />;
  if (!data) return <Loading label="加载账户订单..." />;

  const account = data.accountFacts?.account_summary || {};
  const unknown = data.accountFacts?.unknown_unmanaged_counts || {};
  const positions = data.accountFacts?.positions || [];
  const openOrders = data.accountFacts?.open_orders || [];
  const abnormal = Number(unknown.orders || 0) + Number(unknown.positions || 0);

  return (
    <PageShell title="账户订单" subtitle="当前只读取账户信息，不提供交易操作，禁止下单。">
      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div className="grid grid-cols-1 gap-6 md:grid-cols-4 md:gap-8">
          <Metric bordered label="总权益" value={withUsdt(firstText(data.mi001?.risk_policy.account_equity, account.total_equity, account.equity))} />
          <Metric bordered label="可用余额" value={withUsdt(firstText(data.mi001?.risk_policy.available_margin, account.available_balance, account.available_margin))} />
          <Metric bordered label="保证金占用" value={withUsdt(firstText(account.margin_balance, account.available_margin))} />
          <Metric label="未实现盈亏" value={withUsdt(firstText(account.unrealized_pnl, account.unrealized_profit))} />
        </div>
      </section>

      <section className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <RecordPanel title="持仓" items={positions} empty="暂无持仓" />
        <RecordPanel title="挂单" items={openOrders} empty="暂无挂单" />
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <h3 className="mb-2 text-sm font-bold text-slate-800 dark:text-slate-200">异常敞口</h3>
        <div className={toneBox(abnormal > 0 ? 'rose' : 'teal')}>
          <span className="h-2 w-2 flex-shrink-0 rounded-full bg-current" />
          {abnormal > 0 ? `发现 ${abnormal} 个异常敞口` : '未发现异常敞口。'}
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
  return (
    <PageShell title="复盘分析" subtitle="MI-001 SOL 已完成试验前复核，尚未开始试验。">
      <section className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <ReviewCard title="试验前复核" value="已完成" />
        <ReviewCard title="风险披露" value={latestDecision.risk_disclosure_json ? '已完成' : '暂未上报'} />
        <ReviewCard title="Owner 接受" value={firstText(latestDecision.owner_risk_acceptance_id, latestBinding.owner_risk_acceptance_id, '已完成')} />
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <h3 className="mb-4 flex items-center gap-2 text-base font-bold text-slate-900 dark:text-slate-100">
          <AlertCircle className="h-4.5 w-4.5 text-amber-500" />
          当前结论
        </h3>
        <div className="space-y-3 rounded-lg border border-slate-100 bg-slate-50 p-5 text-sm text-slate-700 dark:border-slate-700/50 dark:bg-slate-800/50 dark:text-slate-300">
          <p className="font-medium text-slate-900 dark:text-slate-100">策略候选已完成准备，但运行时启动保护未完成预检。</p>
          <p>当前只适合继续查看证据或等待下一次授权。</p>
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <h3 className="mb-4 text-base font-bold text-slate-900 dark:text-slate-100">证据摘要</h3>
        <ul className="space-y-3">
          <EvidenceItem label="broad smoke" value={data.mi001 ? '已完成' : '暂未上报'} />
          <EvidenceItem label="Owner acceptance" value={firstText(latestDecision.owner_risk_acceptance_id, latestBinding.owner_risk_acceptance_id, '已完成')} />
          <EvidenceItem label="PG 注册" value={data.mi001?.source_refs.some((ref) => ref.includes('brc_')) ? '已完成' : '暂未上报'} />
          <EvidenceItem label="final review" value={data.reviewPacket ? '已上报' : '已完成'} />
          <EvidenceItem label="trial_trade_intent evidence" value={intentEvidenceText(data)} />
          <EvidenceItem label="订单" value="无订单" />
        </ul>
      </section>

      <TechnicalDetails data={{ reviewPacket: data.reviewPacket, evidence: data.evidence, decisions: data.decisions, bindings: data.bindings }} />
    </PageShell>
  );
}

export function TraceV2() {
  const [expandedNode, setExpandedNode] = useState<string | null>('startup');
  const { data, error } = useConsoleData();
  if (error) return <ErrorState error={error} />;
  if (!data) return <Loading label="加载链路追踪..." />;

  const steps = [
    { id: 'candidate', title: '策略候选形成', status: '已完成', desc: 'MI-001 SOL 多头', tone: 'teal' as const },
    { id: 'risk', title: 'Owner 风险接受', status: '已完成', desc: '已接受进入准备阶段', tone: 'teal' as const },
    { id: 'pg', title: 'PG 注册', status: '已完成', desc: '已写入主数据源', tone: 'teal' as const },
    { id: 'review', title: '最终复核', status: '已完成', desc: 'final pre-start review', tone: 'teal' as const },
    { id: 'startup', title: '启动保护', status: '阻断', desc: '需要运行时预检', tone: 'amber' as const },
  ];

  return (
    <PageShell title="链路追踪" subtitle="查看 MI-001 SOL 从候选到当前阻断状态的完整过程。">
      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div className="relative ml-5 space-y-10 border-l-2 border-slate-200 py-4 dark:border-slate-800">
          {steps.map((step) => (
            <div key={step.id} className="relative pl-8">
              <div className={timelineDot(step.tone)}>
                {step.tone === 'teal' ? <Check className="h-3.5 w-3.5" strokeWidth={3} /> : <AlertCircle className="h-3.5 w-3.5" />}
              </div>
              <button
                type="button"
                onClick={() => setExpandedNode((current) => current === step.id ? null : step.id)}
                className="w-full rounded-xl border border-slate-100 bg-slate-50 p-4 text-left transition-colors hover:bg-slate-100 dark:border-slate-700/50 dark:bg-slate-800/30 dark:hover:bg-slate-800/50"
              >
                <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
                  <div className="flex items-center gap-3">
                    <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">{step.title}</h3>
                    <StatePill tone={step.tone}>{step.status}</StatePill>
                  </div>
                  {expandedNode === step.id ? <ChevronDown className="h-4 w-4 text-slate-400" /> : <ChevronRight className="h-4 w-4 text-slate-400" />}
                </div>
                <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{step.desc}</p>
                {expandedNode === step.id ? (
                  <div className="mt-4 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
                    <p className="text-sm text-slate-600 dark:text-slate-300">
                      说明：{step.id === 'startup' ? '运行时启动保护还没有完成预检。' : '节点已完成，技术来源可在下方展开。'}
                    </p>
                    <div className="mt-4 rounded border border-slate-200 bg-slate-100/50 p-3 dark:border-slate-800 dark:bg-slate-950">
                      <p className="mb-1 text-[11px] font-bold uppercase text-slate-500 dark:text-slate-500">技术状态</p>
                      <p className="break-all font-mono text-xs text-amber-600 dark:text-amber-400">
                        {step.id === 'startup' ? 'blocked_startup_guard_runtime_coupled' : 'reported'}
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
            <div key={index} className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800">
              <span>{firstText(item.symbol, item.display_symbol, `记录 ${index + 1}`)}</span>
              <StatePill tone="slate">{firstText(item.status, item.side, '已上报')}</StatePill>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex min-h-[160px] flex-grow flex-col items-center justify-center p-6 text-sm text-slate-500 dark:text-slate-400">
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
    <section className="flex flex-col items-center justify-center rounded-xl border border-slate-200 bg-white p-10 text-center shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full border border-slate-200 bg-slate-50 text-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-500">
        {icon}
      </div>
      <h4 className="mb-2 text-lg font-bold text-slate-800 dark:text-slate-200">{title}</h4>
      <p className="max-w-sm text-sm text-slate-500 dark:text-slate-400">{subtitle}</p>
    </section>
  );
}

function ReviewCard({ title, value }: { title: string; value: string }) {
  return (
    <section className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-teal-50 text-teal-600 dark:bg-teal-500/10 dark:text-teal-400">
        <CheckCircle2 className="h-6 w-6" />
      </div>
      <div>
        <h3 className="mb-1 text-[13px] font-bold tracking-wider text-slate-500 dark:text-slate-400">{title}</h3>
        <p className="text-base font-bold text-slate-900 dark:text-slate-100">{value}</p>
      </div>
    </section>
  );
}

function EvidenceItem({ label, value }: { label: string; value: string }) {
  return (
    <li className="flex items-center gap-3 text-sm">
      <CheckCircle2 className="h-4 w-4 text-teal-500" />
      <span className="w-44 font-mono text-slate-600 dark:text-slate-400">{label}</span>
      <span className="border-l border-slate-200 pl-3 font-medium text-slate-800 dark:border-slate-700 dark:text-slate-200">{value}</span>
    </li>
  );
}

function StrategyGroupDetail({ item }: { item: StrategyGroupShelfItem }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold text-slate-500 dark:text-slate-400">{item.strategy_group_id}</p>
          <h3 className="mt-1 text-xl font-bold text-slate-950 dark:text-slate-100">{item.strategy_group_name}</h3>
        </div>
        <StatePill tone={item.status_tone}>{item.current_status}</StatePill>
      </div>

      <div className="mt-5 space-y-4">
        <DetailBlock label="Owner 能读懂的总结" value={item.plain_language_summary} />
        <DetailBlock label="吃什么行情" value={item.market_regime_it_eats} />
        <DetailBlock label="怕什么行情" value={item.market_regime_it_hates} />
        <DetailBlock label="证据摘要" value={item.evidence_summary} />
        <DetailBlock label="下一步建议" value={item.next_recommended_action} />
        <ChipBlock label="代表候选" values={item.representative_candidates} />
        <ChipBlock label="关键风险" values={item.key_risks} tone="amber" />
        <ChipBlock label="Confidence flags" values={item.confidence_flags || ['display_model_only']} tone="amber" />
        <DetailBlock label="Evidence reviewability" value={item.evidence_reviewability || 'display_model_only'} />
        <DetailBlock label="Live read-only observation readiness" value={item.live_readonly_observation_readiness || 'display_model_only'} />
        <DetailBlock label="Bounded-trial readiness" value={item.bounded_trial_readiness || 'display_model_only'} />
        <ChipBlock label="Main blockers" values={item.main_blockers || ['api_unavailable']} tone="rose" />
        <ChipBlock label="Owner 可选动作" values={item.owner_action_options} tone="indigo" />
        <ChipBlock label="当前禁止" values={item.not_allowed_now} tone="rose" />
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
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <h3 className="mb-4 text-base font-bold text-slate-900 dark:text-slate-100">Candidate Evidence Comparison</h3>
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
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <h3 className="mb-4 text-base font-bold text-slate-900 dark:text-slate-100">Live Read-only Observation Readiness</h3>
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
          <p className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-950/40 dark:text-slate-300">
            No would-enter case is currently queued from the API. No-action and invalid observations stay excluded from Owner case review.
          </p>
        )}
        {caseQueue?.supported_future_cases?.['CPM-RO-001'] ? (
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
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
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-4 flex flex-col justify-between gap-3 md:flex-row md:items-center">
        <div>
          <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">MI-001 BNB Trial Readiness Gap</h3>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Read-only Owner review map for testnet/manual-live prerequisites. This panel is not authorization.
          </p>
        </div>
        <StatePill tone={data ? 'amber' : 'slate'}>{data?.readiness_verdict || 'api_unavailable'}</StatePill>
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
        <ShelfMiniFact label="Candidate" value={data?.candidate_id || 'MI-001-BNB-LONG'} />
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
        <p className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-950/40 dark:text-slate-300">
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
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-4 flex flex-col justify-between gap-3 md:flex-row md:items-center">
        <div>
          <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">Strategy Trial Readiness Framework</h3>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
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
      <p className="mb-1 text-xs font-semibold text-slate-500 dark:text-slate-400">{label}</p>
      <p className="text-sm leading-6 text-slate-700 dark:text-slate-300">{value}</p>
    </div>
  );
}

function ChipBlock({ label, values, tone = 'slate' }: { label: string; values: string[]; tone?: Tone }) {
  return (
    <div>
      <p className="mb-2 text-xs font-semibold text-slate-500 dark:text-slate-400">{label}</p>
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
    <div className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 dark:border-slate-800 dark:bg-slate-950">
      <div className="text-[11px] font-semibold text-slate-500 dark:text-slate-500">{label}</div>
      <div className="mt-1 text-sm font-medium text-slate-700 dark:text-slate-300">{value}</div>
    </div>
  );
}

function TechnicalDetails({ data, label = '技术详情' }: { data: unknown; label?: string }) {
  return (
    <details className="text-sm">
      <summary className="inline-flex cursor-pointer items-center gap-1.5 rounded-md px-3 py-2 text-xs font-medium text-slate-500 transition-colors hover:bg-slate-200/50 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-800/50 dark:hover:text-slate-200">
        {label}
      </summary>
      <div className="mt-2 rounded-lg border border-slate-800 bg-slate-900 p-5 text-[13px] text-slate-300 shadow-inner">
        <JsonDetails data={data} label="JSON" />
      </div>
    </details>
  );
}

function SoftLink({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <Link
      to={to}
      className="rounded-lg border border-indigo-200 bg-white px-4 py-2 text-sm font-medium text-indigo-700 shadow-sm transition-colors hover:bg-slate-50 dark:border-indigo-800 dark:bg-slate-800 dark:text-indigo-300 dark:hover:bg-slate-700"
    >
      {children}
    </Link>
  );
}

function StatePill({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  const classes = {
    teal: 'bg-teal-50 text-teal-700 border-teal-200 dark:bg-teal-500/10 dark:text-teal-400 dark:border-teal-500/20',
    indigo: 'bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-500/10 dark:text-indigo-300 dark:border-indigo-500/20',
    amber: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20',
    rose: 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-500/10 dark:text-rose-400 dark:border-rose-500/20',
    slate: 'bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700',
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

function timelineDot(tone: 'teal' | 'amber') {
  return `absolute -left-[17px] top-1 flex h-8 w-8 items-center justify-center rounded-full border-4 border-white dark:border-slate-900 ${
    tone === 'teal'
      ? 'bg-teal-100 text-teal-600 dark:bg-teal-900/50 dark:text-teal-400'
      : 'bg-amber-100 text-amber-600 dark:bg-amber-900/50 dark:text-amber-400'
  }`;
}

function Loading({ label }: { label: string }) {
  return <div className="text-sm text-slate-500">{label}</div>;
}

function buildStrategyRows(data: ConsoleData) {
  const mi001 = data.mi001;
  return [
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
  if (data.strategyGroupReviewability) {
    const primaryShelf = data.strategyGroupReviewability.primary_groups.map((item) => ({
      ...item,
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
    gaps: data.gaps,
  };
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

function withUsdt(value: string) {
  if (value === '暂未上报') return value;
  if (value.toUpperCase().includes('USDT')) return value;
  const numeric = Number(value);
  if (Number.isFinite(numeric)) return `${numeric.toFixed(2)} USDT`;
  return `${value} USDT`;
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
