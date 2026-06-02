// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import AppLayout from '@/src/components/layout/AppLayout';
import {
  AccountOrdersV2,
  AnalysisV2,
  HomeV2,
  IntentsV2,
  StrategyCandidatesV2,
  StrategyGroupsV2,
  TraceV2,
  TrialConfirmationV2,
} from './OwnerConsoleV2';

const mockBrcApi = vi.hoisted(() => ({
  readiness: vi.fn(),
  accountFacts: vi.fn(),
  mi001SolReadiness: vi.fn(),
  strategyGroupReviewability: vi.fn(),
  strategyGroupLiveObservationV1: vi.fn(),
  strategyGroupObservationCasesV1: vi.fn(),
  mi001BnbTrialReadinessGap: vi.fn(),
  strategyTrialReadinessV1: vi.fn(),
  strategyTrialArchitectureGovernance: vi.fn(),
  secondCarrierExpansion: vi.fn(),
  multiCarrierBudgetAuthorizationCurrent: vi.fn(),
  ownerTrialFlowCurrent: vi.fn(),
  bnbLiveExecutionBridgeDryRun: vi.fn(),
  createOwnerRiskAcknowledgement: vi.fn(),
  createOwnerAuthorizationDraft: vi.fn(),
  activateOwnerLiveAuthorization: vi.fn(),
  listStrategyFamilies: vi.fn(),
  listAdmissionDecisions: vi.fn(),
  listTrialBindings: vi.fn(),
  currentCampaign: vi.fn(),
  reviewPacket: vi.fn(),
  evidence: vi.fn(),
  listOperations: vi.fn(),
  logout: vi.fn(),
}));

vi.mock('@/src/services/api', () => ({
  brcApi: mockBrcApi,
}));

