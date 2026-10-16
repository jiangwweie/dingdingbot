import React from 'react';
import type { AccountCapacityData } from '../types/controls';
import { Gauge } from 'lucide-react';

interface CapacitySectionProps {
  capacity: AccountCapacityData;
  activeTicketCount: number;
}

export const CapacitySection: React.FC<CapacitySectionProps> = ({
  capacity,
  activeTicketCount,
}) => {
  const isFull = activeTicketCount >= capacity.max_concurrent_tickets;

  // Filter out the zero-occupancy scopes and only highlight what's actively taking capital
  const activeEntries = Object.entries(capacity.strategy_side_active_counts).filter(
    ([, count]) => count > 0
  );

  return (
    <div className="rounded border border-border bg-surface p-4 shadow-xs space-y-4">
      <div className="flex items-center justify-between border-b border-border pb-3">
        <div className="flex items-center gap-2">
          <Gauge className="h-4 w-4 text-brand" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-text-primary">
            组合容量与配额 (只读)
          </h3>
        </div>
        <span className="font-mono text-xs text-text-muted">Policy v28</span>
      </div>

      {/* Global Ticket utilization bar */}
      <div>
        <div className="flex items-center justify-between text-xs mb-2">
          <span className="text-text-secondary">全局 Ticket 占用</span>
          <span className="font-mono font-bold text-text-primary">
            {activeTicketCount} / {capacity.max_concurrent_tickets} 笔
            {isFull ? (
              <span className="ml-1.5 text-status-amber text-xs font-semibold">(已满额)</span>
            ) : null}
          </span>
        </div>
        <div className="h-2 w-full rounded-full bg-surface-subtle overflow-hidden border border-border">
          <div
            className={`h-full transition-all ${
              isFull ? 'bg-status-amber' : 'bg-status-green'
            }`}
            style={{
              width: `${(activeTicketCount / capacity.max_concurrent_tickets) * 100}%`,
            }}
          />
        </div>
      </div>

      {/* Limits Grid */}
      <div className="grid grid-cols-2 gap-2 text-xs font-mono">
        <div className="rounded border border-border bg-surface-subtle p-2.5">
          <span className="text-text-muted font-sans text-xs">同策略同向上限</span>
          <div className="mt-1 font-bold text-text-primary">
            {capacity.max_same_strategy_side} 笔
          </div>
        </div>
        <div className="rounded border border-border bg-surface-subtle p-2.5">
          <span className="text-text-muted font-sans text-xs">空头衰竭上限</span>
          <div className="mt-1 font-bold text-text-primary">
            {capacity.family_limits.rally_failure_short} 笔
          </div>
        </div>
      </div>

      {/* Active Occupations (Concise, no 0s clutter) */}
      <div>
        <span className="block text-xs font-semibold text-text-secondary mb-2">
          当前实时占用分布:
        </span>
        <div className="space-y-1.5 font-mono text-xs">
          {activeEntries.map(([scope, count]) => (
            <div
              key={scope}
              className="flex items-center justify-between rounded bg-surface-subtle px-3 py-1.5 border border-border"
            >
              <span className="text-text-primary font-medium">{scope}</span>
              <span className="font-bold text-brand">{count} 个占用</span>
            </div>
          ))}
          {activeEntries.length === 0 && (
            <div className="text-xs text-text-muted italic">当前无在管持仓占用</div>
          )}
        </div>
        <p className="mt-2.5 text-xs text-text-muted">
          其他 10 个策略方向当前为 0 占用；容量满额时新信号自动在车道排队或被门禁阻断。
        </p>
      </div>
    </div>
  );
};

