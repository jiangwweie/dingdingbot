// @vitest-environment jsdom
import { act, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StrategyMatrix } from './StrategyMatrix';
import { StrategyDetailDrawer } from './strategies/StrategyDetailDrawer';
import * as controlsApi from '../api/controlsApi';
import { _resetInFlightRegistry } from '../hooks/useStrategyControl';
import type { StrategyControlItem } from '../types/controls';
import type { EnrichedStrategyVersion } from '../types/strategies';

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function setInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
  if (setter) {
    setter.call(input, value);
  } else {
    input.value = value;
  }
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
}

const mockStrategyItem: StrategyControlItem = {
  strategy_group_id: 'CPM-RO-001',
  name_zh: '动量突破',
  timeframe: '4h',
  configured_state: 'enabled',
  effective_state: 'enabled',
  control_version: 3,
  updated_at_ms: 1700000000000,
  reason_label: '正常运行',
  admission_health: {
    status: 'cleared',
    summary: '准入正常',
    source: 'server_admission_fact',
  },
  active_tickets: [],
  strategy_version_id: 'cpm_v3.2',
};

const mockEnrichedStrategy: EnrichedStrategyVersion = {
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
  control: {
    strategy_group_id: 'CPM-RO-001',
    configured_state: 'enabled',
    effective_state: 'enabled',
    control_version: 3,
    updated_at_ms: 1700000000000,
    entry_state: 'enabled',
    last_event_id: 'evt-3',
    reason: '正常运行',
  },
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

describe('Cross-Entry Control State Preservation (Controls Matrix <-> Strategy Detail Drawer)', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.restoreAllMocks();
    _resetInFlightRegistry();
    document.body.innerHTML = '';
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
  });

  it('Controls Matrix -> Strategies Drawer: preserves in-flight identity, blocks direct submission, enforces GET verification', async () => {
    // 1. Mock pause API to fail with a network timeout
    const pauseSpy = vi.spyOn(controlsApi, 'pauseStrategy').mockRejectedValue(
      new Error('fetch timeout while contacting backend')
    );

    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);

    // Harness rendering both Matrix and Drawer with toast reflection
    let lastToast = '';
    const TestHarness = ({ showDrawer }: { showDrawer: boolean }) => {
      const [toast, setToast] = useState<string | null>(null);
      const handleSuccess = (msg: string) => {
        lastToast = msg;
        setToast(msg);
      };
      return (
        <QueryClientProvider client={queryClient}>
          <StrategyMatrix strategies={[mockStrategyItem]} onSuccess={handleSuccess} />
          {showDrawer && (
            <StrategyDetailDrawer
              strategy={mockEnrichedStrategy}
              onClose={vi.fn()}
              onSelectTicket={vi.fn()}
              onSuccess={handleSuccess}
            />
          )}
          {toast && <div data-testid="toast-container">{toast}</div>}
        </QueryClientProvider>
      );
    };

    act(() => {
      root.render(<TestHarness showDrawer={false} />);
    });

    // Step 1: Open pause confirmation modal in StrategyMatrix
    const matrixRow = container.querySelector('[data-strategy-id="CPM-RO-001"]');
    const matrixPauseBtn = matrixRow?.querySelector('button');
    expect(matrixPauseBtn?.textContent).toContain('暂停新准入');

    act(() => {
      matrixPauseBtn?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    // Modal opens
    const modalContent = document.body.querySelector('[data-testid="totp-action-modal"]');
    expect(modalContent).not.toBeNull();
    expect(modalContent?.textContent).toContain('确认暂停新准入: CPM-RO-001');

    // Fill reason and submit
    const reasonInput = modalContent?.querySelector('input[placeholder*="本次控制操作原因"]') as HTMLInputElement;
    act(() => {
      setInputValue(reasonInput, 'Matrix 暂停入场操作');
    });

    const submitBtn = modalContent?.querySelector('button[type="submit"]') as HTMLButtonElement;
    await act(async () => {
      submitBtn.click();
    });

    // Step 2: Post failed into unknown_result
    expect(pauseSpy).toHaveBeenCalledTimes(1);
    const firstCallKey = pauseSpy.mock.calls[0][1].idempotency_key;
    expect(firstCallKey).toBeDefined();

    // Verify modal entered unknown_result lock
    expect(document.body.textContent).toContain('执行结果未知，禁止盲目生成新请求重试');
    expect(document.body.textContent).toContain('核验权威状态');

    // Step 3: Close modal by clicking cancel
    const cancelBtn = document.body.querySelector('button[type="button"]') as HTMLButtonElement;
    act(() => {
      cancelBtn.click();
    });

    // Step 4: Open Strategies Detail Drawer for CPM-RO-001
    act(() => {
      root.render(<TestHarness showDrawer={true} />);
    });

    const drawer = container.querySelector('[data-testid="strategy-detail-drawer"]');
    expect(drawer).not.toBeNull();
    const drawerActionBtn = drawer?.querySelector('button') as HTMLButtonElement;
    expect(drawerActionBtn.textContent).toContain('暂停新准入');

    // Step 5: Click pause from inside the drawer
    act(() => {
      drawerActionBtn.click();
    });

    // Step 6: Verify in-flight operation identity is preserved and modal reopens in unknown_result state
    const reopenedModal = document.body.querySelector('[data-testid="totp-action-modal"]');
    expect(reopenedModal).not.toBeNull();
    expect(reopenedModal?.textContent).toContain('该策略存在未决的控制操作，执行结果未知');
    expect(reopenedModal?.textContent).toContain('核验权威状态');

    // Direct submission button must NOT be present
    expect(reopenedModal?.querySelector('button[type="submit"]')).toBeNull();

    // Step 7: Perform GET verification where state is still enabled and version unchanged
    const fetchControlsSpy = vi.spyOn(controlsApi, 'fetchControls').mockResolvedValue({
      strategies: [
        {
          strategy_group_id: 'CPM-RO-001',
          configured_state: 'enabled',
          control_version: 3,
          effective_state: 'enabled',
          entry_state: 'enabled',
          last_event_id: 'evt-3',
          reason: '正常运行',
          updated_at_ms: 1700000000000,
        },
      ],
    } as any);

    const verifyBtn = Array.from(reopenedModal?.querySelectorAll('button') ?? []).find(
      (b) => b.textContent?.includes('核验权威状态')
    );
    expect(verifyBtn).toBeDefined();

    await act(async () => {
      verifyBtn?.click();
    });

    expect(fetchControlsSpy).toHaveBeenCalled();
    // After verification confirms command was not applied, it reports verified notice and unlocks retry
    expect(reopenedModal?.textContent).toContain('核验完成：服务端尚未执行本次操作');
    expect(reopenedModal?.textContent).toContain('已锁定原请求与幂等键');

    // Step 8: Retry with confirmed unapplied status
    pauseSpy.mockResolvedValueOnce({
      ok: true,
      data: {
        strategy_group_id: 'CPM-RO-001',
        control_version: 4,
        entry_state: 'paused',
      },
    } as any);

    const retrySubmitBtn = reopenedModal?.querySelector('button[type="submit"]') as HTMLButtonElement;
    expect(retrySubmitBtn).not.toBeNull();

    await act(async () => {
      retrySubmitBtn.click();
    });

    // Must have sent second POST using the EXACT same preserved idempotency key and frozen reason
    expect(pauseSpy).toHaveBeenCalledTimes(2);
    const retryCallBody = pauseSpy.mock.calls[1][1];
    expect(retryCallBody.idempotency_key).toBe(firstCallKey);
    expect(retryCallBody.reason).toBe('Matrix 暂停入场操作');
    expect(retryCallBody.expected_version).toBe(3);

    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('Strategies Drawer -> Controls Matrix: reverse flow preserves identity and handles truth without false success', async () => {
    const pauseSpy = vi.spyOn(controlsApi, 'pauseStrategy').mockRejectedValue(
      new Error('connection dropped')
    );

    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);

    let lastToast = '';
    const TestHarness = ({ showDrawer }: { showDrawer: boolean }) => {
      const [toast, setToast] = useState<string | null>(null);
      const handleSuccess = (msg: string) => {
        lastToast = msg;
        setToast(msg);
      };
      return (
        <QueryClientProvider client={queryClient}>
          <StrategyMatrix strategies={[mockStrategyItem]} onSuccess={handleSuccess} />
          {showDrawer && (
            <StrategyDetailDrawer
              strategy={mockEnrichedStrategy}
              onClose={vi.fn()}
              onSelectTicket={vi.fn()}
              onSuccess={handleSuccess}
            />
          )}
          {toast && <div data-testid="toast-container">{toast}</div>}
        </QueryClientProvider>
      );
    };

    // Mount with drawer open
    act(() => {
      root.render(<TestHarness showDrawer={true} />);
    });

    // 1. Trigger from Drawer
    const drawer = container.querySelector('[data-testid="strategy-detail-drawer"]');
    const drawerPauseBtn = drawer?.querySelector('button') as HTMLButtonElement;

    act(() => {
      drawerPauseBtn.click();
    });

    const modalContent = document.body.querySelector('[data-testid="totp-action-modal"]');
    expect(modalContent).not.toBeNull();

    const reasonInput = modalContent?.querySelector('input[placeholder*="本次控制操作原因"]') as HTMLInputElement;
    act(() => {
      setInputValue(reasonInput, 'Drawer 暂停入场操作');
    });

    const submitBtn = modalContent?.querySelector('button[type="submit"]') as HTMLButtonElement;
    await act(async () => {
      submitBtn.click();
    });

    expect(pauseSpy).toHaveBeenCalledTimes(1);
    const firstCallKey = pauseSpy.mock.calls[0][1].idempotency_key;

    // 2. Close modal
    const cancelBtn = document.body.querySelector('button[type="button"]') as HTMLButtonElement;
    act(() => {
      cancelBtn.click();
    });

    // 3. Close drawer, view Matrix
    act(() => {
      root.render(<TestHarness showDrawer={false} />);
    });

    // 4. In Matrix, click pause on CPM-RO-001
    const matrixRow = container.querySelector('[data-strategy-id="CPM-RO-001"]');
    const matrixPauseBtn = matrixRow?.querySelector('button');

    act(() => {
      matrixPauseBtn?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    // 5. Verify unknown result state is restored in Matrix
    const reopenedModal = document.body.querySelector('[data-testid="totp-action-modal"]');
    expect(reopenedModal?.textContent).toContain('该策略存在未决的控制操作，执行结果未知');
    expect(reopenedModal?.textContent).toContain('核验权威状态');

    // 6. When GET verification finds state is paused (e.g. jumped to v99 by another operation)
    vi.spyOn(controlsApi, 'fetchControls').mockResolvedValue({
      strategies: [
        {
          strategy_group_id: 'CPM-RO-001',
          configured_state: 'paused', // already target state
          control_version: 99,
          effective_state: 'paused',
          entry_state: 'paused',
          last_event_id: 'evt-99',
          reason: 'concurrent external event',
          updated_at_ms: 1700000000000,
        },
      ],
    } as any);

    const verifyBtn = Array.from(reopenedModal?.querySelectorAll('button') ?? []).find(
      (b) => b.textContent?.includes('核验权威状态')
    );

    await act(async () => {
      verifyBtn?.click();
    });

    // 7. Verify it outputs truthful state without falsely asserting execution certainty
    expect(lastToast).toContain('当前已处于目标状态');
    expect(lastToast).toContain('本次请求结果仍无法确认');
    expect(lastToast).not.toContain('已核验成功：服务端已');

    act(() => {
      root.unmount();
    });
    container.remove();
  });
});