describe('Owner Console v2 shell', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    mockBrcApi.readiness.mockResolvedValue(readinessPayload());
    mockBrcApi.accountFacts.mockResolvedValue(accountFactsPayload());
    mockBrcApi.mi001SolReadiness.mockResolvedValue(mi001Payload());
    mockBrcApi.strategyGroupReviewability.mockResolvedValue(strategyGroupReviewabilityPayload());
    mockBrcApi.strategyGroupLiveObservationV1.mockResolvedValue(liveObservationPayload());
    mockBrcApi.strategyGroupObservationCasesV1.mockResolvedValue(observationCaseQueuePayload());
    mockBrcApi.mi001BnbTrialReadinessGap.mockResolvedValue(bnbTrialGapPayload());
    mockBrcApi.strategyTrialReadinessV1.mockResolvedValue(strategyTrialReadinessPayload());
    mockBrcApi.strategyTrialArchitectureGovernance.mockResolvedValue(strategyTrialGovernancePayload());
    mockBrcApi.secondCarrierExpansion.mockResolvedValue(secondCarrierExpansionPayload());
    mockBrcApi.multiCarrierBudgetAuthorizationCurrent.mockResolvedValue(multiCarrierBudgetAuthorizationPayload());
    mockBrcApi.ownerTrialFlowCurrent.mockResolvedValue(ownerTrialFlowPayload());
    mockBrcApi.bnbLiveExecutionBridgeDryRun.mockResolvedValue(bnbLiveExecutionBridgePayload());
    mockBrcApi.createOwnerRiskAcknowledgement.mockResolvedValue(ownerRiskAcknowledgementPayload());
    mockBrcApi.createOwnerAuthorizationDraft.mockResolvedValue(ownerAuthorizationDraftPayload());
    mockBrcApi.activateOwnerLiveAuthorization.mockResolvedValue(ownerLiveAuthorizationPayload());
    mockBrcApi.listStrategyFamilies.mockResolvedValue([]);
    mockBrcApi.listAdmissionDecisions.mockResolvedValue([{ owner_risk_acceptance_id: 'owner-acceptance-1' }]);
    mockBrcApi.listTrialBindings.mockResolvedValue([]);
    mockBrcApi.currentCampaign.mockResolvedValue({ campaign: null, live_ready: false });
    mockBrcApi.reviewPacket.mockResolvedValue(null);
    mockBrcApi.evidence.mockResolvedValue(null);
    mockBrcApi.listOperations.mockResolvedValue({ operations: [], live_ready: false });
    mockBrcApi.logout.mockResolvedValue({ authenticated: false });
  });

  afterEach(() => {
    cleanup();
    window.localStorage.clear();
  });

  it('renders only the new primary navigation labels and status capsule', async () => {
    render(
      <MemoryRouter initialEntries={['/home']}>
        <Routes>
          <Route path="/" element={<AppLayout />}>
            <Route path="home" element={<HomeV2 />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    for (const label of ['首页', '发起试验', '策略候选', '执行计划', '账户与订单', '复盘', '链路追踪']) {
      expect(await screen.findByRole('link', { name: new RegExp(`^${label}$`) })).toBeTruthy();
    }
    expect(await screen.findByRole('button', { name: /实盘只读 · 记录意图.*禁止下单/ })).toBeTruthy();
    for (const oldLabel of ['Command Center', 'Markets & Orders', 'Campaign', 'Review / Evidence', 'Strategy Families', 'Fixed Rehearsal', 'Runtime Control', 'LLM Copilot', 'Workflow', 'Operator', 'Guide', 'Dashboard', 'Ledger', 'Developer Detail', 'Audit Trail', '审计详情']) {
      expect(screen.queryByText(oldLabel)).toBeNull();
    }
  });

  it('renders the home control panel without dangerous buttons', async () => {
    renderWithRouter(<HomeV2 />);

    expect(await screen.findByText('Owner 工作台')).toBeTruthy();
    expect(screen.getByText('BNB 小额试验准备已完成，等待你的真实资金授权')).toBeTruthy();
    expect(screen.getByText('市场判断')).toBeTruthy();
    expect(screen.getByText('选择候选')).toBeTruthy();
    expect(screen.getByText('风险确认')).toBeTruthy();
    expect(screen.getByText('授权')).toBeTruthy();
    expect(screen.getByText('执行/复盘')).toBeTruthy();
    expect(screen.getByText('当前候选')).toBeTruthy();
    expect(screen.getByText('当前能否执行')).toBeTruthy();
    expect(screen.getByText('下一步动作')).toBeTruthy();
    expect(screen.getByText('未就绪')).toBeTruthy();
    expect(screen.getAllByText(/真实资金授权缺失/).length).toBeGreaterThan(0);
    expect(screen.getAllByText('进入授权前确认').length).toBeGreaterThan(0);
    expect(screen.getByText('为什么现在还不能实盘')).toBeTruthy();
    expect(screen.getByText('需要你知情的风险')).toBeTruthy();
    expect(screen.getByText('查看详细证据 / 技术详情')).toBeTruthy();
    assertNoDangerButtons();
  });

  it('renders strategy candidates and authorization packet as Owner decision flow', async () => {
    renderWithRouter(<StrategyCandidatesV2 />);
    expect(await screen.findByText('策略候选')).toBeTruthy();
    expect(screen.getByText('先说你的判断')).toBeTruthy();
    expect(screen.getByText('币种')).toBeTruthy();
    expect(screen.getByText('行情判断')).toBeTruthy();
    expect(screen.getByText('风险模式')).toBeTruthy();
    expect(screen.getByRole('button', { name: '生成候选' })).toBeTruthy();
    expect(screen.getByText('系统推荐候选')).toBeTruthy();
    expect(screen.getByText('基于你的判断：BNB + 震荡 + 都可 + 极小资金试错。系统给出以下候选。这是候选建议，不是执行授权。')).toBeTruthy();
    expect(screen.getAllByText('MI-001-BNB-LONG').length).toBeGreaterThan(0);
    expect(screen.getByText('后端候选')).toBeTruthy();
    expect(screen.getAllByText('示例候选').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/候选建议不是执行授权/).length).toBeGreaterThan(0);
    expect(screen.getAllByText('查看确认单').length).toBeGreaterThan(0);
    expect(screen.getByText('全部策略类型')).toBeTruthy();
    expect(screen.getByText('看不懂术语？')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'SOL' }));
    fireEvent.click(screen.getByRole('button', { name: '生成候选' }));
    expect(screen.getByText('基于你的判断：SOL + 震荡 + 都可 + 极小资金试错。系统给出以下候选。这是候选建议，不是执行授权。')).toBeTruthy();
    expect(screen.getAllByText('MI-001-SOL-LONG').length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: '查看确认单' }));
    expect(JSON.parse(window.localStorage.getItem('brc-owner-console-main-flow-v1') || '{}').selectedCarrierId).toBe('MI-001-BNB-LONG');
    assertNoDangerButtons();
    cleanup();

    renderWithRouter(<TrialConfirmationV2 />);
    expect(await screen.findByText('授权这一次 BNB 小额试验')).toBeTruthy();
    expect(screen.getByText('点击授权只记录本次授权，不会立即下单。')).toBeTruthy();
    expect(screen.getByText('本次我要授权什么')).toBeTruthy();
    expect(screen.getAllByText('MI-001-BNB-LONG').length).toBeGreaterThan(0);
    expect(screen.getAllByText('BNB/USDT').length).toBeGreaterThan(0);
    expect(screen.getByText('long / 做多')).toBeTruthy();
    expect(screen.getByText('0.01 BNB')).toBeTruthy();
    expect(screen.getAllByText('20 USDT').length).toBeGreaterThan(0);
    expect(screen.getByText('1x')).toBeTruthy();
    expect(screen.getAllByText(/单止盈 \+ 止损/).length).toBeGreaterThan(0);
    expect(screen.getByText('一次性授权')).toBeTruthy();
    expect(screen.getByText('我是否已确认风险')).toBeTruthy();
    expect(screen.getByText('真实资金授权')).toBeTruthy();
    expect(screen.getByText(/我现在能否点击授权/)).toBeTruthy();
    expect(screen.getByText('授权后执行前仍需通过')).toBeTruthy();
    expect(screen.getByText('最终硬安全检查')).toBeTruthy();
    expect(screen.getByText('已授权但尚未执行')).toBeTruthy();
    expect(screen.getAllByText('等待最终硬安全检查').length).toBeGreaterThan(0);
    expect(screen.getByText('运行时安全')).toBeTruthy();
    expect(screen.getByText('启动保护不可用')).toBeTruthy();
    expect(screen.getAllByText('尚未创建执行计划').length).toBeGreaterThan(0);
    expect(screen.getAllByText('尚未下单').length).toBeGreaterThan(0);
    expect(screen.getByText('未授予执行/下单权限')).toBeTruthy();
    expect(screen.getByText('执行计划预览')).toBeTruthy();
    expect(screen.getByText('仅预览，不可执行')).toBeTruthy();
    expect(screen.getByText('硬安全门阻断，仅展示预览')).toBeTruthy();
    expect(screen.getAllByText(/不会创建执行计划或订单/).length).toBeGreaterThan(0);
    expect(screen.getByText('Startup Guard')).toBeTruthy();
    expect(screen.getByText('GKS')).toBeTruthy();
    expect(screen.getByText('账户事实新鲜度')).toBeTruthy();
    expect(screen.getByText('BNB 持仓')).toBeTruthy();
    expect(screen.getByText('BNB 挂单')).toBeTruthy();
    expect(screen.getByText('Persistence')).toBeTruthy();
    expect(screen.getByText('测试网验证结果')).toBeTruthy();
    expect(screen.getByText('其他载体 / 预算基础（非本次授权）')).toBeTruthy();
    expect(screen.getByRole('button', { name: /确认授权这一次真实小额试验/ })).toBeTruthy();
    expect(screen.getAllByText(/风险确认尚未由后端记录/).length).toBeGreaterThan(0);
    expect(screen.getByText('暂不能授权真实资金，还差：')).toBeTruthy();
    expect(screen.getByText('授权草案尚未生成')).toBeTruthy();
    expect(screen.queryByText('策略风险尚未全部确认')).toBeNull();
    expect(screen.getAllByText('阻断').length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByRole('checkbox')[0]);
    expect(screen.getByText('已在本地确认')).toBeTruthy();
    const persisted = JSON.parse(window.localStorage.getItem('brc-owner-console-main-flow-v1') || '{}');
    expect(persisted.riskAcknowledgements['MI-001-BNB-LONG'].strategy_not_proven_profitable).toBe(true);
    expect((screen.getByRole('button', { name: /确认授权这一次真实小额试验/ }) as HTMLButtonElement).disabled).toBe(true);
    assertNoDangerButtons();
    cleanup();

    renderWithRouter(<IntentsV2 />);
    expect(await screen.findByRole('heading', { name: '执行计划' })).toBeTruthy();
    expect(screen.getByText('当前待确认候选')).toBeTruthy();
    expect(screen.getByText('真实资金授权')).toBeTruthy();
    expect(screen.getByText('本地风险确认')).toBeTruthy();
    expect(screen.getByText('1 / 5 项')).toBeTruthy();
    expect(screen.getByText('暂无执行计划记录')).toBeTruthy();
    expect(screen.getByText(/当前还没有真实资金执行计划/)).toBeTruthy();
    expect(screen.getByText('授权链路状态')).toBeTruthy();
    expect(screen.getByText('等待授权')).toBeTruthy();
    expect(screen.getAllByText('执行计划').length).toBeGreaterThan(0);
    expect(screen.getByText('入场订单')).toBeTruthy();
    expect(screen.getByText('保护订单')).toBeTruthy();
    cleanup();

    renderWithRouter(<AccountOrdersV2 />);
    expect(await screen.findByText('账户订单')).toBeTruthy();
    expect(screen.getByText('当前候选账户上下文')).toBeTruthy();
    expect(screen.getAllByText('MI-001-BNB-LONG').length).toBeGreaterThan(0);
    expect(screen.getByText('后端确认暂无 BNB 持仓')).toBeTruthy();
    expect(screen.getByText('后端确认暂无 BNB 挂单')).toBeTruthy();
    expect(screen.getByText('总权益')).toBeTruthy();
    cleanup();

    renderWithRouter(<AnalysisV2 />);
    expect(await screen.findByText('复盘分析')).toBeTruthy();
    expect(screen.getByText('当前结论')).toBeTruthy();
    expect(screen.getByText('BNB 测试网证据')).toBeTruthy();
    expect(screen.getAllByText('测试网保护演练已通过').length).toBeGreaterThan(0);
    expect(screen.getByText(/已成交 \/ 数量 0.01/)).toBeTruthy();
    expect(screen.getByText('止盈保护')).toBeTruthy();
    expect(screen.getByText('止损保护')).toBeTruthy();
    expect(screen.getByText('清理平仓')).toBeTruthy();
    expect(screen.getByText('最终空仓')).toBeTruthy();
    expect(screen.getByText('一致')).toBeTruthy();
    cleanup();

    renderWithRouter(<TraceV2 />);
    expect(await screen.findByText('链路追踪')).toBeTruthy();
    expect(screen.getByText('实盘只读观察')).toBeTruthy();
    expect(screen.getByText('受控测试网路径')).toBeTruthy();
    expect(screen.getByText('第二轮有效保护')).toBeTruthy();
    expect(screen.getByText('等待真实资金授权')).toBeTruthy();
    expect(screen.queryByText('not_live_ready_until_explicit_owner_live_authorization')).toBeNull();
    assertNoDangerButtons();
  });

  it('persists Owner risk acknowledgement and pending authorization draft through backend metadata APIs', async () => {
    renderWithRouter(<TrialConfirmationV2 />);

    expect(await screen.findByText('授权这一次 BNB 小额试验')).toBeTruthy();
    for (const checkbox of screen.getAllByRole('checkbox')) {
      fireEvent.click(checkbox);
    }
    fireEvent.click(screen.getByRole('button', { name: /后端记录风险确认并生成授权草案/ }));

    expect(await screen.findByText(/风险确认已由后端记录：ack-unit/)).toBeTruthy();
    expect(await screen.findByText(/授权草案已生成：draft-unit/)).toBeTruthy();
    expect(screen.getAllByText(/pending_owner_live_authorization/).length).toBeGreaterThan(0);
    expect(screen.getByText(/不会下单，不会创建 live ExecutionIntent/)).toBeTruthy();
    expect(mockBrcApi.createOwnerRiskAcknowledgement).toHaveBeenCalledWith({
      carrier_id: 'MI-001-BNB-LONG',
      acknowledged_warning_codes: [
        'strategy_not_proven_profitable',
        'limited_live_observation_sample',
        'regime_may_be_unfavorable',
        'forward_review_incomplete',
        'historical_fragility_known',
      ],
      acknowledgement_scope: 'strategy_trial_warnings',
    });
    expect(mockBrcApi.createOwnerAuthorizationDraft).toHaveBeenCalledWith({
      carrier_id: 'MI-001-BNB-LONG',
      linked_acknowledgement_id: 'ack-unit',
      symbol: 'BNB/USDT:USDT',
      side: 'long',
      max_notional: '20',
      quantity: '0.01',
      leverage: '1',
      protection_plan_type: 'single_tp_plus_sl',
    });
    expect(screen.getByText(/风险确认 ≠ 真实资金授权/)).toBeTruthy();
    const liveAuthorizationButton = screen.getByRole('button', { name: /确认授权这一次真实小额试验/ }) as HTMLButtonElement;
    expect(liveAuthorizationButton.disabled).toBe(false);
    fireEvent.click(liveAuthorizationButton);
    expect(await screen.findByText(/已授权这一次真实小额试验，等待最终硬安全检查/)).toBeTruthy();
    expect(screen.getAllByText(/尚未创建执行计划，尚未下单/).length).toBeGreaterThan(0);
    expect(mockBrcApi.activateOwnerLiveAuthorization).toHaveBeenCalledWith('draft-unit', {
      carrier_id: 'MI-001-BNB-LONG',
      symbol: 'BNB/USDT:USDT',
      side: 'long',
      max_notional: '20',
      quantity: '0.01',
      leverage: '1',
      protection_plan_type: 'single_tp_plus_sl',
    });
    assertNoDangerButtons();
  });

  it('shows live authorization button for recorded acknowledgement and draft even when local warning checks are not all selected', async () => {
    mockBrcApi.ownerTrialFlowCurrent.mockResolvedValueOnce({
      ...ownerTrialFlowPayload(),
      acknowledged_warnings: [],
      unacknowledged_warnings: [
        'strategy_not_proven_profitable',
        'limited_live_observation_sample',
        'regime_may_be_unfavorable',
        'forward_review_incomplete',
        'historical_fragility_known',
      ],
      latest_acknowledgement: {
        ...ownerRiskAcknowledgementPayload(),
        acknowledged_warning_codes: [],
      },
      authorization_draft: ownerAuthorizationDraftPayload(),
      live_authorization: null,
      authorization_status: 'pending_owner_live_authorization',
      live_ready: false,
      execution_permission_granted: false,
      order_permission_granted: false,
      execution_intent_created: false,
      order_created: false,
    });

    renderWithRouter(<TrialConfirmationV2 />);

    expect(await screen.findByText(/风险确认已由后端记录：ack-unit/)).toBeTruthy();
    expect(screen.getByText(/授权草案已生成：draft-unit/)).toBeTruthy();
    expect(screen.getByText('真实资金授权')).toBeTruthy();
    const liveAuthorizationButton = screen.getByRole('button', { name: /确认授权这一次真实小额试验/ }) as HTMLButtonElement;
    expect(liveAuthorizationButton.disabled).toBe(false);
    expect(screen.getAllByText(/启动保护不可用/).length).toBeGreaterThan(0);

    fireEvent.click(liveAuthorizationButton);

    expect(await screen.findByText(/已授权这一次真实小额试验，等待最终硬安全检查/)).toBeTruthy();
    expect(mockBrcApi.activateOwnerLiveAuthorization).toHaveBeenCalledWith('draft-unit', {
      carrier_id: 'MI-001-BNB-LONG',
      symbol: 'BNB/USDT:USDT',
      side: 'long',
      max_notional: '20',
      quantity: '0.01',
      leverage: '1',
      protection_plan_type: 'single_tp_plus_sl',
    });
    expect(screen.getAllByText(/尚未创建执行计划，尚未下单/).length).toBeGreaterThan(0);
    assertNoDangerButtons();
  });

  it('shows explicit live authorization on intents without implying an order exists', async () => {
    mockBrcApi.ownerTrialFlowCurrent.mockResolvedValueOnce({
      ...ownerTrialFlowPayload(),
      latest_acknowledgement: ownerRiskAcknowledgementPayload(),
      authorization_draft: ownerAuthorizationDraftPayload(),
      live_authorization: ownerLiveAuthorizationPayload(),
      authorization_status: 'owner_live_authorized_pending_final_preflight',
      hard_blockers: [
        {
          blocker_id: 'startup_guard_status_unavailable_runtime_not_started',
          active: true,
          blocks_after_ack: true,
          description: 'Owner live authorization is recorded; final startup guard preflight is still required.',
          source: 'owner_trial_flow',
          classification: 'hard_safety_blocker',
        },
      ],
    });

    renderWithRouter(<IntentsV2 />);

    expect(await screen.findByRole('heading', { name: '执行计划' })).toBeTruthy();
    expect(screen.getByText('已授权，待硬检查')).toBeTruthy();
    expect(screen.getAllByText(/Owner 已授权一笔 bounded live trial/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/尚未创建执行计划/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/等待启动保护确认/).length).toBeGreaterThan(0);
    assertNoDangerButtons();
  });

  it('marks missing decision-critical backend data as unavailable instead of using silent mock facts', async () => {
    mockBrcApi.strategyTrialArchitectureGovernance.mockRejectedValueOnce(new Error('not found'));
    mockBrcApi.strategyTrialReadinessV1.mockRejectedValueOnce(new Error('not found'));
    mockBrcApi.accountFacts.mockRejectedValueOnce(new Error('not found'));

    renderWithRouter(<HomeV2 />);
    expect(await screen.findByText('当前候选数据未接入，无法用于真实授权')).toBeTruthy();
    expect(screen.getAllByText('数据未接入').length).toBeGreaterThan(0);
    expect(screen.getByText('授权门槛数据未接入')).toBeTruthy();
    expect(screen.getByText('无法用于真实授权')).toBeTruthy();
    assertNoDangerButtons();
    cleanup();

    mockBrcApi.strategyTrialArchitectureGovernance.mockRejectedValueOnce(new Error('not found'));
    mockBrcApi.strategyTrialReadinessV1.mockRejectedValueOnce(new Error('not found'));
    mockBrcApi.accountFacts.mockRejectedValueOnce(new Error('not found'));

    renderWithRouter(<TrialConfirmationV2 />);
    expect(await screen.findByText('授权这一次 BNB 小额试验')).toBeTruthy();
    expect(screen.getAllByText('数据未接入').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/授权门槛数据未接入，无法用于真实授权/).length).toBeGreaterThan(0);
    expect((screen.getByRole('button', { name: /确认授权这一次真实小额试验/ }) as HTMLButtonElement).disabled).toBe(true);
    assertNoDangerButtons();
    cleanup();

    mockBrcApi.strategyTrialArchitectureGovernance.mockRejectedValueOnce(new Error('not found'));
    mockBrcApi.strategyTrialReadinessV1.mockRejectedValueOnce(new Error('not found'));
    mockBrcApi.accountFacts.mockRejectedValueOnce(new Error('not found'));

    renderWithRouter(<AccountOrdersV2 />);
    expect(await screen.findByText('账户订单')).toBeTruthy();
    expect(screen.getAllByText('账户事实数据未接入').length).toBeGreaterThan(0);
    expect(screen.queryByText('后端确认暂无 BNB 持仓')).toBeNull();
    expect(screen.queryByText('后端确认暂无 BNB 挂单')).toBeNull();
    assertNoDangerButtons();
  });
});

