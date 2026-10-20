// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useStrategyControl, _resetInFlightRegistry } from './useStrategyControl';
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

describe('useStrategyControl hook', () => {
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
    _resetInFlightRegistry();
  });

  it('configures pause modal correctly for enabled strategy (no TOTP required)', () => {
    const { result, unmount } = renderTestHook(() => useStrategyControl(), createWrapper());

    act(() => {
      result.current.requestToggle({
        strategy_group_id: 'CPM-RO-001',
        configured_state: 'enabled',
        control_version: 2,
        name_zh: '均线回踩做多',
      });
    });

    expect(result.current.modalProps.open).toBe(true);
    expect(result.current.modalProps.actionKind).toBe('pause');
    expect(result.current.modalProps.requireTotp).toBe(false);
    expect(result.current.modalProps.requireReason).toBe(true);
    expect(result.current.modalProps.expectedVersion).toBe(2);
    expect(result.current.modalProps.title).toContain('确认暂停新准入: CPM-RO-001');
    expect(result.current.modalProps.description).toContain('暂停仅阻断 CPM-RO-001 新的 ENTRY 开仓准入');
    expect(result.current.modalProps.confirmLabel).toBe('确认暂停新准入');
    unmount();
  });

  it('configures resume modal correctly for paused strategy (TOTP required)', () => {
    const { result, unmount } = renderTestHook(() => useStrategyControl(), createWrapper());

    act(() => {
      result.current.requestToggle({
        strategy_group_id: 'CPM-RO-001',
        configured_state: 'paused',
        control_version: 5,
        name_zh: '均线回踩做多',
      });
    });

    expect(result.current.modalProps.open).toBe(true);
    expect(result.current.modalProps.actionKind).toBe('resume');
    expect(result.current.modalProps.requireTotp).toBe(true);
    expect(result.current.modalProps.requireReason).toBe(true);
    expect(result.current.modalProps.expectedVersion).toBe(5);
    expect(result.current.modalProps.title).toContain('确认恢复新准入: CPM-RO-001');
    expect(result.current.modalProps.description).toContain('恢复后，CPM-RO-001 的有效信号将允许创建 Ticket');
    expect(result.current.modalProps.confirmLabel).toBe('确认恢复新准入');
    unmount();
  });

  it('blocks resume attempt for permanently retired SOR-001', () => {
    const { result, unmount } = renderTestHook(() => useStrategyControl(), createWrapper());

    act(() => {
      result.current.requestToggle({
        strategy_group_id: 'SOR-001',
        configured_state: 'paused',
        control_version: 1,
        is_retired: true,
      });
    });

    expect(result.current.errorMessage).toContain('SOR-001 已永久退役，禁止恢复新准入');
    unmount();
  });

  it('executes pause with unique idempotency key, expected_version, and no TOTP', async () => {
    const pauseSpy = vi.spyOn(controlsApi, 'pauseStrategy').mockResolvedValue({
      strategy_group_id: 'CPM-RO-001',
      entry_state: 'paused' as any,
      control_version: 3,
      last_event_id: 'evt-1',
      reason: 'Owner 手动暂停新准入',
      updated_at_ms: 1800000000000,
    });

    const invalidateSpy = vi.spyOn(QueryClient.prototype, 'invalidateQueries');

    const onSuccess = vi.fn();
    const { result, unmount } = renderTestHook(() => useStrategyControl({ onSuccess }), createWrapper());

    act(() => {
      result.current.requestToggle({
        strategy_group_id: 'CPM-RO-001',
        configured_state: 'enabled',
        control_version: 2,
      });
    });

    await act(async () => {
      await result.current.modalProps.onConfirm({
        totp: '',
        reason: '测试暂停原因',
      });
    });

    expect(pauseSpy).toHaveBeenCalledTimes(1);
    const [strategyId, body] = pauseSpy.mock.calls[0];
    expect(strategyId).toBe('CPM-RO-001');
    expect(body.expected_version).toBe(2);
    expect(body.reason).toBe('测试暂停原因');
    expect(body.totp_code).toBeNull();
    expect(body.idempotency_key).toMatch(/^owner-request:strategy-pause:CPM-RO-001:/);

    // Invalidates both controls and strategies
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: controlsApi.controlsQueryKey });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['owner', 'strategies'] });

    expect(onSuccess).toHaveBeenCalledWith('已成功暂停 CPM-RO-001 新准入');
    expect(result.current.toastMessage).toBe('已成功暂停 CPM-RO-001 新准入');
    expect(result.current.modalProps.open).toBe(false);
    unmount();
  });

  it('executes resume with valid 6-digit TOTP and expected_version', async () => {
    const resumeSpy = vi.spyOn(controlsApi, 'resumeStrategy').mockResolvedValue({
      strategy_group_id: 'BRF2-001',
      entry_state: 'enabled' as any,
      control_version: 4,
      last_event_id: 'evt-2',
      reason: 'Owner 手动恢复新准入',
      updated_at_ms: 1800000000000,
    });

    const { result, unmount } = renderTestHook(() => useStrategyControl(), createWrapper());

    act(() => {
      result.current.requestToggle({
        strategy_group_id: 'BRF2-001',
        configured_state: 'paused',
        control_version: 3,
      });
    });

    await act(async () => {
      await result.current.modalProps.onConfirm({
        totp: '654321',
        reason: '恢复开仓',
      });
    });

    expect(resumeSpy).toHaveBeenCalledTimes(1);
    const [strategyId, body] = resumeSpy.mock.calls[0];
    expect(strategyId).toBe('BRF2-001');
    expect(body.expected_version).toBe(3);
    expect(body.reason).toBe('恢复开仓');
    expect(body.totp_code).toBe('654321');
    expect(body.idempotency_key).toMatch(/^owner-request:strategy-resume:BRF2-001:/);
    expect(result.current.toastMessage).toBe('已成功恢复 BRF2-001 新准入');
    unmount();
  });

  it('generates distinct idempotency keys across consecutive operations', async () => {
    const pauseSpy = vi.spyOn(controlsApi, 'pauseStrategy').mockResolvedValue({} as any);

    const { result, unmount } = renderTestHook(() => useStrategyControl(), createWrapper());

    // Op 1
    act(() => {
      result.current.requestToggle({
        strategy_group_id: 'MPG-001',
        configured_state: 'enabled',
        control_version: 1,
      });
    });
    await act(async () => {
      await result.current.modalProps.onConfirm({ totp: '', reason: 'first pause' });
    });

    // Op 2
    act(() => {
      result.current.requestToggle({
        strategy_group_id: 'MPG-001',
        configured_state: 'enabled',
        control_version: 2,
      });
    });
    await act(async () => {
      await result.current.modalProps.onConfirm({ totp: '', reason: 'second pause' });
    });

    expect(pauseSpy).toHaveBeenCalledTimes(2);
    const key1 = pauseSpy.mock.calls[0][1].idempotency_key;
    const key2 = pauseSpy.mock.calls[1][1].idempotency_key;
    expect(key1).not.toBe(key2);
    unmount();
  });

  it('rejects requestToggle when control fact is missing or invalid', () => {
    const { result, unmount } = renderTestHook(() => useStrategyControl(), createWrapper());

    act(() => {
      result.current.requestToggle({
        strategy_group_id: 'CPM-RO-001',
        configured_state: undefined as any,
        control_version: 1,
      });
    });

    expect(result.current.pendingTarget).toBeNull();
    expect(result.current.modalProps.open).toBe(false);
    expect(result.current.toastMessage).toContain('缺少真实控制事实');

    act(() => {
      result.current.requestToggle({
        strategy_group_id: 'CPM-RO-001',
        configured_state: 'enabled',
        control_version: null as any,
      });
    });

    expect(result.current.pendingTarget).toBeNull();
    expect(result.current.modalProps.open).toBe(false);
    unmount();
  });

  it('handles 409 version conflict by terminating old confirmation flow and refreshing facts', async () => {
    vi.spyOn(controlsApi, 'pauseStrategy').mockRejectedValue(
      new ApiError(409, 'control_conflict', 'strategy_control_version_conflict')
    );
    const invalidateSpy = vi.spyOn(QueryClient.prototype, 'invalidateQueries');

    const { result, unmount } = renderTestHook(() => useStrategyControl(), createWrapper());

    act(() => {
      result.current.requestToggle({
        strategy_group_id: 'MI-001',
        configured_state: 'enabled',
        control_version: 1,
      });
    });

    expect(result.current.modalProps.open).toBe(true);

    await act(async () => {
      await result.current.modalProps.onConfirm({ totp: '', reason: 'pause attempt' });
    });

    // Old confirmation flow MUST be terminated immediately (modal closed) so stale v1 cannot be resent
    expect(result.current.modalProps.open).toBe(false);
    expect(result.current.pendingTarget).toBeNull();
    expect(result.current.toastMessage).toContain('版本冲突 (HTTP 409)');
    expect(result.current.toastMessage).toContain('请基于最新状态重新确认');
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: controlsApi.controlsQueryKey });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['owner', 'strategies'] });
    unmount();
  });

  it('handles 403 step_up_invalid cleanly without fake success', async () => {
    vi.spyOn(controlsApi, 'resumeStrategy').mockRejectedValue(
      new ApiError(403, 'step_up_invalid', 'Invalid step up code')
    );

    const { result, unmount } = renderTestHook(() => useStrategyControl(), createWrapper());

    act(() => {
      result.current.requestToggle({
        strategy_group_id: 'MI-001',
        configured_state: 'paused',
        control_version: 2,
      });
    });

    await act(async () => {
      await result.current.modalProps.onConfirm({ totp: '000000', reason: 'resume attempt' });
    });

    expect(result.current.errorMessage).toContain('Google Authenticator 动态口令无效');
    expect(result.current.toastMessage).toBeNull();
    unmount();
  });

  it('locks into unknown result on network failure, preserving operation identity and requiring GET verification', async () => {
    const pauseSpy = vi.spyOn(controlsApi, 'pauseStrategy').mockRejectedValue(
      new Error('fetch timeout while contacting backend')
    );

    const { result, unmount } = renderTestHook(() => useStrategyControl(), createWrapper());

    act(() => {
      result.current.requestToggle({
        strategy_group_id: 'CPM-RO-001',
        configured_state: 'enabled',
        control_version: 1,
      });
    });

    const originalIdempotencyKey = result.current.pendingOperation?.idempotency_key;
    expect(originalIdempotencyKey).toBeDefined();

    await act(async () => {
      await result.current.modalProps.onConfirm({ totp: '', reason: 'pause attempt' });
    });

    // 1. Must be locked into unknown result state
    expect(result.current.isUnknownResult).toBe(true);
    expect(result.current.modalProps.isUnknownResult).toBe(true);
    expect(result.current.errorMessage).toContain('执行结果未知');
    expect(result.current.errorMessage).toContain('禁止盲目生成新请求重试');
    expect(result.current.toastMessage).toBeNull();

    // 2. Direct confirm submission must be blocked while in unknown state
    await act(async () => {
      await result.current.modalProps.onConfirm({ totp: '', reason: 'duplicate blind attempt' });
    });
    // Should NOT have made a second POST call
    expect(pauseSpy).toHaveBeenCalledTimes(1);

    // 3. Now perform GET verification: Server did not apply it, version unchanged
    vi.spyOn(controlsApi, 'fetchControls').mockResolvedValue({
      strategies: [
        {
          strategy_group_id: 'CPM-RO-001',
          configured_state: 'enabled', // still enabled
          control_version: 1, // still version 1
          effective_state: 'enabled',
          entry_state: 'enabled',
          last_event_id: 'evt-1',
          reason: 'Initial state',
          updated_at_ms: 1700000000000,
        },
      ],
    } as any);

    await act(async () => {
      await result.current.handleVerifyStatus();
    });

    // Lock is cleared, verified that command was not applied on server
    expect(result.current.isUnknownResult).toBe(false);
    expect(result.current.errorMessage).toContain('核验完成：服务端尚未执行本次操作');
    expect(result.current.errorMessage).toContain('已锁定原请求与幂等键');

    // 4. Retry with confirmed status: It MUST use the EXACT SAME frozen reason and idempotency key!
    pauseSpy.mockResolvedValueOnce({
      ok: true,
      data: {
        strategy_group_id: 'CPM-RO-001',
        control_version: 2,
        entry_state: 'paused',
      },
    } as any);

    // In retry, reason is frozen to 'pause attempt'
    await act(async () => {
      await result.current.modalProps.onConfirm({ totp: '', reason: 'pause attempt' });
    });

    expect(pauseSpy).toHaveBeenCalledTimes(2);
    const retryCallBody = pauseSpy.mock.calls[1][1];
    expect(retryCallBody.idempotency_key).toBe(originalIdempotencyKey);
    expect(retryCallBody.reason).toBe('pause attempt');
    expect(retryCallBody.expected_version).toBe(1);

    unmount();
  });

  it('prevents bypassing unknown_result lock by cancelling and reopening modal', async () => {
    const pauseSpy = vi.spyOn(controlsApi, 'pauseStrategy').mockRejectedValue(
      new Error('fetch timeout while contacting backend')
    );

    const { result, unmount } = renderTestHook(() => useStrategyControl(), createWrapper());

    act(() => {
      result.current.requestToggle({
        strategy_group_id: 'CPM-RO-001',
        configured_state: 'enabled',
        control_version: 1,
      });
    });

    await act(async () => {
      await result.current.modalProps.onConfirm({ totp: '', reason: 'first pause attempt' });
    });

    expect(result.current.isUnknownResult).toBe(true);
    const originalKey = result.current.pendingOperation?.idempotency_key;
    expect(originalKey).toBeDefined();

    // 1. User cancels the modal
    act(() => {
      result.current.closeModal();
    });
    expect(result.current.modalProps.open).toBe(false);

    // 2. User clicks toggle again on same strategy without having completed GET verification
    act(() => {
      result.current.requestToggle({
        strategy_group_id: 'CPM-RO-001',
        configured_state: 'enabled',
        control_version: 1,
      });
    });

    // 3. Modal reopens in unknown_result state with the preserved in-flight operation
    expect(result.current.modalProps.open).toBe(true);
    expect(result.current.isUnknownResult).toBe(true);
    expect(result.current.pendingOperation?.idempotency_key).toBe(originalKey);
    expect(result.current.errorMessage).toContain('未决的控制操作');

    // 4. Blind submission attempt is still blocked
    await act(async () => {
      await result.current.modalProps.onConfirm({ totp: '', reason: 'bypass attempt' });
    });
    expect(pauseSpy).toHaveBeenCalledTimes(1);

    unmount();
  });

  it('reports truthful state when target state is reached without claiming execution certainty', async () => {
    vi.spyOn(controlsApi, 'pauseStrategy').mockRejectedValue(
      new Error('socket disconnected')
    );

    const { result, unmount } = renderTestHook(() => useStrategyControl(), createWrapper());

    act(() => {
      result.current.requestToggle({
        strategy_group_id: 'CPM-RO-001',
        configured_state: 'enabled',
        control_version: 1,
      });
    });

    await act(async () => {
      await result.current.modalProps.onConfirm({ totp: '', reason: 'pause attempt' });
    });

    expect(result.current.isUnknownResult).toBe(true);

    // GET verification discovers server is paused, but we do NOT assume our request caused it
    vi.spyOn(controlsApi, 'fetchControls').mockResolvedValue({
      strategies: [
        {
          strategy_group_id: 'CPM-RO-001',
          configured_state: 'paused', // already in target state!
          control_version: 99, // jumped to v99 by another operation
          effective_state: 'paused',
          entry_state: 'paused',
          last_event_id: 'evt-99',
          reason: 'another operation',
          updated_at_ms: 1700000005000,
        },
      ],
    } as any);

    await act(async () => {
      await result.current.handleVerifyStatus();
    });

    // Must report target state truthfully without asserting execution certainty
    expect(result.current.isUnknownResult).toBe(false);
    expect(result.current.toastMessage).toContain('当前已处于目标状态');
    expect(result.current.toastMessage).toContain('本次请求结果仍无法确认');
    expect(result.current.toastMessage).not.toContain('已核验成功：服务端已');
    unmount();
  });

  it('prevents duplicate submissions when a request is in flight', async () => {
    let resolvePromise!: (value: any) => void;
    const slowPromise = new Promise((resolve) => {
      resolvePromise = resolve;
    });

    const pauseSpy = vi.spyOn(controlsApi, 'pauseStrategy').mockReturnValue(slowPromise as any);

    const { result, unmount } = renderTestHook(() => useStrategyControl(), createWrapper());

    act(() => {
      result.current.requestToggle({
        strategy_group_id: 'CPM-RO-001',
        configured_state: 'enabled',
        control_version: 1,
      });
    });

    let p1: void | Promise<void>;
    let p2: void | Promise<void>;
    act(() => {
      p1 = result.current.modalProps.onConfirm({ totp: '', reason: 'first submit' });
      p2 = result.current.modalProps.onConfirm({ totp: '', reason: 'duplicate submit' });
    });

    // Because submittingRef.current is set synchronously upon first invocation,
    // the second synchronous invocation returns immediately
    expect(pauseSpy).toHaveBeenCalledTimes(1);

    // Now resolve the in-flight request
    await act(async () => {
      resolvePromise({
        ok: true,
        data: {
          strategy_group_id: 'CPM-RO-001',
          strategy_name_zh: '动量突破',
          configured_state: 'paused',
          effective_state: 'paused',
          control_version: 2,
          updated_at: '2026-10-20T12:00:00Z',
          updated_by: 'owner',
          reason: 'first submit',
        },
      });
      await Promise.all([p1, p2]);
    });

    expect(result.current.isSubmitting).toBe(false);
    unmount();
  });
});
