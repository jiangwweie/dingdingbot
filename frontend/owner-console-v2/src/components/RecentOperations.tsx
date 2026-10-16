import React, { useState } from 'react';
import type { RecentOperationItem } from '../types/controls';
import { History, ChevronDown, ChevronUp } from 'lucide-react';

interface RecentOperationsProps {
  operations: RecentOperationItem[];
}

export const RecentOperations: React.FC<RecentOperationsProps> = ({ operations }) => {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="rounded border border-border bg-surface p-4 shadow-xs">
      <div className="flex items-center justify-between border-b border-border pb-3">
        <div className="flex items-center gap-2">
          <History className="h-4 w-4 text-text-muted" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-text-primary">
            控制操作历史 (最近 3 条)
          </h3>
        </div>
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="text-text-muted hover:text-text-primary transition-colors"
        >
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
      </div>

      {expanded && (
        <div className="mt-3.5 space-y-2.5">
          {operations.map((op) => (
            <div
              key={op.authorization_id}
              className="flex items-center justify-between rounded bg-surface-subtle p-3 text-xs border border-border font-mono"
            >
              <div>
                <strong className="text-text-primary font-sans text-xs">{op.name}</strong>
                <div className="text-xs text-text-muted font-sans mt-0.5">
                  {op.ticket_count} 个 Ticket · {new Date(op.updated_at_ms).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                </div>
              </div>

              <span className="inline-flex items-center gap-1.5 rounded bg-status-green-bg px-2.5 py-1 text-xs font-semibold text-status-green font-sans border border-status-green/20">
                <span className="h-1.5 w-1.5 rounded-full bg-status-green" />
                已完成
              </span>
            </div>
          ))}
          <div className="text-right pt-1.5">
            <span className="text-xs text-text-muted hover:text-brand cursor-pointer transition-colors">
              查看全部历史审计流水 →
            </span>
          </div>
        </div>
      )}
    </div>
  );
};