function renderWithRouter(node: React.ReactNode) {
  render(<MemoryRouter>{node}</MemoryRouter>);
}

function assertNoDangerButtons() {
  [
    /Start Trial/i,
    /Place Order/i,
    /Enable Live/i,
    /Execute Order/i,
    /Create Execution Intent/i,
    /Withdraw/i,
    /Transfer/i,
    /Flatten/i,
    /Cancel Order/i,
    /Start Runtime/i,
  ].forEach((name) => {
    expect(screen.queryByRole('button', { name })).toBeNull();
  });
}

function readinessPayload() {
  return {
    mode: 'brc_ready',
    current_conclusion: 'Owner view',
    why: [],
    account_impact: 'none',
    next_step: 'review',
    available_actions: [],
    disabled_actions: [],
    environment_boundary: {
      trading_env: 'live',
      brc_execution_permission_max: 'intent_recording',
      resolved_permission: 'intent_recording',
      live_read_only: true,
      execution_intent_allowed: false,
      order_allowed: false,
    },
    runtime_state: 'observe',
    risk_decision: 'ALLOW_READ',
    risk_account_summary: {},
    strategy_playbook_summary: {},
    action_cards: [],
    global_cutoff_controls: [],
    runtime_summary: {},
    review_summary: {},
    markets_summary: {},
    playbook_summary: {},
    parameter_summary: {},
    audit_summary: {},
    ai_investigator_summary: {},
    developer_details: {},
    live_ready: false,
  };
}

