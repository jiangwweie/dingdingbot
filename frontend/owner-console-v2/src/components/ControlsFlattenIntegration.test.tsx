// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DangerZoneCard } from './DangerZoneCard';
import { ControlledFlattenModal } from './ControlledFlattenModal';
import {
  useFlattenControl,
  _resetInFlightFlattenRegistry,
  _getInFlightFlatten,
} from '../hooks/useFlattenControl';
import * as controlsApi from '../api/controlsApi';

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

const mockPreview: controlsApi.FlattenPreview = {
  venue_id: 'binance-usdm',
  account_id: 'owner-main',
  owner_policy_version: 9,
  global_entry_enabled: true,
  ticket_ids: ['ticket:btc-long', 'ticket:ada-short'],
  ticket_states: {
    'ticket:btc-long': 'eligible',
    'ticket:ada-short': 'eligible',
  },
  snapshot_digest: 'sha256:' + 'f'.repeat(64),
  first_blocker: null,
  runtime_profile_id: 'account-wide',
};

const mockOperation: controlsApi.OwnerControlOperation = {
  authorization_id: 'owner-auth:fl-integ',
  operation_kind: 'flatten_all',
  state: 'pending',
  version: 1,
  runtime_profile_id: 'account-wide',
  venue_id: 'binance-usdm',
  account_id: 'owner-main',
  target_ticket_ids: ['ticket:btc-long', 'ticket:ada-short'],
  snapshot_digest: 'sha256:' + 'f'.repeat(64),
  first_blocker: null,
  created_at_ms: 1800000000000,
  updated_at_ms: 1800000000000,
};

const TestControlsFlattenContainer: React.FC<{ onSuccess?: (op: any) => void }> = ({
  onSuccess,
}) => {
  const flatten = useFlattenControl({ onSuccess });

  return (
    <div>
      <DangerZoneCard
        activeTicketCount={2}
        onTriggerFlatten={flatten.requestPreview}
        isLoading={flatten.isLoadingPreview}
        currentOperation={flatten.currentOperation}
      />
      <ControlledFlattenModal
        open={flatten.isModalOpen}
        onClose={flatten.closeModal}
        preview={flatten.preview}
        isSubmitting={flatten.isSubmitting}
        isVerifying={flatten.isVerifying}
        errorMessage={flatten.errorMessage}
        isUnknownResult={flatten.isUnknownResult}
        isRetryFrozen={flatten.isRetryFrozen}
        currentOperation={flatten.currentOperation}
        inFlightOperation={flatten.inFlight}
        onConfirm={flatten.handleConfirm}
        onVerifyStatus={flatten.handleVerifyStatus}
        onRefreshPreview={flatten.requestPreview}
      />
    </div>
  );
};

