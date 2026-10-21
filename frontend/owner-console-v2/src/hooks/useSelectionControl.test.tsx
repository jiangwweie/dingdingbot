// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  useSelectionControl,
  _resetInFlightSelectionRegistry,
  _reloadInFlightSelectionFromStorage,
  _getInFlightSelection,
} from './useSelectionControl';
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

describe('useSelectionControl', () => {
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

  const mockGenericPreview: controlsApi.GenericSelectionPreview = {
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

  beforeEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    _resetInFlightSelectionRegistry();
  });

  it('blocks retired strategy SOR-001 from opening modal', async () => {
    const { result } = renderTestHook(() => useSelectionControl(), createWrapper());

    await act(async () => {
      await result.current.openSelectionModal('SOR-001', 'dynamic');
    });

    expect(result.current.isModalOpen).toBe(false);
    expect(result.current.toastMessage).toContain('SOR-001 已永久退役');
  });

  it('blocks static rollback when rollback baseline or epoch is missing', async () => {
    vi.spyOn(controlsApi, 'fetchSelectionPreview').mockResolvedValue({
      ...mockGenericPreview,
      control: {
        ...mockGenericPreview.control!,
        selection_mode: 'dynamic_selection' as any,
        rollback_baseline_id: null,
        selection_epoch_id: null,
      },
    });

    const { result } = renderTestHook(() => useSelectionControl(), createWrapper());

    await act(async () => {
      await result.current.openSelectionModal('CPM-RO-001', 'static');
    });

    expect(result.current.isModalOpen).toBe(false);
    expect(result.current.toastMessage).toContain('缺少认证的静态回退基线或 Epoch');
  });

  it('fetches preview and opens modal with initialized operation for dynamic activation', async () => {
    vi.spyOn(controlsApi, 'fetchSelectionPreview').mockResolvedValue(mockGenericPreview);

    const { result } = renderTestHook(() => useSelectionControl(), createWrapper());

    await act(async () => {
      await result.current.openSelectionModal('CPM-RO-001', 'dynamic');
    });

    expect(result.current.isModalOpen).toBe(true);
    expect(result.current.activeGroupId).toBe('CPM-RO-001');
    expect(result.current.action).toBe('dynamic');
    expect(result.current.expectedVersion).toBe(3);
    expect(result.current.effectivePeriodAnchorMs).toBe(1800007200000);
    expect(_getInFlightSelection('CPM-RO-001')?.status).toBe('initialized');
  });

  it('submits dynamic activation for generic strategy with period anchor and TOTP', async () => {
    vi.spyOn(controlsApi, 'fetchSelectionPreview').mockResolvedValue(mockGenericPreview);
    const activateSpy = vi.spyOn(controlsApi, 'activateDynamicSelection').mockResolvedValue({
      ...mockGenericPreview.control!,
      pending_selection_mode: 'dynamic_selection' as any,
      control_version: 4,
    });

    const onSuccess = vi.fn();
    const { result } = renderTestHook(() => useSelectionControl({ onSuccess }), createWrapper());

    await act(async () => {
      await result.current.openSelectionModal('CPM-RO-001', 'dynamic');
    });

    await act(async () => {
      await result.current.handleConfirm({
        totp: '123456',
        reason: 'Enable dynamic selection',
      });
    });

    expect(activateSpy).toHaveBeenCalledWith(
      'CPM-RO-001',
      expect.objectContaining({
        expected_version: 3,
        reason: 'Enable dynamic selection',
        totp_code: '123456',
        effective_period_anchor_ms: 1800007200000,
      })
    );
    expect(result.current.isModalOpen).toBe(false);
    expect(_getInFlightSelection('CPM-RO-001')).toBeNull();
    expect(onSuccess).toHaveBeenCalledWith(expect.stringContaining('已接受 CPM-RO-001 动态选币 授权意图，等待周期生效 [v4]'));
  });

  it('submits dynamic activation for SOR-1H-001 using effective_session_start_ms', async () => {
    const orbPreview: controlsApi.OrbSelectionPreview = {
      strategy_label: 'SOR-1H（1h 入场 / 15m 退出）',
      installed: true,
      control: {
        strategy_group_id: 'SOR-1H-001',
        selection_spec_id: 'SOR_1H_OR_ATR_DYNAMIC_V1',
        selection_mode: 'static_baseline' as any,
        pending_selection_mode: null,
        pending_effective_period_anchor_ms: null,
        pending_authorization_id: null,
        control_version: 1,
        rollback_baseline_id: 'baseline-sor',
        selection_epoch_id: 'epoch-sor',
        updated_at_ms: 1800000000000,
      },
      runtime: null,
      next_effective_period_anchor_ms: 1800086400000,
      next_prepare_not_before_ms: 1800090000000,
      next_eligibility_not_before_ms: 1800093600000,
    };

    vi.spyOn(controlsApi, 'fetchSelectionPreview').mockResolvedValue(orbPreview);
    const activateSpy = vi.spyOn(controlsApi, 'activateDynamicSelection').mockResolvedValue({
      ...orbPreview.control!,
      pending_selection_mode: 'dynamic_selection' as any,
      control_version: 2,
    });

    const { result } = renderTestHook(() => useSelectionControl(), createWrapper());

    await act(async () => {
      await result.current.openSelectionModal('SOR-1H-001', 'dynamic');
    });

    await act(async () => {
      await result.current.handleConfirm({
        totp: '654321',
        reason: 'Activate daily SOR dynamic',
      });
    });

    expect(activateSpy).toHaveBeenCalledWith(
      'SOR-1H-001',
      expect.objectContaining({
        expected_version: 1,
        totp_code: '654321',
        effective_session_start_ms: 1800086400000,
      })
    );
  });

  it('submits static rollback with certified baseline and epoch', async () => {
    vi.spyOn(controlsApi, 'fetchSelectionPreview').mockResolvedValue({
      ...mockGenericPreview,
      control: {
        ...mockGenericPreview.control!,
        selection_mode: 'dynamic_selection' as any,
        control_version: 5,
        rollback_baseline_id: 'certified-baseline-9',
        selection_epoch_id: 'epoch-999',
      },
    });

    const staticSpy = vi.spyOn(controlsApi, 'activateStaticSelection').mockResolvedValue({
      ...mockGenericPreview.control!,
      selection_mode: 'dynamic_selection' as any,
      pending_selection_mode: 'static_baseline' as any,
      control_version: 6,
    });

    const { result } = renderTestHook(() => useSelectionControl(), createWrapper());

    await act(async () => {
      await result.current.openSelectionModal('CPM-RO-001', 'static');
    });

    await act(async () => {
      await result.current.handleConfirm({
        totp: '112233',
        reason: 'Rollback to certified baseline',
      });
    });

    expect(staticSpy).toHaveBeenCalledWith(
      'CPM-RO-001',
      expect.objectContaining({
        expected_version: 5,
        totp_code: '112233',
        rollback_baseline_id: 'certified-baseline-9',
        selection_epoch_id: 'epoch-999',
        effective_period_anchor_ms: 1800007200000,
      })
    );
  });

  it('locks in unknown_result on network error and preserves cross-entry identity across unmount and refresh', async () => {
    vi.spyOn(controlsApi, 'fetchSelectionPreview').mockResolvedValue(mockGenericPreview);
    vi.spyOn(controlsApi, 'activateDynamicSelection').mockRejectedValue(new Error('Gateway timeout'));

    const { result, unmount } = renderTestHook(() => useSelectionControl(), createWrapper());

    await act(async () => {
      await result.current.openSelectionModal('CPM-RO-001', 'dynamic');
    });

    const initialKey = _getInFlightSelection('CPM-RO-001')?.idempotency_key;

    await act(async () => {
      await result.current.handleConfirm({
        totp: '123456',
        reason: 'Enable dynamic',
      });
    });

    expect(result.current.isUnknownResult).toBe(true);
    expect(result.current.errorMessage).toContain('选币授权请求未决或网络超时');
    expect(_getInFlightSelection('CPM-RO-001')?.status).toBe('unknown_result');

    // Cross-entry: unmount and simulate opening from Strategies tab or after reload
    unmount();
    _reloadInFlightSelectionFromStorage('CPM-RO-001');

    const reopened = renderTestHook(() => useSelectionControl(), createWrapper());

    await act(async () => {
      await reopened.result.current.openSelectionModal('CPM-RO-001', 'dynamic');
    });

    expect(reopened.result.current.isModalOpen).toBe(true);
    expect(reopened.result.current.isUnknownResult).toBe(true);
    expect(reopened.result.current.inFlight?.idempotency_key).toBe(initialKey);
  });

  it('performs authoritative GET verification: transitions to verified_unapplied when server has not recorded pending mode', async () => {
    sessionStorage.setItem(
      'brc:owner:in_flight_selection:CPM-RO-001',
      JSON.stringify({
        strategy_group_id: 'CPM-RO-001',
        action: 'dynamic',
        expected_version: 3,
        reason: 'Enable dynamic',
        idempotency_key: 'owner-request:selection-dynamic:cpm:test-key',
        effective_period_anchor_ms: 1800007200000,
        status: 'unknown_result',
        startedAtMs: Date.now(),
      })
    );
    _reloadInFlightSelectionFromStorage('CPM-RO-001');

    vi.spyOn(controlsApi, 'fetchSelectionPreview').mockResolvedValue(mockGenericPreview);

    const { result } = renderTestHook(() => useSelectionControl(), createWrapper());

    await act(async () => {
      await result.current.openSelectionModal('CPM-RO-001', 'dynamic');
    });

    await act(async () => {
      await result.current.handleVerifyStatus();
    });

    expect(_getInFlightSelection('CPM-RO-001')?.status).toBe('verified_unapplied');
    expect(result.current.isReasonFrozen).toBe(true);
    expect(result.current.errorMessage).toContain('服务端尚未记录本次选币授权');
    expect(_getInFlightSelection('CPM-RO-001')?.idempotency_key).toBe('owner-request:selection-dynamic:cpm:test-key');
  });

  it('performs authoritative GET verification: clears in-flight when server records matching authorization proof', async () => {
    sessionStorage.setItem(
      'brc:owner:in_flight_selection:CPM-RO-001',
      JSON.stringify({
        strategy_group_id: 'CPM-RO-001',
        action: 'dynamic',
        expected_version: 3,
        reason: 'Enable dynamic',
        idempotency_key: 'owner-request:selection-dynamic:cpm:test-key',
        effective_period_anchor_ms: 1800007200000,
        status: 'unknown_result',
        startedAtMs: Date.now(),
        submittedAuthId: 'AUTH-CPM-1',
      })
    );
    _reloadInFlightSelectionFromStorage('CPM-RO-001');

    vi.spyOn(controlsApi, 'fetchSelectionPreview').mockResolvedValue({
      ...mockGenericPreview,
      control: {
        ...mockGenericPreview.control!,
        pending_selection_mode: 'dynamic_selection' as any,
        pending_authorization_id: 'AUTH-CPM-1',
        control_version: 4,
      },
    });

    const onSuccess = vi.fn();
    const { result } = renderTestHook(() => useSelectionControl({ onSuccess }), createWrapper());

    await act(async () => {
      await result.current.openSelectionModal('CPM-RO-001', 'dynamic');
    });

    await act(async () => {
      await result.current.handleVerifyStatus();
    });

    expect(_getInFlightSelection('CPM-RO-001')).toBeNull();
    expect(result.current.isModalOpen).toBe(false);
    expect(onSuccess).toHaveBeenCalledWith(expect.stringContaining('已核验服务端：CPM-RO-001 动态选币 授权意图已由服务端受理，等待周期生效'));
  });
});
