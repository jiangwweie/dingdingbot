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

const STORAGE_KEY = 'brc:owner:in_flight_flatten';

function loadInFlightFromStorage(): InFlightFlattenOperation | null {
  if (typeof window === 'undefined' || !window.sessionStorage) return null;
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as InFlightFlattenOperation;
  } catch {
    return null;
  }
}

function saveInFlightToStorage(op: InFlightFlattenOperation | null): void {
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

// Global in-flight registry for account-wide flatten operations
let inFlightFlatten: InFlightFlattenOperation | null = loadInFlightFromStorage();
const registryListeners = new Set<() => void>();

function notifyListeners() {
  registryListeners.forEach((fn) => fn());
}

function setInFlightFlatten(op: InFlightFlattenOperation | null): void {
  inFlightFlatten = op;
  saveInFlightToStorage(op);
  notifyListeners();
}

export function _resetInFlightFlattenRegistry(): void {
  setInFlightFlatten(null);
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
  onError?: (errorMsg: string) => void;
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

  // Check if an operation is currently active (either locally or on server)
  const isOperationActive = Boolean(
    (currentOperation &&
      currentOperation.state !== 'completed' &&
      currentOperation.state !== 'blocked') ||
      (inFlight?.submittedAuthId &&
        inFlight.status === 'submitting')
  );

  const requestPreview = useCallback(async () => {
    if (submittingRef.current || verifyingRef.current) return;

    // 1. Check local in-flight unverified operation
    if (inFlightFlatten) {
      if (inFlightFlatten.status === 'unknown_result') {
        setIsModalOpen(true);
        setErrorMessage(
          '存在未决的受控平仓操作，执行结果未知。禁止重新发起平仓，必须先核验服务端权威状态。'
        );
        return;
      }
      if (inFlightFlatten.status === 'submitting') {
        setIsModalOpen(true);
        setErrorMessage('受控平仓操作正在执行或确认中，请勿重复发起。');
        return;
      }
    }

    // 2. Check if server already has an active non-terminal operation
    try {
      const controlsData = await fetchControls();
      if (
        controlsData.current_operation &&
        controlsData.current_operation.state !== 'completed' &&
        controlsData.current_operation.state !== 'blocked'
      ) {
        setCurrentOperation(controlsData.current_operation);
        setIsModalOpen(true);
        setErrorMessage(
          `服务端已有受控平仓操作处于执行中 [${controlsData.current_operation.state}] (授权 ID: ${controlsData.current_operation.authorization_id})，禁止创建新平仓。`
        );
        return;
      }
    } catch {
      // If fetching controls failed, continue to preview attempt
    }

    setIsLoadingPreview(true);
    setErrorMessage(null);
    try {
      const data = await fetchFlattenPreview();
      setPreview(data);

      // If an existing in-flight operation has a different snapshot digest, discard it
      if (inFlightFlatten && inFlightFlatten.snapshot_digest !== data.snapshot_digest) {
        setInFlightFlatten(null);
      }

      setIsModalOpen(true);

      if (data.first_blocker) {
        setErrorMessage(`存在不可平仓的中间态持仓 (${data.first_blocker})，禁止提交平仓。`);
      }
    } catch (err) {
      const formatted = formatControlError(err);
      setToastMessage(formatted);
      setErrorMessage(formatted);
      options?.onError?.(formatted);
    } finally {
      setIsLoadingPreview(false);
    }
  }, [options]);

  const closeModal = useCallback(() => {
    if (submittingRef.current || verifyingRef.current) return;

    // If an operation was only initialized and not submitted, discard it
    if (inFlightFlatten && inFlightFlatten.status === 'initialized') {
      setInFlightFlatten(null);
    }

    setIsModalOpen(false);
    setErrorMessage(null);
  }, []);

  const clearToast = useCallback(() => {
    setToastMessage(null);
  }, []);

  const handleConfirm = useCallback(
    async ({ totp, confirmText }: { totp: string; confirmText: string }) => {
      if (submittingRef.current || verifyingRef.current || isUnknownResult || isOperationActive) return;

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
        setInFlightFlatten(currentOp);
      } else {
        currentOp.status = 'submitting';
        setInFlightFlatten(currentOp);
      }

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

        // Record authorization id of the submitted operation
        currentOp.submittedAuthId = op.authorization_id;

        if (op.state === 'completed' || op.state === 'blocked') {
          // Terminal operation: safe to clear in-flight operation
          setInFlightFlatten(null);
          setCurrentOperation(op);
          setToastMessage(`受控平仓指令已完成 (${op.state})。`);
        } else {
          // Operation is in-progress (pending, claimed, exits_requested, etc.):
          // Keep tracking it and prevent duplicate submissions!
          setInFlightFlatten(currentOp);
          setCurrentOperation(op);
          setToastMessage(`受控平仓指令已受理 (${op.state})，全局 ENTRY 已挂起。`);
        }
        setIsModalOpen(false);

        // Invalidate controls, tickets, overview, and causality query caches
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: controlsQueryKey }),
          queryClient.invalidateQueries({ queryKey: ['owner', 'tickets'] }),
          queryClient.invalidateQueries({ queryKey: ['owner', 'overview'] }),
          queryClient.invalidateQueries({ queryKey: ['owner', 'causality'] }),
        ]);

        options?.onSuccess?.(op);
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) {
          // Snapshot conflict or version conflict: invalidates old snapshot
          setInFlightFlatten(null);
          setPreview(null);
          setErrorMessage('持仓状态快照已发生变动（409 Conflict），请重新读取最新权威事实。');
          return;
        }

        if (err instanceof ApiError && err.status === 403) {
          // Step-up verification failure
          if (currentOp) {
            currentOp.status = 'initialized';
            setInFlightFlatten(currentOp);
          }
          setErrorMessage('Google Authenticator 验证码无效或已过期，请重新输入。');
          return;
        }

        // Unknown result / timeout / network failure: retain in-flight operation with status unknown_result
        if (currentOp) {
          currentOp.status = 'unknown_result';
          currentOp.lastError = err instanceof Error ? err.message : String(err);
          setInFlightFlatten(currentOp);
        }
        setErrorMessage(
          '平仓请求未决或网络超时，尚未确认结果。请先核验服务端权威状态，切勿重复提交。'
        );
      } finally {
        submittingRef.current = false;
        setIsSubmitting(false);
      }
    },
    [preview, isUnknownResult, isOperationActive, queryClient, options]
  );

  const handleVerifyStatus = useCallback(async () => {
    if (verifyingRef.current || !inFlightFlatten) return;

    verifyingRef.current = true;
    setIsVerifying(true);
    setErrorMessage(null);

    try {
      const controlsData = await fetchControls();

      const currentOp = controlsData.current_operation;
      const recentOps = controlsData.recent_operations ?? [];

      // 1. If we have a known submitted authorization_id, find exact operation
      if (inFlightFlatten.submittedAuthId) {
        const exactOp =
          (currentOp?.authorization_id === inFlightFlatten.submittedAuthId ? currentOp : null) ??
          recentOps.find((op) => op.authorization_id === inFlightFlatten?.submittedAuthId);

        if (exactOp) {
          if (exactOp.state === 'completed' || exactOp.state === 'blocked') {
            setInFlightFlatten(null);
            setCurrentOperation(exactOp);
            setIsModalOpen(false);
            setToastMessage(`已核验服务端状态：受控平仓操作处于 [${exactOp.state}]。`);
          } else {
            // Still in progress: update currentOperation, keep tracking
            setCurrentOperation(exactOp);
            setToastMessage(`已核验服务端状态：受控平仓操作正在推进中 [${exactOp.state}]。`);
          }

          await Promise.all([
            queryClient.invalidateQueries({ queryKey: controlsQueryKey }),
            queryClient.invalidateQueries({ queryKey: ['owner', 'tickets'] }),
            queryClient.invalidateQueries({ queryKey: ['owner', 'overview'] }),
            queryClient.invalidateQueries({ queryKey: ['owner', 'causality'] }),
          ]);
          return;
        }
      }

      // 2. If submittedAuthId is NOT known (network cut out before response returned):
      // NEVER match an operation from recent_operations solely by snapshot_digest!
      // Content digest of an empty portfolio or static state is NOT proof of this operation.
      // We can only consider an active current_operation created strictly during our request window.
      if (
        currentOp &&
        currentOp.created_at_ms >= inFlightFlatten.startedAtMs - 3000 &&
        currentOp.snapshot_digest === inFlightFlatten.snapshot_digest &&
        currentOp.state !== 'completed'
      ) {
        // Active operation created during our window: bind authorization_id and keep tracking!
        inFlightFlatten.submittedAuthId = currentOp.authorization_id;
        inFlightFlatten.status = 'submitting';
        setInFlightFlatten(inFlightFlatten);
        setCurrentOperation(currentOp);
        setToastMessage(`已识别到服务端正在执行本次平仓操作 [${currentOp.state}]。`);
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: controlsQueryKey }),
          queryClient.invalidateQueries({ queryKey: ['owner', 'tickets'] }),
          queryClient.invalidateQueries({ queryKey: ['owner', 'overview'] }),
          queryClient.invalidateQueries({ queryKey: ['owner', 'causality'] }),
        ]);
        return;
      }

      // 3. Check if policy version advanced past our expected version
      if (controlsData.global_entry.policy_version > inFlightFlatten.expected_version) {
        setInFlightFlatten(null);
        setPreview(null);
        setIsModalOpen(false);
        setToastMessage('已核验服务端：全局策略版本已推进，旧平仓快照已失效。');
        await queryClient.invalidateQueries({ queryKey: controlsQueryKey });
        return;
      }

      // 4. No matching operation found on server.
      // CANNOT CLEAR UNKNOWN LOCK: transition to verified_unapplied and retain in-flight idempotency identity!
      inFlightFlatten.status = 'verified_unapplied';
      inFlightFlatten.lastError = '未能关联到本次平仓的受理凭据。历史同快照记录不能证明本次请求已执行。';
      setInFlightFlatten(inFlightFlatten);
      setErrorMessage(
        '核验结果：服务端未查得本次平仓受理记录。历史同快照记录无法作为本次凭据，未决闭锁已保持。重试将锁定原快照与原幂等键。'
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
    isOperationActive,
    inFlight,
    requestPreview,
    closeModal,
    handleConfirm,
    handleVerifyStatus,
    clearToast,
  };
}
