// @vitest-environment jsdom
import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StrategyDetailDrawer } from './StrategyDetailDrawer';
import type { EnrichedStrategyVersion } from '../../types/strategies';

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const baseStrategy: EnrichedStrategyVersion = {
  summary: {
    strategy_group_id: 'CPM-RO-001',
    strategy_version_id: 'cpm_v3.2',
    name_zh: '动量突破',
    timeframe: '4h',
    is_current: true,
    total_tickets: 10,
    active_tickets: 0,
    win_rate: 0.6,
    avg_r: 1.2,
    pnl_r: 12.0,
  },
  control: null, // Control fact intentionally null / removed!
  activeTickets: [],
  displayNameZh: '动量突破',
  timeframe: '4h',
  runtimeStatus: 'enabled',
  totalTrades: 10,
  activeTrades: 0,
  winRate: 0.6,
  pnlR: 12.0,
  avgR: 1.2,
  sampleEfficiency: 1.0,
  confirmedReviews: 8,
  pendingReviews: 2,
};

describe('StrategyDetailDrawer - Missing Fact Protection', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('disables control button and displays "控制事实不可用" when control record is removed/missing', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);

    act(() => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <StrategyDetailDrawer
            strategy={baseStrategy}
            onClose={vi.fn()}
            onSelectTicket={vi.fn()}
          />
        </QueryClientProvider>
      );
    });

    // Check header button: MUST NOT show "恢复新准入" or guess v1!
    const drawer = container.querySelector('[data-testid="strategy-detail-drawer"]');
    expect(drawer).not.toBeNull();
    const actionBtn = drawer?.querySelector('button[title*="缺少真实控制事实"]');
    expect(actionBtn).not.toBeNull();
    expect(actionBtn?.textContent).toContain('控制事实不可用');
    expect(actionBtn?.hasAttribute('disabled')).toBe(true);

    // Verify it did not render "恢复新准入"
    expect(drawer?.textContent).not.toContain('恢复新准入');
    expect(drawer?.textContent).not.toContain('暂停新准入');

    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('renders interactive button when valid control facts exist', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const validStrategy: EnrichedStrategyVersion = {
      ...baseStrategy,
      control: {
        strategy_group_id: 'CPM-RO-001',
        configured_state: 'enabled',
        effective_state: 'enabled',
        control_version: 5,
        updated_at_ms: 1700000000000,
        entry_state: 'enabled',
        last_event_id: 'evt-5',
        reason: '正常运行',
      },
    };

    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);

    act(() => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <StrategyDetailDrawer
            strategy={validStrategy}
            onClose={vi.fn()}
            onSelectTicket={vi.fn()}
          />
        </QueryClientProvider>
      );
    });

    const drawer = container.querySelector('[data-testid="strategy-detail-drawer"]');
    expect(drawer?.textContent).toContain('暂停新准入');

    act(() => {
      root.unmount();
    });
    container.remove();
  });
});
