import React from 'react';
import type { AttentionItem } from '../../types/overview';
import { CheckCircle2, AlertTriangle, AlertOctagon, Bell } from 'lucide-react';

interface RecentAttentionSectionProps {
  attentionList: AttentionItem[];
  incidentsCount: number;
  conclusion: 'no_action' | 'attention' | 'intervention';
}

export const RecentAttentionSection: React.FC<RecentAttentionSectionProps> = ({
  attentionList,
  incidentsCount,
  conclusion,
}) => {
  const isHealthy = conclusion === 'no_action' && incidentsCount === 0;

  return (
    <div className="rounded-lg border border-border bg-surface p-4 shadow-sm">
      <div className="flex items-center justify-between pb-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Bell className="h-4 w-4 text-text-muted" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-text-primary">
            需要关注 (Attention & Incidents)
          </h3>
          <span
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ${
              isHealthy
                ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                : 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
            }`}
          >
            {isHealthy ? '0 项阻断 · 一切正常' : `${incidentsCount} 项异常 · 需关注`}
          </span>
        </div>
        <span className="text-[11px] text-text-muted">
          来自 /api/owner/v1/overview 权威结论
        </span>
      </div>

      {isHealthy ? (
        /* 核心态势结论：一切正常 */
        <div className="mt-3 flex items-start gap-3 rounded border border-emerald-500/20 bg-emerald-500/5 p-4">
          <div className="flex h-7 w-7 flex-none items-center justify-center rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
            <CheckCircle2 className="h-4 w-4" />
          </div>
          <div>
            <h4 className="text-xs font-bold text-text-primary">
              一切正常，无需 Owner 介入
            </h4>
            <p className="mt-1 text-[11px] text-text-secondary leading-relaxed">
              全局准入畅通，各策略组均在预算内正常扫描；在管持仓均已安装交易所保护单；PostgreSQL 与只读事实无冲突。
            </p>
          </div>
        </div>
      ) : (
        /* 存在异常或需要关注项 */
        <div className="mt-3 space-y-2">
          {attentionList.map((item) => {
            const isAlert = item.type === 'alert';
            return (
              <div
                key={item.id}
                className={`flex items-start gap-3 rounded border p-3 text-xs ${
                  isAlert
                    ? 'border-rose-500/30 bg-rose-500/5 text-rose-700 dark:text-rose-300'
                    : 'border-amber-500/30 bg-amber-500/5 text-amber-700 dark:text-amber-300'
                }`}
              >
                <div className="mt-0.5 flex-none">
                  {isAlert ? (
                    <AlertOctagon className="h-4 w-4 text-rose-500" />
                  ) : (
                    <AlertTriangle className="h-4 w-4 text-amber-500" />
                  )}
                </div>
                <div>
                  <h5 className="font-semibold">{item.title}</h5>
                  {item.detail && (
                    <p className="mt-0.5 text-[11px] opacity-90">{item.detail}</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
