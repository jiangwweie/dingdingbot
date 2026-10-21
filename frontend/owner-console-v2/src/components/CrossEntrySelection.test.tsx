// @vitest-environment jsdom
import React, { act, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SelectionSection } from './SelectionSection';
import { StrategyDetailDrawer } from './strategies/StrategyDetailDrawer';
import * as controlsApi from '../api/controlsApi';
import { _resetInFlightSelectionRegistry, _getInFlightSelection } from '../hooks/useSelectionControl';
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
    updated_at_ms: 1800000000000,
    reason: '正常运行',
  },
  metrics: {
    total_trades: 10,
    win_rate: 0.6,
    pnl_r: 12.0,
    sharpe_ratio: 1.8,
    max_drawdown_r: -2.0,
    profit_factor: 1.9,
  },
  recent_tickets: [],
  displayNameZh: '动量突破',
};

const mockSelectionPreview: controlsApi.GenericSelectionPreview = {
  control: {
    strategy_group_id: 'CPM-RO-001',
    selection_spec_id: 'generic-spec-1',
    selection_mode: 'static_baseline' as any,
    pending_selection_mode: null,
    pending_effective_period_anchor_ms: null,
    pending_authorization_id: null,
    control_version: 3,
    rollback_baseline_id: 'baseline-v1',
    selection_epoch_id: 'epoch-20261021',
    updated_at_ms: 1800000000000,
  },
  runtime: {
    strategy_group_id: 'CPM-RO-001',
    selection_spec_id: 'generic-spec-1',
    installed: true,
    selection_mode: 'static_baseline' as any,
    latest_successful_snapshot_id: null,
    latest_successful_cutoff_at_ms: null,
    latest_successful_committed_at_ms: null,
    latest_successful_completion_age_ms: null,
    latest_successful_selection_age_ms: null,
    latest_successful_cutoff_age_ms: null,
    membership_source_snapshot_id: null,
    membership_source_cutoff_at_ms: null,
    membership_source_age_ms: null,
    current_authority_id: 'auth:cpm-1',
    current_authority_outcome: 'AUTHORIZED',
    membership_valid_until_ms: 1800003600000,
    consecutive_missed_periods: 0,
    latest_ready_count: 5,
    latest_selected_count: 3,
    valid_empty_reason: null,
    materialization_generation_id: null,
    materialization_state: 'IDLE',
    materialization_deadline_ms: null,
    vacuum_state: 'clear',
    vacuum_fenced_at_ms: null,
    members: [],
    first_blocker: null,
    observed_at_ms: 1800000000000,
  },
  cadence_hours: 4,
  next_effective_period_anchor_ms: 1800007200000,
  next_eligibility_not_before_ms: 1800010800000,
};

const DualEntryTestApp: React.FC<{
  onSuccess?: (msg: string) => void;
}> = ({ onSuccess }) => {
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <div>
      <SelectionSection onSuccess={onSuccess} />
      <button
        type="button"
        data-testid="open-drawer-btn"
        onClick={() => setDrawerOpen(true)}
      >
        打开策略详情抽屉
      </button>

      {drawerOpen && (
        <StrategyDetailDrawer
          strategy={mockEnrichedStrategy}
          onClose={() => setDrawerOpen(false)}
          onSelectTicket={vi.fn()}
          activeDrawerTab="selection"
          onSuccess={onSuccess}
        />
      )}
    </div>
  );
};

