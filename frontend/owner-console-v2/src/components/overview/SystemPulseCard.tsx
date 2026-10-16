import React from 'react';
import type { SystemPulseData } from '../../types/overview';
import { ShieldCheck, ArrowRight, Activity, Clock } from 'lucide-react';

interface SystemPulseCardProps {
  pulse: SystemPulseData;
  onNavigateToControls: () => void;
}

export const SystemPulseCard: React.FC<SystemPulseCardProps> = ({
  pulse,
  onNavigateToControls,
}) => {
  return (
    <div className="relative overflow-hidden rounded-lg border border-border bg-surface p-4 shadow-sm transition-all">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        {/* Left: Health Pulse & Human Headline */}
        <div className="flex items-start sm:items-center gap-3">
          <div className="flex h-9 w-9 flex-none items-center justify-center rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
            <ShieldCheck className="h-5 w-5" />
          </div>

          <div>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                {pulse.status_label}
              </span>
              <h2 className="text-sm font-bold text-text-primary">
                {pulse.summary}
              </h2>
            </div>
            <p className="mt-0.5 text-xs text-text-secondary">
              {pulse.details}
            </p>
          </div>
        </div>

        {/* Right: Operational Facts & Link to Controls */}
        <div className="flex items-center gap-4 text-xs">
          <div className="hidden md:flex items-center gap-2 border-r border-border pr-4 text-text-muted">
            <Activity className="h-3.5 w-3.5 text-brand" />
            <span>容量占用: <strong className="font-mono text-text-primary">{pulse.ticket_capacity_used}</strong> / {pulse.ticket_capacity_total}</span>
          </div>

          <div className="hidden lg:flex items-center gap-1.5 text-text-muted">
            <Clock className="h-3.5 w-3.5" />
            <span>对账同步: {pulse.data_freshness_seconds}s 前</span>
          </div>

          <button
            type="button"
            onClick={onNavigateToControls}
            className="inline-flex items-center gap-1 rounded border border-border bg-surface-subtle px-2.5 py-1 text-xs font-medium text-text-primary hover:bg-surface-elevated hover:border-brand/40 transition-colors"
          >
            <span>主控中心</span>
            <ArrowRight className="h-3 w-3 text-text-muted" />
          </button>
        </div>
      </div>
    </div>
  );
};
