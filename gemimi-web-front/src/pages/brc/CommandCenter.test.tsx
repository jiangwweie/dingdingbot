// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import CommandCenter, { OperationPreflightModal } from './CommandCenter';
import type { OperationPreflightState } from './CommandCenter';

const mockBrcApi = vi.hoisted(() => ({
  readiness: vi.fn(),
  operationCapabilities: vi.fn(),
  accountFacts: vi.fn(),
  mi001SolReadiness: vi.fn(),
  currentCampaign: vi.fn(),
  reviewPacket: vi.fn(),
  evidence: vi.fn(),
  confirmOperation: vi.fn(),
  cancelOperation: vi.fn(),
}));

vi.mock('@/src/services/api', () => ({
  brcApi: mockBrcApi,
}));

function planningState(operationType: 'emergency_flatten' | 'emergency_stop_runtime'): OperationPreflightState {
  return {
    loading: false,
    phrase: '',
    error: null,
    result: null,
    preflight: {
      operation_id: `op-${operationType}`,
      preflight_id: `pre-${operationType}`,
      operation_type: operationType,
      decision: 'unavailable',
      summary: operationType === 'emergency_flatten'
        ? 'Emergency flatten preflight planning only.'
        : 'Emergency stop runtime preflight planning only.',
      before: {},
      after: {
        planning_only: true,
        actual_execution_available: false,
        estimated_flatten_impact: operationType === 'emergency_flatten' ? { planned_result_status: 'noop' } : undefined,
        expected_stop_behavior: operationType === 'emergency_stop_runtime'
          ? { does_not_flatten: true, does_not_cancel_orders: true }
          : undefined,
      },
      account_order_summary: {
        source: 'mixed',
        truth_level: 'reconciled',
        reconciliation_status: { status: 'clean' },
        checked_sources: ['local_pg', 'exchange_testnet'],
        mismatch_count: 0,
        evidence_refs: ['account_facts:mixed:reconciled:test'],
        unknown_or_unmanaged_orders: [],
        unknown_or_unmanaged_positions: [],
      },
      runtime_summary: {},
      campaign_summary: {},
      playbook_summary: {},
      risk_summary: {
        warnings: [],
        blockers: [`${operationType} executor unavailable; this preflight is planning only`],
      },
      confirmation_requirement: {
        required: false,
        phrase: null,
        expires_at_ms: Date.now() + 60_000,
        totp_freshness_required: false,
      },
      idempotency_key: `idem-${operationType}`,
      status: 'blocked',
    },
  };
}

function executableStopState(): OperationPreflightState {
  return {
    loading: false,
    phrase: 'CONFIRM_STOP_RUNTIME',
    error: null,
    result: null,
    preflight: {
      operation_id: 'op-emergency_stop_runtime',
      preflight_id: 'pre-emergency_stop_runtime',
      operation_type: 'emergency_stop_runtime',
      decision: 'allow',
      summary: 'Plan emergency runtime stop through Operation authorization; it does not flatten or cancel orders.',
      before: { runtime_state: 'armed' },
      after: {
        planning_only: false,
        actual_execution_available: true,
        does_not_flatten: true,
        does_not_cancel_orders: true,
        expected_stop_behavior: {
          would_stop_runtime: true,
          would_pause_new_strategy_actions: true,
          does_not_flatten: true,
          does_not_cancel_orders: true,
        },
      },
      account_order_summary: {
        source: 'mixed',
        truth_level: 'reconciled',
        reconciliation_status: { status: 'clean' },
        unknown_or_unmanaged_orders: [],
        unknown_or_unmanaged_positions: [],
      },
      runtime_summary: { current_runtime_state: 'armed' },
      campaign_summary: {},
      playbook_summary: {},
      risk_summary: {
        warnings: [],
        blockers: [],
      },
      confirmation_requirement: {
        required: true,
        phrase: 'CONFIRM_STOP_RUNTIME',
        expires_at_ms: Date.now() + 60_000,
        totp_freshness_required: false,
      },
      idempotency_key: 'idem-emergency_stop_runtime',
      status: 'awaiting_confirmation',
    },
  };
}

