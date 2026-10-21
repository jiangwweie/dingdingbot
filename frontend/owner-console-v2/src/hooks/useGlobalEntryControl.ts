import { useState, useCallback, useRef, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  fetchControls,
  pauseGlobalEntry,
  resumeGlobalEntry,
  controlsQueryKey,
  type OwnerControlOperation,
} from '../api/controlsApi';
import { ApiError } from '../api/errors';
import { formatControlError } from '../utils/controlErrors';
import type { TotpActionModalProps } from '../components/TotpActionModal';
import { _getInFlightFlatten } from './useFlattenControl';

export type InFlightGlobalStatus =
  | 'initialized'
  | 'submitting'
  | 'unknown_result'
  | 'verified_unapplied';

export interface InFlightGlobalEntryOperation {
  action: 'pause' | 'resume';
  expected_version: number;
  reason: string;
  idempotency_key: string;
  status: InFlightGlobalStatus;
  startedAtMs: number;
  lastError?: string | null;
}

const STORAGE_KEY = 'brc:owner:in_flight_global_entry';

function loadInFlightFromStorage(): InFlightGlobalEntryOperation | null {
  if (typeof window === 'undefined' || !window.sessionStorage) return null;
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const op = JSON.parse(raw) as InFlightGlobalEntryOperation;
    if (op && op.status === 'submitting') {
      op.status = 'unknown_result';
    }
    return op;
  } catch {
    return null;
  }
}

function saveInFlightToStorage(op: InFlightGlobalEntryOperation | null): void {
  if (typeof window === 'undefined' || !window.sessionStorage) return;
  try {
    if (!op) {
      window.sessionStorage.removeItem(STORAGE_KEY);
    } else {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(op));
    }
  } catch {
    // Ignore storage quota or security errors
  }
}

let inFlightGlobalEntry: InFlightGlobalEntryOperation | null = loadInFlightFromStorage();
let isGlobalSubmitting = false;
const registryListeners = new Set<() => void>();

function notifyListeners() {
  registryListeners.forEach((fn) => fn());
}

function setInFlightGlobalEntry(op: InFlightGlobalEntryOperation | null): void {
  inFlightGlobalEntry = op;
  saveInFlightToStorage(op);
  notifyListeners();
}

export function _resetInFlightGlobalEntryRegistry(): void {
  isGlobalSubmitting = false;
  setInFlightGlobalEntry(null);
  registryListeners.clear();
}

export function _reloadInFlightGlobalFromStorage(): void {
  inFlightGlobalEntry = loadInFlightFromStorage();
  notifyListeners();
}

export function _getInFlightGlobalEntry(): InFlightGlobalEntryOperation | null {
  return inFlightGlobalEntry;
}

function hasUnresolvedFlatten(activeFlattenOp?: OwnerControlOperation | null): boolean {
  if (activeFlattenOp && activeFlattenOp.state !== 'completed' && activeFlattenOp.state !== 'blocked') {
    return true;
  }
  const localFlatten = _getInFlightFlatten();
  if (
    localFlatten &&
    (localFlatten.status === 'submitting' ||
      localFlatten.status === 'unknown_result' ||
      localFlatten.status === 'verified_unapplied')
  ) {
    return true;
  }
  return false;
}

function generateGlobalIdempotencyKey(action: 'pause' | 'resume'): string {
  const uuid =
    typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  return `owner-request:global-entry-${action}:${uuid}`;
}

export interface UseGlobalEntryControlOptions {
  onSuccess?: (message: string) => void;
  activeFlattenOperation?: OwnerControlOperation | null;
}

