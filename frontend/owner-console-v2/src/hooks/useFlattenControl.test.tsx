// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  useFlattenControl,
  _resetInFlightFlattenRegistry,
  _getInFlightFlatten,
} from './useFlattenControl';
import * as controlsApi from '../api/controlsApi';
import { ApiError } from '../api/errors';

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function renderTestHook<T>(hook: () => T, wrapper: React.ComponentType<{ children: React.ReactNode }>) {
  const result = { current: null as unknown as T };
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  const TestComponent = () => {
    result.current = hook();
    return null;
  };

  act(() => {
    const WrapperComponent = wrapper;
    root.render(
      <WrapperComponent>
        <TestComponent />
      </WrapperComponent>
    );
  });

  return {
    result,
    unmount: () => {
      act(() => {
        root.unmount();
      });
      container.remove();
    },
  };
}

describe('useFlattenControl', () => {
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
    _resetInFlightFlattenRegistry();
  });

  const mockPreview: controlsApi.FlattenPreview = {
    venue_id: 'binance-usdm',
    account_id: 'owner-main',
    owner_policy_version: 6,
    global_entry_enabled: true,
    ticket_ids: ['ticket:btc-long', 'ticket:eth-short'],
    ticket_states: {
      'ticket:btc-long': 'eligible',
      'ticket:eth-short': 'eligible',
    },
    snapshot_digest: 'sha256:' + '1'.repeat(64),
    first_blocker: null,
    runtime_profile_id: 'account-wide',
  };

  const mockOperation: controlsApi.OwnerControlOperation = {
    authorization_id: 'owner-auth:fl-1',
    operation_kind: 'flatten_all',
    state: 'pending',
    version: 1,
    runtime_profile_id: 'account-wide',
    venue_id: 'binance-usdm',
    account_id: 'owner-main',
    target_ticket_ids: ['ticket:btc-long', 'ticket:eth-short'],
    snapshot_digest: 'sha256:' + '1'.repeat(64),
    first_blocker: null,
    created_at_ms: 1800000000000,
    updated_at_ms: 1800000000000,
  };

  it('fetches preview and opens modal on requestPreview', async () => {
    vi.spyOn(controlsApi, 'fetchFlattenPreview').mockResolvedValue(mockPreview);

    const { result } = renderTestHook(() => useFlattenControl(), createWrapper());

    await act(async () => {
      await result.current.requestPreview();
    });

    expect(result.current.isModalOpen).toBe(true);
    expect(result.current.preview).toEqual(mockPreview);
    expect(result.current.errorMessage).toBeNull();
  });

  it('invokes options.onError when preview request fails with HTTP 500', async () => {
    vi.spyOn(controlsApi, 'fetchFlattenPreview').mockRejectedValue(
      new ApiError(500, 'internal_error', 'Database timeout')
    );

    const onError = vi.fn();
    const { result } = renderTestHook(() => useFlattenControl({ onError }), createWrapper());

    await act(async () => {
      await result.current.requestPreview();
    });

    expect(result.current.isModalOpen).toBe(false);
    expect(onError).toHaveBeenCalledWith(expect.stringContaining('Database timeout'));
    expect(result.current.toastMessage).toContain('Database timeout');
  });

  it('sets error and warns when preview has first_blocker', async () => {
    const blockedPreview: controlsApi.FlattenPreview = {
      ...mockPreview,
      first_blocker: 'ticket_not_flattenable:ticket:btc-long:entry_pending',
    };
    vi.spyOn(controlsApi, 'fetchFlattenPreview').mockResolvedValue(blockedPreview);

    const { result } = renderTestHook(() => useFlattenControl(), createWrapper());

    await act(async () => {
      await result.current.requestPreview();
    });

    expect(result.current.isModalOpen).toBe(true);
    expect(result.current.preview?.first_blocker).toBe(
      'ticket_not_flattenable:ticket:btc-long:entry_pending'
    );
    expect(result.current.errorMessage).toContain('存在不可平仓的中间态持仓');

    // Attempting submit while blocked is rejected
    await act(async () => {
      await result.current.handleConfirm({
        totp: '123456',
        confirmText: '确认平仓全部持仓',
      });
    });
    expect(result.current.errorMessage).toContain('当前持仓存在阻断条件');
  });

  it('validates confirmation text and TOTP format', async () => {
    vi.spyOn(controlsApi, 'fetchFlattenPreview').mockResolvedValue(mockPreview);

    const { result } = renderTestHook(() => useFlattenControl(), createWrapper());

    await act(async () => {
      await result.current.requestPreview();
    });

    // Wrong confirmation text
    await act(async () => {
      await result.current.handleConfirm({
        totp: '123456',
        confirmText: '确认平仓',
      });
    });
    expect(result.current.errorMessage).toContain('必须准确输入“确认平仓全部持仓”');

    // Wrong TOTP format
    await act(async () => {
      await result.current.handleConfirm({
        totp: '123',
        confirmText: '确认平仓全部持仓',
      });
    });
    expect(result.current.errorMessage).toContain('请输入 6 位数字 Google Authenticator 动态口令');
  });

  it('submits flatten successfully and invalidates tickets, overview, causality, and controls', async () => {
    vi.spyOn(controlsApi, 'fetchFlattenPreview').mockResolvedValue(mockPreview);
    const submitSpy = vi.spyOn(controlsApi, 'submitFlatten').mockResolvedValue(mockOperation);

    const onSuccess = vi.fn();
    const { result } = renderTestHook(() => useFlattenControl({ onSuccess }), createWrapper());
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    await act(async () => {
      await result.current.requestPreview();
    });

    await act(async () => {
      await result.current.handleConfirm({
        totp: '123456',
        confirmText: '确认平仓全部持仓',
      });
    });

    expect(submitSpy).toHaveBeenCalledWith({
      expected_version: 6,
      reason: 'owner_flatten_all',
      idempotency_key: expect.stringContaining('owner-request:flatten-all:'),
      totp_code: '123456',
      snapshot_digest: 'sha256:' + '1'.repeat(64),
      confirmation_text: '确认平仓全部持仓',
    });

    expect(result.current.toastMessage).toContain('受控平仓指令已受理 (pending)');
    expect(result.current.currentOperation).toEqual(mockOperation);
    expect(onSuccess).toHaveBeenCalledWith(mockOperation);

    // Verifies correct cache invalidation
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: controlsApi.controlsQueryKey });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['owner', 'tickets'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['owner', 'overview'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['owner', 'causality'] });
  });

  it('handles 409 snapshot conflict by invalidating preview and prompting re-preview', async () => {
    vi.spyOn(controlsApi, 'fetchFlattenPreview').mockResolvedValue(mockPreview);
    vi.spyOn(controlsApi, 'submitFlatten').mockRejectedValue(
      new ApiError(409, 'control_conflict', 'flatten_snapshot_conflict')
    );

    const { result } = renderTestHook(() => useFlattenControl(), createWrapper());

    await act(async () => {
      await result.current.requestPreview();
    });

    await act(async () => {
      await result.current.handleConfirm({
        totp: '123456',
        confirmText: '确认平仓全部持仓',
      });
    });

    expect(result.current.preview).toBeNull();
    expect(result.current.errorMessage).toContain('持仓状态快照已发生变动（409 Conflict）');
    expect(_getInFlightFlatten()).toBeNull();
  });

  it('locks in unknown result on network timeout, and retains lockdown after browser refresh', async () => {
    vi.spyOn(controlsApi, 'fetchFlattenPreview').mockResolvedValue(mockPreview);
    vi.spyOn(controlsApi, 'submitFlatten').mockRejectedValue(new Error('Network Timeout'));

    const { result, unmount } = renderTestHook(() => useFlattenControl(), createWrapper());

    await act(async () => {
      await result.current.requestPreview();
    });

    await act(async () => {
      await result.current.handleConfirm({
        totp: '123456',
        confirmText: '确认平仓全部持仓',
      });
    });

    expect(result.current.isUnknownResult).toBe(true);
    expect(result.current.errorMessage).toContain('平仓请求未决或网络超时');

    const inFlightOp = _getInFlightFlatten();
    expect(inFlightOp).not.toBeNull();
    expect(inFlightOp?.status).toBe('unknown_result');
    const originalKey = inFlightOp?.idempotency_key;

    // Simulate page refresh: unmount current hook and verify sessionStorage has persisted operation
    unmount();
    expect(sessionStorage.getItem('brc:owner:in_flight_flatten')).not.toBeNull();

    // Re-mount hook (simulating page reload)
    const { result: reloadedResult } = renderTestHook(() => useFlattenControl(), createWrapper());

    expect(reloadedResult.current.isUnknownResult).toBe(true);

    // Opening flatten preview detects the persisted in-flight unknown operation and maintains lock
    await act(async () => {
      await reloadedResult.current.requestPreview();
    });

    expect(reloadedResult.current.isModalOpen).toBe(true);
    expect(reloadedResult.current.isUnknownResult).toBe(true);
    expect(reloadedResult.current.errorMessage).toContain('存在未决的受控平仓操作');

    // Attempting submit while in unknown result remains blocked
    await act(async () => {
      await reloadedResult.current.handleConfirm({
        totp: '123456',
        confirmText: '确认平仓全部持仓',
      });
    });

    // Idempotency key did NOT change or regenerate
    expect(_getInFlightFlatten()?.idempotency_key).toBe(originalKey);
  });

  it('keeps active operation in progress and prevents creating a duplicate second flatten operation', async () => {
    vi.spyOn(controlsApi, 'fetchFlattenPreview').mockResolvedValue(mockPreview);
    vi.spyOn(controlsApi, 'submitFlatten').mockResolvedValue(mockOperation);

    const { result } = renderTestHook(() => useFlattenControl(), createWrapper());

    await act(async () => {
      await result.current.requestPreview();
    });

    await act(async () => {
      await result.current.handleConfirm({
        totp: '123456',
        confirmText: '确认平仓全部持仓',
      });
    });

    // Operation was submitted and is pending
    expect(result.current.isOperationActive).toBe(true);
    expect(result.current.currentOperation?.state).toBe('pending');

    // Attempting another preview while operation is in progress prevents second submission
    await act(async () => {
      await result.current.requestPreview();
    });

    expect(result.current.errorMessage).toContain('受控平仓操作正在执行或确认中');

    // Submit is disabled while isOperationActive is true
    await act(async () => {
      await result.current.handleConfirm({
        totp: '123456',
        confirmText: '确认平仓全部持仓',
      });
    });

    expect(controlsApi.submitFlatten).toHaveBeenCalledTimes(1);
  });

  it('does NOT clear unknown lockdown when historical completed operation has identical snapshot_digest', async () => {
    vi.spyOn(controlsApi, 'fetchFlattenPreview').mockResolvedValue(mockPreview);
    vi.spyOn(controlsApi, 'submitFlatten').mockRejectedValue(new Error('Network Timeout'));

    const { result } = renderTestHook(() => useFlattenControl(), createWrapper());

    await act(async () => {
      await result.current.requestPreview();
    });
    await act(async () => {
      await result.current.handleConfirm({
        totp: '123456',
        confirmText: '确认平仓全部持仓',
      });
    });

    expect(result.current.isUnknownResult).toBe(true);

    // Mock fetchControls returning a historical completed operation with the same snapshot_digest
    // but created in the past (before our submit started)
    const historicalCompletedOp: controlsApi.OwnerControlOperation = {
      authorization_id: 'owner-auth:fl-old',
      operation_kind: 'flatten_all',
      state: 'completed',
      version: 5,
      runtime_profile_id: 'account-wide',
      venue_id: 'binance-usdm',
      account_id: 'owner-main',
      target_ticket_ids: [],
      snapshot_digest: mockPreview.snapshot_digest,
      first_blocker: null,
      created_at_ms: 1700000000000, // Historical!
      updated_at_ms: 1700000000000,
    };

    vi.spyOn(controlsApi, 'fetchControls').mockResolvedValue({
      generated_at_ms: 1800000000000,
      global_entry: {
        configured_state: 'paused',
        effective_state: 'paused',
        policy_version: 6,
        active_ticket_count: 0,
      },
      account_capacity: {} as any,
      runtime_entry_authority: {} as any,
      dynamic_selection: null,
      strategies: [],
      current_operation: null,
      recent_operations: [historicalCompletedOp],
      events: [],
    });

    await act(async () => {
      await result.current.handleVerifyStatus();
    });

    // CANNOT clear unknown lock! Must retain in-flight operation and indicate unapplied
    expect(_getInFlightFlatten()).not.toBeNull();
    expect(result.current.isRetryFrozen).toBe(true);
    expect(result.current.errorMessage).toContain('历史同快照记录无法作为本次凭据，未决闭锁已保持');
  });

  it('binds to active current_operation created during our window when submittedAuthId was lost', async () => {
    vi.spyOn(controlsApi, 'fetchFlattenPreview').mockResolvedValue(mockPreview);
    vi.spyOn(controlsApi, 'submitFlatten').mockRejectedValue(new Error('Network Timeout'));

    const { result } = renderTestHook(() => useFlattenControl(), createWrapper());

    await act(async () => {
      await result.current.requestPreview();
    });
    await act(async () => {
      await result.current.handleConfirm({
        totp: '123456',
        confirmText: '确认平仓全部持仓',
      });
    });

    expect(result.current.isUnknownResult).toBe(true);

    const now = Date.now();
    const liveServerOp: controlsApi.OwnerControlOperation = {
      authorization_id: 'owner-auth:fl-live',
      operation_kind: 'flatten_all',
      state: 'exits_requested',
      version: 2,
      runtime_profile_id: 'account-wide',
      venue_id: 'binance-usdm',
      account_id: 'owner-main',
      target_ticket_ids: ['ticket:btc-long'],
      snapshot_digest: mockPreview.snapshot_digest,
      first_blocker: null,
      created_at_ms: now,
      updated_at_ms: now,
    };

    vi.spyOn(controlsApi, 'fetchControls').mockResolvedValue({
      generated_at_ms: now,
      global_entry: {
        configured_state: 'paused',
        effective_state: 'paused',
        policy_version: 6,
        active_ticket_count: 1,
      },
      account_capacity: {} as any,
      runtime_entry_authority: {} as any,
      dynamic_selection: null,
      strategies: [],
      current_operation: liveServerOp,
      recent_operations: [],
      events: [],
    });

    await act(async () => {
      await result.current.handleVerifyStatus();
    });

    expect(result.current.currentOperation?.authorization_id).toBe('owner-auth:fl-live');
    expect(result.current.currentOperation?.state).toBe('exits_requested');
    expect(result.current.toastMessage).toContain('已识别到服务端正在执行本次平仓操作');
    expect(_getInFlightFlatten()?.submittedAuthId).toBe('owner-auth:fl-live');
  });
});
