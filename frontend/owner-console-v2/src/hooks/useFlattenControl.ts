import { useState, useCallback, useRef, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  fetchFlattenPreview,
  submitFlatten,
  fetchControls,
  controlsQueryKey,
  type FlattenPreview,
  type OwnerControlOperation,
} from '../api/controlsApi';
import { ApiError } from '../api/errors';
import { formatControlError } from '../utils/controlErrors';

export type InFlightFlattenStatus =
  | 'initialized'
  | 'submitting'
  | 'unknown_result'
  | 'verified_unapplied';

export interface InFlightFlattenOperation {
  expected_version: number;
  snapshot_digest: string;
  ticket_ids: string[];
  reason: string;
  idempotency_key: string;
  status: InFlightFlattenStatus;
  startedAtMs: number;
  lastError?: string | null;
  submittedAuthId?: string | null;
}

// Global in-flight registry for account-wide flatten operations
let inFlightFlatten: InFlightFlattenOperation | null = null;
const registryListeners = new Set<() => void>();

function notifyListeners() {
  registryListeners.forEach((fn) => fn());
}

export function _resetInFlightFlattenRegistry(): void {
  inFlightFlatten = null;
  registryListeners.clear();
}

export function _getInFlightFlatten(): InFlightFlattenOperation | null {
  return inFlightFlatten;
}

function generateFlattenIdempotencyKey(): string {
  const uuid =
    typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  return `owner-request:flatten-all:${uuid}`;
}

export interface UseFlattenControlOptions {
  onSuccess?: (operation: OwnerControlOperation) => void;
}

