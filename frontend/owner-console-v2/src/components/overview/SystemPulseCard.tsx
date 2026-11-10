import React from 'react';
import type { SystemPulseData } from '../../types/overview';
import { ShieldCheck, ShieldAlert, AlertOctagon, ArrowRight, Activity, Clock } from 'lucide-react';

interface SystemPulseCardProps {
  pulse: SystemPulseData;
  onNavigateToControls: () => void;
}

export const SystemPulseCard: React.FC<SystemPulseCardProps> = ({
  pulse,
  onNavigateToControls,
}) => {
  const isDanger = pulse.status === 'danger';
  const isAttention = pulse.status === 'attention';

  return (
    <div className="relative overflow-hidden rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-xs transition-all">
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        {/* Left: Health Pulse & Human Headline */}
        <div className="flex items-start sm:items-center gap-3 sm:gap-3.5 min-w-0 flex-1">
          <div
            className={`flex h-10 w-10 flex-none items-center justify-center rounded-lg border ${
              isDanger
                ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20'
                : isAttention
                ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20'
                : 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20'
            }`}
          >
            {isDanger ? (
              <AlertOctagon className="h-5 w-5" />
            ) : isAttention ? (
              <ShieldAlert className="h-5 w-5" />
            ) : (
              <ShieldCheck className="h-5 w-5" />
            )}
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                  isDanger
                    ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20'
                    : isAttention
                    ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20'
                    : 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                }`}
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    isDanger
                      ? 'bg-rose-500 animate-ping'
                      : isAttention
                      ? 'bg-amber-500'
                      : 'bg-emerald-500 animate-pulse'
                  }`}
                />
                {pulse.status_label}
              </span>

              <span className="font-mono text-[11px] uppercase font-semibold px-2 py-0.5 rounded bg-surface-subtle border border-border text-text-muted">
                {pulse.freshness_label}
              </span>

              <h2 className="text-sm sm:text-base font-bold tracking-tight text-text-primary break-words">
                {pulse.summary}
              </h2>
            </div>

            <p className="mt-1 text-xs text-text-secondary leading-relaxed break-words">
              {pulse.details}
            </p>
          </div>
        </div>

        {/* Right: Operational Facts & Link to Controls */}
        <div className="flex flex-wrap items-center justify-between sm:justify-start gap-3 sm:gap-4 text-xs border-t border-border/50 pt-3 lg:border-t-0 lg:pt-0 w-full lg:w-auto">
          <div data-testid="capacity-pulse" className="flex items-center gap-2 border-r border-border pr-3 sm:pr-4 text-text-muted">
            <Activity className="h-3.5 w-3.5 text-brand flex-none" />
            <span className="truncate">
              容量占用:{' '}
              <strong className="font-mono text-text-primary font-bold">{pulse.active_ticket_count ?? 0}</strong> /{' '}
              <span className="font-mono">{pulse.ticket_capacity_total != null ? pulse.ticket_capacity_total : '未知'}</span>
            </span>
          </div>

          <div className="hidden sm:flex items-center gap-1.5 text-text-muted font-mono text-[11px]">
            <Clock className="h-3.5 w-3.5 flex-none" />
            <span>
              快照:{' '}
              {pulse.generated_at
                ? new Date(pulse.generated_at).toLocaleTimeString('zh-CN', { hour12: false })
                : '时间未知'}
            </span>
          </div>

          <button
            type="button"
            onClick={onNavigateToControls}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-1.5 text-xs font-semibold text-text-primary hover:bg-surface-elevated hover:border-brand/40 transition-colors shadow-2xs cursor-pointer ml-auto sm:ml-0"
          >
            <span>主控中心</span>
            <ArrowRight className="h-3.5 w-3.5 text-text-muted" />
          </button>
        </div>
      </div>
    </div>
  );
};
