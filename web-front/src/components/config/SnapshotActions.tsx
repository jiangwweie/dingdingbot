import { useState } from 'react';
import { RotateCcw, Trash2, Loader2, AlertTriangle } from 'lucide-react';
import { rollbackToSnapshot, deleteSnapshot } from '../../lib/api';
import { cn } from '../../lib/utils';

interface SnapshotActionsProps {
  snapshotId: number;
  version: string;
  isActive: boolean;
  onRollbackSuccess: () => void;
  onDeleteSuccess: () => void;
  onError: (message: string) => void;
}

export default function SnapshotActions({
  snapshotId,
  version,
  isActive,
  onRollbackSuccess,
  onDeleteSuccess,
  onError,
}: SnapshotActionsProps) {
  const [rollingBack, setRollingBack] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleRollback = async () => {
    if (!confirm(`确定要回滚到版本 ${version} 吗？\n\n此操作将替换当前配置。`)) {
      return;
    }

    setRollingBack(true);
    try {
      await rollbackToSnapshot(snapshotId);
      onRollbackSuccess();
    } catch (err: any) {
      onError(err.message || '回滚失败，请重试');
    } finally {
      setRollingBack(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`确定要删除快照 ${version} 吗？\n\n此操作不可恢复。`)) {
      return;
    }

    setDeleting(true);
    try {
      await deleteSnapshot(snapshotId);
      onDeleteSuccess();
    } catch (err: any) {
      onError(err.message || '删除失败，请重试');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      {/* Rollback button */}
      <button
        onClick={handleRollback}
        disabled={isActive || rollingBack}
        className={cn(
          'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all',
          isActive || rollingBack
            ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
            : 'bg-black text-white hover:bg-gray-800'
        )}
      >
        {rollingBack ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            回滚中...
          </>
        ) : (
          <>
            <RotateCcw className="w-4 h-4" />
            回滚
          </>
        )}
      </button>

      {/* Delete button */}
      <button
        onClick={handleDelete}
        disabled={isActive || deleting}
        className={cn(
          'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all',
          isActive || deleting
            ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
            : 'bg-red-50 text-red-600 hover:bg-red-100'
        )}
      >
        {deleting ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            删除中...
          </>
        ) : (
          <>
            <Trash2 className="w-4 h-4" />
            删除
          </>
        )}
      </button>

      {/* Protected warning */}
      {isActive && (
        <span className="inline-flex items-center gap-1 px-2 py-1 bg-amber-50 text-amber-700 rounded text-xs font-medium">
          <AlertTriangle className="w-3 h-3" />
          受保护
        </span>
      )}
    </div>
  );
}
