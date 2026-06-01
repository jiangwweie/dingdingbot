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
  strategyGroupReviewability: vi.fn(),
  strategyGroupLiveObservationV1: vi.fn(),
  strategyGroupObservationCasesV1: vi.fn(),
  mi001BnbTrialReadinessGap: vi.fn(),
  strategyTrialReadinessV1: vi.fn(),
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
    mockBrcApi.strategyGroupReviewability.mockResolvedValue(strategyGroupReviewabilityPayload());
    mockBrcApi.strategyGroupLiveObservationV1.mockResolvedValue(liveObservationPayload());
    mockBrcApi.strategyGroupObservationCasesV1.mockResolvedValue(observationCaseQueuePayload());
    mockBrcApi.mi001BnbTrialReadinessGap.mockResolvedValue(bnbTrialGapPayload());
    mockBrcApi.strategyTrialReadinessV1.mockResolvedValue(strategyTrialReadinessPayload());
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
    expect(screen.getByText('Primary Strategy Groups')).toBeTruthy();
    expect(screen.getByText(/Exactly six primary groups/)).toBeTruthy();
    expect(screen.getByText('Secondary / Extended Shelf')).toBeTruthy();
    expect(screen.getAllByText('live_readonly_observation_v1_evaluator_ready_requires_runner_binding').length).toBeGreaterThan(0);
    expect(screen.getAllByText('coverage_repaired_not_runtime_ready').length).toBeGreaterThan(0);
    expect(screen.getAllByText('VI-001 ETH long').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Owner Special Observation').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/CPM historical OOS 2021\/2022 was negative/).length).toBeGreaterThan(0);
    expect(screen.getAllByText('not_proven_alpha').length).toBeGreaterThan(0);
    expect(screen.getAllByText('not_runtime_eligible_by_default').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Trend Breakout').length).toBeGreaterThan(0);
    expect(screen.getAllByText('research_pool / keep_for_later').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Pullback Continuation').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Volatility Breakout').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Mean Reversion / Range Boundary').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Tier 1 Data Families').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Funding/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Taker flow/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Attention \/ search/).length).toBeGreaterThan(0);
    expect(screen.getByText('Candidate Evidence Comparison')).toBeTruthy();
    expect(screen.getByText('Live Read-only Observation Readiness')).toBeTruthy();
    expect(screen.getByText('Observation Case Queue v1')).toBeTruthy();
    expect(screen.getAllByText('MI-001-BNB-LONG-live-case-001').length).toBeGreaterThan(0);
    expect(screen.getAllByText('pending_forward_review').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/no_chase_required/).length).toBeGreaterThan(0);
    expect(screen.queryByText('CPM-RO-001:future-would-enter')).toBeNull();
    expect(screen.getByText('MI-001 BNB Trial Readiness Gap')).toBeTruthy();
    expect(screen.getAllByText('not_testnet_ready_not_live_ready').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/BNB Operation Layer cap/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/missing_bnb_specific_cap/).length).toBeGreaterThan(0);
    expect(screen.getByText('Strategy Trial Readiness Framework')).toBeTruthy();
    expect(screen.getAllByText('testnet_rehearsal_not_ready_with_explicit_blockers').length).toBeGreaterThan(0);
    expect(screen.getAllByText('owner_confirm_each_entry').length).toBeGreaterThan(0);
    expect(screen.getAllByText('websocket not required').length).toBeGreaterThan(0);
    expect(screen.getAllByText('MI-001-BNB-LONG').length).toBeGreaterThan(0);
    expect(screen.getAllByText('CPM-RO-001').length).toBeGreaterThan(0);
    expect(screen.getAllByText('wired_read_only_v1').length).toBeGreaterThan(0);
    expect(screen.getByText('local_sqlite_v3_dev_closed_klines_read_only')).toBeTruthy();
    expect(screen.getByText('process_local_sink_available_not_recorded_by_get')).toBeTruthy();
    expect(screen.getByText(/MI\/CPM evaluator glue now produces read-only current signal records/)).toBeTruthy();
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
      testnet_rehearsal_requires_owner_authorization: true,
    },
    preflight_result: {
      status: 'blocked',
      blockers: ['active_position_check_required_before_rehearsal', 'gks_status_required_before_rehearsal'],
      warnings: ['owner_testnet_authorization_missing'],
      evidence: {
        requested_symbol: 'BNBUSDT',
        requested_side: 'long',
        requested_mode: 'owner_confirm_each_entry',
        live_trading_requested: false,
        auto_execution_enabled: false,
      },
      next_owner_action: 'Resolve blockers before Owner can authorize testnet same-path rehearsal.',
      execution_intent_created: false,
      order_created: false,
      live_order_created: false,
      execution_permission_granted: false,
    },
    owner_decision_state: {
      owner_authorization_status: 'missing',
      owner_authorization_required: true,
      owner_can_authorize_testnet_rehearsal_next: false,
      allowed_decisions: ['continue_observation_only', 'prepare_owner_authorized_testnet_rehearsal'],
    },
    rehearsal_readiness_state: {
      testnet_rehearsal_status: 'blocked',
      live_status: 'blocked',
      auto_execution_status: 'disabled',
      same_path_rehearsal: true,
      requires_owner_authorization: true,
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
    readiness_verdict: 'testnet_rehearsal_not_ready_with_explicit_blockers',
    blockers: ['active_position_check_required_before_rehearsal', 'gks_status_required_before_rehearsal'],
    warnings: ['owner_testnet_authorization_missing'],
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
