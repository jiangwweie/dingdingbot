import React from 'react';
import { AlertOctagon, Loader2 } from 'lucide-react';
import type { OwnerControlOperation } from '../api/controlsApi';

export interface DangerZoneCardProps {
  activeTicketCount: number;
  onTriggerFlatten?: () => void;
  isLoading?: boolean;
  currentOperation?: OwnerControlOperation | null;
}

export const DangerZoneCard: React.FC<DangerZoneCardProps> = ({
  activeTicketCount,
  onTriggerFlatten,
  isLoading = false,
  currentOperation,
}) => {
  const isOperationActive = Boolean(
    currentOperation &&
      currentOperation.state !== 'completed' &&
      currentOperation.state !== 'blocked'
  );

  return (
    <div className="rounded border border-status-red/50 bg-surface p-4 shadow-xs">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-1.5 text-status-red">
            <AlertOctagon className="h-4 w-4 flex-none" />
            <span className="text-xs font-bold uppercase tracking-wider">
              危险操作 · 紧急熔断
            </span>
          </div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold text-text-primary">受控平仓全部仓位</h3>
            {isOperationActive && (
              <span className="rounded bg-brand/10 px-2 py-0.5 text-[11px] font-mono font-bold text-brand border border-brand/30">
                进行中: {currentOperation?.state}
              </span>
            )}
          </div>
          <p className="text-xs text-text-secondary leading-relaxed max-w-sm">
            安全挂起全局 ENTRY，由 Lifecycle 调度逐笔有序平仓当前全部在管持仓。
          </p>
        </div>

        <button
          type="button"
          data-testid="danger-zone-flatten-btn"
          disabled={isLoading}
          onClick={onTriggerFlatten}
          className={`flex-none rounded px-3.5 py-2 text-xs font-bold transition-colors ${
            isLoading
              ? 'bg-surface-subtle text-text-disabled cursor-not-allowed border border-border'
              : isOperationActive
              ? 'bg-brand/10 text-brand border border-brand/30 hover:bg-brand/20 shadow-xs cursor-pointer'
              : 'bg-status-red text-white hover:bg-red-700 shadow-xs cursor-pointer'
          }`}
        >
          {isLoading ? (
            <span className="inline-flex items-center gap-1.5">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              读取权威快照...
            </span>
          ) : isOperationActive ? (
            `平仓进行中 (${currentOperation?.state}) · 查看进度`
          ) : (
            `受控平仓全部仓位 (${activeTicketCount})`
          )}
        </button>
      </div>
    </div>
  );
};
