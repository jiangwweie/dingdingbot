import React, { useState, useEffect } from 'react';
import * as AlertDialog from '@radix-ui/react-alert-dialog';
import { Compass, RotateCcw, AlertTriangle, AlertCircle, Loader2, RefreshCw, X, Clock } from 'lucide-react';

export interface SelectionActionModalProps {
  open: boolean;
  onClose: () => void;
  groupId: string | null;
  action: 'dynamic' | 'static';
  expectedVersion?: number | null;
  cadenceHours?: number;
  effectivePeriodAnchorMs?: number | null;
  nextEligibilityNotBeforeMs?: number | null;
  rollbackBaselineId?: string | null;
  selectionEpochId?: string | null;
  defaultReason?: string;
  isSubmitting?: boolean;
  isUnknownResult?: boolean;
  isVerifying?: boolean;
  isReasonFrozen?: boolean;
  errorMessage?: string | null;
  onConfirm: (data: { totp: string; reason: string }) => void | Promise<void>;
  onVerifyStatus?: () => void | Promise<void>;
}

function formatUtc(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms)) return '—';
  return new Date(ms).toISOString().replace('.000Z', ' UTC');
}

export const SelectionActionModal: React.FC<SelectionActionModalProps> = ({
  open,
  onClose,
  groupId,
  action,
  expectedVersion,
  cadenceHours = 4,
  effectivePeriodAnchorMs,
  nextEligibilityNotBeforeMs,
  rollbackBaselineId,
  selectionEpochId,
  defaultReason: initialReason,
  isSubmitting = false,
  isUnknownResult = false,
  isVerifying = false,
  isReasonFrozen = false,
  errorMessage = null,
  onConfirm,
  onVerifyStatus,
}) => {
  const isDynamic = action === 'dynamic';
  const fallbackReason = isDynamic
    ? 'Owner 激活动态选币授权'
    : 'Owner 回退至已认证静态基线';
  const defaultReason = initialReason ?? fallbackReason;

  const [totp, setTotp] = useState('');
  const [reason, setReason] = useState(defaultReason);

  useEffect(() => {
    if (open) {
      setTotp('');
      setReason(defaultReason);
    }
  }, [open, defaultReason]);

  // Handle ESC key press specifically with capture phase for layered dismissal
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (!isSubmitting && !isVerifying) {
          e.stopPropagation();
          onClose();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown, true);
    return () => {
      window.removeEventListener('keydown', handleKeyDown, true);
    };
  }, [open, isSubmitting, isVerifying, onClose]);

  const hasMissingBaseline = !isDynamic && (!rollbackBaselineId || !selectionEpochId);

  const isTotpValid = totp.length === 6 && /^\d{6}$/.test(totp);
  const isReasonValid = reason.trim().length > 0;
  const canSubmit =
    !hasMissingBaseline &&
    isTotpValid &&
    isReasonValid &&
    !isSubmitting &&
    !isUnknownResult &&
    !isVerifying;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    await onConfirm({ totp: totp.trim(), reason: reason.trim() });
  };

  const handleClose = () => {
    if (isSubmitting || isVerifying) return;
    setTotp('');
    setReason(defaultReason);
    onClose();
  };

  return (
    <AlertDialog.Root open={open} onOpenChange={(isOpen) => { if (!isOpen) handleClose(); }}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 z-40 bg-black/70 backdrop-blur-xs transition-opacity" />
        <AlertDialog.Content
          data-testid="selection-action-modal"
          onEscapeKeyDown={(e) => {
            if (isSubmitting || isVerifying) {
              e.preventDefault();
            } else {
              handleClose();
            }
          }}
          className="fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-surface p-6 shadow-2xl animate-in fade-in-50 zoom-in-95 duration-150 focus:outline-hidden"
        >
          {/* Header */}
          <div className="flex items-start justify-between border-b border-border pb-3.5">
            <div className="flex items-center gap-2.5">
              <div
                className={`rounded-full p-2 ${
                  isDynamic
                    ? 'bg-status-blue-bg text-status-blue border border-status-blue/20'
                    : 'bg-status-amber-bg text-status-amber border border-status-amber/20'
                }`}
              >
                {isDynamic ? <Compass className="h-4 w-4" /> : <RotateCcw className="h-4 w-4" />}
              </div>
              <div>
                <AlertDialog.Title className="text-sm font-bold text-text-primary">
                  {groupId} {isDynamic ? '激活动态选币授权' : '回退已认证静态基线'}
                </AlertDialog.Title>
                <div className="flex items-center gap-2 mt-0.5 font-mono text-[11px] text-text-muted">
                  <span>控制基线版本: v{expectedVersion ?? '—'}</span>
                  <span>·</span>
                  <span>周期: {cadenceHours}h</span>
                </div>
              </div>
            </div>

            <AlertDialog.Cancel asChild>
              <button
                type="button"
                disabled={isSubmitting || isVerifying}
                onClick={handleClose}
                className="text-text-muted hover:text-text-primary transition-colors cursor-pointer disabled:cursor-not-allowed"
                aria-label="关闭选币控制弹窗"
              >
                <X className="h-4 w-4" />
              </button>
            </AlertDialog.Cancel>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="mt-4 space-y-4">
            {/* Fact Box */}
            <div className="rounded border border-border bg-surface-subtle p-3 space-y-2 text-xs font-mono">
              <div className="flex items-center justify-between">
                <span className="text-text-muted">目标选择模式:</span>
                <span className={`font-semibold ${isDynamic ? 'text-status-blue' : 'text-status-amber'}`}>
                  {isDynamic ? 'DYNAMIC 动态打分轮动' : 'STATIC 认证静态基线'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-text-muted">生效周期锚点:</span>
                <span className="text-text-primary font-medium">{formatUtc(effectivePeriodAnchorMs)}</span>
              </div>
              {nextEligibilityNotBeforeMs != null && (
                <div className="flex items-center justify-between">
                  <span className="text-text-muted">最早准入生效时间:</span>
                  <span className="text-text-primary font-medium">{formatUtc(nextEligibilityNotBeforeMs)}</span>
                </div>
              )}
              {!isDynamic && (
                <>
                  <div className="flex items-center justify-between border-t border-border/50 pt-1.5">
                    <span className="text-text-muted">认证回退基线 ID:</span>
                    <span className="text-text-primary font-medium truncate max-w-[240px]" title={rollbackBaselineId ?? '缺失'}>
                      {rollbackBaselineId ?? '缺失'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-text-muted">回退 Selection Epoch:</span>
                    <span className="text-text-primary font-medium truncate max-w-[240px]" title={selectionEpochId ?? '缺失'}>
                      {selectionEpochId ?? '缺失'}
                    </span>
                  </div>
                </>
              )}
            </div>

            {/* Constraints notice */}
            <div className="rounded border border-border bg-surface-subtle p-3 text-xs leading-relaxed text-text-secondary">
              <strong className="text-text-primary">授权生效说明: </strong>
              仅提交下一周期的授权意图，由 Worker 在周期边界物化；提交授权不会强制平仓存量持仓，已有仓位止损保护与退出由 Lifecycle 调度。
            </div>

            {/* Missing baseline blocker warning */}
            {hasMissingBaseline && (
              <div
                role="alert"
                className="flex items-start gap-2 rounded border border-status-red/40 bg-status-red-bg p-3 text-xs text-status-red"
              >
                <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                <div>
                  <strong className="font-semibold">缺少静态回退基线: </strong>
                  服务端未记录该策略的认证回退基线或 Epoch，无法安全回退，提交已闭锁。
                </div>
              </div>
            )}

            {/* Unknown result lockdown banner */}
            {isUnknownResult && (
              <div
                role="alert"
                className="flex flex-col gap-2 rounded border border-status-amber/40 bg-status-amber-bg p-3 text-xs text-status-amber"
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold flex items-center gap-1.5">
                    <AlertTriangle className="h-4 w-4" />
                    选币授权结果未知（闭锁保护）
                  </span>
                  {onVerifyStatus && (
                    <button
                      type="button"
                      disabled={isVerifying}
                      onClick={onVerifyStatus}
                      className="inline-flex items-center gap-1 rounded border border-status-amber/50 bg-surface px-2.5 py-1 text-[11px] font-semibold text-status-amber hover:bg-surface-elevated transition-colors cursor-pointer"
                    >
                      {isVerifying ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <RefreshCw className="h-3 w-3" />
                      )}
                      核验权威状态 (GET)
                    </button>
                  )}
                </div>
                <p className="leading-relaxed opacity-90 m-0">
                  提交遇到网络超时或未决响应。为防止双重写入，本次未决请求已锁定原快照与幂等键。请先点击右上角按钮核验服务端事实。
                </p>
              </div>
            )}

            {/* Verified unapplied banner */}
            {isReasonFrozen && !isUnknownResult && (
              <div
                role="alert"
                className="flex flex-col gap-2 rounded border border-status-blue/40 bg-status-blue-bg p-3 text-xs text-status-blue"
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold flex items-center gap-1.5">
                    <Clock className="h-4 w-4" />
                    重试已锁定原请求
                  </span>
                  {onVerifyStatus && (
                    <button
                      type="button"
                      disabled={isVerifying}
                      onClick={onVerifyStatus}
                      className="inline-flex items-center gap-1 rounded border border-status-blue/50 bg-surface px-2.5 py-1 text-[11px] font-semibold text-status-blue hover:bg-surface-elevated transition-colors cursor-pointer"
                    >
                      {isVerifying ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <RefreshCw className="h-3 w-3" />
                      )}
                      再次核验权威状态 (GET)
                    </button>
                  )}
                </div>
                <p className="leading-relaxed opacity-90 m-0">
                  服务端尚未记录上次授权请求。重试将严格复用原周期锚点与原幂等键。
                </p>
              </div>
            )}

            {/* Error message */}
            {errorMessage && !isUnknownResult && !isReasonFrozen && (
              <div
                role="alert"
                className="flex items-center gap-2 rounded border border-status-red/40 bg-status-red-bg p-3 text-xs text-status-red"
              >
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span className="break-words">{errorMessage}</span>
              </div>
            )}

            {/* Reason input */}
            <div>
              <label className="block text-xs font-medium text-text-primary mb-1">
                操作原因 (Reason) <span className="text-status-red">*</span>
              </label>
              <input
                type="text"
                maxLength={512}
                value={reason}
                disabled={isSubmitting || isUnknownResult || isVerifying || isReasonFrozen}
                onChange={(e) => setReason(e.target.value)}
                placeholder="请输入详细操作原因以记录审计事实"
                className="w-full rounded border border-border bg-background px-3 py-2 text-xs text-text-primary placeholder:text-text-disabled focus:border-brand focus:outline-hidden disabled:bg-surface-subtle disabled:text-text-muted"
              />
            </div>

            {/* TOTP Step-Up Input */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-xs font-medium text-text-primary">
                  Google Authenticator 动态口令 (6 位数字) <span className="text-status-red">*</span>
                </label>
                <span className="font-mono text-[10px] text-text-muted">
                  {totp.length}/6
                </span>
              </div>
              <input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                placeholder="000000"
                value={totp}
                disabled={isSubmitting || isUnknownResult || isVerifying}
                onChange={(e) => setTotp(e.target.value.replace(/\D/g, ''))}
                className="w-full rounded border border-border-strong bg-background px-3 py-2 font-mono text-sm tracking-widest text-text-primary placeholder:text-text-disabled focus:border-brand focus:outline-hidden disabled:bg-surface-subtle disabled:text-text-muted"
                autoFocus
              />
            </div>

            {/* Actions */}
            <div className="flex items-center justify-end gap-3 pt-3 border-t border-border">
              <AlertDialog.Cancel asChild>
                <button
                  type="button"
                  disabled={isSubmitting || isVerifying}
                  onClick={handleClose}
                  className="rounded border border-border bg-surface px-4 py-2 text-xs font-medium text-text-secondary hover:bg-surface-elevated transition-colors cursor-pointer disabled:cursor-not-allowed"
                >
                  取消
                </button>
              </AlertDialog.Cancel>
              <button
                type="submit"
                disabled={!canSubmit}
                className={`inline-flex items-center gap-1.5 rounded px-4 py-2 text-xs font-bold text-white shadow-xs transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-50 ${
                  isDynamic ? 'bg-status-blue hover:bg-status-blue/90' : 'bg-status-amber hover:bg-status-amber/90'
                }`}
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    正在提交选币授权...
                  </>
                ) : hasMissingBaseline ? (
                  '缺少回退基线，禁止提交'
                ) : isDynamic ? (
                  '确认激活动态选币'
                ) : (
                  '确认回退静态基线'
                )}
              </button>
            </div>
          </form>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
};