function accountFactsPayload() {
  return {
    source: 'mixed',
    truth_level: 'exchange_read',
    generated_at_ms: Date.now(),
    evidence_refs: [],
    checked_sources: [],
    source_snapshots: {},
    reconciliation_checked_at_ms: Date.now(),
    mismatch_count: 0,
    unknown_unmanaged_counts: { orders: 0, positions: 0 },
    account_summary: {
      total_equity: '4663.39',
      available_balance: '3652.57',
      active_position_count: 0,
      open_order_count: 0,
      unrealized_pnl: '0',
    },
    positions: [],
    open_orders: [],
    recent_orders: [],
    recent_fills: [],
    exposure_by_symbol: {},
    unknown_or_unmanaged_orders: [],
    unknown_or_unmanaged_positions: [],
    connection_health: {},
    reconciliation_status: { status: 'clean' },
    limitations: [],
    warnings: [],
    blockers: [],
    live_ready: false,
  };
}

function mi001Payload() {
  return {
    candidate: {
      id: 'MI-001',
      candidate_id: 'MI-001-SOL-LONG',
      strategy_family: 'Momentum Impulse',
      variant_label: '12h momentum',
      symbol: 'SOL/USDT:USDT',
      side: 'long',
      status: 'blocked_startup_guard_runtime_coupled',
    },
    evidence: { signal_count: 8135, mean_72h: '1.9531', positive_rate_72h: '0.5175', mean_7d: '4.7372', positive_rate_7d: '0.5398', limitations: [] },
    risk_policy: {
      capital_source: 'dedicated_subaccount',
      account_equity: '4663.39779623',
      available_margin: '3652.57096292',
      max_leverage: 5,
      operation_layer_notional_cap: '18262.85481460',
      max_notional_rule: 'min(...)',
      max_total_loss_rule: 'current_dedicated_subaccount_equity',
      prohibitions: [],
    },
    readiness: { verdict: 'blocked_startup_guard_runtime_coupled', blockers: [], checks: [] },
    owner_actions: { allowed_actions: [], disabled_actions: [] },
    non_permissions: {
      no_execution_permission: true,
      no_order_permission: true,
      no_runtime_start: true,
      no_leverage_change: true,
      no_order_capability: true,
      no_automatic_trial_start: true,
    },
    startup_guard_action: {
      endpoint: '',
      label: '',
      enabled: false,
      enabled_when: [],
      safety_text: '',
      does_not_start_trial: true,
      does_not_create_execution_intent: true,
      does_not_place_order: true,
    },
    terminal_state: 'blocked_until_startup_guard_preflight',
    source_refs: [],
    live_ready: false,
  };
}

function strategyGroupReviewabilityPayload() {
  return {
    generated_from: 'read_only_strategy_group_reviewability_snapshot',
    primary_groups: [
      groupPayload({
        strategy_group_id: 'MI-001',
        strategy_group_name: 'Momentum Impulse',
        representative_candidates: ['MI-001 SOL long', 'MI-001 BNB long'],
        current_status: 'primary_chain_candidate / strong_smoke_candidate',
        evidence_summary: 'SOL current chain sample; BNB repaired coverage remains review-only.',
        confidence_flags: ['BNB coverage repaired; review 2025 weakness and top-tail dependence before admission'],
        live_readonly_observation_readiness: 'live_readonly_observation_v1_evaluator_ready_requires_runner_binding',
        bounded_trial_readiness: 'SOL chain sample has bounded-trial metadata',
      }),
      groupPayload({
        strategy_group_id: 'VI-001',
        strategy_group_name: 'Volume Impulse',
        representative_candidates: ['VI-001 ETH long'],
        current_status: 'backup_observation_candidate',
        evidence_summary: 'ETH positive but cost-sensitive backup.',
        confidence_flags: ['cost-sensitive backup observation'],
        live_readonly_observation_readiness: 'backup_requires_signal_glue',
      }),
      groupPayload({
        strategy_group_id: 'CPM-RO-001',
        strategy_group_name: 'Owner Special Observation',
        representative_candidates: ['CPM read-only observation'],
        current_status: 'owner_special_observation',
        evidence_summary: 'CPM historical OOS 2021/2022 was negative; not proven alpha.',
        confidence_flags: ['Owner special observation rationale', 'not_proven_alpha'],
        bounded_trial_readiness: 'not_runtime_eligible_by_default',
        live_readonly_observation_readiness: 'live_readonly_observation_v1_evaluator_ready_requires_runner_binding',
      }),
      groupPayload({
        strategy_group_id: 'TB',
        strategy_group_name: 'Trend Breakout',
        representative_candidates: ['TB-001', 'TB-002'],
        current_status: 'research_pool / keep_for_later',
        evidence_summary: 'TB remains research pool.',
        live_readonly_observation_readiness: 'live_readonly_candidate_requires_signal_glue',
      }),
      groupPayload({
        strategy_group_id: 'PC',
        strategy_group_name: 'Pullback Continuation',
        representative_candidates: ['PC-001', 'PC-002'],
        current_status: 'research_pool',
        evidence_summary: 'PC remains research pool.',
      }),
      groupPayload({
        strategy_group_id: 'VB',
        strategy_group_name: 'Volatility Breakout',
        representative_candidates: ['VB-001'],
        current_status: 'research_pool',
        evidence_summary: 'VB remains research pool.',
      }),
    ],
    secondary_groups: [
      groupPayload({
        strategy_group_id: 'MR/RB',
        strategy_group_name: 'Mean Reversion / Range Boundary',
        representative_candidates: ['MR-001', 'RB-001'],
        current_status: 'weak_or_secondary / needs better variant',
        evidence_summary: 'Secondary shelf only.',
      }),
      groupPayload({
        strategy_group_id: 'Tier1-Data-Families',
        strategy_group_name: 'Tier 1 Data Families',
        representative_candidates: ['Funding', 'OI', 'Taker flow', 'Long-short ratio', 'Basis / premium', 'Attention / search'],
        current_status: 'data_request_ready / not_downloaded / not_admitted',
        evidence_summary: 'Data request ready; not downloaded.',
      }),
    ],
    candidate_evidence: [
      candidatePayload('MI-001-SOL-LONG', 'MI-001', {
        signal_count: '8135',
        mean_72h: '1.9531',
        positive_rate_72h: '0.5175',
        mean_7d: '4.7372',
      }, ['chain sample']),
      candidatePayload('MI-001-BNB-LONG', 'MI-001', {
        signal_count: '4166',
        mean_72h: '2.4074',
        positive_rate_72h: '0.5470',
        mean_7d: '5.4482',
      }, ['coverage_repaired_not_runtime_ready']),
      candidatePayload('VI-001-ETH-LONG', 'VI-001', {
        signal_count: '1277',
        mean_72h: '1.1164',
        positive_rate_72h: '0.5348',
        mean_7d: '2.2386',
      }, ['cost-sensitive backup observation']),
      candidatePayload('CPM-RO-001', 'CPM-RO-001', {
        historical_oos_2021_2022: 'negative',
      }, ['owner_special_observation', 'not_proven_alpha']),
    ],
    observation_chain_summary: {
      existing_runner: 'brc_live_read_only_detection_runner',
      can_record_metadata_and_evidence_without_orders: true,
      active_live_readonly_observation: false,
      strategy_specific_signal_evaluator_glue_wired: true,
      execution_intent_created: false,
      order_created: false,
    },
    non_permissions: {
      no_trial_start: true,
      no_execution_intent: true,
      no_order_permission: true,
      no_runtime_start: true,
      no_automatic_strategy_routing: true,
    },
    source_refs: [],
    live_ready: false,
  };
}

function liveObservationPayload() {
  return {
    generated_from: 'strategy_group_live_readonly_observation_v1',
    candidates: [
      observationCandidate('MI-001-SOL-LONG', 'MI-001', 'SOL/USDT:USDT', 'would_enter'),
      observationCandidate('MI-001-BNB-LONG', 'MI-001', 'BNB/USDT:USDT', 'would_enter'),
      observationCandidate('CPM-RO-001', 'CPM-RO-001', 'ETH/USDT:USDT', 'no_action'),
    ],
    current_signals: [
      observationRecord('MI-001-SOL-LONG', 'MI-001', 'SOL/USDT:USDT', 'would_enter'),
      observationRecord('MI-001-BNB-LONG', 'MI-001', 'BNB/USDT:USDT', 'would_enter'),
      observationRecord('CPM-RO-001', 'CPM-RO-001', 'ETH/USDT:USDT', 'no_action'),
    ],
    signal_history: [
      observationRecord('MI-001-SOL-LONG', 'MI-001', 'SOL/USDT:USDT', 'would_enter', 'recorded_process_local'),
    ],
    sink_summary: {
      sink_id: 'process_local_in_memory_strategy_group_observation_sink',
      sink_status: 'process_local_sink_available_not_recorded_by_get',
      writes_execution_or_order_tables: false,
    },
    input_source_summary: {
      source_id: 'local_sqlite_v3_dev_closed_klines_read_only',
      external_exchange_write: false,
      runtime_started: false,
    },
    review_hook_summary: {
      review_hook_status: 'records_include_pending_forward_outcome_windows',
    },
    runner_mapping: {
      existing_runner: 'brc_live_read_only_detection_runner',
      strategy_specific_signal_evaluator_glue_wired: true,
      live_observation_active: false,
    },
    observation_chain_summary: {
      active_live_readonly_observation: false,
      main_blocker: 'runner_binding_and_observation_sink_scheduler_not_started',
    },
    non_permissions: {
      no_trial_start: true,
      no_execution_intent: true,
      no_order_permission: true,
      no_runtime_start: true,
      no_automatic_strategy_routing: true,
      no_exchange_write: true,
    },
    live_observation_active: false,
    live_ready: false,
  };
}

