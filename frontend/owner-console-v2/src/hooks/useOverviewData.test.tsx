// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useOverviewData } from './useOverviewData';
import * as overviewApi from '../api/overviewApi';
import * as controlsApi from '../api/controlsApi';
import * as ticketsApi from '../api/ticketsApi';

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function renderHook<T>(hook: () => T) {
  const result = { current: null as unknown as T };
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  const TestComponent = () => {
    result.current = hook();
    return null;
  };

  act(() => {
    root.render(
      <QueryClientProvider client={queryClient}>
        <TestComponent />
      </QueryClientProvider>
    );
  });

  return {
    result,
    unmount: () => {
      act(() => {
        root.unmount();
      });
      container.remove();
      queryClient.clear();
    },
  };
}

describe('useOverviewData - Truthful Attention & Protection Semantics', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does NOT synthesize a global protection health assertion when active ticket has unconfirmed protection', async () => {
    const nowMs = Date.now();

    vi.spyOn(overviewApi, 'fetchOverview').mockResolvedValue({
      code: 0,
      message: 'ok',
      data: {
        account_snapshot: {
          wallet_balance: '2450.00',
          available_balance: '1800.00',
          margin_mode: 'cross',
          updated_at_ms: nowMs - 60000,
        },
        active_ticket_count: 2,
        active_ticket_ids: ['t-ltc', 't-sol'],
        admitted_signal_count: 6,
        rejected_signal_count: 2,
        today_signal_count: 8,
        execution_incident_count: 0,
        ticket_capacity: 1,
        observed_at_ms: nowMs,
        conclusion: {
          level: 'no_action',
          summary: null,
        },
        attention_summary: [],
        evidence: [],
        notification_delivery: {
          channel_state: 'configured',
          pending_count: 0,
          pending_count_capped: false,
          failed_count: 0,
          failed_count_capped: false,
          last_accepted_at_ms: nowMs - 1800000,
        },
        today_net_pnl: { value: '342.50', unit: 'USDT', unavailable_reason: null },
        today_net_r: { value: '2.85', unit: 'R', unavailable_reason: null },
        performance: {
          from_ms: nowMs - 36000000,
          confirmed_count: 6,
          sample_count: 6,
          win_count: 4,
          loss_count: 2,
          breakeven_count: 0,
          unreviewed_count: 0,
          verified_totals: {
            net_pnl: { value: '342.50', unit: 'USDT' },
            net_r: { value: '2.85', unit: 'R' },
            gross_pnl: { value: '380.00', unit: 'USDT' },
            fees: { value: '-37.50', unit: 'USDT' },
            funding: { value: '0.00', unit: 'USDT' },
          },
          by_strategy_group: {},
          metric_coverage: {},
        },
      },
      freshness: 'fresh',
      generated_at: new Date(nowMs).toISOString(),
      snapshot_id: 'snap-normal',
    });

    vi.spyOn(controlsApi, 'fetchControls').mockResolvedValue({
      account_capacity: {
        max_concurrent_tickets: 3,
        strategy_side_active_counts: {},
      },
      current_operation: null,
      dynamic_selection: null,
      events: [],
      generated_at_ms: nowMs,
      global_entry: {
        configured_state: 'enabled',
        effective_state: 'enabled',
      },
      recent_operations: [],
      runtime_entry_authority: {
        venue_id: 'binance-usdm',
        account_id: 'primary',
        status: 'ready',
      },
      strategies: [],
    });

    vi.spyOn(ticketsApi, 'fetchTickets').mockResolvedValue({
      code: 0,
      message: 'ok',
      data: {
        items: [
          {
            ticket_id: 't-ltc',
            strategy_group_id: 'BRF2-001',
            event_spec_id: 'event:brf2-001',
            exchange_instrument_id: 'binance-usdm:LTCUSDT:perpetual',
            position_side: 'short',
            ticket_status: 'active',
            terminal_at_ms: null,
            issued_at_ms: nowMs - 9910000,
            aggregate_status: 'position_protected',
            lifecycle_stage: 'protection',
            completed_stage_count: 4,
            total_stage_count: 8,
            management_mode: 'AUTO',
            manual_risk_reason: null,
            net_pnl: { value: '165.00', unit: 'USDT' },
            net_r: { value: '1.24', unit: 'R' },
            gross_pnl: { value: '170.00', unit: 'USDT' },
            fees: { value: '-5.00', unit: 'USDT' },
            funding: { value: '0.00', unit: 'USDT' },
            attention_items: [],
            evidence: [],
          },
          {
            ticket_id: 't-sol',
            strategy_group_id: 'CPM-RO-001',
            event_spec_id: 'event:cpm-002',
            exchange_instrument_id: 'binance-usdm:SOLUSDT:perpetual',
            position_side: 'long',
            ticket_status: 'active',
            terminal_at_ms: null,
            issued_at_ms: nowMs - 3600000,
            aggregate_status: 'entry_submitted',
            lifecycle_stage: 'entry',
            completed_stage_count: 2,
            total_stage_count: 8,
            management_mode: 'AUTO',
            manual_risk_reason: null,
            net_pnl: { value: null, unit: 'USDT' },
            net_r: { value: null, unit: 'R' },
            gross_pnl: { value: null, unit: 'USDT' },
            fees: { value: null, unit: 'USDT' },
            funding: { value: null, unit: 'USDT' },
            attention_items: ['入场回报已确认，等待初始止损挂单事实确认'],
            evidence: [],
          },
        ],
        next_cursor: null,
      },
    });

    const { result, unmount } = renderHook(() => useOverviewData());

    // Wait for queries to resolve
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

    expect(result.current.isLoading).toBe(false);

    // Verify SOL is unconfirmed protection
    const solEpisode = result.current.episodes.find((e) => e.symbol === 'SOLUSDT');
    expect(solEpisode).toBeDefined();
    expect(solEpisode?.is_protected).toBe(false);
    expect(solEpisode?.protection_state).toBe('保护证据不足 · entry_submitted');

    // Regression Assertion: attentionList must NOT claim global protection health
    const attentionList = result.current.attentionList;
    const hasProtectionHealthClaim = attentionList.some(
      (item) =>
        item.title.includes('保护策略处于健康状态') ||
        (item.detail && item.detail.includes('保护策略处于健康状态')) ||
        item.title.includes('一切正常，无需介入') ||
        item.id === 'clean-state'
    );

    expect(hasProtectionHealthClaim).toBe(false);
    unmount();
  });

  it('keeps attentionList strictly bounded to real facts and never creates synthetic clean-state', async () => {
    const nowMs = Date.now();

    vi.spyOn(overviewApi, 'fetchOverview').mockResolvedValue({
      code: 0,
      message: 'ok',
      data: {
        account_snapshot: {
          wallet_balance: '2000.00',
          available_balance: '2000.00',
          margin_mode: 'cross',
          updated_at_ms: nowMs,
        },
        active_ticket_count: 0,
        active_ticket_ids: [],
        admitted_signal_count: 0,
        rejected_signal_count: 0,
        today_signal_count: 0,
        execution_incident_count: 0,
        ticket_capacity: 3,
        observed_at_ms: nowMs,
        conclusion: { level: 'no_action', summary: null },
        attention_summary: [],
        evidence: [],
        notification_delivery: {
          channel_state: 'configured',
          pending_count: 0,
          pending_count_capped: false,
          failed_count: 0,
          failed_count_capped: false,
          last_accepted_at_ms: null,
        },
        today_net_pnl: { value: null, unit: 'USDT', unavailable_reason: null },
        today_net_r: { value: null, unit: 'R', unavailable_reason: null },
        performance: {
          from_ms: nowMs - 36000000,
          confirmed_count: 0,
          sample_count: 0,
          win_count: 0,
          loss_count: 0,
          breakeven_count: 0,
          unreviewed_count: 0,
          verified_totals: {
            net_pnl: { value: null, unit: 'USDT' },
            net_r: { value: null, unit: 'R' },
            gross_pnl: { value: null, unit: 'USDT' },
            fees: { value: null, unit: 'USDT' },
            funding: { value: null, unit: 'USDT' },
          },
          by_strategy_group: {},
          metric_coverage: {},
        },
      },
      freshness: 'fresh',
      generated_at: new Date(nowMs).toISOString(),
      snapshot_id: 'snap-empty',
    });

    vi.spyOn(controlsApi, 'fetchControls').mockResolvedValue({
      account_capacity: {
        max_concurrent_tickets: 3,
        strategy_side_active_counts: {},
      },
      current_operation: null,
      dynamic_selection: null,
      events: [],
      generated_at_ms: nowMs,
      global_entry: {
        configured_state: 'enabled',
        effective_state: 'enabled',
      },
      recent_operations: [],
      runtime_entry_authority: {
        venue_id: 'binance-usdm',
        account_id: 'primary',
        status: 'ready',
      },
      strategies: [],
    });

    vi.spyOn(ticketsApi, 'fetchTickets').mockResolvedValue({
      code: 0,
      message: 'ok',
      data: { items: [], next_cursor: null },
    });

    const { result, unmount } = renderHook(() => useOverviewData());

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

    // attentionList should be an empty array, NOT containing any synthetic items
    expect(result.current.attentionList).toEqual([]);
    unmount();
  });
});
