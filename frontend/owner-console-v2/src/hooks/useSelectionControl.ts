import { useState, useCallback, useRef, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  fetchSelectionPreview,
  activateDynamicSelection,
  activateStaticSelection,
  selectionQueryKey,
  controlsQueryKey,
  type SelectionControl,
  type GenericSelectionPreview,
  type OrbSelectionPreview,
} from '../api/controlsApi';
import { ApiError } from '../api/errors';
import { formatControlError } from '../utils/controlErrors';
import type { SelectionActionModalProps } from '../components/SelectionActionModal';

export type InFlightSelectionStatus =
  | 'initialized'
  | 'submitting'
  | 'unknown_result'
  | 'verified_unapplied';

export interface InFlightSelectionOperation {
  strategy_group_id: string;
  action: 'dynamic' | 'static';
  expected_version: number;
  reason: string;
  idempotency_key: string;
  effective_period_anchor_ms: number;
  next_eligibility_not_before_ms?: number | null;
  rollback_baseline_id?: string | null;
  selection_epoch_id?: string | null;
  status: InFlightSelectionStatus;
  startedAtMs: number;
  lastError?: string | null;
  submittedAuthId?: string | null;
}

const STORAGE_PREFIX = 'brc:owner:in_flight_selection:';

function getStorageKey(groupId: string): string {
  return `${STORAGE_PREFIX}${groupId}`;
}

function loadInFlightFromStorage(groupId: string): InFlightSelectionOperation | null {
  if (typeof window === 'undefined' || !window.sessionStorage) return null;
  try {
    const raw = window.sessionStorage.getItem(getStorageKey(groupId));
    if (!raw) return null;
    const op = JSON.parse(raw) as InFlightSelectionOperation;
    if (op && op.status === 'submitting') {
      op.status = 'unknown_result';
    }
    return op;
  } catch {
    return null;
  }
}

function saveInFlightToStorage(op: InFlightSelectionOperation | null, groupId: string): void {
  if (typeof window === 'undefined' || !window.sessionStorage) return;
  try {
    const key = getStorageKey(groupId);
    if (!op) {
      window.sessionStorage.removeItem(key);
    } else {
      window.sessionStorage.setItem(key, JSON.stringify(op));
    }
  } catch {
    // Ignore storage quota or security errors
  }
}

// Module-level registry so in-flight selection operations persist across matrix, drawer, and tab switches
const inFlightSelectionRegistry = new Map<string, InFlightSelectionOperation>();
const inFlightSubmittingGroups = new Set<string>();
const registryListeners = new Set<() => void>();

function notifyListeners() {
  registryListeners.forEach((fn) => fn());
}

function setInFlightForGroup(groupId: string, op: InFlightSelectionOperation | null): void {
  if (!op) {
    inFlightSelectionRegistry.delete(groupId);
  } else {
    inFlightSelectionRegistry.set(groupId, op);
  }
  saveInFlightToStorage(op, groupId);
  notifyListeners();
}

export function _resetInFlightSelectionRegistry(): void {
  inFlightSelectionRegistry.clear();
  inFlightSubmittingGroups.clear();
  registryListeners.clear();
}

export function _reloadInFlightSelectionFromStorage(groupId: string): void {
  const op = loadInFlightFromStorage(groupId);
  if (op) {
    inFlightSelectionRegistry.set(groupId, op);
  } else {
    inFlightSelectionRegistry.delete(groupId);
  }
  notifyListeners();
}

export function _getInFlightSelection(groupId: string): InFlightSelectionOperation | null {
  return inFlightSelectionRegistry.get(groupId) ?? loadInFlightFromStorage(groupId);
}

function generateSelectionIdempotencyKey(action: 'dynamic' | 'static', groupId: string): string {
  const uuid =
    typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  return `owner-request:selection-${action}:${groupId}:${uuid}`;
}

export interface UseSelectionControlOptions {
  onSuccess?: (message: string) => void;
}

