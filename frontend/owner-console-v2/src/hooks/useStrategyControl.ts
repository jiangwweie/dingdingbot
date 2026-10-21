import { useState, useCallback, useRef, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  fetchControls,
  pauseStrategy,
  resumeStrategy,
  controlsQueryKey,
} from '../api/controlsApi';
import { ApiError } from '../api/errors';
import { formatControlError } from '../utils/controlErrors';
import type { TotpActionModalProps } from '../components/TotpActionModal';

export interface StrategyControlTarget {
  strategy_group_id: string;
  configured_state: 'enabled' | 'paused';
  control_version: number;
  name_zh?: string;
  is_retired?: boolean;
}

export type InFlightStatus = 'initialized' | 'submitting' | 'unknown_result' | 'verified_unapplied';

export interface InFlightOperation {
  strategy_group_id: string;
  action: 'pause' | 'resume';
  expected_version: number;
  initial_configured_state: 'enabled' | 'paused';
  reason: string;
  idempotency_key: string;
  status: InFlightStatus;
  startedAtMs: number;
}

// Module-level registry so in-flight operations persist across modal close/open and between Matrix and Drawer
const inFlightRegistry = new Map<string, InFlightOperation>();
const registryListeners = new Set<() => void>();

function notifyListeners() {
  registryListeners.forEach((fn) => fn());
}

export function _resetInFlightRegistry(): void {
  inFlightRegistry.clear();
  registryListeners.clear();
}

function generateIdempotencyKey(action: 'pause' | 'resume', groupId: string): string {
  const uuid =
    typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  return `owner-request:strategy-${action}:${groupId}:${uuid}`;
}

export interface UseStrategyControlOptions {
  onSuccess?: (message: string) => void;
}

