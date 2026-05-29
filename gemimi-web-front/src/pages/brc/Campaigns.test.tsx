// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Campaigns from './Campaigns';

const mockBrcApi = vi.hoisted(() => ({
  readiness: vi.fn(),
  currentCampaign: vi.fn(),
  listAdmissionDecisions: vi.fn(),
  listTrialBindings: vi.fn(),
  evidence: vi.fn(),
  reviewPacket: vi.fn(),
  nextEligibility: vi.fn(),
}));

vi.mock('@/src/services/api', () => ({
  brcApi: mockBrcApi,
}));

describe('Campaigns owner-readable empty state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockBrcApi.readiness.mockResolvedValue(readinessPayload());
    mockBrcApi.currentCampaign.mockResolvedValue({ campaign: null, live_ready: false });
    mockBrcApi.listAdmissionDecisions.mockResolvedValue([]);
    mockBrcApi.listTrialBindings.mockResolvedValue([]);
    mockBrcApi.evidence.mockResolvedValue(null);
    mockBrcApi.reviewPacket.mockResolvedValue(null);
    mockBrcApi.nextEligibility.mockResolvedValue(null);
  });

  afterEach(() => cleanup());

  it('explains that no campaign exists because trial has not started', async () => {
    render(
      <MemoryRouter>
        <Campaigns />
      </MemoryRouter>,
    );

    expect((await screen.findAllByText(/当前没有已启动 Campaign/)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/MI-001 SOL 仍处于 pre-start readiness 阶段/).length).toBeGreaterThan(0);
    expect(screen.getByText(/trial 未启动，所以没有可复盘 campaign/)).toBeTruthy();
    expect(screen.getByText(/这不是 campaign 数据丢失/)).toBeTruthy();
    expect(screen.getAllByText(/不会要求 Owner 手填 Campaign ID/).length).toBeGreaterThan(0);
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
    why: ['MI-001 SOL trial not started.'],
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
