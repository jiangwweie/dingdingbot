import React, { useState, useEffect } from 'react';
import * as AlertDialog from '@radix-ui/react-alert-dialog';
import { ShieldCheck, AlertTriangle, AlertCircle, Loader2, RefreshCw, X } from 'lucide-react';

export interface TotpActionModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel: string;
  actionKind?: 'pause' | 'resume';
  expectedVersion?: number | null;
  requireTotp?: boolean;
  requireReason?: boolean;
  defaultReason?: string;
  isSubmitting?: boolean;
  isUnknownResult?: boolean;
  isVerifying?: boolean;
  isReasonFrozen?: boolean;
  errorMessage?: string | null;
  onConfirm: (data: { totp: string; reason: string }) => void | Promise<void>;
  onVerifyStatus?: () => void | Promise<void>;
}

export const TotpActionModal: React.FC<TotpActionModalProps> = ({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  actionKind = 'resume',
  expectedVersion,
  requireTotp = true,
  requireReason = true,
  defaultReason = '',
  isSubmitting = false,
  isUnknownResult = false,
  isVerifying = false,
  isReasonFrozen = false,
  errorMessage = null,
  onConfirm,
  onVerifyStatus,
}) => {
  const [totp, setTotp] = useState('');
  const [reason, setReason] = useState(defaultReason);

  // Sync state whenever modal opens
  useEffect(() => {
    if (open) {
      setTotp('');
      setReason(defaultReason);
    }
  }, [open, defaultReason]);

  const isTotpValid = !requireTotp || (totp.length === 6 && /^\d{6}$/.test(totp));
  const isReasonValid = !requireReason || reason.trim().length > 0;
  const canSubmit = isTotpValid && isReasonValid && !isSubmitting && !isUnknownResult && !isVerifying;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    await onConfirm({ totp: totp.trim(), reason: reason.trim() });
  };

  const handleClose = () => {
    if (isSubmitting || isVerifying) return;
    setTotp('');
    setReason(defaultReason);
    onOpenChange(false);
  };

  const isPause = actionKind === 'pause';

  return (
    <AlertDialog.Root open={open} onOpenChange={handleClose}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 z-40 bg-black/70 backdrop-blur-xs transition-opacity" />
        <AlertDialog.Content
          data-testid="totp-action-modal"
          onEscapeKeyDown={(e) => {
            if (isSubmitting || isVerifying) {
              e.preventDefault();
            } else {
              handleClose();
            }
          }}
          className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-surface p-5 shadow-2xl animate-in fade-in-50 zoom-in-95 duration-150"
        >
          {/* Header */}
          <div className="flex items-start justify-between border-b border-border pb-3">
            <div className="flex items-center gap-2">
              {isPause ? (
                <div className="rounded-full bg-status-amber-bg p-1.5 text-status-amber border border-status-amber/20">
                  <AlertCircle className="h-4 w-4" />
                </div>
              ) : (
                <div className="rounded-full bg-status-green-bg p-1.5 text-status-green border border-status-green/20">
                  <ShieldCheck className="h-4 w-4" />
                </div>
              )}
              <div>
                <AlertDialog.Title className="text-sm font-bold text-text-primary">
                  {title}
                </AlertDialog.Title>
                {expectedVersion != null && (
                  <span className="font-mono text-[10px] text-text-muted">
                    当前基线版本: v{expectedVersion}
                  </span>
                )}
              </div>
            </div>
            <AlertDialog.Cancel asChild>
              <button
                type="button"
                disabled={isSubmitting}
                onClick={handleClose}
                className="text-text-muted hover:text-text-primary transition-colors cursor-pointer disabled:cursor-not-allowed"
                aria-label="关闭控制弹窗"
              >
                <X className="h-4 w-4" />
              </button>
            </AlertDialog.Cancel>
          </div>

          <form onSubmit={handleSubmit} className="mt-3.5 space-y-4 text-xs">
            {/* Description */}
            <AlertDialog.Description className="text-xs text-text-secondary leading-relaxed bg-surface-subtle p-2.5 rounded border border-border">
              {description}
            </AlertDialog.Description>

            {/* Error Message Alert */}
            {errorMessage && (
              <div
                role="alert"
                className={`flex items-start gap-2 rounded border p-2.5 text-xs leading-snug ${
                  isUnknownResult
                    ? 'border-status-amber/40 bg-status-amber-bg text-status-amber'
                    : 'border-status-red/40 bg-status-red-bg text-status-red'
                }`}
              >
                <AlertTriangle className="h-4 w-4 flex-none mt-0.5" />
                <span className="leading-snug">{errorMessage}</span>
              </div>
            )}

            {/* Reason Input */}
            {requireReason && (
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-xs font-medium text-text-primary">
                    操作原因 (Reason) <span className="text-status-red">*</span>
                  </label>
                  {isReasonFrozen && (
                    <span className="font-mono text-[10px] text-text-muted">
                      (已锁定原请求原因)
                    </span>
                  )}
                </div>
                <input
                  type="text"
                  maxLength={512}
                  value={reason}
                  disabled={isSubmitting || isUnknownResult || isVerifying || isReasonFrozen}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="请输入本次控制操作原因"
                  className="w-full rounded border border-border-strong bg-background px-3 py-2 text-xs text-text-primary placeholder:text-text-disabled focus:border-brand focus:outline-hidden disabled:bg-surface-subtle disabled:text-text-muted"
                />
              </div>
            )}

            {/* TOTP Input (Only for resume / step-up) */}
            {requireTotp && (
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
            )}

            {/* Actions */}
            <div className="flex items-center justify-end gap-2.5 border-t border-border pt-3.5">
              <AlertDialog.Cancel asChild>
                <button
                  type="button"
                  disabled={isSubmitting || isVerifying}
                  onClick={handleClose}
                  className="rounded border border-border-strong bg-surface-subtle px-3.5 py-1.5 text-xs font-medium text-text-secondary hover:bg-surface-elevated hover:text-text-primary transition-colors cursor-pointer disabled:cursor-not-allowed"
                >
                  取消
                </button>
              </AlertDialog.Cancel>

              {onVerifyStatus && (
                <button
                  type="button"
                  disabled={isVerifying}
                  onClick={onVerifyStatus}
                  className={`inline-flex items-center gap-1.5 rounded px-4 py-1.5 text-xs font-bold transition-colors cursor-pointer disabled:opacity-60 ${
                    isUnknownResult
                      ? 'bg-brand text-slate-950 hover:bg-brand-hover shadow-xs'
                      : 'border border-border-strong bg-surface-subtle text-text-primary hover:bg-surface-elevated'
                  }`}
                >
                  {isVerifying ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      正在核验权威状态...
                    </>
                  ) : (
                    <>
                      <RefreshCw className="h-3.5 w-3.5" />
                      核验权威状态
                    </>
                  )}
                </button>
              )}

              {!isUnknownResult && (
                <button
                  type="submit"
                  disabled={!canSubmit}
                  className={`inline-flex items-center gap-1.5 rounded px-4 py-1.5 text-xs font-bold transition-colors cursor-pointer ${
                    canSubmit
                      ? isPause
                        ? 'bg-amber-600 text-white hover:bg-amber-700 shadow-xs'
                        : 'bg-brand text-slate-950 hover:bg-brand-hover shadow-xs'
                      : 'bg-surface-subtle text-text-disabled cursor-not-allowed border border-border'
                  }`}
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      正在提交...
                    </>
                  ) : (
                    confirmLabel
                  )}
                </button>
              )}
            </div>
          </form>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
};
