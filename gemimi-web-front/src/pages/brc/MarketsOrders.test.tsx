// @vitest-environment jsdom

import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import MarketsOrders from './MarketsOrders';

const mockBrcApi = vi.hoisted(() => ({
  readiness: vi.fn(),
  accountFacts: vi.fn(),
}));

vi.mock('@/src/services/api', () => ({
  brcApi: mockBrcApi,
}));

function readinessPayload() {
  return {
    mode: 'brc_ready',
    current_conclusion: 'Ready for read-only account review.',
    why: [],
    account_impact: 'none',
    next_step: 'Review account facts',
    available_actions: [],
    disabled_actions: [],
    environment_boundary: {},
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
    source: 'local_pg',
    truth_level: 'summary',
    generated_at_ms: Date.now(),
    evidence_refs: ['account_facts:local_pg:summary:test'],
    checked_sources: ['local_pg'],
    source_snapshots: {
      local_pg: { available: true, position_count: 0, open_order_count: 0 },
      exchange_testnet: { available: false },
      exchange_live: { available: false, reason: 'forbidden in Owner Console account facts slice' },
    },
    reconciliation_checked_at_ms: Date.now(),
    mismatch_count: 0,
    unknown_unmanaged_counts: { orders: 0, positions: 0 },
    account_summary: {
      active_position_count: 0,
      open_order_count: 0,
      all_local_flat: true,
      complete_exchange_account_truth: false,
    },
    positions: [],
    open_orders: [],
    recent_orders: [],
    recent_fills: [],
    exposure_by_symbol: {
      'ETH/USDT:USDT': {
        display_symbol: 'ETHUSDT',
        position_count: 0,
        open_order_count: 0,
        local_flat: true,
        source: 'local_pg',
        truth_level: 'summary',
      },
    },
    unknown_or_unmanaged_orders: [],
    unknown_or_unmanaged_positions: [],
    connection_health: {
      local_pg: { available: true },
      exchange_testnet_read: { available: false },
      exchange_live_read: { available: false },
      mutation_enabled: false,
    },
    reconciliation_status: {
      status: 'not_available',
      checked_sources: ['local_pg'],
      mismatches: [],
      limitations: ['No exchange read source is wired.'],
    },
    limitations: ['Current view is local BRC summary, not complete exchange account truth.'],
    warnings: [],
    blockers: [],
    live_ready: false,
  };
}

describe('MarketsOrders', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockBrcApi.readiness.mockResolvedValue(readinessPayload());
    mockBrcApi.accountFacts.mockResolvedValue(accountFactsPayload());
  });

  it('renders local_pg summary honestly without fake fills or full account truth', async () => {
    render(<MarketsOrders />);

    expect(await screen.findByText('Account Facts')).toBeTruthy();
    expect(screen.getAllByText('Current view is local BRC summary, not complete exchange account truth.').length).toBeGreaterThan(0);
    expect(screen.getAllByText('local_pg').length).toBeGreaterThan(0);
    expect(screen.getAllByText('summary').length).toBeGreaterThan(0);
    expect(screen.getAllByText('not_available').length).toBeGreaterThan(0);
    expect(screen.getByText('Evidence Summary')).toBeTruthy();
    expect(screen.getByText('checked_sources')).toBeTruthy();
    expect(screen.getByText('mismatches')).toBeTruthy();
    expect(screen.getByText('Evidence refs')).toBeTruthy();
    expect(screen.getByText('Recent orders are unavailable; they are not mocked.')).toBeTruthy();
    expect(screen.getByText('Recent fills are unavailable; they are not mocked.')).toBeTruthy();
    expect(screen.getByText(/Cannot place orders, cancel orders, close positions, flatten, withdraw, transfer, enable live/)).toBeTruthy();
    expect(screen.queryByText('Complete exchange account truth')).toBeNull();
  });
});
