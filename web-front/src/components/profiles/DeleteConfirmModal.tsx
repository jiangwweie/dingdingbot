import { X, AlertTriangle } from 'lucide-react';
import { cn } from '../../lib/utils';

interface DeleteConfirmModalProps {
  open: boolean;
  onClose: () => void;
  profileName: string;
  onConfirm: () => Promise<void>;
}

export default function DeleteConfirmModal({
  open,
  onClose,
  profileName,
  onConfirm,
}: DeleteConfirmModalProps) {
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    try {
      setSubmitting(true);
      await onConfirm();
    } catch (err: any) {
      console.error('Delete failed:', err);
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="text-lg font-semibold text-gray-900">删除 Profile</h2>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          <div className="flex items-start gap-4 p-4 bg-red-50 rounded-xl border border-red-100">
            <div className="p-2 bg-red-100 rounded-lg">
              <AlertTriangle className="w-5 h-5 text-red-600" />
            </div>
            <div className="flex-1">
              <h3 className="text-sm font-semibold text-red-900">
                确定要删除「{profileName}」吗？
              </h3>
              <p className="text-sm text-red-700 mt-1">
                此操作不可逆，删除后无法恢复。该 Profile 包含的所有配置项也将被删除。
              </p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center gap-3 px-6 py-4 border-t border-gray-100">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg font-medium hover:bg-gray-50 transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className={cn(
              'flex-1 px-4 py-2 text-white rounded-lg font-medium transition-colors',
              'bg-red-600 hover:bg-red-700',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
          >
            {submitting ? '删除中...' : '删除'}
          </button>
        </div>
      </div>
    </div>
  );
}

import { useState } from 'react';
