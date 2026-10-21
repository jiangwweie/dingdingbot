// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  useGlobalEntryControl,
  _resetInFlightGlobalEntryRegistry,
  _reloadInFlightGlobalFromStorage,
  _getInFlightGlobalEntry,
} from './useGlobalEntryControl';
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

describe('useGlobalEntryControl', () => {
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
    _resetInFlightGlobalEntryRegistry();
  });

  it('opens modal and generates inFlight initialized state on requestAction', () => {
    const { result } = renderTestHook(() => useGlobalEntryControl(), createWrapper());

    act(() => {
      result.current.requestAction('pause', 6);
    });

    expect(result.current.isModalOpen).toBe(true);
    expect(result.current.action).toBe('pause');
    expect(result.current.expectedVersion).toBe(6);
    expect(_getInFlightGlobalEntry()?.status).toBe('initialized');
    expect(_getInFlightGlobalEntry()?.idempotency_key).toContain('owner-request:global-entry-pause');
  });

  it('submits pause successfully without requiring TOTP', async () => {
    const pauseSpy = vi.spyOn(controlsApi, 'pauseGlobalEntry').mockResolvedValue({
      configured_state: 'paused',
      effective_state: 'paused',
      version: 7,
      updated_at_ms: 1800000000000,
    });

    const onSuccess = vi.fn();
    const { result } = renderTestHook(() => useGlobalEntryControl({ onSuccess }), createWrapper());

    act(() => {
      result.current.requestAction('pause', 6);
    });

    await act(async () => {
      await result.current.handleConfirm({
        totp: '',
        reason: 'Emergency pause',
      });
    });

    expect(pauseSpy).toHaveBeenCalledTimes(1);
    expect(pauseSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        expected_version: 6,
        reason: 'Emergency pause',
        totp_code: null,
      })
    );
    expect(result.current.isModalOpen).toBe(false);
    expect(_getInFlightGlobalEntry()).toBeNull();
    expect(onSuccess).toHaveBeenCalledWith(expect.stringContaining('全局 ENTRY 已成功暂停 [v7]'));
  });

  it('requires 6-digit TOTP when action is resume', async () => {
    const resumeSpy = vi.spyOn(controlsApi, 'resumeGlobalEntry');
    const { result } = renderTestHook(() => useGlobalEntryControl(), createWrapper());

    act(() => {
      result.current.requestAction('resume', 7);
    });

    await act(async () => {
      await result.current.handleConfirm({
        totp: '123',
        reason: 'Resume trading',
      });
    });

    expect(resumeSpy).not.toHaveBeenCalled();
    expect(result.current.errorMessage).toContain('6 位数字 Google Authenticator 动态口令');
  });

  it('blocks resume when activeFlattenOperation is in progress', async () => {
    const activeFlatten: any = {
      authorization_id: 'auth:flat-active',
      state: 'exits_requested',
    };

    const { result } = renderTestHook(
      () => useGlobalEntryControl({ activeFlattenOperation: activeFlatten }),
      createWrapper()
    );

    act(() => {
      result.current.requestAction('resume', 7);
    });

    expect(result.current.isModalOpen).toBe(false);
    expect(result.current.toastMessage).toContain('受控平仓操作正在执行中');
  });

  it('handles 409 conflict by invalidating and prompting user', async () => {
    vi.spyOn(controlsApi, 'pauseGlobalEntry').mockRejectedValue(
      new ApiError(409, 'control_conflict', 'global_policy_version_conflict')
    );

    const { result } = renderTestHook(() => useGlobalEntryControl(), createWrapper());

    act(() => {
      result.current.requestAction('pause', 6);
    });

    await act(async () => {
      await result.current.handleConfirm({
        totp: '',
        reason: 'test',
      });
    });

    expect(_getInFlightGlobalEntry()).toBeNull();
    expect(result.current.errorMessage).toContain('全局策略版本已发生冲突（409 Conflict）');
  });

  it('locks in unknown_result on network failure and preserves identity across simulated refresh', async () => {
    vi.spyOn(controlsApi, 'pauseGlobalEntry').mockRejectedValue(new Error('Network disconnected'));

    const { result, unmount } = renderTestHook(() => useGlobalEntryControl(), createWrapper());

    act(() => {
      result.current.requestAction('pause', 6);
    });

    const initialKey = _getInFlightGlobalEntry()?.idempotency_key;

    await act(async () => {
      await result.current.handleConfirm({
        totp: '',
        reason: 'Emergency pause',
      });
    });

    expect(result.current.isUnknownResult).toBe(true);
    expect(result.current.errorMessage).toContain('全局控制请求未决或网络超时');
    expect(_getInFlightGlobalEntry()?.status).toBe('unknown_result');

    // Simulate page refresh
    unmount();
    _reloadInFlightGlobalFromStorage();

    const refreshed = renderTestHook(() => useGlobalEntryControl(), createWrapper());

    expect(refreshed.result.current.isUnknownResult).toBe(true);
    expect(refreshed.result.current.inFlight?.idempotency_key).toBe(initialKey);

    // Reopen modal: retains locked state
    act(() => {
      refreshed.result.current.requestAction('pause', 6);
    });
    expect(refreshed.result.current.isModalOpen).toBe(true);
    expect(refreshed.result.current.isUnknownResult).toBe(true);
  });

  it('performs authoritative GET verification: transitions to verified_unapplied when server has not executed', async () => {
    // Inject in-flight unknown_result
    sessionStorage.setItem(
      'brc:owner:in_flight_global_entry',
      JSON.stringify({
        action: 'pause',
        expected_version: 6,
        reason: 'Emergency pause',
        idempotency_key: 'owner-request:global-entry-pause:test-key',
        status: 'unknown_result',
        startedAtMs: Date.now(),
      })
    );
    _reloadInFlightGlobalFromStorage();

    vi.spyOn(controlsApi, 'fetchControls').mockResolvedValue({
      generated_at_ms: Date.now(),
      global_entry: {
        configured_state: 'enabled',
        effective_state: 'enabled',
        policy_version: 6,
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

    const { result } = renderTestHook(() => useGlobalEntryControl(), createWrapper());

    await act(async () => {
      await result.current.handleVerifyStatus();
    });

    expect(_getInFlightGlobalEntry()?.status).toBe('verified_unapplied');
    expect(result.current.isReasonFrozen).toBe(true);
    expect(result.current.errorMessage).toContain('服务端尚未执行本次全局开仓控制');
    expect(_getInFlightGlobalEntry()?.idempotency_key).toBe('owner-request:global-entry-pause:test-key');
  });

  it('performs authoritative GET verification: retains unknown_result and does NOT trigger success when server version has advanced without local identity proof', async () => {
    sessionStorage.setItem(
      'brc:owner:in_flight_global_entry',
      JSON.stringify({
        action: 'pause',
        expected_version: 6,
        reason: 'Emergency pause',
        idempotency_key: 'owner-request:global-entry-pause:test-key',
        status: 'unknown_result',
        startedAtMs: Date.now(),
      })
    );
    _reloadInFlightGlobalFromStorage();

    vi.spyOn(controlsApi, 'fetchControls').mockResolvedValue({
      generated_at_ms: Date.now(),
      global_entry: {
        configured_state: 'paused',
        effective_state: 'paused',
        policy_version: 7,
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

    const onSuccess = vi.fn();
    const { result } = renderTestHook(() => useGlobalEntryControl({ onSuccess }), createWrapper());

    await act(async () => {
      await result.current.handleVerifyStatus();
    });

    expect(onSuccess).not.toHaveBeenCalled();
    expect(_getInFlightGlobalEntry()?.idempotency_key).toBe('owner-request:global-entry-pause:test-key');
    expect(_getInFlightGlobalEntry()?.status).toBe('unknown_result');
    expect(result.current.errorMessage).toContain('未能关联本次请求身份凭据');
  });
});
