// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import AppLayout from '@/src/components/layout/AppLayout';
import {
  AccountOrdersV2,
  AnalysisV2,
  HomeV2,
  IntentsV2,
  StrategyGroupsV2,
  TraceV2,
} from './OwnerConsoleV2';

const mockBrcApi = vi.hoisted(() => ({
  readiness: vi.fn(),
  accountFacts: vi.fn(),
  mi001SolReadiness: vi.fn(),
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
    mockBrcApi.readiness.mockResolvedValue(readinessPayload());
    mockBrcApi.accountFacts.mockResolvedValue(accountFactsPayload());
    mockBrcApi.mi001SolReadiness.mockResolvedValue(mi001Payload());
    mockBrcApi.listStrategyFamilies.mockResolvedValue([]);
    mockBrcApi.listAdmissionDecisions.mockResolvedValue([{ owner_risk_acceptance_id: 'owner-acceptance-1' }]);
    mockBrcApi.listTrialBindings.mockResolvedValue([]);
    mockBrcApi.currentCampaign.mockResolvedValue({ campaign: null, live_ready: false });
    mockBrcApi.reviewPacket.mockResolvedValue(null);
    mockBrcApi.evidence.mockResolvedValue(null);
    mockBrcApi.listOperations.mockResolvedValue({ operations: [], live_ready: false });
    mockBrcApi.logout.mockResolvedValue({ authenticated: false });
  });

  afterEach(() => cleanup());

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

    for (const label of ['首页', '策略组', '执行意图', '账户订单', '复盘分析', '链路追踪']) {
      expect(await screen.findByRole('link', { name: new RegExp(`^${label}$`) })).toBeTruthy();
    }
    expect(await screen.findByRole('button', { name: /实盘只读 · 记录意图.*禁止下单/ })).toBeTruthy();
    for (const oldLabel of ['Command Center', 'Markets & Orders', 'Campaign', 'Review / Evidence', 'Strategy Families', 'Fixed Rehearsal', 'Runtime Control', 'LLM Copilot', 'Workflow', 'Operator', 'Guide', 'Dashboard', 'Ledger', 'Developer Detail', 'Audit Trail', '审计详情']) {
      expect(screen.queryByText(oldLabel)).toBeNull();
    }
  });

  it('renders the home control panel without dangerous buttons', async () => {
    renderWithRouter(<HomeV2 />);

    expect(await screen.findByText(/MI-001 SOL 已完成试验前准备/)).toBeTruthy();
    expect(screen.getAllByText(/MI-001 动量冲击/).length).toBeGreaterThan(0);
    expect(screen.getByText(/运行时启动保护未预检/)).toBeTruthy();
    expect(screen.getAllByText('禁止下单').length).toBeGreaterThan(0);
    expect(screen.getByText('暂无新意图')).toBeTruthy();
    expect(screen.getByText(/没有执行指令，没有订单/)).toBeTruthy();
    expect(screen.getByText('最近执行意图')).toBeTruthy();
    expect(screen.getByText('查看链路追踪')).toBeTruthy();
    assertNoDangerButtons();
  });

  it('renders strategy groups, intents, account orders, analysis, and trace shells', async () => {
    renderWithRouter(<StrategyGroupsV2 />);
    expect((await screen.findAllByText('策略组')).length).toBeGreaterThan(0);
    expect(screen.getByText('策略组货架 / 选择器。这里只用于观察和复盘，不会自动选择策略。')).toBeTruthy();
    expect(screen.getAllByText('MI-001 动量冲击').length).toBeGreaterThan(0);
    expect(screen.getAllByText('MI-001 SOL long').length).toBeGreaterThan(0);
    expect(screen.getAllByText('MI-001 BNB long').length).toBeGreaterThan(0);
    expect(screen.getAllByText('VI-001 ETH long').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Owner Special Observation').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/CPM historical OOS 2021\/2022 negative/).length).toBeGreaterThan(0);
    expect(screen.getAllByText('Trend Breakout').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Pullback Continuation').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Volatility Breakout').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Mean Reversion / Range Boundary').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Tier 1 Data Families').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Funding/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Taker flow/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Attention \/ search/).length).toBeGreaterThan(0);
    cleanup();

    renderWithRouter(<IntentsV2 />);
    expect(await screen.findByText('执行意图')).toBeTruthy();
    expect(screen.getByText('暂无执行意图记录')).toBeTruthy();
    cleanup();

    renderWithRouter(<AccountOrdersV2 />);
    expect(await screen.findByText('账户订单')).toBeTruthy();
    expect(screen.getByText('总权益')).toBeTruthy();
    cleanup();

    renderWithRouter(<AnalysisV2 />);
    expect(await screen.findByText('复盘分析')).toBeTruthy();
    expect(screen.getByText('当前结论')).toBeTruthy();
    cleanup();

    renderWithRouter(<TraceV2 />);
    expect(await screen.findByText('链路追踪')).toBeTruthy();
    expect(screen.getByText('策略候选形成')).toBeTruthy();
    expect(screen.getAllByText('启动保护').length).toBeGreaterThan(0);
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