export function useFlattenControl(options?: UseFlattenControlOptions) {
  const queryClient = useQueryClient();

  const [preview, setPreview] = useState<FlattenPreview | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const verifyingRef = useRef(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [currentOperation, setCurrentOperation] = useState<OwnerControlOperation | null>(null);

  // Synchronize across components if state changes
  const [, setTick] = useState(0);
  useEffect(() => {
    const handler = () => setTick((t) => t + 1);
    registryListeners.add(handler);
    return () => {
      registryListeners.delete(handler);
    };
  }, []);

  const inFlight = inFlightFlatten;
  const isUnknownResult = inFlight?.status === 'unknown_result';
  const isRetryFrozen = inFlight != null && inFlight.status === 'verified_unapplied';

  const requestPreview = useCallback(async () => {
    if (submittingRef.current || verifyingRef.current) return;

    // Check if an existing in-flight operation exists
    if (inFlightFlatten) {
      if (inFlightFlatten.status === 'unknown_result') {
        setIsModalOpen(true);
        setErrorMessage(
          '存在未决的受控平仓操作，执行结果未知。禁止重新发起平仓，必须先核验服务端权威状态。'
        );
        return;
      }
    }

    setIsLoadingPreview(true);
    setErrorMessage(null);
    try {
      const data = await fetchFlattenPreview();
      setPreview(data);

      // If an existing in-flight operation has a different snapshot digest, discard it
      if (inFlightFlatten && inFlightFlatten.snapshot_digest !== data.snapshot_digest) {
        inFlightFlatten = null;
        notifyListeners();
      }

      setIsModalOpen(true);

      if (data.first_blocker) {
        setErrorMessage(`存在不可平仓的中间态持仓 (${data.first_blocker})，禁止提交平仓。`);
      }
    } catch (err) {
      const formatted = formatControlError(err);
      setToastMessage(formatted);
    } finally {
      setIsLoadingPreview(false);
    }
  }, []);

  const closeModal = useCallback(() => {
    if (submittingRef.current || verifyingRef.current) return;

    // If an operation was only initialized and not submitted, discard it
    if (inFlightFlatten && inFlightFlatten.status === 'initialized') {
      inFlightFlatten = null;
      notifyListeners();
    }

    setIsModalOpen(false);
    setErrorMessage(null);
  }, []);

  const clearToast = useCallback(() => {
    setToastMessage(null);
  }, []);

  const handleConfirm = useCallback(
    async ({ totp, confirmText }: { totp: string; confirmText: string }) => {
      if (submittingRef.current || verifyingRef.current || isUnknownResult) return;

      if (!preview) {
        setErrorMessage('缺少服务端平仓快照，请重新读取权威事实。');
        return;
      }

      if (preview.first_blocker) {
        setErrorMessage(`当前持仓存在阻断条件 (${preview.first_blocker})，禁止提交平仓。`);
        return;
      }

      if (confirmText !== '确认平仓全部持仓') {
        setErrorMessage('必须准确输入“确认平仓全部持仓”以确认。');
        return;
      }

      const cleanTotp = totp.trim();
      if (!/^\d{6,8}$/.test(cleanTotp)) {
        setErrorMessage('请输入 6 位数字 Google Authenticator 动态口令。');
        return;
      }

      let currentOp = inFlightFlatten;
      if (!currentOp) {
        currentOp = {
          expected_version: preview.owner_policy_version,
          snapshot_digest: preview.snapshot_digest,
          ticket_ids: preview.ticket_ids,
          reason: 'owner_flatten_all',
          idempotency_key: generateFlattenIdempotencyKey(),
          status: 'submitting',
          startedAtMs: Date.now(),
        };
        inFlightFlatten = currentOp;
      } else {
        currentOp.status = 'submitting';
      }
      notifyListeners();

      submittingRef.current = true;
      setIsSubmitting(true);
      setErrorMessage(null);

      const payload = {
        expected_version: currentOp.expected_version,
        reason: currentOp.reason,
        idempotency_key: currentOp.idempotency_key,
        totp_code: cleanTotp,
        snapshot_digest: currentOp.snapshot_digest,
        confirmation_text: '确认平仓全部持仓' as const,
      };

      try {
        const op = await submitFlatten(payload);

        // Success: clear in-flight operation, record completed/pending op
        inFlightFlatten = null;
        notifyListeners();

        setCurrentOperation(op);
        setToastMessage(`受控平仓指令已提交 (${op.state})，全局 ENTRY 已挂起。`);
        setIsModalOpen(false);

        // Invalidate controls and trades cache to sync UI
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: controlsQueryKey }),
          queryClient.invalidateQueries({ queryKey: ['owner', 'trades'] }),
        ]);

        options?.onSuccess?.(op);
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) {
          // Snapshot conflict or version conflict: invalidates old snapshot
          inFlightFlatten = null;
          setPreview(null);
          notifyListeners();
          setErrorMessage('持仓状态快照已发生变动（409 Conflict），请重新读取最新权威事实。');
          return;
        }

        if (err instanceof ApiError && err.status === 403) {
          // Step-up verification failure
          if (currentOp) {
            currentOp.status = 'initialized';
            notifyListeners();
          }
          setErrorMessage('Google Authenticator 验证码无效或已过期，请重新输入。');
          return;
        }

        // Unknown result / timeout / network failure
        if (currentOp) {
          currentOp.status = 'unknown_result';
          currentOp.lastError = err instanceof Error ? err.message : String(err);
          notifyListeners();
        }
        setErrorMessage(
          '平仓请求未决或网络超时，尚未确认结果。请先核验服务端权威状态，切勿重复提交。'
        );
      } finally {
        submittingRef.current = false;
        setIsSubmitting(false);
      }
    },
    [preview, isUnknownResult, queryClient, options]
  );

  const handleVerifyStatus = useCallback(async () => {
    if (verifyingRef.current || !inFlightFlatten) return;

    verifyingRef.current = true;
    setIsVerifying(true);
    setErrorMessage(null);

    try {
      const controlsData = await fetchControls();

      // Check current_operation or recent_operations
      const currentOp = controlsData.current_operation;
      const recentOps = controlsData.recent_operations ?? [];

      const matchingOp =
        (currentOp && currentOp.snapshot_digest === inFlightFlatten.snapshot_digest
          ? currentOp
          : null) ??
        recentOps.find((op) => op.snapshot_digest === inFlightFlatten?.snapshot_digest);

      if (matchingOp) {
        // Authoritative confirmation that operation was executed/accepted!
        inFlightFlatten = null;
        notifyListeners();
        setCurrentOperation(matchingOp);
        setIsModalOpen(false);
        setToastMessage(`已核验服务端状态：受控平仓操作处于 [${matchingOp.state}]。`);
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: controlsQueryKey }),
          queryClient.invalidateQueries({ queryKey: ['owner', 'trades'] }),
        ]);
        return;
      }

      // Check if policy version advanced or tickets changed
      if (controlsData.global_entry.policy_version > inFlightFlatten.expected_version) {
        inFlightFlatten = null;
        setPreview(null);
        notifyListeners();
        setIsModalOpen(false);
        setToastMessage('已核验服务端：全局策略版本已推进，旧平仓快照已失效。');
        await queryClient.invalidateQueries({ queryKey: controlsQueryKey });
        return;
      }

      // If version hasn't changed and no operation recorded: verified unapplied
      inFlightFlatten.status = 'verified_unapplied';
      notifyListeners();
      setErrorMessage(
        '已核验服务端：未检测到本次平仓记录。重试将锁定原快照与幂等键，切勿使用新快照重试。'
      );
    } catch (err) {
      const formatted = formatControlError(err);
      setErrorMessage(`核验失败 (${formatted})，请保持闭锁并稍后重试核验。`);
    } finally {
      verifyingRef.current = false;
      setIsVerifying(false);
    }
  }, [queryClient]);

  return {
    preview,
    isModalOpen,
    isLoadingPreview,
    isSubmitting,
    isVerifying,
    errorMessage,
    toastMessage,
    currentOperation,
    isUnknownResult,
    isRetryFrozen,
    inFlight,
    requestPreview,
    closeModal,
    handleConfirm,
    handleVerifyStatus,
    clearToast,
  };
}
