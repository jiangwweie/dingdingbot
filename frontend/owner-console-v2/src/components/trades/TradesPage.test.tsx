// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TradesPage } from './TradesPage';
import { ActiveTradeCard } from './ActiveTradeCard';
import { CompletedTradeTable } from './CompletedTradeTable';
import { TradesFilterBar } from './TradesFilterBar';
import { useTradesFilterState } from '../../hooks/useUrlSearchParams';
import * as ticketsApi from '../../api/ticketsApi';
import * as overviewApi from '../../api/overviewApi';
import * as performanceApi from '../../api/performanceApi';
import type { TradeEpisode } from '../../types/trades';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: ReturnType<typeof createRoot> | undefined;
let container: HTMLDivElement;

afterEach(() => {
  act(() => root?.unmount());
  root = undefined;
  container?.remove();
  vi.restoreAllMocks();
});

function render(element: React.ReactNode) {
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root!.render(element);
  });
}

describe('Trades Page & Components Product Convergence', () => {
  it('ActiveTradeCard does NOT guarantee existing TP1/stop orders remain valid on MANUAL takeover and preserves supplemental risk items', () => {
    const manualEp: TradeEpisode = {
      ticket_id: 'ticket:manual-001',
      strategy_id: 'CPM-RO-001',
      strategy_name_zh: '均线回踩做多',
      symbol: 'BTCUSDT',
      side: 'long',
      lifecycle_stage: 'manual',
      lifecycle_stage_zh: '人工管理',
      completed_stage_count: 4,
      total_stage_count: 8,
      ticket_status: 'active',
      issued_at_ms: 1700000000000,
      issued_at_formatted: '09:00:00',
      terminal_at_ms: null,
      closed_at_formatted: null,
      duration_formatted: '1h',
      outcome: 'active',
      outcome_zh: '持仓中',
      net_pnl_formatted: '--',
      net_pnl_is_positive: null,
      net_r_formatted: '--',
      net_r_is_positive: null,
      net_pnl_is_gross: false,
      exit_reason: null,
      exit_reason_zh: '—',
      is_protected: false,
      protection_state: '人工管理 · 保护待核实',
      attention_items: ['整笔已转人工管理 · 外部干预触发', '整笔已转人工管理；止损已撤销，当前没有保护单'],
      evidence: [],
      raw_item: {
        ticket_id: 'ticket:manual-001',
        strategy_group_id: 'CPM-RO-001',
        event_spec_id: 'evt-1',
        exchange_instrument_id: 'binance-usdm:BTCUSDT:perpetual',
        position_side: 'long',
        ticket_status: 'active',
        terminal_at_ms: null,
        issued_at_ms: 1700000000000,
        aggregate_status: 'position_protected',
        lifecycle_stage: 'manual',
        completed_stage_count: 4,
        total_stage_count: 8,
        management_mode: 'MANUAL',
        manual_risk_reason: 'MANUAL_TAKEOVER_ACTIVE_ON_SYMBOL: BTCUSDT',
        management_orders: [],
        net_pnl: { value: null, unit: 'USDT' },
        net_r: { value: null, unit: 'R' },
        gross_pnl: { value: null, unit: 'USDT' },
        fees: { value: null, unit: 'USDT' },
        funding: { value: null, unit: 'USDT' },
        attention_items: [],
        evidence: [],
      },
    };

    render(<ActiveTradeCard episode={manualEp} onSelectEpisode={vi.fn()} />);

    expect(container.textContent).toContain('人工管理 · 不再自动处置');
    expect(container.textContent).toContain('同币种 (BTCUSDT) 新增开仓已锁定');
    expect(container.textContent).toContain('关联挂单 0 笔');
    expect(container.textContent).not.toContain('现有 TP1 和止损仍有效');
    expect(container.textContent).toContain('既有挂单是否有效以交易所最新订单事实为准');
    expect(container.textContent).toContain('整笔已转人工管理；止损已撤销，当前没有保护单');
  });

  it('ActiveTradeCard keeps unknown manual_risk_reason persistently tagged and preserves raw code in details (P2 regression)', () => {
    const unknownReasonEp: TradeEpisode = {
      ticket_id: 'ticket:manual-unknown-002',
      strategy_id: 'CPM-RO-001',
      strategy_name_zh: '均线回踩做多',
      symbol: 'SOLUSDT',
      side: 'long',
      lifecycle_stage: 'manual',
      lifecycle_stage_zh: '人工管理',
      completed_stage_count: 4,
      total_stage_count: 8,
      ticket_status: 'active',
      issued_at_ms: 1700000000000,
      issued_at_formatted: '09:00:00',
      terminal_at_ms: null,
      closed_at_formatted: null,
      duration_formatted: '1h',
      outcome: 'active',
      outcome_zh: '持仓中',
      net_pnl_formatted: '--',
      net_pnl_is_positive: null,
      net_r_formatted: '--',
      net_r_is_positive: null,
      net_pnl_is_gross: false,
      exit_reason: null,
      exit_reason_zh: '—',
      is_protected: false,
      protection_state: '人工管理 · 保护待核实',
      attention_items: [],
      evidence: [],
      raw_item: {
        ticket_id: 'ticket:manual-unknown-002',
        strategy_group_id: 'CPM-RO-001',
        event_spec_id: 'evt-2',
        exchange_instrument_id: 'binance-usdm:SOLUSDT:perpetual',
        position_side: 'long',
        ticket_status: 'active',
        terminal_at_ms: null,
        issued_at_ms: 1700000000000,
        aggregate_status: 'position_protected',
        lifecycle_stage: 'manual',
        completed_stage_count: 4,
        total_stage_count: 8,
        management_mode: 'MANUAL',
        manual_risk_reason: 'custom_unrecognized_risk_reason_77',
        management_orders: [],
        net_pnl: { value: null, unit: 'USDT' },
        net_r: { value: null, unit: 'R' },
        gross_pnl: { value: null, unit: 'USDT' },
        fees: { value: null, unit: 'USDT' },
        funding: { value: null, unit: 'USDT' },
        attention_items: [],
        evidence: [],
      },
    };

    render(<ActiveTradeCard episode={unknownReasonEp} onSelectEpisode={vi.fn()} />);

    expect(container.textContent).toContain('新增开仓受限 · 原因待核实');
    expect(container.textContent).toContain('custom_unrecognized_risk_reason_77');
  });

  it('TradesFilterBar displays strategy_version_id and resets strategy_version_id, view, and exit_scope completely (P2 regression)', async () => {
    window.history.replaceState(
      null,
      '',
      '?tab=trades&strategy_version_id=sgv:BRF2-001:v3&view=current&exit_scope=owner'
    );

    function FilterProbe() {
      const { filters, setFilters, resetFilters } = useTradesFilterState();
      return (
        <div>
          <TradesFilterBar filters={filters} onChange={setFilters} onReset={resetFilters} />
          <div data-testid="probe-state">
            {`${filters.strategy_version_id ?? 'none'}|${filters.view}|${filters.exit_scope}`}
          </div>
        </div>
      );
    }

    render(<FilterProbe />);

    expect(container.textContent).toContain('版本: sgv:BRF2-001:v3');
    expect(container.textContent).toContain('高级筛选 (3)');
    expect(container.textContent).toContain('清除筛选');
    expect(container.querySelector('[data-testid="probe-state"]')?.textContent).toBe(
      'sgv:BRF2-001:v3|current|owner'
    );

    const resetBtn = [...container.querySelectorAll<HTMLButtonElement>('button')].find((b) =>
      b.textContent?.includes('清除筛选')
    )!;
    await act(async () => {
      resetBtn.click();
    });

    expect(container.querySelector('[data-testid="probe-state"]')?.textContent).toBe('none|all|all');
    expect(container.textContent).not.toContain('版本: sgv:BRF2-001:v3');
    expect(window.location.search).not.toContain('strategy_version_id');
    expect(window.location.search).not.toContain('view=current');
    expect(window.location.search).not.toContain('exit_scope=owner');
  });

  it('CompletedTradeTable uses accurate gross-only label when fees/funding are incomplete', () => {
    const grossEp: TradeEpisode = {
      ticket_id: 'ticket:gross-001',
      strategy_id: 'BRF2-001',
      strategy_name_zh: '假反弹衰竭做空',
      symbol: 'ETHUSDT',
      side: 'short',
      lifecycle_stage: 'review',
      lifecycle_stage_zh: '复盘',
      completed_stage_count: 8,
      total_stage_count: 8,
      ticket_status: 'terminal',
      issued_at_ms: 1700000000000,
      issued_at_formatted: '09:00:00',
      terminal_at_ms: 1700003600000,
      closed_at_formatted: '10:00:00',
      duration_formatted: '1h',
      outcome: 'unknown',
      outcome_zh: '已结束 · 经济数据不可用',
      net_pnl_formatted: '+12.00 USDT',
      net_pnl_is_positive: true,
      net_r_formatted: '—',
      net_r_is_positive: null,
      net_pnl_is_gross: true,
      exit_reason: 'initial_stop_triggered',
      exit_reason_zh: '初始止损触发',
      is_protected: true,
      protection_state: '已结束',
      attention_items: [],
      evidence: [],
      raw_item: {} as TradeEpisode['raw_item'],
    };

    render(<CompletedTradeTable episodes={[grossEp]} onSelectEpisode={vi.fn()} />);
    expect(container.textContent).toContain('毛收益 · 费用未完整核实');
  });

  it('TradesPage opens CausalityDrawer directly by ticketId for unloaded missing tickets and keeps active-coverage visible in completed mode', async () => {
    window.history.replaceState(null, '', '?tab=trades&filter_mode=completed');

    vi.spyOn(overviewApi, 'fetchOverview').mockResolvedValue({
      code: 0,
      message: 'ok',
      data: {
        active_ticket_count: 1,
        active_ticket_ids: ['ticket:active-1'],
        observed_at_ms: 1700000000000,
      } as never,
      freshness: 'fresh',
      generated_at: new Date().toISOString(),
      snapshot_id: 'snap-1',
    });

    vi.spyOn(ticketsApi, 'fetchTickets').mockResolvedValue({
      code: 0,
      message: 'ok',
      data: {
        items: [],
        next_cursor: null,
      },
    });

    vi.spyOn(performanceApi, 'fetchPerformance').mockResolvedValue({
      data: {
        sample_count: 2,
        confirmed_count: 1,
        unreviewed_count: 0,
        win_count: 1,
        loss_count: 0,
        breakeven_count: 0,
        from_ms: 1700000000000,
        to_ms: 1700086400000,
        summary_scope: 'full_window',
        time_basis: 'terminal',
        view: 'all',
        exit_scope: 'all',
        snapshot_id: 'profit:test',
        complete_review_count: 1,
        incomplete_review_count: 1,
        attention_count: 0,
        verified_totals: {
          gross_pnl: { value: '10', unit: 'USDT', unavailable_reason: null },
          net_pnl: { value: '8', unit: 'USDT', unavailable_reason: null },
          net_r: { value: '1.2', unit: 'R', unavailable_reason: null },
          fees: { value: '-1', unit: 'USDT', unavailable_reason: null },
          funding: { value: '-1', unit: 'USDT', unavailable_reason: null },
        },
        metric_coverage: {
          gross_pnl: { available_count: 2, total_count: 2, missing_ticket_ids: [] },
          net_pnl: { available_count: 1, total_count: 2, missing_ticket_ids: ['ticket:unloaded-missing-999'] },
          net_r: { available_count: 1, total_count: 2, missing_ticket_ids: ['ticket:unloaded-missing-999'] },
          fees: { available_count: 2, total_count: 2, missing_ticket_ids: [] },
          funding: { available_count: 2, total_count: 2, missing_ticket_ids: [] },
        },
        breakdown: {
          strategy: { sample_count: 2, confirmed_count: 1, unreviewed_count: 0, win_count: 1, loss_count: 0, breakeven_count: 0, verified_totals: { gross_pnl: { value: '10', unit: 'USDT', unavailable_reason: null }, net_pnl: { value: '8', unit: 'USDT', unavailable_reason: null }, net_r: { value: '1.2', unit: 'R', unavailable_reason: null }, fees: { value: '-1', unit: 'USDT', unavailable_reason: null }, funding: { value: '-1', unit: 'USDT', unavailable_reason: null } }, metric_coverage: {} },
          owner: { sample_count: 0, confirmed_count: 0, unreviewed_count: 0, win_count: 0, loss_count: 0, breakeven_count: 0, verified_totals: { gross_pnl: { value: null, unit: 'USDT', unavailable_reason: null }, net_pnl: { value: null, unit: 'USDT', unavailable_reason: null }, net_r: { value: null, unit: 'R', unavailable_reason: null }, fees: { value: null, unit: 'USDT', unavailable_reason: null }, funding: { value: null, unit: 'USDT', unavailable_reason: null } }, metric_coverage: {} },
          safety: { sample_count: 0, confirmed_count: 0, unreviewed_count: 0, win_count: 0, loss_count: 0, breakeven_count: 0, verified_totals: { gross_pnl: { value: null, unit: 'USDT', unavailable_reason: null }, net_pnl: { value: null, unit: 'USDT', unavailable_reason: null }, net_r: { value: null, unit: 'R', unavailable_reason: null }, fees: { value: null, unit: 'USDT', unavailable_reason: null }, funding: { value: null, unit: 'USDT', unavailable_reason: null } }, metric_coverage: {} },
          unknown: { sample_count: 0, confirmed_count: 0, unreviewed_count: 0, win_count: 0, loss_count: 0, breakeven_count: 0, verified_totals: { gross_pnl: { value: null, unit: 'USDT', unavailable_reason: null }, net_pnl: { value: null, unit: 'USDT', unavailable_reason: null }, net_r: { value: null, unit: 'R', unavailable_reason: null }, fees: { value: null, unit: 'USDT', unavailable_reason: null }, funding: { value: null, unit: 'USDT', unavailable_reason: null } }, metric_coverage: {} },
        },
      } as never,
    });

    const causalitySpy = vi.spyOn(ticketsApi, 'fetchTicketCausality').mockResolvedValue({
      code: 0,
      message: 'ok',
      data: {
        trade: {
          ticket_id: 'ticket:unloaded-missing-999',
          strategy_group_id: 'CPM-RO-001',
          exchange_instrument_id: 'binance-usdm:BTCUSDT:perpetual',
          position_side: 'long',
          ticket_status: 'terminal',
          terminal_at_ms: 1700003600000,
          issued_at_ms: 1700000000000,
          aggregate_status: 'terminal',
          lifecycle_stage: 'review',
          completed_stage_count: 8,
          total_stage_count: 8,
          attention_items: [],
          evidence: [],
        },
        current_stage: 'review',
        stages: [],
        annotations: [],
        raw_commands: [],
        raw_events: [],
      } as never,
    });

    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <TradesPage />
      </QueryClientProvider>
    );

    await act(async () => {
      await vi.waitFor(() => expect(container.textContent).toContain('ticket:unloaded-missing-999'));
    });

    // active-coverage remains visible even in completed mode, and redundant ribbon is gone
    expect(container.querySelector('[data-testid="active-coverage"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="trades-metrics-ribbon"]')).toBeNull();

    // Click the unloaded missing ticket ID button
    const missingBtn = [...container.querySelectorAll<HTMLButtonElement>('button')].find((b) =>
      b.textContent?.includes('ticket:unloaded-missing-999')
    )!;
    await act(async () => {
      missingBtn.click();
    });

    await act(async () => {
      await vi.waitFor(() => expect(causalitySpy).toHaveBeenCalledWith('ticket:unloaded-missing-999'));
    });
    expect(container.querySelector('[data-testid="causality-drawer"]')).not.toBeNull();
  });
});