describe('ControlsFlattenIntegration', () => {
  let queryClient: QueryClient;
  let container: HTMLDivElement;
  let root: ReturnType<typeof createRoot>;

  beforeEach(() => {
    vi.restoreAllMocks();
    _resetInFlightFlattenRegistry();
    if (typeof window !== 'undefined' && window.sessionStorage) {
      sessionStorage.clear();
    }
    document.body.innerHTML = '';
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  it('runs complete preview to submit flow end-to-end', async () => {
    vi.spyOn(controlsApi, 'fetchFlattenPreview').mockResolvedValue(mockPreview);
    const submitSpy = vi.spyOn(controlsApi, 'submitFlatten').mockResolvedValue(mockOperation);
    const onSuccess = vi.fn();

    act(() => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <TestControlsFlattenContainer onSuccess={onSuccess} />
        </QueryClientProvider>
      );
    });

    // 1. Click button in DangerZoneCard
    const triggerBtn = container.querySelector(
      '[data-testid="danger-zone-flatten-btn"]'
    ) as HTMLButtonElement;
    expect(triggerBtn).toBeDefined();

    await act(async () => {
      triggerBtn.click();
    });

    // 2. Modal should now be open with preview details
    const modal = document.body.querySelector('[data-testid="controlled-flatten-modal"]');
    expect(modal).not.toBeNull();
    expect(modal?.textContent).toContain('ticket:btc-long');
    expect(modal?.textContent).toContain('ticket:ada-short');

    // 3. Enter TOTP and confirmation text
    const totpInput = modal?.querySelector('input[placeholder="000000"]') as HTMLInputElement;
    const confirmInput = modal?.querySelector(
      'input[placeholder="确认平仓全部持仓"]'
    ) as HTMLInputElement;
    const submitBtn = modal?.querySelector('button[type="submit"]') as HTMLButtonElement;

    expect(submitBtn.disabled).toBe(true);

    act(() => {
      setInputValue(totpInput, '888999');
      setInputValue(confirmInput, '确认平仓全部持仓');
    });

    expect(submitBtn.disabled).toBe(false);

    // 4. Submit flatten
    await act(async () => {
      submitBtn.click();
    });

    expect(submitSpy).toHaveBeenCalledWith({
      expected_version: 9,
      reason: 'owner_flatten_all',
      idempotency_key: expect.stringContaining('owner-request:flatten-all:'),
      totp_code: '888999',
      snapshot_digest: 'sha256:' + 'f'.repeat(64),
      confirmation_text: '确认平仓全部持仓',
    });

    expect(onSuccess).toHaveBeenCalledWith(mockOperation);

    // Modal should now be closed
    const closedModal = document.body.querySelector('[data-testid="controlled-flatten-modal"]');
    expect(closedModal).toBeNull();
  });

  it('locks down on network timeout, maintains lock after cancel, and resolves via verification', async () => {
    vi.spyOn(controlsApi, 'fetchFlattenPreview').mockResolvedValue(mockPreview);
    vi.spyOn(controlsApi, 'submitFlatten').mockRejectedValue(new Error('Gateway Timeout 504'));

    act(() => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <TestControlsFlattenContainer />
        </QueryClientProvider>
      );
    });

    // Trigger preview
    const triggerBtn = container.querySelector(
      '[data-testid="danger-zone-flatten-btn"]'
    ) as HTMLButtonElement;
    await act(async () => {
      triggerBtn.click();
    });

    const modal = document.body.querySelector('[data-testid="controlled-flatten-modal"]');
    const totpInput = modal?.querySelector('input[placeholder="000000"]') as HTMLInputElement;
    const confirmInput = modal?.querySelector(
      'input[placeholder="确认平仓全部持仓"]'
    ) as HTMLInputElement;
    const submitBtn = modal?.querySelector('button[type="submit"]') as HTMLButtonElement;

    act(() => {
      setInputValue(totpInput, '111222');
      setInputValue(confirmInput, '确认平仓全部持仓');
    });

    // Submit -> triggers timeout
    await act(async () => {
      submitBtn.click();
    });

    // Modal is in unknown result mode
    expect(modal?.textContent).toContain('平仓结果未知（闭锁保护）');
    expect(submitBtn.disabled).toBe(true);

    // Cancel modal
    const cancelBtn = Array.from(modal?.querySelectorAll('button') ?? []).find(
      (b) => b.textContent === '取消'
    );
    act(() => {
      cancelBtn?.click();
    });

    // Re-open from DangerZoneCard
    await act(async () => {
      triggerBtn.click();
    });

    // Modal opens directly in unknown result lockdown mode
    const reopenedModal = document.body.querySelector('[data-testid="controlled-flatten-modal"]');
    expect(reopenedModal?.textContent).toContain('平仓结果未知（闭锁保护）');
    const verifyBtn = Array.from(reopenedModal?.querySelectorAll('button') ?? []).find(
      (b) => b.textContent?.includes('核验权威状态 (GET)')
    );
    expect(verifyBtn).toBeDefined();

    // Mock authoritative check returning the completed operation
    vi.spyOn(controlsApi, 'fetchControls').mockResolvedValue({
      generated_at_ms: 1800000000000,
      global_entry: {
        configured_state: 'paused',
        effective_state: 'paused',
        policy_version: 10,
        active_ticket_count: 0,
      },
      account_capacity: {} as any,
      runtime_entry_authority: {} as any,
      dynamic_selection: null,
      strategies: [],
      current_operation: {
        ...mockOperation,
        state: 'completed',
      },
      recent_operations: [],
      events: [],
    });

    // Click verify
    await act(async () => {
      verifyBtn?.click();
    });

    // Modal closes upon successful verification
    const finalModal = document.body.querySelector('[data-testid="controlled-flatten-modal"]');
    expect(finalModal).toBeNull();
  });

  it('retains unknown result lockdown across simulated browser reload and prevents duplicate submission', async () => {
    vi.spyOn(controlsApi, 'fetchFlattenPreview').mockResolvedValue(mockPreview);
    vi.spyOn(controlsApi, 'submitFlatten').mockRejectedValue(new Error('Network disconnected'));

    act(() => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <TestControlsFlattenContainer />
        </QueryClientProvider>
      );
    });

    // 1. Open modal & submit -> triggers timeout/unknown result
    const triggerBtn = container.querySelector(
      '[data-testid="danger-zone-flatten-btn"]'
    ) as HTMLButtonElement;
    await act(async () => {
      triggerBtn.click();
    });

    const modal = document.body.querySelector('[data-testid="controlled-flatten-modal"]');
    const totpInput = modal?.querySelector('input[placeholder="000000"]') as HTMLInputElement;
    const confirmInput = modal?.querySelector(
      'input[placeholder="确认平仓全部持仓"]'
    ) as HTMLInputElement;
    const submitBtn = modal?.querySelector('button[type="submit"]') as HTMLButtonElement;

    act(() => {
      setInputValue(totpInput, '123456');
      setInputValue(confirmInput, '确认平仓全部持仓');
    });

    await act(async () => {
      submitBtn.click();
    });

    expect(modal?.textContent).toContain('平仓结果未知（闭锁保护）');
    const originalKey = _getInFlightFlatten()?.idempotency_key;
    expect(originalKey).toBeDefined();

    // 2. Simulate browser reload:
    // Unmount current root, discard DOM container, but preserve sessionStorage
    act(() => {
      root.unmount();
    });
    container.remove();

    // New mount (simulating reloaded page)
    const newContainer = document.createElement('div');
    document.body.appendChild(newContainer);
    const newRoot = createRoot(newContainer);

    act(() => {
      newRoot.render(
        <QueryClientProvider client={queryClient}>
          <TestControlsFlattenContainer />
        </QueryClientProvider>
      );
    });

    // 3. Open modal on the fresh page
    const newTriggerBtn = newContainer.querySelector(
      '[data-testid="danger-zone-flatten-btn"]'
    ) as HTMLButtonElement;
    await act(async () => {
      newTriggerBtn.click();
    });

    // 4. Modal is immediately locked in unknown result mode
    const reloadedModal = document.body.querySelector('[data-testid="controlled-flatten-modal"]');
    expect(reloadedModal?.textContent).toContain('平仓结果未知（闭锁保护）');
    expect(reloadedModal?.textContent).toContain('网络超时或未决请求');

    // Submit button must be disabled
    const reloadedSubmitBtn = reloadedModal?.querySelector('button[type="submit"]') as HTMLButtonElement;
    expect(reloadedSubmitBtn.disabled).toBe(true);

    // Idempotency key must remain frozen to original key, NO new key generated
    expect(_getInFlightFlatten()?.idempotency_key).toBe(originalKey);

    act(() => {
      newRoot.unmount();
    });
    newContainer.remove();
  });

  it('displays active operation status in DangerZoneCard and opens progress view preventing new flatten intent', async () => {
    vi.spyOn(controlsApi, 'fetchFlattenPreview').mockResolvedValue(mockPreview);
    vi.spyOn(controlsApi, 'submitFlatten').mockResolvedValue(mockOperation); // mockOperation has state: 'pending'

    act(() => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <TestControlsFlattenContainer />
        </QueryClientProvider>
      );
    });

    // 1. Trigger preview and submit
    const triggerBtn = container.querySelector(
      '[data-testid="danger-zone-flatten-btn"]'
    ) as HTMLButtonElement;
    await act(async () => {
      triggerBtn.click();
    });

    const modal = document.body.querySelector('[data-testid="controlled-flatten-modal"]');
    const totpInput = modal?.querySelector('input[placeholder="000000"]') as HTMLInputElement;
    const confirmInput = modal?.querySelector(
      'input[placeholder="确认平仓全部持仓"]'
    ) as HTMLInputElement;
    const submitBtn = modal?.querySelector('button[type="submit"]') as HTMLButtonElement;

    act(() => {
      setInputValue(totpInput, '888999');
      setInputValue(confirmInput, '确认平仓全部持仓');
    });

    await act(async () => {
      submitBtn.click();
    });

    // Modal closes upon submit
    expect(document.body.querySelector('[data-testid="controlled-flatten-modal"]')).toBeNull();

    // 2. DangerZoneCard now displays active operation progress button
    const activeOpBtn = container.querySelector(
      '[data-testid="danger-zone-flatten-btn"]'
    ) as HTMLButtonElement;
    expect(container.textContent).toContain('平仓进行中 (pending) · 查看进度');

    // 3. Clicking "查看进度" opens progress view
    await act(async () => {
      activeOpBtn.click();
    });

    const progressModal = document.body.querySelector('[data-testid="controlled-flatten-modal"]');
    expect(progressModal).not.toBeNull();
    expect(progressModal?.textContent).toContain('受控平仓正在执行中 (Controlled Flatten Active)');
    expect(progressModal?.textContent).toContain('已受理平仓任务，正在由 Lifecycle 进程推进有序退出');
    expect(progressModal?.textContent).toContain('ticket:btc-long');
    expect(progressModal?.textContent).toContain('ticket:ada-short');

    // Ensure NO submission form or confirm button is rendered
    expect(progressModal?.querySelector('input')).toBeNull();
    expect(progressModal?.querySelector('button[type="submit"]')).toBeNull();
    expect(progressModal?.textContent).toContain('关闭');
  });

  it('refuses to clear unknown result lock when authoritative GET only returns historical completed operation with same snapshot_digest', async () => {
    vi.spyOn(controlsApi, 'fetchFlattenPreview').mockResolvedValue(mockPreview);
    vi.spyOn(controlsApi, 'submitFlatten').mockRejectedValue(new Error('Gateway Timeout'));

    act(() => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <TestControlsFlattenContainer />
        </QueryClientProvider>
      );
    });

    // 1. Submit flatten -> network timeout -> unknown result
    const triggerBtn = container.querySelector(
      '[data-testid="danger-zone-flatten-btn"]'
    ) as HTMLButtonElement;
    await act(async () => {
      triggerBtn.click();
    });

    const modal = document.body.querySelector('[data-testid="controlled-flatten-modal"]');
    const totpInput = modal?.querySelector('input[placeholder="000000"]') as HTMLInputElement;
    const confirmInput = modal?.querySelector(
      'input[placeholder="确认平仓全部持仓"]'
    ) as HTMLInputElement;
    const submitBtn = modal?.querySelector('button[type="submit"]') as HTMLButtonElement;

    act(() => {
      setInputValue(totpInput, '111222');
      setInputValue(confirmInput, '确认平仓全部持仓');
    });

    await act(async () => {
      submitBtn.click();
    });

    expect(modal?.textContent).toContain('平仓结果未知（闭锁保护）');
    const originalKey = _getInFlightFlatten()?.idempotency_key;

    // 2. Mock authoritative GET returning NO active operation, but a historical completed operation with SAME digest
    vi.spyOn(controlsApi, 'fetchControls').mockResolvedValue({
      generated_at_ms: Date.now(),
      global_entry: {
        configured_state: 'paused',
        effective_state: 'paused',
        policy_version: 9, // Same policy version, unapplied on server
        active_ticket_count: 0,
      },
      account_capacity: {} as any,
      runtime_entry_authority: {} as any,
      dynamic_selection: null,
      strategies: [],
      current_operation: null,
      recent_operations: [
        {
          authorization_id: 'owner-auth:historical-past-op',
          operation_kind: 'flatten_all',
          state: 'completed',
          version: 1,
          runtime_profile_id: 'account-wide',
          venue_id: 'binance-usdm',
          account_id: 'owner-main',
          target_ticket_ids: ['ticket:btc-long'],
          snapshot_digest: mockPreview.snapshot_digest, // Identical digest from past operation
          first_blocker: null,
          created_at_ms: Date.now() - 3600000,
          updated_at_ms: Date.now() - 3500000,
        },
      ],
      events: [],
    });

    // 3. Click "核验权威状态 (GET)"
    const verifyBtn = Array.from(modal?.querySelectorAll('button') ?? []).find(
      (b) => b.textContent?.includes('核验权威状态 (GET)')
    );
    await act(async () => {
      verifyBtn?.click();
    });

    // 4. Modal must NOT close! It must refuse to clear lock on identical snapshot digest
    const lockedModal = document.body.querySelector('[data-testid="controlled-flatten-modal"]');
    expect(lockedModal).not.toBeNull();
    expect(lockedModal?.textContent).toContain('历史同快照记录无法作为本次凭据');

    // Lock remains active with frozen idempotency key
    expect(_getInFlightFlatten()?.status).toBe('verified_unapplied');
    expect(_getInFlightFlatten()?.idempotency_key).toBe(originalKey);
  });

  it('runs complete combined path: refresh -> verify server has no record -> restores preview -> retries with frozen original request', async () => {
    vi.spyOn(controlsApi, 'fetchFlattenPreview').mockResolvedValue(mockPreview);
    const submitSpy = vi.spyOn(controlsApi, 'submitFlatten')
      .mockRejectedValueOnce(new Error('Network disconnected on submit'))
      .mockResolvedValueOnce(mockOperation);

    act(() => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <TestControlsFlattenContainer />
        </QueryClientProvider>
      );
    });

    // 1. Initial preview and submit -> fails with network error
    const triggerBtn = container.querySelector(
      '[data-testid="danger-zone-flatten-btn"]'
    ) as HTMLButtonElement;
    await act(async () => {
      triggerBtn.click();
    });

    const modal = document.body.querySelector('[data-testid="controlled-flatten-modal"]');
    const totpInput = modal?.querySelector('input[placeholder="000000"]') as HTMLInputElement;
    const confirmInput = modal?.querySelector(
      'input[placeholder="确认平仓全部持仓"]'
    ) as HTMLInputElement;
    const submitBtn = modal?.querySelector('button[type="submit"]') as HTMLButtonElement;

    act(() => {
      setInputValue(totpInput, '111111');
      setInputValue(confirmInput, '确认平仓全部持仓');
    });

    await act(async () => {
      submitBtn.click();
    });

    expect(modal?.textContent).toContain('平仓结果未知（闭锁保护）');
    const originalKey = _getInFlightFlatten()?.idempotency_key;
    expect(originalKey).toBeDefined();

    // 2. Real browser reload simulation:
    // Unmount root and DOM container, but preserve sessionStorage
    act(() => {
      root.unmount();
    });
    container.remove();

    const newContainer = document.createElement('div');
    document.body.appendChild(newContainer);
    const newRoot = createRoot(newContainer);

    act(() => {
      newRoot.render(
        <QueryClientProvider client={queryClient}>
          <TestControlsFlattenContainer />
        </QueryClientProvider>
      );
    });

    // Open modal on fresh page
    const newTriggerBtn = newContainer.querySelector(
      '[data-testid="danger-zone-flatten-btn"]'
    ) as HTMLButtonElement;
    await act(async () => {
      newTriggerBtn.click();
    });

    const reloadedModal = document.body.querySelector('[data-testid="controlled-flatten-modal"]');
    expect(reloadedModal?.textContent).toContain('平仓结果未知（闭锁保护）');
    // Restored preview shows tickets and snapshot
    expect(reloadedModal?.textContent).toContain('ticket:btc-long');
    expect(reloadedModal?.textContent).toContain('ticket:ada-short');

    // 3. Click "核验权威状态 (GET)" -> server returns no active task, policy version unchanged (9)
    vi.spyOn(controlsApi, 'fetchControls').mockResolvedValue({
      generated_at_ms: Date.now(),
      global_entry: {
        configured_state: 'paused',
        effective_state: 'paused',
        policy_version: 9,
        active_ticket_count: 2,
      },
      account_capacity: {} as any,
      runtime_entry_authority: {} as any,
      dynamic_selection: null,
      strategies: [],
      current_operation: null,
      recent_operations: [],
      events: [],
    });

    const verifyBtn = Array.from(reloadedModal?.querySelectorAll('button') ?? []).find(
      (b) => b.textContent?.includes('核验权威状态 (GET)')
    );
    expect(verifyBtn).toBeDefined();

    await act(async () => {
      verifyBtn?.click();
    });

    // 4. Modal is now in verified_unapplied state:
    // - Shows "重试已锁定原请求"
    // - Shows "再次核验权威状态 (GET)" button
    // - Preserves restored preview tickets
    expect(reloadedModal?.textContent).toContain('重试已锁定原请求');
    expect(reloadedModal?.textContent).toContain('再次核验权威状态 (GET)');
    expect(reloadedModal?.textContent).toContain('ticket:btc-long');
    expect(reloadedModal?.textContent).toContain('ticket:ada-short');

    // 5. User enters TOTP and confirmation text to perform retry
    const retryTotp = reloadedModal?.querySelector('input[placeholder="000000"]') as HTMLInputElement;
    const retryConfirm = reloadedModal?.querySelector(
      'input[placeholder="确认平仓全部持仓"]'
    ) as HTMLInputElement;
    const retrySubmitBtn = reloadedModal?.querySelector('button[type="submit"]') as HTMLButtonElement;

    expect(retrySubmitBtn.disabled).toBe(true);

    act(() => {
      setInputValue(retryTotp, '222222');
      setInputValue(retryConfirm, '确认平仓全部持仓');
    });

    // Submit button is now enabled!
    expect(retrySubmitBtn.disabled).toBe(false);

    // 6. Click retry submit
    await act(async () => {
      retrySubmitBtn.click();
    });

    // Verified that submit was called with EXACT original frozen key, version, and digest!
    expect(submitSpy).toHaveBeenCalledTimes(2);
    expect(submitSpy).toHaveBeenLastCalledWith({
      expected_version: 9,
      reason: 'owner_flatten_all',
      idempotency_key: originalKey, // EXACT SAME IDEMPOTENCY KEY
      totp_code: '222222',
      snapshot_digest: mockPreview.snapshot_digest,
      confirmation_text: '确认平仓全部持仓',
    });

    // Modal closes upon successful submit
    expect(document.body.querySelector('[data-testid="controlled-flatten-modal"]')).toBeNull();

    act(() => {
      newRoot.unmount();
    });
    newContainer.remove();
  });
});
