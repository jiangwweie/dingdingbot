import React, { useState } from 'react';
import type { RecentOperationItem } from '../types/controls';
import { History, ChevronDown, ChevronUp } from 'lucide-react';

interface RecentOperationsProps {
  operations: RecentOperationItem[];
}

export const RecentOperations: React.FC<RecentOperationsProps> = ({ operations }) => {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="rounded border border-border-base bg-surface-1 p-4 shadow-sm">
      <div className="flex items-center justify-between border-b border-border-base pb-2.5">
        <div className="flex items-center gap-2">
          <History className="h-4 w-4 text-slate-400" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200">
            控制操作历史 (最近 3 条)
          </h3>
        </div>
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="text-slate-400 hover:text-slate-200 transition-colors"
        >
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
      </div>

      {expanded && (
        <div className="mt-3 space-y-2">
          {operations.map((op) => (
            <div
              key={op.authorization_id}
              className="flex items-center justify-between rounded bg-surface-2 p-2.5 text-xs font-mono"
            >
              <div>
                <strong className="text-slate-200 font-sans">{op.name}</strong>
                <div className="text-[10px] text-slate-500 font-sans mt-0.5">
                  {op.ticket_count} 个 Ticket · {new Date(op.updated_at_ms).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                </div>
              </div>

              <span className="inline-flex items-center gap-1 rounded bg-status-green-bg px-2 py-0.5 text-[10px] font-semibold text-status-green font-sans">
                <span className="h-1.5 w-1.5 rounded-full bg-status-green" />
                已完成
              </span>
            </div>
          ))}
          <div className="text-right pt-1">
            <span className="text-[10px] text-slate-500 hover:text-slate-300 cursor-pointer">
              查看全部历史审计流水 →
            </span>
          </div>
        </div>
      )}
    </div>
  );
};