function observationCaseQueuePayload() {
  return {
    generated_from: 'strategy_group_observation_case_queue_v1',
    queue_status: 'available',
    sink_source: 'pg_brc_strategy_group_observations',
    forward_review_source: 'pg_brc_strategy_group_forward_reviews',
    case_count: 1,
    cases: [
      {
        case_id: 'MI-001-BNB-LONG-live-case-001',
        observation_id: 'MI-001-BNB-LONG:mi001-5bb8b1c1b14437d7bddbacab:1780196400000',
        strategy_group_id: 'MI-001',
        candidate_id: 'MI-001-BNB-LONG',
        symbol: 'BNB/USDT:USDT',
        side: 'long',
        signal_type: 'would_enter',
        case_status: 'pending_forward_review',
        owner_review_status: 'owner_review_pending',
        observed_at_ms: 1780196400000,
        recorded_at_ms: 1780196400100,
        market_bar_timestamp_ms: 1780196400000,
        market_bar_close: '672.90',
        source_type: 'live_market_read_only',
        market_source: 'binance_usdm_public_klines_read_only',
        review_windows: ['1h', '4h', '12h', '24h', '72h'],
        completed_review_windows: ['1h', '4h'],
        pending_review_windows: ['12h', '24h', '72h'],
        forward_reviews: [
          { review_window: '1h', review_status: 'completed', review_due_at_ms: 1780203600000, forward_return_pct: '-0.7593', mfe_pct: '0.3121', mae_pct: '-1.1483' },
          { review_window: '4h', review_status: 'completed', review_due_at_ms: 1780214400000, forward_return_pct: '-0.9821', mfe_pct: '0.3121', mae_pct: '-1.5512' },
          { review_window: '12h', review_status: 'pending', review_due_at_ms: 1780243200000 },
          { review_window: '24h', review_status: 'pending', review_due_at_ms: 1780286400000 },
          { review_window: '72h', review_status: 'pending', review_due_at_ms: 1780459200000 },
        ],
        risk_tags: ['adverse_path_watch', 'bnb_live_case_001', 'local_exhaustion_watch', 'no_chase_required', 'owner_review_required', 'signal_not_order', 'wait_for_confirmation_required'],
        reason_codes: ['mi001_12h_momentum_impulse', 'observe_only_review_required'],
        human_summary: 'MI-001 would-enter long observation.',
        owner_interpretation: 'BNB live case #001 remains an Owner-review case, not a trade.',
        source_refs: ['src/application/strategy_group_observation_case_queue.py'],
        not_order: true,
        not_execution_intent: true,
        no_execution_permission: true,
        no_order_permission: true,
        no_runtime_start: true,
      },
    ],
    excluded_signal_types: ['no_action', 'invalid'],
    supported_future_cases: {
      'CPM-RO-001': 'future CPM would_enter signals will enter the same Owner review queue with owner_special_observation / OOS-negative risk tags',
    },
    non_permissions: {
      no_trial_start: true,
      no_execution_intent: true,
      no_order_permission: true,
      no_execution_permission: true,
      no_runtime_start: true,
      no_automatic_strategy_routing: true,
      signal_not_order: true,
      observation_not_execution_readiness: true,
    },
    source_refs: ['src/application/strategy_group_observation_case_queue.py'],
  };
}

function bnbTrialGapPayload() {
  return {
    generated_from: 'mi001_bnb_trial_readiness_gap_v1',
    candidate_id: 'MI-001-BNB-LONG',
    strategy_group_id: 'MI-001',
    symbol: 'BNB/USDT:USDT',
    side: 'long',
    current_phase: 'live_observation_case_plus_trial_design_draft',
    current_status: ['live_readonly_observation_active_as_evidence', 'no execution intent, no order'],
    readiness_verdict: 'not_testnet_ready_not_live_ready',
    gap_matrix: [
      bnbGate('G01', 'Account facts', 'partially_available_needs_bnb_refresh'),
      bnbGate('G02', 'BNB Operation Layer cap', 'missing_bnb_specific_cap'),
      bnbGate('G05', 'Execution permission', 'read_only_by_default'),
      bnbGate('G06', 'Order path', 'not_touched_by_observation_chain'),
      bnbGate('G18', 'Testnet rehearsal', 'design_only_not_started'),
      bnbGate('G19', 'Small live trial', 'draft_only_not_authorized'),
    ],
    testnet_rehearsal_design: {
      design_id: 'MI-001-BNB-owner-confirmed-testnet-rehearsal-v0',
      status: ['design_only', 'not_started', 'not_live_authorized', 'not_execution_ready'],
      mode: 'Owner confirms each entry',
      trigger: 'BNB live observation would_enter plus explicit Owner review decision',
      allowed_scope: ['BNB/USDT:USDT long testnet only'],
      risk_controls: ['max_leverage=5x'],
      exit_controls: ['time stop', 'manual stop'],
      recordkeeping: ['order id', 'fill/reject'],
      blockers: ['BNB-specific Operation Layer cap missing'],
      non_permissions: ['no_trial_start', 'no_order_permission'],
    },
    small_live_trial_readiness_draft: {
      design_id: 'MI-001-BNB-small-live-trial-readiness-draft-v0',
      status: ['draft_only', 'not_authorized', 'not_started', 'requires_owner_final_approval'],
      mode: 'Owner manually confirms each entry',
      trigger: 'separate final Owner approval',
      allowed_scope: ['BNB/USDT:USDT long only'],
      risk_controls: ['max_leverage=5x'],
      exit_controls: ['kill-switch rollback'],
      recordkeeping: ['Owner final approval record'],
      blockers: ['not authorized'],
      non_permissions: ['no_trial_start', 'no_order_permission'],
    },
    execution_boundary_audit: [
      {
        boundary: 'ExecutionIntent path exists',
        code_path: 'src/infrastructure/pg_execution_intent_repository.py',
        current_assessment: 'available in repo but not touched',
        bnb_chain_touches_path: false,
        required_control: 'separate Owner authorization',
      },
    ],
    owner_decision_checklist: [
      {
        decision_id: 'D01',
        question: 'Continue observation only?',
        options: ['continue_observation_only'],
        recommended_default: 'continue_observation_only',
        authorization_effect: 'No execution or order permission.',
      },
    ],
    api_console_impact: {
      endpoint: '/api/brc/readiness/mi001-bnb/trial-gap',
      console_surface: '/strategy-groups read-only panel',
      runtime_effect: 'none',
      execution_or_order_effect: 'none',
      display_only: true,
    },
    non_permissions: {
      no_trial_start: true,
      no_testnet_rehearsal_start: true,
      no_small_live_authorization: true,
      no_execution_intent: true,
      no_order_permission: true,
      no_execution_permission: true,
      no_runtime_start: true,
      no_leverage_change: true,
      no_transfer_or_withdrawal: true,
    },
    source_refs: ['src/application/mi001_bnb_trial_readiness_gap.py'],
    live_ready: false,
  };
}

