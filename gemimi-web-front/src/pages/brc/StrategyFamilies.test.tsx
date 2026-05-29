// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import StrategyFamilies from './StrategyFamilies';

const mockBrcApi = vi.hoisted(() => ({
  listStrategyFamilies: vi.fn(),
  listAdmissionDecisions: vi.fn(),
  listTrialBindings: vi.fn(),
  currentCampaign: vi.fn(),
  mi001SolReadiness: vi.fn(),
}));

vi.mock('@/src/services/api', () => ({
  brcApi: mockBrcApi,
}));

describe('StrategyFamilies', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockBrcApi.listStrategyFamilies.mockResolvedValue([]);
    mockBrcApi.listAdmissionDecisions.mockResolvedValue([]);
    mockBrcApi.listTrialBindings.mockResolvedValue([]);
    mockBrcApi.currentCampaign.mockResolvedValue({ campaign: null, live_ready: false });
    mockBrcApi.mi001SolReadiness.mockResolvedValue({
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
      risk_policy: {},
      readiness: { verdict: 'blocked_startup_guard_runtime_coupled', blockers: [], checks: [] },
      owner_actions: { allowed_actions: [], disabled_actions: [] },
      non_permissions: {},
      startup_guard_action: {},
      terminal_state: 'blocked_until_startup_guard_preflight',
      source_refs: ['brc_strategy_family_registry:MI-001:MI-001-smoke-v0', 'brc_owner_risk_acceptances:MI-001-SOL-LONG-owner-trial-start-approval-v1'],
      live_ready: false,
    });
  });

  afterEach(() => cleanup());

  it('renders MI-001 fallback as read-only without execution controls', async () => {
    render(<StrategyFamilies />);

    expect(await screen.findByText('Strategy Families')).toBeTruthy();
    expect(screen.getByText('Candidate Status Table')).toBeTruthy();
    expect(screen.getAllByText(/MI-001-SOL-LONG/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/SOL\/USDT:USDT \/ long/).length).toBeGreaterThan(0);
    expect(screen.getAllByText('pre-start / accepted / registered').length).toBeGreaterThan(0);
    expect(screen.getAllByText('ready').length).toBeGreaterThan(0);
    expect(screen.getByText('final review complete, blocked by startup guard')).toBeTruthy();
    expect(screen.getByText('live read-only / intent recording / no order')).toBeTruthy();
    expect(screen.getByText(/trial_trade_intent evidence 不等于可交易授权/)).toBeTruthy();
    expect(screen.getAllByText(/Read-only \/ no execution/).length).toBeGreaterThan(0);
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