describe('CrossEntrySelection Integration', () => {
  let queryClient: QueryClient;

  const createWrapper = () => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    return ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    _resetInFlightSelectionRegistry();
    document.body.innerHTML = '';
  });

  it('Controls SelectionSection -> Strategies Drawer: preserves in-flight identity, blocks direct submission, enforces GET verification', async () => {
    const fetchPreviewSpy = vi
      .spyOn(controlsApi, 'fetchSelectionPreview')
      .mockResolvedValue(mockSelectionPreview);

    const activateDynamicSpy = vi
      .spyOn(controlsApi, 'activateDynamicSelection')
      .mockRejectedValue(new Error('Network timeout during dynamic activation'));

    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);
    const Wrapper = createWrapper();

    const onSuccess = vi.fn();

    act(() => {
      root.render(
        <Wrapper>
          <DualEntryTestApp onSuccess={onSuccess} />
        </Wrapper>
      );
    });

    // Wait for useSelectionPreview query to resolve
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50));
    });

    // Step 1: Open modal from SelectionSection for CPM-RO-001
    const dynamicBtn = Array.from(document.body.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('授权 Dynamic')
    );
    expect(dynamicBtn).toBeDefined();

    await act(async () => {
      dynamicBtn?.click();
    });

    const modal = document.body.querySelector('[data-testid="selection-action-modal"]');
    expect(modal).not.toBeNull();
    expect(modal?.textContent).toContain('CPM-RO-001 激活动态选币授权');

    const initialKey = _getInFlightSelection('CPM-RO-001')?.idempotency_key;
    expect(initialKey).toBeDefined();

    // Fill TOTP and submit
    const totpInput = modal?.querySelector('input[placeholder="000000"]') as HTMLInputElement;
    act(() => {
      setInputValue(totpInput, '123456');
    });

    const submitBtn = modal?.querySelector('button[type="submit"]') as HTMLButtonElement;
    expect(submitBtn.disabled).toBe(false);

    // Step 2: Submit fails due to timeout -> enters unknown_result
    await act(async () => {
      submitBtn.click();
    });

    expect(activateDynamicSpy).toHaveBeenCalledTimes(1);
    expect(modal?.textContent).toContain('选币授权结果未知（闭锁保护）');
    expect(_getInFlightSelection('CPM-RO-001')?.status).toBe('unknown_result');

    // Step 3: Close modal in SelectionSection
    const cancelBtn = Array.from(modal?.querySelectorAll('button') ?? []).find(
      (b) => b.textContent?.trim() === '取消'
    );
    act(() => {
      cancelBtn?.click();
    });

    expect(document.body.querySelector('[data-testid="selection-action-modal"]')).toBeNull();

    // Verify in-flight identity is RETAINED even after modal is closed!
    expect(_getInFlightSelection('CPM-RO-001')?.status).toBe('unknown_result');
    expect(_getInFlightSelection('CPM-RO-001')?.idempotency_key).toBe(initialKey);

    // Step 4: Open StrategyDetailDrawer and go to Selection tab
    const openDrawerBtn = document.body.querySelector(
      '[data-testid="open-drawer-btn"]'
    ) as HTMLButtonElement;
    act(() => {
      openDrawerBtn.click();
    });

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50));
    });

    const drawer = document.body.querySelector('[data-testid="strategy-detail-drawer"]');
    expect(drawer).not.toBeNull();

    // Step 5: Click "启用 Dynamic 模式" inside StrategyDetailDrawer
    const drawerDynamicBtn = Array.from(drawer?.querySelectorAll('button') ?? []).find((b) =>
      b.textContent?.includes('启用 Dynamic 模式')
    );
    expect(drawerDynamicBtn).toBeDefined();

    await act(async () => {
      drawerDynamicBtn?.click();
    });

    // Step 6: Modal re-opens, MUST be in unknown_result lockdown!
    const reopenedModal = document.body.querySelector('[data-testid="selection-action-modal"]');
    expect(reopenedModal).not.toBeNull();
    expect(reopenedModal?.textContent).toContain('选币授权结果未知（闭锁保护）');

    // Reopened modal MUST reuse the exact same idempotency key
    expect(_getInFlightSelection('CPM-RO-001')?.idempotency_key).toBe(initialKey);

    // Submit button MUST be disabled
    const reopenedSubmitBtn = reopenedModal?.querySelector('button[type="submit"]') as HTMLButtonElement;
    expect(reopenedSubmitBtn.disabled).toBe(true);

    // Step 7: Perform authoritative GET verification
    const verifyBtn = Array.from(reopenedModal?.querySelectorAll('button') ?? []).find((b) =>
      b.textContent?.includes('核验权威状态 (GET)')
    );
    expect(verifyBtn).toBeDefined();

    // Set confirmed authorization id on client inFlight record
    const currentInFlight = _getInFlightSelection('CPM-RO-001');
    if (currentInFlight) {
      currentInFlight.submittedAuthId = 'AUTH-CPM-MATCH';
    }

    // Mock server showing that matching authorization was recorded on server
    fetchPreviewSpy.mockResolvedValueOnce({
      ...mockSelectionPreview,
      control: {
        ...mockSelectionPreview.control!,
        pending_selection_mode: 'dynamic_selection' as any,
        pending_authorization_id: 'AUTH-CPM-MATCH',
        control_version: 4,
      },
    });

    await act(async () => {
      verifyBtn?.click();
    });

    // Step 8: Successfully verified and cleared!
    expect(_getInFlightSelection('CPM-RO-001')).toBeNull();
    expect(document.body.querySelector('[data-testid="selection-action-modal"]')).toBeNull();
    expect(onSuccess).toHaveBeenCalledWith(
      expect.stringContaining('CPM-RO-001 动态选币 授权意图已由服务端受理，等待周期生效')
    );
  });
});