function strategyTrialReadinessPayload() {
  return {
    generated_from: 'strategy_trial_readiness_v1',
    strategy_profile: {
      strategy_group: 'MI',
      strategy_id: 'MI-001',
      candidate_id: 'MI-001-BNB-LONG',
      symbol: 'BNBUSDT',
      side: 'long',
      execution_mode: 'owner_confirm_each_entry',
      auto_within_budget: false,
      owner_confirm_each_entry: true,
      not_runtime_source_of_truth: true,
    },
    observation_case: {
      case_id: 'MI-001-BNB-LONG-live-case-001',
      observation_id: 'MI-001-BNB-LONG:mi001-5bb8b1c1b14437d7bddbacab:1780196400000',
      latest_signal: 'would_enter',
      case_status: 'pending_forward_review',
      completed_review_windows: ['1h', '4h'],
      pending_review_windows: ['12h', '24h', '72h'],
    },
    risk_cap_profile: {
      cap_profile_id: 'MI-001-BNB-LONG-testnet-rehearsal-cap-v0',
      profile_status: 'present',
      max_concurrent_position: 1,
      max_daily_attempts: 1,
      max_trial_attempts: 3,
      max_notional_usdt: 'tiny_configurable_placeholder_requires_owner_confirmation',
      leverage: '1x_testnet_default_or_lower_until_owner_changes',
      no_auto_reentry: true,
      no_averaging_down: true,
      no_auto_top_up: true,
      no_transfer: true,
      no_withdrawal: true,
      owner_confirm_each_entry: true,
      live_ready: false,
      testnet_rehearsal_requires_owner_authorization: false,
    },
    preflight_result: {
      status: 'blocked',
      blockers: ['active_position_check_required_before_rehearsal', 'gks_status_required_before_rehearsal'],
      warnings: [],
      evidence: {
        requested_symbol: 'BNBUSDT',
        requested_side: 'long',
        requested_mode: 'owner_confirm_each_entry',
        live_trading_requested: false,
        auto_execution_enabled: false,
      },
      next_owner_action: 'Resolve blockers before BNB testnet same-path rehearsal.',
      execution_intent_created: false,
      order_created: false,
      live_order_created: false,
      execution_permission_granted: false,
    },
    owner_decision_state: {
      owner_authorization_status: 'not_required_for_testnet',
      owner_authorization_required: false,
      testnet_rehearsal_can_proceed_if_runtime_gate_passes: false,
      allowed_decisions: ['continue_observation_only', 'run_testnet_rehearsal_if_runtime_gates_pass'],
    },
    rehearsal_readiness_state: {
      testnet_rehearsal_status: 'blocked',
      live_status: 'blocked',
      auto_execution_status: 'disabled',
      same_path_rehearsal: true,
      requires_owner_authorization: false,
      requires_runtime_testnet_gates: true,
    },
    fact_checks: {
      generated_at_ms: Date.now(),
      candidate_id: 'MI-001-BNB-LONG',
      symbol: 'BNBUSDT',
      side: 'long',
      facts: [
        {
          fact_id: 'active_position',
          status: 'unavailable',
          source: 'unavailable',
          blocking: true,
          blocker: 'active_position_check_required_before_rehearsal',
          blockers: ['active_position_check_required_before_rehearsal'],
          observed_at_ms: Date.now(),
          evidence: {},
          notes: ['no active position read-only source was injected'],
        },
        {
          fact_id: 'open_order',
          status: 'unavailable',
          source: 'unavailable',
          blocking: true,
          blocker: 'open_order_check_required_before_rehearsal',
          blockers: ['open_order_check_required_before_rehearsal'],
          observed_at_ms: Date.now(),
          evidence: {},
          notes: ['no open order read-only source was injected'],
        },
        {
          fact_id: 'gks',
          status: 'unavailable',
          source: 'unavailable',
          blocking: true,
          blocker: 'gks_status_required_before_rehearsal',
          blockers: ['gks_status_required_before_rehearsal'],
          observed_at_ms: Date.now(),
          evidence: {},
          notes: ['no GKS read-only source was injected'],
        },
      ],
      blockers: [
        'active_position_check_required_before_rehearsal',
        'open_order_check_required_before_rehearsal',
        'gks_status_required_before_rehearsal',
      ],
      warnings: [],
      execution_intent_created: false,
      order_created: false,
      execution_permission_granted: false,
      live_ready: false,
    },
    readiness_verdict: 'testnet_rehearsal_blocked_with_explicit_reasons',
    blockers: ['active_position_check_required_before_rehearsal', 'gks_status_required_before_rehearsal'],
    warnings: [],
    evidence: {
      latest_signal: 'would_enter',
      observation_case_id: 'MI-001-BNB-LONG-live-case-001',
      cap_profile_present: true,
      public_rest_kline_observation_source: true,
      exchange_gateway_used: false,
      private_account_api_used: false,
    },
    market_data_architecture: {
      provider_abstraction: 'StrategyGroupMarketBarSource',
      current_provider: 'BinancePublicKlineMarketSource / public REST USD-M klines',
      current_source_is_public_read_only: true,
      websocket_required_for_this_sprint: false,
      evaluator_source_agnostic: true,
      exchange_gateway_market_provider: 'future controlled runtime/testnet/live context only',
    },
    non_permissions: {
      no_live_order: true,
      no_real_funds: true,
      no_withdrawal_or_transfer: true,
      no_credential_change: true,
      no_execution_intent: true,
      no_order_creation: true,
      no_execution_permission: true,
      no_runtime_start: true,
      no_auto_execution: true,
      would_enter_is_not_order: true,
      testnet_rehearsal_not_started: true,
      live_ready_false: true,
    },
    reusable_for_future_profiles: true,
    live_ready: false,
    auto_execution_ready: false,
  };
}

function strategyTrialGovernancePayload() {
  return {
    generated_from: 'strategy_trial_architecture_governance_v1',
    final_state: 'not_live_ready_until_explicit_owner_live_authorization',
    bnb_state: 'bnb_first_carrier_consolidated',
    owner_review_packet: {
      packet_id: 'MI-001-BNB-LONG-owner-review-packet-v1',
      carrier: {
        carrier_id: 'MI-001-BNB-LONG',
        strategy_family: 'MI-001',
        strategy_id: 'MI-001',
        candidate_id: 'MI-001-BNB-LONG',
        symbol: 'BNBUSDT',
        runtime_symbol: 'BNB/USDT:USDT',
        side: 'long',
        execution_mode: 'owner_confirm_each_entry',
        quantity: '0.01',
        max_notional: '20',
        leverage: '1',
        max_leverage_allowed: '5',
        protection_plan_type: 'single_tp_plus_sl',
        strategy_family_order_authority: false,
        carrier_is_order_authority: false,
        live_ready: false,
        auto_execution_ready: false,
      },
      testnet_rehearsal_result: 'completed_with_valid_protection',
      testnet_rehearsal_evidence: {
        result: 'completed_with_valid_protection',
        entry_order_id: 'testnet-entry-1',
        entry_filled_quantity: '0.01',
        entry_status: 'FILLED',
        tp_order_id: 'testnet-tp-1',
        tp_status: 'ACCEPTED',
        sl_order_id: 'testnet-sl-1',
        sl_status: 'ACCEPTED',
        cleanup_close_order_id: 'testnet-cleanup-1',
        cleanup_status: 'FILLED',
        final_position_flat: true,
        final_local_active_bnb_positions: '0',
        final_local_open_bnb_orders: '0',
        periodic_reconciliation: 'consistent',
        campaign_id: 'bnb-testnet-carrier-path-2',
        campaign_outcome: 'completed_with_valid_protection',
      },
      strategy_warnings: [
        {
          warning_id: 'strategy_not_proven_profitable',
          severity: 'warning',
          owner_ack_required: true,
          acknowledged: false,
          blocks_after_ack: false,
          description: 'Strategy warning is acknowledgeable and not a hard safety blocker.',
        },
        {
          warning_id: 'limited_live_observation_sample',
          severity: 'warning',
          owner_ack_required: true,
          acknowledged: false,
          blocks_after_ack: false,
          description: 'BNB live observation sample is limited.',
        },
      ],
      hard_safety_blockers: [
        {
          blocker_id: 'live_authorization_missing',
          active: true,
          blocks_after_ack: true,
          description: 'Explicit Owner live authorization is missing.',
          source: 'authorization_gate',
        },
      ],
      next_owner_action: 'explicit_owner_live_authorization_required',
      live_authorization_effect: 'Owner live authorization may create a single-use bounded authorization, but it does not place an order by itself.',
      no_execution_permission: true,
      no_order_permission: true,
      no_runtime_start: true,
      live_ready: false,
    },
    authorization_draft: {
      authorization_id: 'MI-001-BNB-LONG-bounded-live-trial-draft-v1',
      carrier_id: 'MI-001-BNB-LONG',
      pending_owner_live_authorization: true,
      owner_confirmed: false,
      live_ready: false,
      execution_permission_granted: false,
      order_permission_granted: false,
    },
    minimal_live_trial_gate: {
      can_execute_bounded_live_trial: false,
      final_state: 'blocked_missing_owner_live_authorization',
      hard_blockers: ['live_authorization_missing'],
      acknowledgement_blockers: ['strategy_not_proven_profitable'],
      warnings: ['limited_live_observation_sample'],
      live_ready: false,
      execution_intent_created: false,
      order_created: false,
      execution_permission_granted: false,
    },
    architecture_classification: [
      {
        concept: 'StrategyFamily',
        current_item: 'MI-001',
        classification: 'generic_now',
        decision: 'StrategyFamily has no order authority.',
      },
      {
        concept: 'Carrier',
        current_item: 'MI-001-BNB-LONG',
        classification: 'carrier_specific_by_design',
        decision: 'Carrier combines family, symbol, side, and risk cap.',
      },
    ],
    generic_now: ['StrategyFamily', 'BoundedLiveTrialAuthorization'],
    carrier_specific_by_design: ['MI-001-BNB-LONG'],
    technical_debt_later: [],
    not_live_ready_until_explicit_owner_live_authorization: true,
    not_auto_execution_ready: true,
    no_real_funds: true,
    non_permissions: {
      no_live_order: true,
      no_execution_intent: true,
      no_order_creation: true,
      no_runtime_start: true,
      authorization_draft_is_not_order_permission: true,
      warning_acknowledgement_is_not_live_authorization: true,
    },
  };
}