function flattenDryRunState(): OperationPreflightState {
  return {
    loading: false,
    phrase: 'CONFIRM_FLATTEN_DRY_RUN',
    error: null,
    result: null,
    preflight: {
      operation_id: 'op-emergency_flatten',
      preflight_id: 'pre-emergency_flatten',
      operation_type: 'emergency_flatten',
      decision: 'warn',
      summary: 'Generate and confirm an emergency flatten dry-run record only.',
      before: {},
      after: {
        dry_run_only: true,
        actual_execution: false,
        actual_execution_available: false,
        dry_run_plan: {
          dry_run_id: 'flatdry-test',
          cancel_order_candidates: [
            {
              candidate_id: 'cancel_candidate_1',
              candidate_type: 'cancel_open_order',
              candidate_only: true,
              executable_order_request: false,
            },
          ],
          close_position_candidates: [
            {
              candidate_id: 'close_candidate_1',
              candidate_type: 'close_position',
              candidate_only: true,
              executable_order_request: false,
            },
          ],
          estimated_actions_count: 2,
        },
      },
      account_order_summary: {
        source: 'mixed',
        truth_level: 'reconciled',
        reconciliation_status: { status: 'clean' },
        unknown_or_unmanaged_orders: [],
        unknown_or_unmanaged_positions: [],
      },
      runtime_summary: {},
      campaign_summary: {},
      playbook_summary: {},
      risk_summary: {
        warnings: ['actual flatten execution remains unavailable'],
        blockers: [],
      },
      confirmation_requirement: {
        required: true,
        phrase: 'CONFIRM_FLATTEN_DRY_RUN',
        expires_at_ms: Date.now() + 60_000,
        totp_freshness_required: false,
      },
      idempotency_key: 'idem-emergency_flatten',
      status: 'awaiting_confirmation',
    },
  };
}

describe('OperationPreflightModal emergency planning', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockBrcApi.readiness.mockResolvedValue(readinessPayload());
    mockBrcApi.operationCapabilities.mockResolvedValue({ capabilities: [], live_ready: false });
    mockBrcApi.accountFacts.mockResolvedValue({ source: 'mixed', truth_level: 'exchange_read', account_summary: {}, reconciliation_status: {}, live_ready: false });
    mockBrcApi.mi001SolReadiness.mockResolvedValue(mi001Payload());
    mockBrcApi.currentCampaign.mockResolvedValue({ campaign: null, live_ready: false });
    mockBrcApi.reviewPacket.mockResolvedValue({ review_packet: { final_pre_start_review: true } });
    mockBrcApi.evidence.mockResolvedValue({ evidence: { signal_evaluation: 'not_reported' } });
  });

  afterEach(() => {
    cleanup();
  });

  it('renders owner-view safety facts without trial/order/live buttons', async () => {
    render(<CommandCenter />);

    expect(await screen.findByText('Execution Permission')).toBeTruthy();
    expect(screen.getByText('MI-001 SOL Golden Path')).toBeTruthy();
    expect(screen.getByText(/MI-001 SOL 已完成试验前准备和最终 review/)).toBeTruthy();
    expect(screen.getByText(/当前系统处于 Live 只读 \/ Intent Recording，不能下单/)).toBeTruthy();
    expect(screen.getByText('trial')).toBeTruthy();
    expect(screen.getByText('not started')).toBeTruthy();
    expect(screen.getAllByText('none').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/runtime-owned startup guard blocker/)).toBeTruthy();
    expect(screen.getByText(/不是策略失败，不是 PG 注册失败，也不是账户事实失败/)).toBeTruthy();
    expect(screen.getByText(/离线报告、PG metadata、Markdown packet/)).toBeTruthy();
    expect(screen.getAllByText(/Live 只读 \/ Intent Recording/).length).toBeGreaterThan(0);
    [
      /Start Trial/i,
      /Place Order/i,
      /Enable Live Trading/i,
      /Execute Order/i,
      /Create Execution Intent/i,
      /Withdraw/i,
      /Transfer/i,
      /Flatten Now/i,
      /Cancel Order/i,
      /Start Runtime/i,
    ].forEach((name) => {
      expect(screen.queryByRole('button', { name })).toBeNull();
    });
  });

  it('renders flatten dry-run honestly and does not show actual flatten execution', () => {
    render(
      <OperationPreflightModal
        state={flattenDryRunState()}
        onClose={() => undefined}
        onStateChange={() => undefined}
        onRefresh={async () => undefined}
      />,
    );

    expect(screen.getAllByText('emergency_flatten').length).toBeGreaterThan(0);
    expect(screen.getByText(/Dry-run only. No orders will be cancelled/)).toBeTruthy();
    expect(screen.getByText(/No positions will be closed/)).toBeTruthy();
    expect(screen.getByText(/diagnostic candidates, not executable actions/)).toBeTruthy();
    expect(screen.getByText('actual_execution')).toBeTruthy();
    expect(screen.getAllByText('unavailable').length).toBeGreaterThan(0);
    expect(screen.getByText('checked_sources')).toBeTruthy();
    expect(screen.getByText('mismatch_count')).toBeTruthy();
    expect(screen.getByText('evidence_refs')).toBeTruthy();
    expect(screen.getByText('Dry-run candidates')).toBeTruthy();
    expect((screen.getByText('Confirm dry-run record') as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByRole('button', { name: /^Flatten$/i })).toBeNull();
  });

  it('renders stop runtime planning without flatten or cancel implication', () => {
    render(
      <OperationPreflightModal
        state={planningState('emergency_stop_runtime')}
        onClose={() => undefined}
        onStateChange={() => undefined}
        onRefresh={async () => undefined}
      />,
    );

    expect(screen.getAllByText('emergency_stop_runtime').length).toBeGreaterThan(0);
    expect(screen.getByText(/Stop Runtime does not flatten or cancel orders by itself/)).toBeTruthy();
    expect(screen.getByText(/Stop Runtime does not flatten positions/)).toBeTruthy();
    expect(screen.getByText(/Stop Runtime does not cancel orders/)).toBeTruthy();
    expect((screen.getByText('Confirm once') as HTMLButtonElement).disabled).toBe(true);
  });

  it('enables stop runtime confirm only when backend preflight is executable and phrase matches', () => {
    render(
      <OperationPreflightModal
        state={executableStopState()}
        onClose={() => undefined}
        onStateChange={() => undefined}
        onRefresh={async () => undefined}
      />,
    );

    expect(screen.getByText('actual_execution')).toBeTruthy();
    expect(screen.getByText('available')).toBeTruthy();
    expect(screen.getByText(/Stop Runtime does not flatten positions/)).toBeTruthy();
    expect(screen.getByText(/Stop Runtime does not cancel orders/)).toBeTruthy();
    expect((screen.getByText('Confirm once') as HTMLButtonElement).disabled).toBe(false);
  });
});