export function useGlobalEntryControl(options?: UseGlobalEntryControlOptions) {
  const queryClient = useQueryClient();

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [targetAction, setTargetAction] = useState<'pause' | 'resume' | null>(null);
  const [expectedVersion, setExpectedVersion] = useState<number | null>(null);
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

  const inFlight = inFlightGlobalEntry;
  const isUnknownResult = inFlight?.status === 'unknown_result';
  const isReasonFrozen =
    inFlight != null &&
    (inFlight.status === 'verified_unapplied' || inFlight.status === 'unknown_result');
  const currentAction = inFlight ? inFlight.action : targetAction ?? 'pause';

  const requestAction = useCallback(
    (action: 'pause' | 'resume', version: number) => {
      if (typeof version !== 'number' || !Number.isFinite(version)) {
        setToastMessage('缺少全局 ENTRY 控制版本事实，禁止发起控制操作。');
        return;
      }

      // Mutual exclusion check with Flatten: cannot resume while controlled flatten is active or unresolved
      if (action === 'resume') {
        if (options?.activeFlattenOperation) {
          const flattenOp = options.activeFlattenOperation;
          if (flattenOp.state !== 'completed' && flattenOp.state !== 'blocked') {
            setToastMessage(
              `受控平仓操作正在执行中 [${flattenOp.state}] (授权 ID: ${flattenOp.authorization_id})，禁止恢复全局新交易准入。`
            );
            return;
          }
        }
        if (hasUnresolvedFlatten(options?.activeFlattenOperation)) {
          setToastMessage('受控平仓操作正在执行中或结果未决，禁止恢复全局新交易准入。');
          return;
        }
      }

      if (inFlightGlobalEntry) {
        if (
          inFlightGlobalEntry.status === 'unknown_result' ||
          inFlightGlobalEntry.status === 'verified_unapplied'
        ) {
          // Locked in flight operation: retain identity and key regardless of server version!
          setTargetAction(inFlightGlobalEntry.action);
          setExpectedVersion(inFlightGlobalEntry.expected_version);
          setIsModalOpen(true);
          if (inFlightGlobalEntry.status === 'unknown_result') {
            setErrorMessage(
              '存在未决的全局 ENTRY 控制操作，结果尚未确认。禁止重新发起，必须先核验服务端权威状态。'
            );
          } else {
            setErrorMessage(
              `已核验服务端尚未执行本次操作（版本仍为 v${inFlightGlobalEntry.expected_version}）。重试已锁定原请求与幂等键。`
            );
          }
          return;
        }

        // If version on server already advanced, old in-flight is obsolete
        if (inFlightGlobalEntry.expected_version !== version) {
          setInFlightGlobalEntry(null);
        } else {
          // Reopen existing in-flight operation without losing key or status
          setTargetAction(inFlightGlobalEntry.action);
          setExpectedVersion(inFlightGlobalEntry.expected_version);
          setIsModalOpen(true);
          return;
        }
      }

      // Initialize fresh operation
      const newKey = generateGlobalIdempotencyKey(action);
      const newOp: InFlightGlobalEntryOperation = {
        action,
        expected_version: version,
        reason: action === 'pause' ? 'Owner 手动暂停全局新开仓' : 'Owner 手动恢复全局新开仓',
        idempotency_key: newKey,
        status: 'initialized',
        startedAtMs: Date.now(),
      };
      setInFlightGlobalEntry(newOp);
      setTargetAction(action);
      setExpectedVersion(version);
      setIsModalOpen(true);
      setErrorMessage(null);
    },
    [options?.activeFlattenOperation]
  );

  const closeModal = useCallback(() => {
    if (submittingRef.current || verifyingRef.current) return;

    if (inFlightGlobalEntry && inFlightGlobalEntry.status === 'initialized') {
      setInFlightGlobalEntry(null);
    }

    setIsModalOpen(false);
    setErrorMessage(null);
  }, []);

  const clearToast = useCallback(() => {
    setToastMessage(null);
  }, []);

  const handleConfirm = useCallback(
    async ({ totp, reason }: { totp: string; reason: string }) => {
      if (
        submittingRef.current ||
        isGlobalSubmitting ||
        inFlightGlobalEntry?.status === 'submitting' ||
        verifyingRef.current ||
        isUnknownResult
      ) {
        return;
      }

      if (!isModalOpen || targetAction === null || expectedVersion === null) {
        return;
      }

      const act = currentAction;

      // Mutual exclusion check on submit
      if (act === 'resume' && hasUnresolvedFlatten(options?.activeFlattenOperation)) {
        setErrorMessage('受控平仓操作正在执行或结果未决，禁止恢复全局新交易准入。');
        return;
      }

      if (act === 'resume' && (!totp || !/^\d{6,8}$/.test(totp.trim()))) {
        setErrorMessage('恢复全局新开仓必须输入 6 位数字 Google Authenticator 动态口令。');
        return;
      }

      if (!reason || reason.trim().length === 0) {
        setErrorMessage('必须输入操作原因以记录审计事实。');
        return;
      }

      let currentOp = inFlightGlobalEntry;
      if (!currentOp) {
        currentOp = {
          action: act,
          expected_version: expectedVersion,
          reason: reason.trim(),
          idempotency_key: generateGlobalIdempotencyKey(act),
          status: 'submitting',
          startedAtMs: Date.now(),
        };
        setInFlightGlobalEntry(currentOp);
      } else {
        const isFrozen =
          currentOp.status === 'verified_unapplied' || currentOp.status === 'unknown_result';
        currentOp.status = 'submitting';
        if (!isFrozen) {
          currentOp.reason = reason.trim();
        }
        setInFlightGlobalEntry(currentOp);
      }

      submittingRef.current = true;
      isGlobalSubmitting = true;
      setIsSubmitting(true);
      setErrorMessage(null);

      const payload = {
        expected_version: currentOp.expected_version,
        reason: currentOp.reason,
        idempotency_key: currentOp.idempotency_key,
        totp_code: act === 'resume' ? totp.trim() : null,
      };

      try {
        let resultMutation;
        if (act === 'pause') {
          resultMutation = await pauseGlobalEntry(payload);
        } else {
          resultMutation = await resumeGlobalEntry(payload);
        }

        setInFlightGlobalEntry(null);
        setIsModalOpen(false);
        setTargetAction(null);
        setExpectedVersion(null);

        await Promise.all([
          queryClient.invalidateQueries({ queryKey: controlsQueryKey }),
          queryClient.invalidateQueries({ queryKey: ['owner', 'tickets'] }),
          queryClient.invalidateQueries({ queryKey: ['owner', 'overview'] }),
        ]);

        const successMsg = `全局 ENTRY 已成功${act === 'pause' ? '暂停' : '恢复'} [v${resultMutation.version}]。`;
        setToastMessage(successMsg);
        options?.onSuccess?.(successMsg);
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) {
          setInFlightGlobalEntry(null);
          setIsModalOpen(false);
          setTargetAction(null);
          setExpectedVersion(null);
          await queryClient.invalidateQueries({ queryKey: controlsQueryKey });
          const conflictMsg = '全局策略版本已发生冲突（409 Conflict），已终止当前操作。请刷新后重新发起。';
          setErrorMessage(conflictMsg);
          setToastMessage(conflictMsg);
          return;
        }

        if (err instanceof ApiError && err.status === 403) {
          if (currentOp) {
            currentOp.status = 'initialized';
            setInFlightGlobalEntry(currentOp);
          }
          setErrorMessage('Google Authenticator 验证码无效或已过期，请重新输入。');
          return;
        }

        // Unknown result / timeout / network failure
        if (currentOp) {
          currentOp.status = 'unknown_result';
          currentOp.lastError = err instanceof Error ? err.message : String(err);
          setInFlightGlobalEntry(currentOp);
        }
        setErrorMessage(
          '全局控制请求未决或网络超时，尚未确认结果。请先核验服务端权威状态，切勿直接以新请求重发。'
        );
      } finally {
        submittingRef.current = false;
        isGlobalSubmitting = false;
        setIsSubmitting(false);
      }
    },
    [currentAction, expectedVersion, isModalOpen, targetAction, options, queryClient, isUnknownResult]
  );

  const handleVerifyStatus = useCallback(async () => {
    if (verifyingRef.current) return;
    verifyingRef.current = true;
    setIsVerifying(true);
    setErrorMessage(null);

    try {
      const controlsData = await fetchControls();
      const currentPolicyVersion = controlsData.global_entry.policy_version;
      const configuredState = controlsData.global_entry.configured_state;

      if (!inFlightGlobalEntry) {
        setIsModalOpen(false);
        setToastMessage(`已刷新全局 ENTRY 权威状态: ${configuredState} [v${currentPolicyVersion}]。`);
        await queryClient.invalidateQueries({ queryKey: controlsQueryKey });
        return;
      }

      const op = inFlightGlobalEntry;
      const targetConfigured = op.action === 'pause' ? 'paused' : 'enabled';

      if (currentPolicyVersion > op.expected_version) {
        if (configuredState === targetConfigured) {
          // Target state reached, but cannot correlate local request without exact proof
          op.status = 'unknown_result';
          op.lastError = `服务端当前状态已达到目标 (${configuredState} [v${currentPolicyVersion}])，但未能关联本次请求身份凭据，本次请求结果未确认。保持闭锁保护。`;
          setInFlightGlobalEntry(op);
          setErrorMessage(
            `核验结果：服务端当前状态已为 ${configuredState} [v${currentPolicyVersion}]，但未能关联本次请求身份凭据。本次请求结果未确认，保持闭锁保护。`
          );
        } else {
          // Version advanced by other means (or jumped by > 1, e.g. 8 vs 6)
          setInFlightGlobalEntry(null);
          setIsModalOpen(false);
          setTargetAction(null);
          setExpectedVersion(null);
          setToastMessage(
            `已核验服务端：全局策略版本已推进至 v${currentPolicyVersion}（原预期 v${op.expected_version}），无法证明属于本次请求。本地闭锁已解除。`
          );
        }
        await queryClient.invalidateQueries({ queryKey: controlsQueryKey });
        return;
      }

      // Policy version has not advanced: operation was NOT executed
      op.status = 'verified_unapplied';
      op.lastError = `核验确认服务端当前版本仍为 v${currentPolicyVersion}，尚未执行原操作。`;
      setInFlightGlobalEntry(op);
      setErrorMessage(
        `核验结果：服务端尚未执行本次全局开仓控制（版本仍为 v${currentPolicyVersion}）。重试已锁定原请求与原幂等键。`
      );
      await queryClient.invalidateQueries({ queryKey: controlsQueryKey });
    } catch (err) {
      const formatted = formatControlError(err);
      setErrorMessage(`核验失败 (${formatted})，请保持闭锁并稍后重试核验。`);
    } finally {
      verifyingRef.current = false;
      setIsVerifying(false);
    }
  }, [options, queryClient]);

  const modalProps: TotpActionModalProps = {
    open: isModalOpen,
    onOpenChange: (open: boolean) => {
      if (!open) closeModal();
    },
    title:
      currentAction === 'pause'
        ? '暂停全局新交易准入 (Pause Global ENTRY)'
        : '恢复全局新交易准入 (Resume Global ENTRY)',
    description:
      currentAction === 'pause'
        ? '暂停全局 ENTRY 将阻止所有策略建立新仓位。现有持仓的保护、出场、对账和结算生命周期将继续正常运行。'
        : '恢复全局 ENTRY 必须由 Owner 使用 Google Authenticator 强认证。恢复后仍受各策略的独立配置状态与门禁规则约束。',
    confirmLabel: currentAction === 'pause' ? '确认暂停新开仓' : '确认恢复新开仓',
    actionKind: currentAction,
    requireTotp: currentAction === 'resume',
    defaultReason:
      inFlight && (inFlight.status === 'unknown_result' || inFlight.status === 'verified_unapplied')
        ? inFlight.reason
        : currentAction === 'pause'
        ? 'Owner 手动暂停全局新开仓'
        : 'Owner 手动恢复全局新开仓',
    isReasonFrozen,
    expectedVersion: inFlight?.expected_version ?? expectedVersion,
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
    expectedVersion: inFlight?.expected_version ?? expectedVersion,
    inFlight,
    modalProps,
    requestAction,
    closeModal,
    handleConfirm,
    handleVerifyStatus,
    errorMessage,
    toastMessage,
    clearToast,
    isResumeBlocked: hasUnresolvedFlatten(options?.activeFlattenOperation),
  };
}
