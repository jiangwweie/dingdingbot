// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { StrategiesPage } from './StrategiesPage';
import { StrategyDetailDrawer } from './StrategyDetailDrawer';
import * as strategiesApi from '../../api/strategiesApi';
import * as controlsApi from '../../api/controlsApi';
import * as overviewApi from '../../api/overviewApi';
import * as performanceApi from '../../api/performanceApi';
import type { EnrichedStrategyVersion } from '../../types/strategies';

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

describe('Strategies Page & Drawer Convergence', () => {
  it('separates group/version counts, avoids claiming running health for configured-enabled, marks unknown controls, and performs full filter reset', async () => {
    window.history.replaceState(
      null,
      '',
      '?tab=strategies&view=current&exit_scope=owner&strategy_group_id=CPM-RO-001&drawer_tab=tickets&scope=natural&exit_path=tp1_reached&first_path=tp1_first'
    );

    vi.spyOn(strategiesApi, 'fetchStrategies').mockResolvedValue({
      code: 0,
      message: 'ok',
      freshness: 'fresh',
      data: {
        items: [
          {
            strategy_group_id: 'CPM-RO-001',
            strategy_version_id: 'sgv:CPM-RO-001:v1',
            version: 1,
            is_current: true,
            name: '均线回踩做多',
            timeframe: '1h',
            ticket_count: 5,
            observation_count: 12,
            natural_terminal_count: 4,
            controlled_exit_count: 1,
            safety_exit_count: 0,
            unknown_exit_count: 0,
            tp1_reached_count: 2,
            tp1_not_reached_count: 2,
            confirmed_review_count: 4,
            pending_review_count: 1,
            win_count: 3,
            loss_count: 1,
            net_pnl: { value: '120.00', unit: 'USDT' },
            net_r: { value: '1.50', unit: 'R' },
            metric_coverage: { net_pnl: { available_count: 4, total_count: 5 } },
          },
          {
            strategy_group_id: 'BRF2-001',
            strategy_version_id: 'sgv:BRF2-001:v2',
            version: 2,
            is_current: true,
            name: '假反弹衰竭做空',
            timeframe: '1h',
            ticket_count: 2,
            observation_count: 8,
            natural_terminal_count: 2,
            controlled_exit_count: 0,
            safety_exit_count: 0,
            unknown_exit_count: 0,
            tp1_reached_count: 1,
            tp1_not_reached_count: 1,
            confirmed_review_count: 2,
            pending_review_count: 0,
            win_count: 1,
            loss_count: 1,
            net_pnl: { value: '30.00', unit: 'USDT' },
            net_r: { value: '0.40', unit: 'R' },
            metric_coverage: {
              net_pnl: { available_count: 2, total_count: 2 },
              net_r: { available_count: 1, total_count: 2 },
            },
          },
        ],
      },
    } as never);

    vi.spyOn(controlsApi, 'fetchControls').mockResolvedValue({
      strategies: [
        {
          strategy_group_id: 'CPM-RO-001',
          configured_state: 'enabled',
          effective_state: 'paused_by_global',
          control_version: 3,
        },
        // BRF2-001 intentionally missing control fact!
      ],
      global_entry: { configured_state: 'paused', effective_state: 'paused' },
      account_capacity: { max_concurrent_tickets: 3, active_ticket_count: 2, strategy_side_active_counts: {} },
    } as never);

    vi.spyOn(overviewApi, 'fetchOverview').mockResolvedValue({
      code: 0,
      message: 'ok',
      freshness: 'fresh',
      data: { active_ticket_count: 2, active_ticket_ids: [] } as never,
    } as never);

    vi.spyOn(performanceApi, 'fetchPerformance').mockResolvedValue({
      data: {
        sample_count: 7,
        confirmed_count: 6,
        unreviewed_count: 0,
        win_count: 4,
        loss_count: 2,
        breakeven_count: 0,
        from_ms: 1700000000000,
        to_ms: 1700086400000,
        summary_scope: 'full_window',
        time_basis: 'terminal',
        view: 'current',
        exit_scope: 'owner',
        snapshot_id: 'profit:strat-test',
        complete_review_count: 6,
        incomplete_review_count: 1,
        attention_count: 0,
        verified_totals: {
          gross_pnl: { value: '160', unit: 'USDT', unavailable_reason: null },
          net_pnl: { value: '150', unit: 'USDT', unavailable_reason: null },
          net_r: { value: '1.9', unit: 'R', unavailable_reason: null },
          fees: { value: '-10', unit: 'USDT', unavailable_reason: null },
          funding: { value: '0', unit: 'USDT', unavailable_reason: null },
        },
        metric_coverage: {
          gross_pnl: { available_count: 7, total_count: 7, missing_ticket_ids: [] },
          net_pnl: { available_count: 6, total_count: 7, missing_ticket_ids: ['t-miss-1'] },
          net_r: { available_count: 6, total_count: 7, missing_ticket_ids: ['t-miss-1'] },
          fees: { available_count: 7, total_count: 7, missing_ticket_ids: [] },
          funding: { available_count: 7, total_count: 7, missing_ticket_ids: [] },
        },
        breakdown: {
          strategy: { sample_count: 6, confirmed_count: 6, unreviewed_count: 0, win_count: 4, loss_count: 2, breakeven_count: 0, verified_totals: { gross_pnl: { value: '130', unit: 'USDT', unavailable_reason: null }, net_pnl: { value: '120', unit: 'USDT', unavailable_reason: null }, net_r: { value: '1.5', unit: 'R', unavailable_reason: null }, fees: { value: '-8', unit: 'USDT', unavailable_reason: null }, funding: { value: '0', unit: 'USDT', unavailable_reason: null } }, metric_coverage: {} },
          owner: { sample_count: 1, confirmed_count: 0, unreviewed_count: 0, win_count: 0, loss_count: 0, breakeven_count: 0, verified_totals: { gross_pnl: { value: '30', unit: 'USDT', unavailable_reason: null }, net_pnl: { value: '30', unit: 'USDT', unavailable_reason: null }, net_r: { value: '0.4', unit: 'R', unavailable_reason: null }, fees: { value: '-2', unit: 'USDT', unavailable_reason: null }, funding: { value: '0', unit: 'USDT', unavailable_reason: null } }, metric_coverage: {} },
          safety: { sample_count: 0, confirmed_count: 0, unreviewed_count: 0, win_count: 0, loss_count: 0, breakeven_count: 0, verified_totals: { gross_pnl: { value: null, unit: 'USDT', unavailable_reason: 'no_review_evidence' }, net_pnl: { value: null, unit: 'USDT', unavailable_reason: 'no_review_evidence' }, net_r: { value: null, unit: 'R', unavailable_reason: 'no_review_evidence' }, fees: { value: null, unit: 'USDT', unavailable_reason: 'no_review_evidence' }, funding: { value: null, unit: 'USDT', unavailable_reason: 'no_review_evidence' } }, metric_coverage: {} },
          unknown: { sample_count: 0, confirmed_count: 0, unreviewed_count: 0, win_count: 0, loss_count: 0, breakeven_count: 0, verified_totals: { gross_pnl: { value: null, unit: 'USDT', unavailable_reason: 'no_review_evidence' }, net_pnl: { value: null, unit: 'USDT', unavailable_reason: 'no_review_evidence' }, net_r: { value: null, unit: 'R', unavailable_reason: 'no_review_evidence' }, fees: { value: null, unit: 'USDT', unavailable_reason: 'no_review_evidence' }, funding: { value: null, unit: 'USDT', unavailable_reason: 'no_review_evidence' } }, metric_coverage: {} },
        },
      } as never,
    });

    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <StrategiesPage />
      </QueryClientProvider>
    );

    await act(async () => {
      await vi.waitFor(() => {
        expect(container.textContent).toContain('策略表现矩阵');
        expect(container.textContent).toContain('账户当前在管 2 笔');
      });
    });

    expect(container.querySelector('[data-testid="strategies-metrics-ribbon"]')).toBeNull();
    expect(container.textContent).toContain('策略组 2 · 版本 2');
    // Configured-enabled counts even when globally paused, and blocked count is shown separately
    expect(container.textContent).toContain('已启用 1 · 生效受阻 1 · 控制未知 1');
    expect(container.textContent).toContain('账户当前在管 2 笔');
    expect(container.textContent).toContain('研究观察 20 条 (非实盘成交)');
    expect(container.textContent).not.toContain('正常运行中');
    expect(container.textContent).toContain('控制状态未知');
    // Independent Net R partial coverage (1/2) shown even when Net PnL is 2/2
    expect(container.textContent).toContain('部分合计 · 覆盖 1/2 笔');
    expect(container.textContent).toContain('部分合计 · 净 R 覆盖 1/2');

    // Full reset clears exit_scope, strategy_group_id, drawer_tab, scope, exit_path, first_path
    const resetBtn = [...container.querySelectorAll<HTMLButtonElement>('button')].find((b) =>
      b.textContent?.includes('清除筛选')
    )!;
    await act(async () => {
      resetBtn.click();
    });

    expect(window.location.search).not.toContain('exit_scope=owner');
    expect(window.location.search).not.toContain('strategy_group_id=CPM-RO-001');
    expect(window.location.search).not.toContain('drawer_tab=tickets');
    expect(window.location.search).not.toContain('exit_path=tp1_reached');
    expect(window.location.search).not.toContain('first_path=tp1_first');
  });

  it('StrategyDetailDrawer aligns net PnL scope explanation with active exit_scope', () => {
    const strategy: EnrichedStrategyVersion = {
      summary: {
        strategy_group_id: 'CPM-RO-001',
        strategy_version_id: 'sgv:CPM-RO-001:v1',
        name_zh: '均线回踩做多',
        timeframe: '1h',
        is_current: true,
        ticket_count: 5,
        metric_coverage: {
          net_pnl: { available_count: 5, total_count: 5 },
          net_r: { available_count: 3, total_count: 5 },
        },
      },
      control: null,
      activeTickets: [],
      displayNameZh: '均线回踩做多',
      timeframe: '1h',
      runtimeStatus: 'enabled',
      runtimeStatusLabel: '已启用',
      totalTickets: 5,
      naturalTerminals: 4,
      controlledExits: 1,
      tp1Reached: 2,
      tp1NotReached: 2,
      confirmedReviews: 4,
      pendingReviews: 1,
      observationCount: 10,
      activeTicketCount: 0,
      isCurrent: true,
      netPnlFormatted: '+120.00 USDT',
      netPnlIsPositive: true,
      netRFormatted: '+1.50 R',
      netRIsPositive: true,
      winRatePercent: 75,
      winRateLabel: '3 胜 / 1 负',
      hasConfirmedReview: true,
    } as unknown as EnrichedStrategyVersion;

    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <StrategyDetailDrawer
          strategy={strategy}
          exit_scope="owner"
          onClose={vi.fn()}
          onSelectTicket={vi.fn()}
        />
      </QueryClientProvider>
    );

    expect(container.textContent).toContain('仅统计 Owner 平仓且已核实净额的终态交易');
    expect(container.textContent).not.toContain('排除受控退出');
    expect(container.textContent).toContain('所选范围净胜率');
    expect(container.textContent).not.toContain('自然胜率');
    expect(container.textContent).toContain('已入账所选范围终态经济数据');
    expect(container.textContent).not.toContain('已入账自然终态经济数据');
    expect(container.textContent).toContain('部分合计 · 覆盖 3/5 笔');
  });
});