function readinessPayload() {
  return {
    mode: 'brc_ready',
    current_conclusion: 'Owner view',
    why: ['MI-001 is blocked by startup guard runtime coupling.'],
    account_impact: 'none',
    next_step: 'Review blocker.',
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
    risk_account_summary: {
      exposure_orders: {
        flatness_proof: { all_local_flat: true },
        active_position_count: 0,
        open_order_count: 0,
      },
    },
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
    evidence: {
      signal_count: 8135,
      mean_72h: '1.9531',
      positive_rate_72h: '0.5175',
      mean_7d: '4.7372',
      positive_rate_7d: '0.5398',
      limitations: ['research evidence is not execution permission'],
    },
    risk_policy: {
      capital_source: 'dedicated_subaccount',
      account_equity: '4663.39779623',
      available_margin: '3652.57096292',
      max_leverage: 5,
      operation_layer_notional_cap: '18262.85481460',
      max_notional_rule: 'min(...)',
      max_total_loss_rule: 'current_dedicated_subaccount_equity',
      prohibitions: ['no_transfer'],
    },
    readiness: {
      verdict: 'blocked_startup_guard_runtime_coupled',
      blockers: ['StartupTradingGuardService is runtime-owned and is not armed in this console process'],
      checks: [
        { check: 'PG registration', status: 'pass', evidence: 'PG metadata applied', blocking: false },
        { check: 'Startup guard', status: 'blocked', evidence: 'runtime-owned guard not armed', blocking: true },
      ],
    },
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
      endpoint: '/api/brc/readiness/startup-guard/preflight-arm',
      label: 'Arm startup guard preflight',
      enabled: false,
      enabled_when: [],
      safety_text: 'readiness only',
      does_not_start_trial: true,
      does_not_create_execution_intent: true,
      does_not_place_order: true,
    },
    terminal_state: 'blocked_until_startup_guard_preflight',
    source_refs: ['brc_strategy_family_registry:MI-001:MI-001-smoke-v0', 'brc_owner_risk_acceptances:MI-001-SOL-LONG-owner-trial-start-approval-v1'],
    live_ready: false,
  };
}