function ownerTrialFlowPayload() {
  return {
    generated_from: 'owner_trial_flow_v1',
    selected_carrier_id: 'MI-001-BNB-LONG',
    carrier: {
      carrier_id: 'MI-001-BNB-LONG',
      strategy_family_id: 'MI-001',
      strategy_id: 'MI-001',
      candidate_id: 'MI-001-BNB-LONG',
      symbol: 'BNBUSDT',
      runtime_symbol: 'BNB/USDT:USDT',
      side: 'long',
      execution_mode: 'owner_confirm_each_entry',
      max_notional: '20',
      quantity: '0.01',
      leverage: '1',
      protection_plan_type: 'single_tp_plus_sl',
      live_ready: false,
      order_permission_granted: false,
    },
    strategy_warnings: [
      ownerTrialWarning('strategy_not_proven_profitable', 'BNB carrier evidence is sufficient for Owner review, not proof of durable alpha.'),
      ownerTrialWarning('limited_live_observation_sample', 'Live read-only observation sample remains small.'),
      ownerTrialWarning('regime_may_be_unfavorable', 'Current regime may differ from historical high-quality samples.'),
      ownerTrialWarning('forward_review_incomplete', 'Forward review is evidence for disclosure, not a permanent execution blocker.'),
      ownerTrialWarning('historical_fragility_known', 'Historical fragility and adverse early path risk must be acknowledged.'),
    ],
    hard_blockers: [
      {
        blocker_id: 'missing_explicit_live_authorization',
        active: true,
        blocks_after_ack: true,
        description: 'Real live / real-funds authorization has not been explicitly granted.',
        source: 'owner_trial_flow',
        classification: 'hard_safety_blocker',
      },
    ],
    acknowledged_warnings: [],
    unacknowledged_warnings: [
      'strategy_not_proven_profitable',
      'limited_live_observation_sample',
      'regime_may_be_unfavorable',
      'forward_review_incomplete',
      'historical_fragility_known',
    ],
    latest_acknowledgement: null,
    authorization_draft: null,
    live_authorization: null,
    authorization_status: 'not_started',
    live_ready: false,
    execution_permission_granted: false,
    order_permission_granted: false,
    execution_intent_created: false,
    order_created: false,
    hard_blockers_remain_blocking: true,
    risk_acknowledgement_is_not_live_authorization: true,
    authorization_draft_is_not_executable: true,
    live_authorization_is_not_execution_intent: true,
    live_authorization_does_not_create_order: true,
    source: 'backend_metadata',
  };
}

function ownerTrialWarning(warning_id: string, description: string) {
  return {
    warning_id,
    severity: 'warning',
    description,
    owner_ack_required: true,
    blocks_after_ack: false,
    classification: 'strategy_warning',
  };
}

function ownerRiskAcknowledgementPayload() {
  return {
    acknowledgement_id: 'ack-unit',
    carrier_id: 'MI-001-BNB-LONG',
    strategy_family_id: 'MI-001',
    acknowledged_warning_codes: [
      'strategy_not_proven_profitable',
      'limited_live_observation_sample',
      'regime_may_be_unfavorable',
      'forward_review_incomplete',
      'historical_fragility_known',
    ],
    owner_id: 'owner',
    acknowledged_at_ms: Date.now(),
    acknowledgement_scope: 'strategy_trial_warnings',
    source: 'owner_console',
    non_live_metadata_only: true,
  };
}

function ownerAuthorizationDraftPayload() {
  return {
    draft_id: 'draft-unit',
    carrier_id: 'MI-001-BNB-LONG',
    strategy_family_id: 'MI-001',
    symbol: 'BNB/USDT:USDT',
    side: 'long',
    max_notional: '20',
    quantity: '0.01',
    leverage: '1',
    protection_plan_type: 'single_tp_plus_sl',
    single_use: true,
    status: 'pending_owner_live_authorization',
    live_ready: false,
    order_permission_granted: false,
    execution_permission_granted: false,
    execution_intent_created: false,
    order_created: false,
    auto_execution_enabled: false,
    consumed: false,
    expires_at_ms: null,
    linked_acknowledgement_id: 'ack-unit',
    created_at_ms: Date.now(),
    updated_at_ms: Date.now(),
    source: 'owner_console',
    non_live_metadata_only: true,
  };
}

function ownerLiveAuthorizationPayload() {
  return {
    authorization_id: 'auth-unit',
    draft_id: 'draft-unit',
    carrier_id: 'MI-001-BNB-LONG',
    strategy_family_id: 'MI-001',
    symbol: 'BNB/USDT:USDT',
    side: 'long',
    max_notional: '20',
    quantity: '0.01',
    leverage: '1',
    protection_plan_type: 'single_tp_plus_sl',
    single_use: true,
    status: 'owner_live_authorized_pending_final_preflight',
    live_authorized: true,
    owner_live_authorized_by: 'owner',
    owner_live_authorized_at_ms: Date.now(),
    live_ready: false,
    order_permission_granted: false,
    execution_permission_granted: false,
    execution_intent_created: false,
    order_created: false,
    auto_execution_enabled: false,
    consumed: false,
    expires_at_ms: null,
    linked_acknowledgement_id: 'ack-unit',
    source_draft_id: 'draft-unit',
    final_preflight_required: true,
    hard_blockers: ['startup_guard_status_unavailable_runtime_not_started'],
    next_executable: false,
    created_at_ms: Date.now(),
    updated_at_ms: Date.now(),
    source: 'owner_console',
    metadata_only: true,
  };
}

function secondCarrierExpansionPayload() {
  return {
    generated_from: 'second_carrier_expansion_v1',
    selected_second_carrier_id: 'TB-BTC-SHORT',
    carriers: [
      {
        carrier_id: 'TB-BTC-SHORT',
        strategy_family: 'TB',
        strategy_id: 'TB-001',
        symbol: 'BTCUSDT',
        runtime_symbol: 'BTC/USDT:USDT',
        side: 'short',
        regime_fit: 'bearish 1-2 month view fit',
        risk_cap_draft: { per_carrier_cap: '20' },
        protection_feasibility: { protection_plan_type: 'single_tp_plus_sl' },
        testnet_rehearsal_gap_summary: ['rehearsal_not_run'],
      },
    ],
    non_permissions: {
      live_ready: false,
      auto_execution_enabled: false,
      order_created: false,
    },
  };
}

function multiCarrierBudgetAuthorizationPayload() {
  return {
    generated_from: 'multi_carrier_budget_authorization_foundation_v1',
    latest_budget_authorization: {
      budget_authorization_id: 'budget-unit',
      allowed_carriers: [
        { carrier_id: 'MI-001-BNB-LONG' },
        { carrier_id: 'TB-BTC-SHORT' },
      ],
      global_budget: '40',
      daily_loss_limit: '10',
      status: 'draft_disabled_pending_owner_authorization',
    },
    eligible_carrier_ids: ['MI-001-BNB-LONG', 'TB-BTC-SHORT'],
    disabled_execution_state: {
      live_ready: false,
      auto_execution_enabled: false,
      order_created: false,
    },
    budget_scope_source: 'pg_metadata',
  };
}

