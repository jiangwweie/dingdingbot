// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Review from './Review';

const mockBrcApi = vi.hoisted(() => ({
  readiness: vi.fn(),
  reviewPacket: vi.fn(),
  evidence: vi.fn(),
  accountFacts: vi.fn(),
  mi001SolReadiness: vi.fn(),
  listAdmissionDecisions: vi.fn(),
  listTrialBindings: vi.fn(),
  nextEligibility: vi.fn(),
  preflightOperation: vi.fn(),
  confirmOperation: vi.fn(),
  cancelOperation: vi.fn(),
}));

vi.mock('@/src/services/api', () => ({
  brcApi: mockBrcApi,
}));

describe('Review owner-readable evidence conclusion', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockBrcApi.readiness.mockResolvedValue(readinessPayload());
    mockBrcApi.reviewPacket.mockResolvedValue({ review_packet: { final_pre_start_review: true } });
    mockBrcApi.evidence.mockResolvedValue(null);
    mockBrcApi.accountFacts.mockResolvedValue({ source: 'mixed', truth_level: 'exchange_read', account_summary: {} });
    mockBrcApi.mi001SolReadiness.mockResolvedValue(mi001Payload());
    mockBrcApi.listAdmissionDecisions.mockResolvedValue([]);
    mockBrcApi.listTrialBindings.mockResolvedValue([]);
    mockBrcApi.nextEligibility.mockResolvedValue(null);
  });

  afterEach(() => cleanup());

  it('renders final pre-start conclusion and keeps trial intent as evidence only', async () => {
    render(<Review />);

    expect(await screen.findByText(/Final pre-start review 已完成/)).toBeTruthy();
    expect(screen.getByText(/Review \/ Evidence 仅用于复盘和验收，不授权 execution intent 或 order/)).toBeTruthy();
    expect(screen.getByText(/Startup Guard runtime-coupled blocker 是 runtime-owned safety blocker，不是策略失败/)).toBeTruthy();
    expect(screen.getAllByText(/not reported yet/).length).toBeGreaterThan(0);
    expect(screen.getByText(/trial_trade_intent 只是 evidence，不是 order/)).toBeTruthy();
    expect(screen.getByText('execution intent')).toBeTruthy();
    expect(screen.getByText('order')).toBeTruthy();
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
});

function readinessPayload() {
  return {
    mode: 'brc_ready',
    current_conclusion: 'Owner view',
    why: ['Review unavailable because campaign has not started.'],
    account_impact: 'none',
    next_step: 'Review blocker.',
    available_actions: [
      {
        action_id: 'write_review_decision',
        label: 'Write review decision',
        enabled: false,
        disabled_reason: 'No latest campaign because trial has not started.',
        requires_confirmation: false,
      },
    ],
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
    latest_campaign: null,
    risk_account_summary: {},
    strategy_playbook_summary: {},
    action_cards: [],
    global_cutoff_controls: [],
    runtime_summary: {},
    review_summary: { review_available: false, latest_review_present: false },
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
    evidence: { signal_count: 8135, mean_72h: '1.9531', positive_rate_72h: '0.5175', mean_7d: '4.7372', positive_rate_7d: '0.5398', limitations: [] },
    risk_policy: { account_equity: '4663.39779623' },
    readiness: { verdict: 'blocked_startup_guard_runtime_coupled', blockers: [], checks: [] },
    owner_actions: { allowed_actions: [], disabled_actions: [] },
    non_permissions: {},
    startup_guard_action: {},
    terminal_state: 'blocked_until_startup_guard_preflight',
    source_refs: [],
    live_ready: false,
  };
}