export function useSelectionControl(options?: UseSelectionControlOptions) {
  const queryClient = useQueryClient();

  const [activeGroupId, setActiveGroupId] = useState<string | null>(null);
  const [activeAction, setActiveAction] = useState<'dynamic' | 'static' | null>(null);
  const [activeAnchorMs, setActiveAnchorMs] = useState<number | null>(null);
  const [activeEligibilityMs, setActiveEligibilityMs] = useState<number | null>(null);
  const [activeRollbackBaselineId, setActiveRollbackBaselineId] = useState<string | null>(null);
  const [activeSelectionEpochId, setActiveSelectionEpochId] = useState<string | null>(null);
  const [activeControlVersion, setActiveControlVersion] = useState<number | null>(null);
  const [activeCadenceHours, setActiveCadenceHours] = useState<number>(4);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const verifyingRef = useRef(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Sync across listeners
  const [, setTick] = useState(0);
  useEffect(() => {
    const handler = () => setTick((t) => t + 1);
    registryListeners.add(handler);
    return () => {
      registryListeners.delete(handler);
    };
  }, []);

  const inFlight = activeGroupId
    ? inFlightSelectionRegistry.get(activeGroupId) ?? loadInFlightFromStorage(activeGroupId)
    : null;

  const isUnknownResult = inFlight?.status === 'unknown_result';
  const isReasonFrozen =
    inFlight != null &&
    (inFlight.status === 'verified_unapplied' || inFlight.status === 'unknown_result');
  const currentAction = inFlight ? inFlight.action : activeAction ?? 'dynamic';

  const openSelectionModal = useCallback(
    async (groupId: string, action: 'dynamic' | 'static') => {
      if (submittingRef.current || verifyingRef.current) return;

      if (groupId === 'SOR-001') {
        setToastMessage('SOR-001 已永久退役，不支持动态选币或静态回退操作。');
        return;
      }

      // Check existing in-flight operation for this group
      const existing = inFlightSelectionRegistry.get(groupId) ?? loadInFlightFromStorage(groupId);
      if (existing) {
        setActiveGroupId(groupId);
        setActiveAction(existing.action);
        setActiveControlVersion(existing.expected_version);
        setActiveAnchorMs(existing.effective_period_anchor_ms);
        setActiveEligibilityMs(existing.next_eligibility_not_before_ms ?? null);
        setActiveRollbackBaselineId(existing.rollback_baseline_id ?? null);
        setActiveSelectionEpochId(existing.selection_epoch_id ?? null);
        setIsModalOpen(true);

        if (existing.status === 'unknown_result') {
          setErrorMessage(
            `该策略存在未决的选币授权操作，结果尚未确认。禁止重新发起，必须先核验服务端权威状态。`
          );
        } else if (existing.status === 'verified_unapplied') {
          setErrorMessage(
            `已核验服务端尚未执行本次选币操作（版本仍为 v${existing.expected_version}）。重试已锁定原请求与幂等键。`
          );
        }
        return;
      }

      // Fetch fresh authoritative preview before opening
      try {
        const preview = await fetchSelectionPreview(groupId);
        const isOrb = groupId === 'SOR-1H-001' || 'strategy_label' in preview;
        const control = preview.control;

        if (!control) {
          setToastMessage(`策略 ${groupId} 缺少权威选币控制记录，无法发起控制操作。`);
          return;
        }

        const isInstalled = isOrb
          ? (preview as OrbSelectionPreview).installed
          : (preview as GenericSelectionPreview).runtime?.installed;
        if (!isInstalled) {
          setToastMessage(`策略 ${groupId} 的选币 Spec 未安装或未认证，无法发起授权操作。`);
          return;
        }

        const cadenceHours = isOrb ? 24 : (preview as GenericSelectionPreview).cadence_hours ?? 4;
        const anchorMs = preview.next_effective_period_anchor_ms;
        const eligibilityMs = preview.next_eligibility_not_before_ms;

        if (!anchorMs || anchorMs <= 0) {
          setToastMessage(`未能获取策略 ${groupId} 合法的下一周期锚点，无法发起授权。`);
          return;
        }

        if (action === 'dynamic') {
          if (control.selection_mode === 'dynamic_selection' && !control.pending_selection_mode) {
            setToastMessage(`策略 ${groupId} 当前已经处于 Dynamic 模式，无需重复激活。`);
            return;
          }
        } else {
          // Static rollback
          if (!control.rollback_baseline_id || !control.selection_epoch_id) {
            setToastMessage(
              `策略 ${groupId} 缺少认证的静态回退基线或 Epoch，禁止提交静态回退。`
            );
            return;
          }
        }

        const newKey = generateSelectionIdempotencyKey(action, groupId);
        const newOp: InFlightSelectionOperation = {
          strategy_group_id: groupId,
          action,
          expected_version: control.control_version,
          reason: action === 'dynamic' ? 'Owner 激活动态选币授权' : 'Owner 回退至已认证静态基线',
          idempotency_key: newKey,
          effective_period_anchor_ms: anchorMs,
          next_eligibility_not_before_ms: eligibilityMs,
          rollback_baseline_id: control.rollback_baseline_id ?? null,
          selection_epoch_id: control.selection_epoch_id ?? null,
          status: 'initialized',
          startedAtMs: Date.now(),
        };

        setInFlightForGroup(groupId, newOp);

        setActiveGroupId(groupId);
        setActiveAction(action);
        setActiveControlVersion(control.control_version);
        setActiveCadenceHours(cadenceHours);
        setActiveAnchorMs(anchorMs);
        setActiveEligibilityMs(eligibilityMs ?? null);
        setActiveRollbackBaselineId(control.rollback_baseline_id ?? null);
        setActiveSelectionEpochId(control.selection_epoch_id ?? null);
        setIsModalOpen(true);
        setErrorMessage(null);
      } catch (err) {
        const formatted = formatControlError(err);
        setToastMessage(`读取选币权威事实失败 (${formatted})，操作已取消。`);
      }
    },
    []
  );

  const closeModal = useCallback(() => {
    if (submittingRef.current || verifyingRef.current) return;

    if (activeGroupId) {
      const op =
        inFlightSelectionRegistry.get(activeGroupId) ?? loadInFlightFromStorage(activeGroupId);
      if (op && op.status === 'initialized') {
        setInFlightForGroup(activeGroupId, null);
      }
    }

    setIsModalOpen(false);
    setErrorMessage(null);
  }, [activeGroupId]);

  const clearToast = useCallback(() => {
    setToastMessage(null);
  }, []);

  const handleConfirm = useCallback(
    async ({ totp, reason }: { totp: string; reason: string }) => {
      const groupId = activeGroupId;
      if (!isModalOpen || !groupId || activeControlVersion === null) return;

      const existingOp =
        inFlightSelectionRegistry.get(groupId) ?? loadInFlightFromStorage(groupId);

      // Shared submitting lock across instances for the same strategy group
      if (
        submittingRef.current ||
        inFlightSubmittingGroups.has(groupId) ||
        existingOp?.status === 'submitting' ||
        verifyingRef.current ||
        isUnknownResult
      ) {
        return;
      }

      const act = currentAction;

      const cleanTotp = totp.trim();
      if (!/^\d{6,8}$/.test(cleanTotp)) {
        setErrorMessage('必须输入 6 位数字 Google Authenticator 动态口令。');
        return;
      }

      if (!reason || reason.trim().length === 0) {
        setErrorMessage('必须输入操作原因以记录审计事实。');
        return;
      }

      let currentOp = existingOp;
      if (!currentOp) {
        if (activeControlVersion == null || activeAnchorMs == null) {
          setErrorMessage('缺少选币控制版本或周期锚点事实，请重新读取最新权威事实。');
          return;
        }
        currentOp = {
          strategy_group_id: groupId,
          action: act,
          expected_version: activeControlVersion,
          reason: reason.trim(),
          idempotency_key: generateSelectionIdempotencyKey(act, groupId),
          effective_period_anchor_ms: activeAnchorMs,
          next_eligibility_not_before_ms: activeEligibilityMs,
          rollback_baseline_id: activeRollbackBaselineId,
          selection_epoch_id: activeSelectionEpochId,
          status: 'submitting',
          startedAtMs: Date.now(),
        };
        setInFlightForGroup(groupId, currentOp);
      } else {
        const isFrozen =
          currentOp.status === 'verified_unapplied' || currentOp.status === 'unknown_result';
        currentOp.status = 'submitting';
        if (!isFrozen) {
          currentOp.reason = reason.trim();
        }
        setInFlightForGroup(groupId, currentOp);
      }

      submittingRef.current = true;
      inFlightSubmittingGroups.add(groupId);
      setIsSubmitting(true);
      setErrorMessage(null);

      try {
        let resultControl: SelectionControl;
        if (act === 'dynamic') {
          if (groupId === 'SOR-1H-001') {
            resultControl = await activateDynamicSelection(groupId, {
              expected_version: currentOp.expected_version,
              reason: currentOp.reason,
              idempotency_key: currentOp.idempotency_key,
              totp_code: cleanTotp,
              effective_session_start_ms: currentOp.effective_period_anchor_ms,
            });
          } else {
            resultControl = await activateDynamicSelection(groupId, {
              expected_version: currentOp.expected_version,
              reason: currentOp.reason,
              idempotency_key: currentOp.idempotency_key,
              totp_code: cleanTotp,
              effective_period_anchor_ms: currentOp.effective_period_anchor_ms,
            });
          }
        } else {
          // Static
          if (!currentOp.rollback_baseline_id || !currentOp.selection_epoch_id) {
            throw new Error('缺少合法回退基线或 Epoch');
          }
          resultControl = await activateStaticSelection(groupId, {
            expected_version: currentOp.expected_version,
            reason: currentOp.reason,
            idempotency_key: currentOp.idempotency_key,
            totp_code: cleanTotp,
            effective_period_anchor_ms: currentOp.effective_period_anchor_ms,
            rollback_baseline_id: currentOp.rollback_baseline_id,
            selection_epoch_id: currentOp.selection_epoch_id,
          });
        }

        setInFlightForGroup(groupId, null);
        setIsModalOpen(false);
        setActiveGroupId(null);
        setActiveAction(null);
        setActiveControlVersion(null);
        setActiveAnchorMs(null);

        await Promise.all([
          queryClient.invalidateQueries({ queryKey: selectionQueryKey(groupId) }),
          queryClient.invalidateQueries({ queryKey: controlsQueryKey }),
        ]);

        const successMsg = `已接受 ${groupId} ${
          act === 'dynamic' ? '动态选币' : '静态基线回退'
        } 授权意图，等待周期生效 [v${resultControl.control_version}]。`;
        setToastMessage(successMsg);
        options?.onSuccess?.(successMsg);
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) {
          setInFlightForGroup(groupId, null);
          setIsModalOpen(false);
          setActiveGroupId(null);
          setActiveAction(null);
          setActiveControlVersion(null);
          setActiveAnchorMs(null);
          await queryClient.invalidateQueries({ queryKey: selectionQueryKey(groupId) });
          setToastMessage(
            '选币控制版本或 Epoch 已发生冲突（409 Conflict），已终止当前操作。请重新读取权威状态。'
          );
          return;
        }

        if (err instanceof ApiError && err.status === 403) {
          if (currentOp) {
            currentOp.status = 'initialized';
            setInFlightForGroup(groupId, currentOp);
          }
          setErrorMessage('Google Authenticator 验证码无效或已过期，请重新输入。');
          return;
        }

        // Unknown result / timeout / network failure
        if (currentOp) {
          currentOp.status = 'unknown_result';
          currentOp.lastError = err instanceof Error ? err.message : String(err);
          setInFlightForGroup(groupId, currentOp);
        }
        setErrorMessage(
          '选币授权请求未决或网络超时，尚未确认结果。请先核验服务端权威状态，切勿重复提交。'
        );
      } finally {
        submittingRef.current = false;
        inFlightSubmittingGroups.delete(groupId);
        setIsSubmitting(false);
      }
    },
    [
      activeGroupId,
      isModalOpen,
      currentAction,
      activeControlVersion,
      activeAnchorMs,
      activeEligibilityMs,
      activeRollbackBaselineId,
      activeSelectionEpochId,
      options,
      queryClient,
      isUnknownResult,
    ]
  );

  const handleVerifyStatus = useCallback(async () => {
    if (verifyingRef.current || !activeGroupId) return;
    const groupId = activeGroupId;

    verifyingRef.current = true;
    setIsVerifying(true);
    setErrorMessage(null);

    try {
      const preview = await fetchSelectionPreview(groupId);
      const control = preview.control;

      if (!control) {
        setErrorMessage('未能获取服务端选币控制记录，请稍后重试核验。');
        return;
      }

      const op = inFlightSelectionRegistry.get(groupId) ?? loadInFlightFromStorage(groupId);
      if (!op) {
        setIsModalOpen(false);
        setToastMessage(
          `已核验服务端：${groupId} 当前模式为 ${control.selection_mode} [v${control.control_version}]。`
        );
        await queryClient.invalidateQueries({ queryKey: selectionQueryKey(groupId) });
        return;
      }

      // Check for presence of an external or conflicting pending authorization
      // Check for presence of an external or conflicting pending authorization (applies to ALL versions)
      const hasOtherPendingAuth =
        Boolean(control.pending_authorization_id) &&
        (!op.submittedAuthId || control.pending_authorization_id !== op.submittedAuthId);

      const anchorMismatch =
        control.pending_effective_period_anchor_ms != null &&
        op.effective_period_anchor_ms != null &&
        control.pending_effective_period_anchor_ms !== op.effective_period_anchor_ms;

      if (hasOtherPendingAuth || anchorMismatch) {
        // Another pending authorization exists on the server, or anchor does not match.
        // It cannot prove this request regardless of version: keep locked in unknown_result, do NOT clear registry, do NOT call onSuccess!
        op.status = 'unknown_result';
        op.lastError = `服务端当前存在其他授权任务 [${control.pending_authorization_id}]，且周期锚点或凭据不符。无法关联为本次请求凭据。本次操作结果未知。`;
        setInFlightForGroup(groupId, op);
        setErrorMessage(
          `核验结果：服务端当前存在其他授权任务 [${control.pending_authorization_id}]，且周期锚点或凭据不符。本次操作结果未知，保持闭锁保护。`
        );
        await queryClient.invalidateQueries({ queryKey: selectionQueryKey(groupId) });
        return;
      }

      // If control version has not advanced (control.control_version <= op.expected_version):
      if (control.control_version <= op.expected_version) {
        if (control.pending_selection_mode === null && control.pending_authorization_id === null) {
          // Not applied: transition to verified_unapplied and freeze reason & key
          op.status = 'verified_unapplied';
          op.lastError = `核验确认服务端当前版本仍为 v${control.control_version}，尚未记录本次授权。`;
          setInFlightForGroup(groupId, op);
          setErrorMessage(
            `核验结果：服务端尚未记录本次选币授权（版本仍为 v${control.control_version}）。重试已锁定原请求与幂等键。`
          );
          await queryClient.invalidateQueries({ queryKey: selectionQueryKey(groupId) });
          return;
        }

        // Fallback for unchanged version
        op.status = 'unknown_result';
        op.lastError = '未能关联到本次选币授权的确切服务端凭据。';
        setInFlightForGroup(groupId, op);
        setErrorMessage('未能关联到本次选币授权的确切服务端凭据，保持闭锁保护。');
        await queryClient.invalidateQueries({ queryKey: selectionQueryKey(groupId) });
        return;
      }

      // If control version advanced
      const authorityId =
        preview.runtime && 'current_authority_id' in preview.runtime
          ? preview.runtime.current_authority_id
          : preview.runtime && 'current_authority' in preview.runtime
          ? (preview.runtime as any).current_authority?.authority_id
          : null;

      const hasExactAuthIdMatch =
        Boolean(op.submittedAuthId) &&
        (control.pending_authorization_id === op.submittedAuthId ||
          authorityId === op.submittedAuthId);

      if (hasExactAuthIdMatch) {
        setInFlightForGroup(groupId, null);
        setIsModalOpen(false);
        setActiveGroupId(null);
        const successMsg = `已核验服务端：${groupId} ${
          op.action === 'dynamic' ? '动态选币' : '静态回退'
        } 授权意图已由服务端受理，等待周期生效 [v${control.control_version}]。`;
        setToastMessage(successMsg);
        options?.onSuccess?.(successMsg);
        await queryClient.invalidateQueries({ queryKey: selectionQueryKey(groupId) });
        return;
      }

      // Without exact request identity proof, any state change on the server
      // cannot prove this request was executed. Retain unknown_result and preserve idempotency key!
      op.status = 'unknown_result';
      op.lastError = `服务端当前选币事实已更新 [v${control.control_version}]，但未能关联本次请求身份凭据。本次请求结果未确认。`;
      setInFlightForGroup(groupId, op);
      setErrorMessage(
        `核验结果：服务端当前选币事实已更新（当前模式: ${control.selection_mode} [v${control.control_version}]），但未能关联本次请求身份凭据。本次请求结果未确认，保持闭锁保护。`
      );
      await queryClient.invalidateQueries({ queryKey: selectionQueryKey(groupId) });
      return;
    } catch (err) {
      const formatted = formatControlError(err);
      setErrorMessage(`核验失败 (${formatted})，请保持闭锁并稍后重试核验。`);
    } finally {
      verifyingRef.current = false;
      setIsVerifying(false);
    }
  }, [activeGroupId, options, queryClient]);

  const modalProps: SelectionActionModalProps = {
    open: isModalOpen,
    onClose: closeModal,
    groupId: activeGroupId,
    action: currentAction,
    expectedVersion: inFlight?.expected_version ?? activeControlVersion,
    cadenceHours: activeCadenceHours,
    effectivePeriodAnchorMs: inFlight?.effective_period_anchor_ms ?? activeAnchorMs,
    nextEligibilityNotBeforeMs: inFlight?.next_eligibility_not_before_ms ?? activeEligibilityMs,
    rollbackBaselineId: inFlight?.rollback_baseline_id ?? activeRollbackBaselineId,
    selectionEpochId: inFlight?.selection_epoch_id ?? activeSelectionEpochId,
    defaultReason:
      inFlight && (inFlight.status === 'unknown_result' || inFlight.status === 'verified_unapplied')
        ? inFlight.reason
        : currentAction === 'dynamic'
        ? 'Owner 激活动态选币授权'
        : 'Owner 回退至已认证静态基线',
    isReasonFrozen,
    isSubmitting,
    isUnknownResult,
    isVerifying,
    errorMessage,
    onConfirm: handleConfirm,
    onVerifyStatus:
      isUnknownResult || inFlight?.status === 'verified_unapplied'
        ? handleVerifyStatus
        : undefined,
  };

  return {
    isModalOpen,
    isSubmitting,
    isVerifying,
    isUnknownResult,
    isReasonFrozen,
    action: currentAction,
    currentAction,
    expectedVersion: inFlight?.expected_version ?? activeControlVersion,
    effectivePeriodAnchorMs: inFlight?.effective_period_anchor_ms ?? activeAnchorMs,
    activeGroupId,
    inFlight,
    modalProps,
    openSelectionModal,
    closeModal,
    handleConfirm,
    handleVerifyStatus,
    errorMessage,
    toastMessage,
    clearToast,
  };
}
