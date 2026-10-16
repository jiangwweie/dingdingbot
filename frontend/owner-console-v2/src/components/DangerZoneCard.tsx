import React from 'react';
import { AlertOctagon } from 'lucide-react';

interface DangerZoneCardProps {
  onTriggerFlatten: () => void;
  activeTicketCount: number;
}

export const DangerZoneCard: React.FC<DangerZoneCardProps> = ({
  onTriggerFlatten,
  activeTicketCount,
}) => {
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
          <h3 className="text-sm font-bold text-text-primary">受控平仓全部仓位</h3>
          <p className="text-xs text-text-secondary leading-relaxed max-w-sm">
            安全挂起全局 ENTRY，由 Lifecycle 调度逐笔有序平仓当前全部在管持仓。
          </p>
        </div>

        <button
          type="button"
          onClick={onTriggerFlatten}
          className="flex-none rounded border border-status-red/60 bg-status-red/10 px-3.5 py-2 text-xs font-bold text-status-red hover:bg-status-red hover:text-white transition-all shadow-xs"
        >
          受控平仓全部仓位 ({activeTicketCount})
        </button>
      </div>
    </div>
  );
};

