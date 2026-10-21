import React, { useState, useEffect } from 'react';
import * as AlertDialog from '@radix-ui/react-alert-dialog';
import { AlertOctagon, X, Loader2, ShieldAlert, RefreshCw, AlertTriangle } from 'lucide-react';
import type { FlattenPreview } from '../api/controlsApi';

export interface ControlledFlattenModalProps {
  open: boolean;
  onClose: () => void;
  preview: FlattenPreview | null;
  isSubmitting: boolean;
  isVerifying: boolean;
  errorMessage: string | null;
  isUnknownResult: boolean;
  isRetryFrozen?: boolean;
  onConfirm: (payload: { totp: string; confirmText: string }) => Promise<void>;
  onVerifyStatus: () => Promise<void>;
  onRefreshPreview?: () => Promise<void>;
}

export const ControlledFlattenModal: React.FC<ControlledFlattenModalProps> = ({
  open,
  onClose,
  preview,
  isSubmitting,
  isVerifying,
  errorMessage,
  isUnknownResult,
  isRetryFrozen,
  onConfirm,
  onVerifyStatus,
  onRefreshPreview,
}) => {
  const [totp, setTotp] = useState('');
  const [confirmText, setConfirmText] = useState('');

  // Reset inputs when modal opens or closes
  useEffect(() => {
    if (open) {
      setTotp('');
      setConfirmText('');
    }
  }, [open]);

  // Handle ESC key press specifically for this top-level modal
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

  const isTotpValid = totp.length === 6 && /^\d+$/.test(totp);
  const isTextValid = confirmText === '确认平仓全部持仓';
  const hasBlocker = Boolean(preview?.first_blocker);

  const canSubmit =
    Boolean(preview) &&
    !hasBlocker &&
    !isUnknownResult &&
    isTotpValid &&
    isTextValid &&
    !isSubmitting &&
    !isVerifying;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    await onConfirm({ totp, confirmText });
  };

  return (
    <AlertDialog.Root open={open} onOpenChange={(isOpen) => { if (!isOpen) onClose(); }}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 z-40 bg-black/70 backdrop-blur-xs transition-opacity" />
        <AlertDialog.Content
          data-testid="controlled-flatten-modal"
          className="fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-lg border border-status-red/50 bg-surface p-6 shadow-2xl focus:outline-hidden"
          onEscapeKeyDown={(e) => {
            if (isSubmitting || isVerifying) {
              e.preventDefault();
            }
          }}
        >
          {/* Header */}
          <div className="flex items-start justify-between border-b border-border pb-3.5">
            <div className="flex items-center gap-3">
              <div className="rounded-full bg-status-red-bg p-2 text-status-red border border-status-red/20">
                <AlertOctagon className="h-5 w-5" />
              </div>
              <div>
                <AlertDialog.Title className="text-sm font-bold text-text-primary">
                  确认受控平仓全部仓位 (Controlled Flatten)
                </AlertDialog.Title>
                <AlertDialog.Description className="text-xs text-text-secondary mt-0.5">
                  先挂起全局 ENTRY，再由 Lifecycle 调度逐笔有序退出全部活动 Ticket。
                </AlertDialog.Description>
              </div>
            </div>
            <AlertDialog.Cancel asChild>
              <button
                type="button"
                onClick={onClose}
                disabled={isSubmitting || isVerifying}
                aria-label="关闭"
                className="text-text-muted hover:text-text-primary transition-colors disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
              >
                <X className="h-4 w-4" />
              </button>
            </AlertDialog.Cancel>
          </div>

          {/* Unknown Result Lockdown Banner */}
          {isUnknownResult && (
            <div className="mt-3.5 rounded border border-status-red bg-status-red-bg p-3 text-xs text-status-red space-y-2">
              <div className="flex items-center gap-2 font-bold">
                <ShieldAlert className="h-4 w-4 flex-none" />
                <span>平仓结果未知（闭锁保护）</span>
              </div>
              <p className="leading-relaxed">
                网络超时或未决请求，尚未确认服务端实际执行状态。禁止直接重新提交，必须先核验权威状态！
              </p>
              <div className="pt-1">
                <button
                  type="button"
                  disabled={isVerifying}
                  onClick={onVerifyStatus}
                  className="inline-flex items-center gap-1.5 rounded bg-status-red px-3 py-1.5 text-xs font-bold text-white shadow-xs hover:bg-red-700 disabled:opacity-50"
                >
                  {isVerifying ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      正在核验权威状态...
                    </>
                  ) : (
                    <>
                      <RefreshCw className="h-3.5 w-3.5" />
                      核验权威状态 (GET)
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* Blocker Alert */}
          {hasBlocker && (
            <div className="mt-3.5 rounded border border-status-red/40 bg-status-red-bg p-3 text-xs text-status-red space-y-1">
              <div className="flex items-center gap-2 font-bold">
                <AlertTriangle className="h-4 w-4 flex-none" />
                <span>存在不可平仓的中间态持仓 (Blocked)</span>
              </div>
              <p className="font-mono text-[11px] leading-relaxed">
                阻断条件: {preview?.first_blocker}
              </p>
              <p className="text-text-secondary leading-relaxed">
                当前有 Ticket 处于未受保护状态（如 ENTRY 开仓中或撤单中），无法执行受控平仓。
              </p>
            </div>
          )}

          {/* Error Message */}
          {errorMessage && !isUnknownResult && !hasBlocker && (
            <div className="mt-3.5 rounded border border-status-red/40 bg-status-red-bg p-3 text-xs text-status-red flex items-start justify-between gap-2">
              <p className="leading-relaxed">{errorMessage}</p>
              {onRefreshPreview && errorMessage.includes('409') && (
                <button
                  type="button"
                  onClick={onRefreshPreview}
                  className="flex-none rounded bg-surface px-2 py-1 text-[11px] font-bold text-status-red border border-status-red/30 hover:bg-surface-elevated"
                >
                  重新读取
                </button>
              )}
            </div>
          )}

          {/* Retry Frozen Alert */}
          {isRetryFrozen && (
            <div className="mt-3.5 rounded border border-brand/40 bg-brand-bg p-3 text-xs text-brand space-y-1">
              <strong>重试已锁定原请求</strong>
              <p className="text-text-secondary leading-relaxed">
                服务端尚未记录上次平仓请求。重试将复用原快照与原幂等键。
              </p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="mt-4 space-y-4 text-xs">
            {/* Server Frozen Scope & Active Tickets */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="block text-xs font-bold text-text-muted">
                  服务端冻结范围 ({preview?.ticket_ids.length ?? 0} 笔持仓受影响):
                </span>
                {preview && (
                  <span className="font-mono text-[10px] text-text-muted">
                    Policy v{preview.owner_policy_version} · Snapshot {preview.snapshot_digest.slice(0, 14)}...
                  </span>
                )}
              </div>

              <div className="max-h-36 overflow-y-auto divide-y divide-border rounded border border-border bg-surface-subtle font-mono">
                {preview && preview.ticket_ids.length > 0 ? (
                  preview.ticket_ids.map((ticketId) => (
                    <div key={ticketId} className="flex items-center justify-between p-2.5 text-xs">
                      <span className="text-text-primary font-medium">{ticketId}</span>
                      <span className="rounded bg-surface px-2 py-0.5 text-[11px] font-sans text-text-secondary border border-border">
                        {preview.ticket_states[ticketId] ?? 'unknown'}
                      </span>
                    </div>
                  ))
                ) : (
                  <div className="p-3 text-center text-text-secondary font-sans text-xs">
                    当前已经全平，将执行空仓幂等确认。
                  </div>
                )}
              </div>
            </div>

            {/* Warning notice */}
            <div className="rounded border border-border bg-surface-subtle p-3 text-text-secondary text-xs leading-relaxed">
              <strong className="text-text-primary">受控退出约束: </strong>
              提交后全局 ENTRY 将保持暂停，由 Lifecycle 调度平仓。页面不能指定平仓数量、方向或订单类型。
            </div>

            {/* Step 1: TOTP input */}
            <div>
              <label className="block text-xs font-medium text-text-primary mb-1.5">
                1. Google Authenticator 动态口令 (6 位数字)
              </label>
              <input
                type="text"
                maxLength={6}
                placeholder="000000"
                value={totp}
                disabled={isSubmitting || isVerifying || isUnknownResult || hasBlocker}
                onChange={(e) => setTotp(e.target.value.replace(/\D/g, ''))}
                className="w-full rounded border border-border-strong bg-background px-3 py-2 font-mono text-sm tracking-widest text-text-primary placeholder:text-text-disabled focus:border-brand focus:outline-hidden disabled:opacity-50 disabled:cursor-not-allowed"
              />
            </div>

            {/* Step 2: Confirm text input */}
            <div>
              <label className="block text-xs font-medium text-text-primary mb-1.5">
                2. 输入“<span className="text-status-red font-bold">确认平仓全部持仓</span>”以解锁
              </label>
              <input
                type="text"
                placeholder="确认平仓全部持仓"
                value={confirmText}
                disabled={isSubmitting || isVerifying || isUnknownResult || hasBlocker}
                onChange={(e) => setConfirmText(e.target.value)}
                className="w-full rounded border border-border-strong bg-background px-3 py-2 text-xs text-text-primary placeholder:text-text-disabled focus:border-status-red focus:outline-hidden disabled:opacity-50 disabled:cursor-not-allowed"
              />
            </div>

            {/* Action Buttons */}
            <div className="flex items-center justify-end gap-2.5 border-t border-border pt-4">
              <AlertDialog.Cancel asChild>
                <button
                  type="button"
                  onClick={onClose}
                  disabled={isSubmitting || isVerifying}
                  className="rounded border border-border-strong bg-surface-subtle px-3.5 py-1.5 text-xs font-medium text-text-secondary hover:bg-surface-elevated hover:text-text-primary transition-colors disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
                >
                  取消
                </button>
              </AlertDialog.Cancel>

              <button
                type="submit"
                disabled={!canSubmit}
                className={`inline-flex items-center gap-1.5 rounded px-4 py-1.5 text-xs font-bold transition-colors ${
                  canSubmit
                    ? 'bg-status-red text-white hover:bg-red-700 shadow-xs cursor-pointer'
                    : 'bg-surface-subtle text-text-disabled cursor-not-allowed border border-border'
                }`}
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    正在提交受控平仓...
                  </>
                ) : (
                  '确认受控平仓全部持仓'
                )}
              </button>
            </div>
          </form>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
};