function bnbLiveExecutionBridgePayload() {
  const fact = (state: string, status = 'clear', source = 'unit', evidence: Record<string, unknown> = {}) => ({
    state,
    status,
    source,
    blockers: state === 'clear' ? [] : [`${state}_blocker`],
    evidence,
  });
  return {
    generated_from: 'bnb_live_execution_bridge_dry_run_v1',
    generated_at_ms: Date.now(),
    carrier_id: 'MI-001-BNB-LONG',
    symbol: 'BNB/USDT:USDT',
    side: 'long',
    bridge_status: 'blocked_before_execution_boundary',
    final_preflight_result: 'blocked',
    hard_blockers: ['startup_guard_status_required_before_rehearsal'],
    authorization_state: {
      exists: true,
      status: 'owner_live_authorized_pending_final_preflight',
      live_authorized: true,
      single_use: true,
      unconsumed: true,
      live_ready: false,
      execution_permission_granted: false,
      order_permission_granted: false,
      execution_intent_created: false,
      order_created: false,
    },
    final_gate_read_model: {
      result: 'blocked',
      exact_blockers: ['startup_guard_status_required_before_rehearsal'],
      runtime_safety_state: 'startup_guard_unavailable',
      startup_guard: fact('unavailable', 'unavailable', 'unavailable'),
      gks: fact('clear', 'clear', 'unit_gks', { active: false }),
      account_facts: fact('clear', 'clear', 'unit_account', { freshness: 'fresh', read_only_guarantee: true }),
      bnb_position: fact('clear', 'clear', 'unit_position', { active_position_count: 0 }),
      bnb_open_order: fact('clear', 'clear', 'unit_order', { open_order_count: 0 }),
      persistence_readiness: {
        execution_intents: true,
        orders: true,
        result_review_logging: true,
        source: 'pg_table_audit',
      },
      execution_boundary_status: 'blocked_before_execution_boundary',
      no_order_created: true,
      no_executable_execution_intent_created: true,
      no_permission_granted: true,
    },
    authorization_hard_blockers_snapshot: ['startup_guard_status_unavailable_runtime_not_started'],
    acknowledged_strategy_warnings: [
      'strategy_not_proven_profitable',
      'limited_live_observation_sample',
    ],
    strategy_warnings_block_execution: false,
    execution_plan_preview: {
      status: 'preview_blocked_by_hard_gates',
      authorization_id: 'auth-mi001-bnb',
      draft_id: 'draft-mi001-bnb',
      carrier_id: 'MI-001-BNB-LONG',
      symbol: 'BNB/USDT:USDT',
      side: 'long',
      max_notional: '20',
      quantity: '0.01',
      leverage: '1',
      entry_order: {
        order_type: 'market',
        intended_behavior: 'one-shot BNB entry only after final hard gates',
        quantity: '0.01',
        max_notional: '20',
        leverage: '1',
      },
      protection_plan: {
        plan_type: 'single_tp_plus_sl',
        take_profit_quantity: '0.01',
        stop_loss_quantity: '0.01',
        safety_assumptions: [
          'single TP and SL cover the full preview entry quantity',
          'preview does not grant order permission',
        ],
      },
      expected_record_path: [
        'pg_execution_intents_non_preview_only_after_separate_executable_authorization',
        'pg_orders_after_exchange_write_boundary_only',
        'pg_brc_execution_results',
        'owner_review_record',
      ],
      expected_review_state: 'pending_owner_review_after_execution_result',
      cleanup_behavior_if_protection_attach_fails: 'record failed protection attach and require owner review',
      exact_blockers: ['startup_guard_status_required_before_rehearsal'],
      flags: {
        preview_only: true,
        execution_intent_created: false,
        order_created: false,
        order_permission_granted: false,
        auto_execution_enabled: false,
      },
      executable: false,
    },
    execution_boundary: {
      would_create_execution_intent_if_all_gates_passed: false,
      would_create_order: false,
      order_path_enabled: false,
    },
    table_audit: {
      execution_intents: true,
      orders: true,
      brc_execution_results: true,
    },
    environment_checks: {
      live_environment_valid: true,
      exchange_testnet_false: true,
    },
    preflight_fact_checks: {},
    non_permissions: {
      live_ready: false,
      execution_permission_granted: false,
      order_permission_granted: false,
      execution_intent_created: false,
      order_created: false,
    },
    dry_run_only: true,
  };
}

function bnbGate(gateId: string, gateName: string, currentStatus: string) {
  return {
    gate_id: gateId,
    gate_name: gateName,
    current_status: currentStatus,
    required_for_testnet_rehearsal: true,
    required_for_small_live_trial: true,
    existing_source_or_code_path: 'source',
    gap: `${gateName} gap`,
    recommended_action: `${gateName} action`,
    risk_if_skipped: `${gateName} risk`,
    owner_decision_required: true,
  };
}

function observationRecord(candidateId: string, strategyGroupId: string, symbol: string, signalType: string, sinkStatus = 'preview_not_recorded') {
  return {
    record_id: `${candidateId}-record`,
    candidate_id: candidateId,
    strategy_group_id: strategyGroupId,
    symbol,
    side: signalType === 'would_enter' ? 'long' : 'none',
    evaluated_at_ms: 1770000000000,
    recorded_at_ms: sinkStatus === 'recorded_process_local' ? 1770000001000 : null,
    source: 'strategy_group_live_readonly_observation_v1',
    source_type: 'local_sqlite_fallback',
    market_source: 'local_sqlite_v3_dev_closed_klines_read_only',
    market_bar_timestamp_ms: 1770000000000,
    market_bar_close: '100',
    signal_type: signalType,
    confidence: '0.65',
    reason_codes: ['observe_only_review_required'],
    human_summary: 'observe-only signal record',
    evidence_payload: {},
    signal_snapshot: {},
    invalidation_conditions: [],
    review_windows: ['24h', '72h', '7d'],
    review_status_by_window: { '24h': 'pending_forward_outcome_capture' },
    input_refs: {},
    sink_status: sinkStatus,
    not_order: true,
    not_execution_intent: true,
    no_execution_permission: true,
    no_order_permission: true,
    no_runtime_start: true,
  };
}

function observationCandidate(candidateId: string, strategyGroupId: string, symbol: string, signalType: string) {
  return {
    candidate_id: candidateId,
    strategy_group_id: strategyGroupId,
    symbol,
    side: 'long',
    observation_role: 'owner_review',
    evaluator_glue_status: 'wired_read_only_v1',
    signal_contract: ['no_action', 'would_enter', 'invalid'],
    review_windows: ['24h', '72h', '7d'],
    latest_signal_preview: {
      signal_type: signalType,
      side: signalType === 'would_enter' ? 'long' : 'none',
      not_order: true,
      not_execution_intent: true,
    },
    evidence_payload_fields: ['field'],
    evidence_record_mapping: 'metadata_only_observation_record_ready',
    readiness_status: 'evaluator_ready_requires_runner_binding',
    blockers: ['live observation runner is not started'],
    not_allowed_now: ['trial start', 'execution intent creation', 'order placement'],
    source_refs: [],
  };
}

function groupPayload(overrides: Partial<Record<string, unknown>>) {
  return {
    strategy_group_id: 'GROUP',
    strategy_group_name: 'Group',
    plain_language_summary: 'Owner-readable summary.',
    market_regime_it_eats: 'clean regime',
    market_regime_it_hates: 'hostile regime',
    representative_candidates: [],
    current_status: 'research_pool',
    evidence_summary: 'evidence summary',
    key_risks: ['risk'],
    confidence_flags: ['flag'],
    owner_action_options: ['review'],
    next_recommended_action: 'review',
    not_allowed_now: ['trial start', 'order placement'],
    evidence_reviewability: 'reviewable',
    live_readonly_observation_readiness: 'research_pool_requires_frozen_evaluator',
    bounded_trial_readiness: 'not_current_trial_candidate',
    main_blockers: ['signal glue missing'],
    source_refs: [],
    display_model_only: true,
    not_runtime_source_of_truth: true,
    no_execution_permission: true,
    no_order_permission: true,
    no_runtime_start: true,
    no_automatic_strategy_routing: true,
    ...overrides,
  };
}

function candidatePayload(candidateId: string, strategyGroupId: string, metrics: Record<string, string>, confidenceFlags: string[]) {
  return {
    candidate_id: candidateId,
    strategy_group_id: strategyGroupId,
    symbol: candidateId.includes('BNB') ? 'BNB/USDT:USDT' : candidateId.includes('ETH') ? 'ETH/USDT:USDT' : 'SOL/USDT:USDT',
    side: 'long',
    review_status: 'reviewable',
    evidence_summary: 'candidate evidence',
    metrics,
    limitations: [],
    confidence_flags: confidenceFlags,
    source_refs: [],
  };
}
