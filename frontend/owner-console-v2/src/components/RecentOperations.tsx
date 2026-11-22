import React, { useState } from 'react';
import type { RecentOperationItem } from '../types/controls';
import { formatControlOperationState } from '../mapping/controlStateMapping';
import { History, ChevronDown, ChevronUp } from 'lucide-react';

interface RecentOperationsProps {
  operations: RecentOperationItem[];
}

function getOperationTone(state: string, blocker?: string | null): {
  bg: string;
  text: string;
  border: string;
  dotBg: string;
  label: string;
  isUnknown?: boolean;
} {
  const meta = formatControlOperationState(state, blocker);
  if (meta.tone === 'success') {
    return {
      bg: 'bg-status-green-bg',
      text: 'text-status-green',
      border: 'border-status-green/20',
      dotBg: 'bg-status-green',
      label: meta.label,
      isUnknown: meta.isUnknown,
    };
  }
  if (meta.tone === 'danger') {
    return {
      bg: 'bg-status-red-bg',
      text: 'text-status-red',
      border: 'border-status-red/30',
      dotBg: 'bg-status-red',
      label: meta.label,
      isUnknown: meta.isUnknown,
    };
  }
  if (meta.tone === 'attention') {
    return {
      bg: 'bg-status-amber-bg',
      text: 'text-status-amber',
      border: 'border-status-amber/30',
      dotBg: 'bg-status-amber',
      label: meta.label,
      isUnknown: meta.isUnknown,
    };
  }
  return {
    bg: 'bg-brand-bg',
    text: 'text-brand',
    border: 'border-brand/30',
    dotBg: 'bg-brand',
    label: meta.label,
    isUnknown: meta.isUnknown,
  };
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
          className="text-text-muted hover:text-text-primary transition-colors cursor-pointer"
        >
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
      </div>

      {expanded && (
        <div className="mt-3.5 space-y-2.5">
          {operations.length === 0 ? (
            <div className="p-3 text-center text-xs text-text-secondary">暂无受控操作记录</div>
          ) : (
            operations.map((op) => {
              const tone = getOperationTone(op.state, op.first_blocker);
              return (
                <div
                  key={op.authorization_id}
                  className="flex items-center justify-between rounded bg-surface-subtle p-3 text-xs border border-border font-mono"
                >
                  <div>
                    <strong className="text-text-primary font-sans text-xs">{op.name}</strong>
                    <div className="text-xs text-text-muted font-sans mt-0.5">
                      {op.ticket_count} 个 Ticket ·{' '}
                      {new Date(op.updated_at_ms).toLocaleString('zh-CN', {
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </div>
                    {op.first_blocker && (
                      <div
                        className="text-[11px] text-status-red font-sans mt-0.5 max-w-sm truncate"
                        title={op.first_blocker}
                      >
                        过程关注: {op.first_blocker}
                      </div>
                    )}
                  </div>

                  <div className="flex flex-col items-end gap-1">
                    <span
                      className={`inline-flex items-center gap-1.5 rounded ${tone.bg} px-2.5 py-1 text-xs font-semibold ${tone.text} font-sans border ${tone.border}`}
                    >
                      <span className={`h-1.5 w-1.5 rounded-full ${tone.dotBg}`} />
                      {tone.label}
                    </span>
                    {tone.isUnknown && (
                      <details className="text-[10px] text-text-muted font-sans">
                        <summary className="cursor-pointer">原始状态码</summary>
                        <span className="font-mono">{op.state}</span>
                      </details>
                    )}
                  </div>
                </div>
              );
            })
          )}
          <div className="text-right pt-1">
            <span className="text-[11px] text-text-muted">
              仅展示最近受控操作记录
            </span>
          </div>
        </div>
      )}
    </div>
  );
};
