import React from 'react';
import type { AttentionItem } from '../../types/overview';
import { CheckCircle2, AlertTriangle, AlertOctagon, Bell, ArrowRight, ArrowUp } from 'lucide-react';

interface RecentAttentionSectionProps {
  attentionList: AttentionItem[];
  incidentsCount: number;
  conclusion: 'no_action' | 'attention' | 'intervention';
  freshness?: 'fresh' | 'stale' | 'unavailable' | 'contradictory';
  onNavigateToControls?: () => void;
  onLocateActiveEpisodes?: () => void;
  onNavigateToTrades?: () => void;
}

export const RecentAttentionSection: React.FC<RecentAttentionSectionProps> = ({
  attentionList,
  incidentsCount,
  conclusion,
  freshness = 'fresh',
  onNavigateToControls,
  onLocateActiveEpisodes,
  onNavigateToTrades,
}) => {
  const hasItems = attentionList.length > 0;
  const isCompletelyClear = freshness === 'fresh' && !hasItems && incidentsCount === 0 && conclusion === 'no_action';
  const isIntervention = conclusion === 'intervention';
  const isAttention = conclusion === 'attention' || incidentsCount > 0;

  return (
    <div id="recent-attention-section" className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-xs transition-all">
      <div className="flex flex-col sm:flex-row sm:items-baseline justify-between pb-3.5 border-b border-border/80 gap-1 sm:gap-2">
        <div className="flex items-center gap-2.5">
          <Bell className="h-4 w-4 text-text-muted flex-none" />
          <h2 className="text-sm font-bold tracking-tight text-text-primary">
            运行关注与异常
          </h2>
          <span
            className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ${
              isCompletelyClear
                ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                : incidentsCount > 0 || isIntervention
                ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20'
                : 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20'
            }`}
          >
            {isCompletelyClear
              ? '0 项阻断 · 一切平稳'
              : incidentsCount > 0
              ? `${incidentsCount} 项异常 · 需关注`
              : `${attentionList.length} 项关注`}
          </span>
        </div>
        <details className="text-[11px] text-text-muted sm:text-right">
          <summary className="cursor-pointer select-none hover:text-text-secondary focus-visible:outline-2 focus-visible:outline-brand rounded px-1 inline-block">
            数据来源
          </summary>
          <div className="mt-1 text-text-muted break-words">
            来自 /api/owner/v1/overview 权威事实
          </div>
        </details>
      </div>

      {isCompletelyClear ? (
        /* 核心态势结论：正常状态保持安静，单行摘要展示 */
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-border bg-surface-subtle/60 px-3.5 py-2.5 text-xs">
          <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400 flex-none" />
          <span className="font-bold text-text-primary">运行平稳 · 暂无关注项</span>
          <span className="text-text-muted">·</span>
          <span className="text-text-secondary">
            当前快照暂无需 Owner 介入处置的提示；各笔保护状态以持仓卡片事实为准。
          </span>
        </div>
      ) : (
        /* 存在关注项、异常或介入要求：绝不隐藏任何关注项 */
        <div className="mt-4 space-y-2.5">
          {/* Owner 决策与操作状态横幅 (独立表达，不与开仓准入混淆) */}
          <div
            className={`flex items-center justify-between rounded-lg px-3.5 py-2 text-xs border ${
              isIntervention
                ? 'border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300 font-bold'
                : isAttention
                ? 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300 font-semibold'
                : 'border-border bg-surface-subtle text-text-secondary'
            }`}
          >
            <span>
              {freshness !== 'fresh' ? '当前快照已滞后或不可用，请刷新核实' : isIntervention
                ? '需 Owner 紧急介入'
                : isAttention
                ? '需 Owner 关注与核实'
                : '当前无需 Owner 操作 · 存在系统提示关注项'}
            </span>
            <span className="font-mono text-[11px] opacity-80">
              共 {attentionList.length} 项提示
            </span>
          </div>

          {/* 渲染全部关注项 */}
          {attentionList.map((item) => {
            const isAlert = item.type === 'alert';
            return (
              <div
                key={item.id}
                className={`flex items-start justify-between gap-3 rounded-lg border p-3.5 text-xs ${
                  isAlert
                    ? 'border-rose-500/30 bg-rose-500/5 text-rose-700 dark:text-rose-300'
                    : 'border-amber-500/30 bg-amber-500/5 text-amber-700 dark:text-amber-300'
                }`}
              >
                <div className="flex items-start gap-2.5 min-w-0 flex-1">
                  <div className="mt-0.5 flex-none">
                    {isAlert ? (
                      <AlertOctagon className="h-4 w-4 text-rose-500" />
                    ) : (
                      <AlertTriangle className="h-4 w-4 text-amber-500" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <h4 className="font-semibold break-words">{item.title}</h4>
                    {item.detail && (
                      <p className="mt-1 text-xs opacity-90 leading-relaxed break-words">
                        {item.detail}
                      </p>
                    )}
                  </div>
                </div>

                {/* Contextual Navigation Action */}
                {item.action_target === 'controls' && onNavigateToControls && (
                  <button
                    type="button"
                    onClick={onNavigateToControls}
                    className="flex-none inline-flex items-center gap-1 rounded border border-current/25 bg-surface/80 px-2.5 py-1 text-[11px] font-semibold hover:bg-surface transition-colors cursor-pointer"
                  >
                    <span>查看控制</span>
                    <ArrowRight className="h-3 w-3" />
                  </button>
                )}
                {item.action_target === 'active_episodes' && onLocateActiveEpisodes && (
                  <button
                    type="button"
                    onClick={onLocateActiveEpisodes}
                    className="flex-none inline-flex items-center gap-1 rounded border border-current/25 bg-surface/80 px-2.5 py-1 text-[11px] font-semibold hover:bg-surface transition-colors cursor-pointer"
                  >
                    <span>定位持仓</span>
                    <ArrowUp className="h-3 w-3" />
                  </button>
                )}
                {item.action_target === 'trades' && onNavigateToTrades && (
                  <button
                    type="button"
                    onClick={onNavigateToTrades}
                    className="flex-none inline-flex items-center gap-1 rounded border border-current/25 bg-surface/80 px-2.5 py-1 text-[11px] font-semibold hover:bg-surface transition-colors cursor-pointer"
                  >
                    <span>查看因果</span>
                    <ArrowRight className="h-3 w-3" />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
