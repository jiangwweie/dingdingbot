import React, { useState } from 'react';
import * as AlertDialog from '@radix-ui/react-alert-dialog';
import { AlertOctagon, X, Check, Loader2 } from 'lucide-react';
import type { FlattenPreviewData } from '../types/controls';

interface ControlledFlattenModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preview: FlattenPreviewData;
  onConfirmFlatten: (totp: string) => Promise<void>;
}

export const ControlledFlattenModal: React.FC<ControlledFlattenModalProps> = ({
  open,
  onOpenChange,
  preview,
  onConfirmFlatten,
}) => {
  const [totp, setTotp] = useState('');
  const [confirmText, setConfirmText] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [completed, setCompleted] = useState(false);

  const isTotpValid = totp.length === 6 && /^\d+$/.test(totp);
  const isTextValid = confirmText === '确认平仓全部持仓';
  const canSubmit = isTotpValid && isTextValid && !isSubmitting;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;

    setIsSubmitting(true);
    try {
      await onConfirmFlatten(totp);
      setCompleted(true);
      setTimeout(() => {
        setCompleted(false);
        setIsSubmitting(false);
        setTotp('');
        setConfirmText('');
        onOpenChange(false);
      }, 1500);
    } catch {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    if (isSubmitting) return;
    setTotp('');
    setConfirmText('');
    setCompleted(false);
    onOpenChange(false);
  };

  return (
    <AlertDialog.Root open={open} onOpenChange={handleClose}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 z-40 bg-black/70 backdrop-blur-xs transition-opacity" />
        <AlertDialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-lg border border-status-red/50 bg-surface p-6 shadow-2xl">
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
                  先安全挂起全局 ENTRY，再由 Lifecycle 调度逐笔有序平仓当前全部持仓。
                </AlertDialog.Description>
              </div>
            </div>
            <AlertDialog.Cancel asChild>
              <button
                type="button"
                onClick={handleClose}
                className="text-text-muted hover:text-text-primary transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </AlertDialog.Cancel>
          </div>

          {completed ? (
            <div className="py-8 text-center space-y-3">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-status-green-bg text-status-green border border-status-green/30">
                <Check className="h-6 w-6" />
              </div>
              <p className="text-sm font-bold text-text-primary">受控平仓指令已提交</p>
              <p className="text-xs text-text-secondary">全局 ENTRY 已挂起，Lifecycle 正在调度有序退出。</p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="mt-4 space-y-4 text-xs">
              {/* Affected Tickets list from server preview */}
              <div>
                <span className="block text-xs font-bold uppercase tracking-wider text-text-muted mb-2">
                  服务端冻结范围 ({preview.tickets.length} 笔持仓受影响):
                </span>
                <div className="divide-y divide-border rounded border border-border bg-surface-subtle font-mono">
                  {preview.tickets.map((t) => (
                    <div key={t.ticket_id} className="flex items-center justify-between p-3 text-xs">
                      <div className="flex items-center gap-2">
                        <span
                          className={`font-bold ${
                            t.side === 'long' ? 'text-status-green' : 'text-status-red'
                          }`}
                        >
                          {t.side.toUpperCase()}
                        </span>
                        <span className="text-text-primary font-medium">
                          {t.instrument.split(':')[1] ?? t.instrument}
                        </span>
                        <span className="text-text-muted font-sans text-xs">({t.strategy_group_id})</span>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-text-secondary font-sans text-xs">生命周期保护中</span>
                        <strong
                          className={`font-semibold ${
                            t.unrealized_r.startsWith('+') ? 'text-status-green' : 'text-status-red'
                          }`}
                        >
                          {t.unrealized_r}
                        </strong>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Warning notice: Subtle in light, restrained in dark */}
              <div className="rounded border border-border bg-surface-subtle p-3 text-text-secondary text-xs leading-relaxed">
                <strong className="text-text-primary">受控退出约束: </strong>
                系统将按预设生命周期计划有序平仓，页面不支持指定平仓数量、方向或订单类型。
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
                  onChange={(e) => setTotp(e.target.value.replace(/\D/g, ''))}
                  className="w-full rounded border border-border-strong bg-background px-3 py-2 font-mono text-sm tracking-widest text-text-primary placeholder:text-text-disabled focus:border-brand focus:outline-hidden"
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
                  onChange={(e) => setConfirmText(e.target.value)}
                  className="w-full rounded border border-border-strong bg-background px-3 py-2 text-xs text-text-primary placeholder:text-text-disabled focus:border-status-red focus:outline-hidden"
                />
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-end gap-2.5 border-t border-border pt-4">
                <AlertDialog.Cancel asChild>
                  <button
                    type="button"
                    onClick={handleClose}
                    className="rounded border border-border-strong bg-surface-subtle px-3.5 py-1.5 text-xs font-medium text-text-secondary hover:bg-surface-elevated hover:text-text-primary transition-colors"
                  >
                    取消
                  </button>
                </AlertDialog.Cancel>

                <button
                  type="submit"
                  disabled={!canSubmit}
                  className={`inline-flex items-center gap-1.5 rounded px-4 py-1.5 text-xs font-bold transition-colors ${
                    canSubmit
                      ? 'bg-status-red text-white hover:bg-red-700 shadow-xs'
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
          )}
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
};