export function useStrategyControl(options?: UseStrategyControlOptions) {
  const queryClient = useQueryClient();

  const [activeTarget, setActiveTarget] = useState<StrategyControlTarget | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const verifyingRef = useRef(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Subscribe to registry updates so Matrix and Drawer stay synchronized
  const [, setTick] = useState(0);
  useEffect(() => {
    const handler = () => setTick((t) => t + 1);
    registryListeners.add(handler);
    return () => {
      registryListeners.delete(handler);
    };
  }, []);

  const activeGroupId = activeTarget?.strategy_group_id ?? null;
  const inFlight = activeGroupId ? inFlightRegistry.get(activeGroupId) ?? null : null;

  const isUnknownResult = inFlight?.status === 'unknown_result';
  const isReasonFrozen = inFlight != null && inFlight.status === 'verified_unapplied';

  const action = inFlight
    ? inFlight.action
    : activeTarget?.configured_state === 'enabled'
    ? 'pause'
    : 'resume';

  const requestToggle = useCallback((target: StrategyControlTarget) => {
    // 1. Guard against missing or invalid control facts
    if (
      !target ||
      (target.configured_state !== 'enabled' && target.configured_state !== 'paused') ||
      typeof target.control_version !== 'number' ||
      !Number.isFinite(target.control_version)
    ) {
      setToastMessage('缺少真实控制事实 (configured_state / control_version)，禁止发起控制操作。');
      return;
    }

    const groupId = target.strategy_group_id;
    const existingInFlight = inFlightRegistry.get(groupId);

    if (existingInFlight) {
      // If server version already changed from what we froze, the in-flight intent is obsolete
      if (existingInFlight.expected_version !== target.control_version) {
        inFlightRegistry.delete(groupId);
        notifyListeners();
      } else {
        // Reopen existing in-flight operation without losing its identity!
        setActiveTarget(target);
        setIsModalOpen(true);
        if (existingInFlight.status === 'unknown_result') {
          setErrorMessage(
            '该策略存在未决的控制操作，执行结果未知。禁止发起新操作，必须先核验服务端权威状态。'
          );
        } else if (existingInFlight.status === 'verified_unapplied') {
          setErrorMessage(
            `已核验服务端尚未执行本次操作（版本仍为 v${existingInFlight.expected_version}）。重试已锁定原请求与幂等键。`
          );
        }
        return;
      }
    }

    // 2. SOR-001 or retired strategy: strictly prohibit resume
    if (target.is_retired || groupId === 'SOR-001') {
      if (target.configured_state === 'paused') {
        setErrorMessage('SOR-001 已永久退役，禁止恢复新准入。');
        setActiveTarget(target);
        setIsModalOpen(true);
        return;
      }
    }

    // 3. Initialize fresh operation with unique idempotency key
    const targetAction = target.configured_state === 'enabled' ? 'pause' : 'resume';
    const newKey = generateIdempotencyKey(targetAction, groupId);
    const newOp: InFlightOperation = {
      strategy_group_id: groupId,
      action: targetAction,
      expected_version: target.control_version,
      initial_configured_state: target.configured_state,
      reason: targetAction === 'pause' ? 'Owner 手动暂停新准入' : 'Owner 手动恢复新准入',
      idempotency_key: newKey,
      status: 'initialized',
      startedAtMs: Date.now(),
    };
    inFlightRegistry.set(groupId, newOp);
    notifyListeners();

    setActiveTarget(target);
    setIsModalOpen(true);
    setErrorMessage(null);
  }, []);

  const closeModal = useCallback(() => {
    if (submittingRef.current || verifyingRef.current) return;

    if (activeGroupId) {
      const op = inFlightRegistry.get(activeGroupId);
      // If operation was never submitted to the network, safe to discard
      if (op && op.status === 'initialized') {
        inFlightRegistry.delete(activeGroupId);
        notifyListeners();
      }
      // Note: If op is in 'unknown_result' or 'verified_unapplied', it is NOT deleted, preserving in-flight safety!
    }

    setIsModalOpen(false);
    setActiveTarget(null);
    setErrorMessage(null);
  }, [activeGroupId]);

  const clearToast = useCallback(() => {
    setToastMessage(null);
  }, []);

  const handleConfirm = useCallback(
    async ({ totp, reason }: { totp: string; reason: string }) => {
      if (submittingRef.current || verifyingRef.current || !activeTarget || isUnknownResult) return;

      const groupId = activeTarget.strategy_group_id;
      const targetAction = activeTarget.configured_state === 'enabled' ? 'pause' : 'resume';

      // Double-check retirement defense before network write
      if ((activeTarget.is_retired || groupId === 'SOR-001') && targetAction === 'resume') {
        setErrorMessage('SOR-001 已永久退役，系统禁止恢复新准入。');
        return;
      }

      let currentOp = inFlightRegistry.get(groupId);

      if (!currentOp) {
        const newKey = generateIdempotencyKey(targetAction, groupId);
        currentOp = {
          strategy_group_id: groupId,
          action: targetAction,
          expected_version: activeTarget.control_version,
          initial_configured_state: activeTarget.configured_state,
          reason: reason.trim(),
          idempotency_key: newKey,
          status: 'submitting',
          startedAtMs: Date.now(),
        };
        inFlightRegistry.set(groupId, currentOp);
      } else {
        // Freeze reason on first submission; keep frozen reason on retries
        if (currentOp.status === 'initialized') {
          currentOp.reason = reason.trim();
        }
        currentOp.status = 'submitting';
      }
      notifyListeners();

      submittingRef.current = true;
      setIsSubmitting(true);
      setErrorMessage(null);

      // Entire request payload is strictly frozen, only totp_code is supplied fresh on retry
      const writeBody = {
        expected_version: currentOp.expected_version,
        reason: currentOp.reason, // Strictly frozen payload!
        idempotency_key: currentOp.idempotency_key, // Strictly frozen identity!
        totp_code: currentOp.action === 'resume' ? totp.trim() : null,
      };

      try {
        if (currentOp.action === 'pause') {
          await pauseStrategy(groupId, writeBody);
        } else {
          await resumeStrategy(groupId, writeBody);
        }

        // Succeeded on exchange/backend: delete in-flight operation and invalidate queries
        inFlightRegistry.delete(groupId);
        notifyListeners();

        await Promise.all([
          queryClient.invalidateQueries({ queryKey: controlsQueryKey }),
          queryClient.invalidateQueries({ queryKey: ['owner', 'strategies'] }),
        ]);

        const successMsg = `已成功${currentOp.action === 'pause' ? '暂停' : '恢复'} ${groupId} 新准入`;
        setToastMessage(successMsg);
        options?.onSuccess?.(successMsg);

        setIsModalOpen(false);
        setActiveTarget(null);
      } catch (err) {
        // Case 1: 409 Version Conflict -> Stale expectation, clear in-flight, terminate modal, refresh facts
        if (err instanceof ApiError && (err.status === 409 || err.code === 'control_conflict')) {
          inFlightRegistry.delete(groupId);
          notifyListeners();
          setIsModalOpen(false);
          setActiveTarget(null);
          setErrorMessage(null);

          await Promise.all([
            queryClient.invalidateQueries({ queryKey: controlsQueryKey }),
            queryClient.invalidateQueries({ queryKey: ['owner', 'strategies'] }),
          ]);

          const conflictMsg = '版本冲突 (HTTP 409)：服务端控制记录已更新。已自动同步最新事实，请基于最新状态重新确认。';
          setToastMessage(conflictMsg);
          options?.onSuccess?.(conflictMsg);
          return;
        }

        // Case 2: Unknown outcome (Network timeout, network failure, 5xx) -> Lock into unknown_result
        const isNetworkOrTimeout =
          !(err instanceof ApiError) ||
          err.status === 0 ||
          err.status >= 500 ||
          err.code === 'network_error';

        if (isNetworkOrTimeout) {
          if (currentOp) {
            currentOp.status = 'unknown_result';
            notifyListeners();
          }
          const formatted = formatControlError(err);
          setErrorMessage(
            `${formatted} 执行结果未知，禁止盲目生成新请求重试。请点击“核验权威状态”检查服务端是否已执行本次操作。`
          );
          return;
        }

        // Case 3: Other client errors (403 step_up_invalid, 422 strategy_retired) -> clear in-flight
        inFlightRegistry.delete(groupId);
        notifyListeners();
        const formatted = formatControlError(err);
        setErrorMessage(formatted);
      } finally {
        submittingRef.current = false;
        setIsSubmitting(false);
      }
    },
    [activeTarget, isUnknownResult, queryClient, options]
  );

  const handleVerifyStatus = useCallback(async () => {
    if (verifyingRef.current || submittingRef.current || !activeTarget) return;

    const groupId = activeTarget.strategy_group_id;
    const currentOp = inFlightRegistry.get(groupId);

    verifyingRef.current = true;
    setIsVerifying(true);
    setErrorMessage(null);

    const targetAction = currentOp ? currentOp.action : activeTarget.configured_state === 'enabled' ? 'pause' : 'resume';
    const expectedConfiguredState = targetAction === 'pause' ? 'paused' : 'enabled';

    try {
      const controls = await fetchControls();
      const currentFact = controls.strategies.find((s) => s.strategy_group_id === groupId);

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: controlsQueryKey }),
        queryClient.invalidateQueries({ queryKey: ['owner', 'strategies'] }),
      ]);

      if (!currentFact) {
        inFlightRegistry.delete(groupId);
        notifyListeners();
        setIsModalOpen(false);
        setActiveTarget(null);
        const msg = `核验结果：服务端未返回 ${groupId} 的控制事实，未决操作已终止。`;
        setToastMessage(msg);
        options?.onSuccess?.(msg);
        return;
      }

      if (currentFact.configured_state === expectedConfiguredState) {
        // CASE A: State on server is already in target state.
        // P1 #2 fix: Do NOT claim "已核验成功：服务端已执行本次操作" without server idempotency receipt.
        inFlightRegistry.delete(groupId);
        notifyListeners();
        setIsModalOpen(false);
        setActiveTarget(null);
        const noticeMsg = `当前已处于目标状态（${targetAction === 'pause' ? '已配置暂停' : '已配置启用'}，当前版本: v${
          currentFact.control_version
        }），但本次请求结果仍无法确认。已同步服务端最新事实。`;
        setToastMessage(noticeMsg);
        options?.onSuccess?.(noticeMsg);
      } else if (
        currentOp &&
        currentFact.control_version === currentOp.expected_version &&
        currentFact.configured_state === currentOp.initial_configured_state
      ) {
        // CASE B: Verified: Server did NOT execute the command, and version is completely unchanged.
        currentOp.status = 'verified_unapplied';
        notifyListeners();
        setErrorMessage(
          `核验完成：服务端尚未执行本次操作（当前版本仍为 v${currentFact.control_version}）。可安全重试本次操作（已锁定原请求与幂等键）。`
        );
      } else {
        // CASE C: Server control version or state has changed by another operation
        inFlightRegistry.delete(groupId);
        notifyListeners();
        setIsModalOpen(false);
        setActiveTarget(null);
        const conflictMsg = `核验完成：服务端控制版本已变更为 v${currentFact.control_version}（配置状态: ${
          currentFact.configured_state === 'enabled' ? '已启用' : '已暂停'
        }）。本次请求未执行或已被覆盖。已同步最新事实。`;
        setToastMessage(conflictMsg);
        options?.onSuccess?.(conflictMsg);
      }
    } catch (verifyErr) {
      const formatted = formatControlError(verifyErr);
      setErrorMessage(`核验失败：无法获取服务端权威状态 (${formatted})。请检查网络后重试核验。`);
    } finally {
      verifyingRef.current = false;
      setIsVerifying(false);
    }
  }, [activeTarget, queryClient, options]);

  const modalProps: TotpActionModalProps = {
    open: isModalOpen && activeTarget !== null,
    onOpenChange: (open) => {
      if (!open) closeModal();
    },
    title:
      action === 'pause'
        ? `确认暂停新准入: ${activeTarget?.strategy_group_id ?? ''}`
        : `确认恢复新准入: ${activeTarget?.strategy_group_id ?? ''}`,
    description:
      action === 'pause'
        ? `暂停仅阻断 ${activeTarget?.strategy_group_id ?? ''} 新的 ENTRY 开仓准入；已持有的活动持仓继续由系统严格执行止损、追踪与退出管理。`
        : `恢复后，${activeTarget?.strategy_group_id ?? ''} 的有效信号将允许创建 Ticket 并进入 ENTRY 准入队列；存量持仓不受影响。`,
    confirmLabel: action === 'pause' ? '确认暂停新准入' : '确认恢复新准入',
    actionKind: action,
    expectedVersion: inFlight ? inFlight.expected_version : activeTarget?.control_version,
    requireTotp: action === 'resume',
    requireReason: true,
    defaultReason: inFlight
      ? inFlight.reason
      : action === 'pause'
      ? 'Owner 手动暂停新准入'
      : 'Owner 手动恢复新准入',
    isSubmitting,
    isUnknownResult,
    isVerifying,
    isReasonFrozen,
    errorMessage,
    onConfirm: handleConfirm,
    onVerifyStatus: handleVerifyStatus,
  };

  return {
    modalProps,
    pendingTarget: activeTarget,
    pendingOperation: inFlight,
    isSubmitting,
    isVerifying,
    isUnknownResult,
    isReasonFrozen,
    errorMessage,
    toastMessage,
    requestToggle,
    closeModal,
    clearToast,
    handleVerifyStatus,
  };
}
