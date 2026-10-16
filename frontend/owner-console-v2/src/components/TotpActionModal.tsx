import React, { useState } from 'react';
import * as AlertDialog from '@radix-ui/react-alert-dialog';
import { ShieldCheck, X } from 'lucide-react';

interface TotpActionModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel: string;
  requireTotp?: boolean;
  onConfirm: (totp: string) => void;
}

export const TotpActionModal: React.FC<TotpActionModalProps> = ({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  requireTotp = true,
  onConfirm,
}) => {
  const [totp, setTotp] = useState('');

  const canSubmit = !requireTotp || (totp.length === 6 && /^\d+$/.test(totp));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    onConfirm(totp);
    setTotp('');
    onOpenChange(false);
  };

  return (
    <AlertDialog.Root open={open} onOpenChange={onOpenChange}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 z-40 bg-black/75 backdrop-blur-xs transition-opacity" />
        <AlertDialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border-base bg-surface-1 p-5 shadow-2xl">
          <div className="flex items-start justify-between border-b border-border-base pb-3">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-brand" />
              <AlertDialog.Title className="text-sm font-bold text-slate-100">
                {title}
              </AlertDialog.Title>
            </div>
            <AlertDialog.Cancel asChild>
              <button
                type="button"
                className="text-slate-400 hover:text-slate-200"
              >
                <X className="h-4 w-4" />
              </button>
            </AlertDialog.Cancel>
          </div>

          <form onSubmit={handleSubmit} className="mt-3.5 space-y-4 text-xs">
            <AlertDialog.Description className="text-xs text-slate-400 leading-relaxed">
              {description}
            </AlertDialog.Description>

            {requireTotp && (
              <div>
                <label className="block font-medium text-slate-300 mb-1">
                  Google Authenticator 动态口令 (6 位数字)
                </label>
                <input
                  type="text"
                  maxLength={6}
                  placeholder="000000"
                  value={totp}
                  onChange={(e) => setTotp(e.target.value.replace(/\D/g, ''))}
                  className="w-full rounded border border-border-strong bg-canvas px-3 py-2 font-mono text-sm tracking-widest text-slate-100 placeholder:text-slate-600 focus:border-brand focus:outline-hidden"
                  autoFocus
                />
              </div>
            )}

            <div className="flex items-center justify-end gap-2 border-t border-border-base pt-3">
              <AlertDialog.Cancel asChild>
                <button
                  type="button"
                  className="rounded border border-border-strong bg-surface-2 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-surface-3 hover:text-white"
                >
                  取消
                </button>
              </AlertDialog.Cancel>

              <button
                type="submit"
                disabled={!canSubmit}
                className={`rounded px-4 py-1.5 text-xs font-bold transition-colors ${
                  canSubmit
                    ? 'bg-brand text-slate-950 hover:bg-brand-hover'
                    : 'bg-surface-3 text-slate-500 cursor-not-allowed border border-border-base'
                }`}
              >
                {confirmLabel}
              </button>
            </div>
          </form>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
};
