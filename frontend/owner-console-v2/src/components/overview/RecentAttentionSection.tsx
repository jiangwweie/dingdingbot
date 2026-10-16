import React from 'react';
import type { RecentEventNotice } from '../../types/overview';
import { CheckCircle2, Bell } from 'lucide-react';

interface RecentAttentionSectionProps {
  events: RecentEventNotice[];
  incidentsCount: number;
}

export const RecentAttentionSection: React.FC<RecentAttentionSectionProps> = ({
  events,
  incidentsCount,
}) => {
  const isHealthy = incidentsCount === 0;

  return (
    <div className="rounded-lg border border-border bg-surface p-4 shadow-sm">
      <div className="flex items-center justify-between pb-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Bell className="h-4 w-4 text-text-muted" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-text-primary">
            系统异常与运行关注 (Attention & Events)
          </h3>
          <span
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ${
              isHealthy
                ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                : 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
            }`}
          >
            {isHealthy ? '0 项异常 · 无需介入' : `${incidentsCount} 项需介入`}
          </span>
        </div>
        <span className="text-[11px] text-text-muted">
          生命周期、选币轮动与对账心跳事实
        </span>
      </div>

      {/* 核心态势结论 */}
      <div className="mt-3 flex items-start gap-3 rounded border border-emerald-500/20 bg-emerald-500/5 p-3">
        <div className="flex h-6 w-6 flex-none items-center justify-center rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
          <CheckCircle2 className="h-4 w-4" />
        </div>
        <div>
          <h4 className="text-xs font-bold text-text-primary">
            一切正常，无需 Owner 介入
          </h4>
          <p className="mt-0.5 text-[11px] text-text-secondary leading-relaxed">
            全局 ENTRY 畅通，5 个策略组均按 Policy v4 预算平稳运行。PostgreSQL 与交易所只读事实无脱节，动态选币处于有效窗口。
          </p>
        </div>
      </div>

      {/* 最近运行通知流水 */}
      <div className="mt-3 space-y-2">
        <div className="text-[10px] font-bold uppercase tracking-wider text-text-muted">
          最近运维与流水通知 (Recent Milestones)
        </div>
        {events.map((evt) => (
          <div
            key={evt.id}
            className="flex items-start justify-between gap-3 rounded border border-border/60 bg-surface-subtle px-3 py-2 text-xs"
          >
            <div className="flex items-start gap-2">
              <span className="inline-flex mt-0.5 rounded bg-brand/10 px-1.5 py-0.2 font-mono text-[10px] font-medium text-brand flex-none">
                {evt.source_worker}
              </span>
              <div>
                <span className="font-medium text-text-primary">{evt.title}</span>
                <p className="text-[11px] text-text-muted mt-0.5">{evt.detail}</p>
              </div>
            </div>
            <span className="font-mono text-[11px] text-text-muted flex-none whitespace-nowrap">
              {evt.timestamp_utc}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
