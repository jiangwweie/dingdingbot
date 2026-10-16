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

  const handleClose = () => {
    setTotp('');
    onOpenChange(false);
  };

  return (
    <AlertDialog.Root open={open} onOpenChange={handleClose}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 z-40 bg-black/70 backdrop-blur-xs transition-opacity" />
        <AlertDialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-surface p-5 shadow-2xl">
          <div className="flex items-start justify-between border-b border-border pb-3">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-brand" />
              <AlertDialog.Title className="text-sm font-bold text-text-primary">
                {title}
              </AlertDialog.Title>
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

          <form onSubmit={handleSubmit} className="mt-3.5 space-y-4 text-xs">
            <AlertDialog.Description className="text-xs text-text-secondary leading-relaxed">
              {description}
            </AlertDialog.Description>

            {requireTotp && (
              <div>
                <label className="block text-xs font-medium text-text-primary mb-1.5">
                  Google Authenticator 动态口令 (6 位数字)
                </label>
                <input
                  type="text"
                  maxLength={6}
                  placeholder="000000"
                  value={totp}
                  onChange={(e) => setTotp(e.target.value.replace(/\D/g, ''))}
                  className="w-full rounded border border-border-strong bg-background px-3 py-2 font-mono text-sm tracking-widest text-text-primary placeholder:text-text-disabled focus:border-brand focus:outline-hidden"
                  autoFocus
                />
              </div>
            )}

            <div className="flex items-center justify-end gap-2.5 border-t border-border pt-3.5">
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
                className={`rounded px-4 py-1.5 text-xs font-bold transition-colors ${
                  canSubmit
                    ? 'bg-brand text-slate-950 hover:bg-brand-hover shadow-xs'
                    : 'bg-surface-subtle text-text-disabled cursor-not-allowed border border-border'
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

