import React from 'react';
import type { TradeEpisodeSummary } from '../../types/overview';
import {
  Shield,
  ShieldCheck,
  ShieldAlert,
  ArrowUpRight,
  ArrowDownRight,
  Clock,
  ChevronRight,
  AlertTriangle,
  AlertCircle,
  RefreshCw,
  Loader2,
  Cpu,
  UserCheck,
} from 'lucide-react';

interface ActiveEpisodesSectionProps {
  episodes: TradeEpisodeSummary[];
  onSelectEpisode: (episode: TradeEpisodeSummary) => void;
  isLoading?: boolean;
  isError?: boolean;
  errorMessage?: string | null;
  unloadedActiveCount?: number;
  onRetry?: () => void;
}

export const ActiveEpisodesSection: React.FC<ActiveEpisodesSectionProps> = ({
  episodes,
  onSelectEpisode,
  isLoading = false,
  isError = false,
  errorMessage,
  unloadedActiveCount = 0,
  onRetry,
}) => {
  return (
    <div id="active-episodes" className="rounded-xl border border-border bg-surface p-5 shadow-xs transition-all">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-baseline justify-between pb-4 border-b border-border/80 gap-1 sm:gap-3">
        <div className="flex items-center gap-2.5">
          <h2 className="text-sm font-bold tracking-tight text-text-primary">
            在管交易
          </h2>
          {isLoading ? (
            <span className="inline-flex items-center gap-1 rounded-md bg-surface-subtle px-2 py-0.5 font-mono text-[11px] text-text-muted border border-border">
              <Loader2 className="h-3 w-3 animate-spin text-brand" />
              读取中...
            </span>
          ) : isError ? (
            <span className="inline-flex items-center gap-1 rounded-md bg-rose-500/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-rose-600 dark:text-rose-400 border border-rose-500/20">
              <AlertCircle className="h-3 w-3" />
              读取失败
            </span>
          ) : (
            <span className="inline-flex items-center rounded-md bg-brand/10 px-2 py-0.5 font-mono text-xs font-semibold text-brand border border-brand/20">
              {episodes.length} 笔在管
            </span>
          )}
        </div>
        <span className="text-[11px] sm:text-xs text-text-muted break-words">
          来自生产 Ticket 账本只读事实 · 自动与人工管理状态分别展示
        </span>
      </div>

      {isLoading ? (
        <div className="py-12 text-center">
          <div className="inline-flex items-center justify-center gap-2 text-xs text-text-muted">
            <Loader2 className="h-4 w-4 animate-spin text-brand" />
            <span>正在读取在管持仓事实 (/api/owner/v1/tickets)...</span>
          </div>
        </div>
      ) : isError ? (
        <div className="my-4 flex items-center justify-between rounded-lg border border-rose-500/30 bg-rose-500/5 p-4 text-xs">
          <div className="flex items-center gap-2.5 text-rose-600 dark:text-rose-400">
            <AlertCircle className="h-4 w-4 flex-none" />
            <div>
              <span className="font-bold">在管持仓事实读取失败: </span>
              <span className="opacity-90">{errorMessage ?? '网络错误或服务端无响应'}</span>
            </div>
          </div>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="inline-flex items-center gap-1 rounded-md border border-rose-500/30 bg-surface px-3 py-1.5 text-xs font-semibold text-rose-600 dark:text-rose-400 hover:bg-rose-500/10 transition-colors cursor-pointer"
            >
              <RefreshCw className="h-3 w-3" />
              <span>重试</span>
            </button>
          )}
        </div>
      ) : episodes.length === 0 ? (
        <div className="py-12 text-center">
          <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-surface-subtle text-text-muted mb-2">
            <Shield className="h-5 w-5 opacity-40" />
          </div>
          <p className="text-xs font-semibold text-text-secondary">
            当前无活动持仓
          </p>
          <p className="mt-1 text-[11px] text-text-muted">
            生产策略组在 Observation 持续扫描中，准入前不会占用持仓容量
          </p>
        </div>
      ) : (
        <div className="mt-4 space-y-3">
          {episodes.map((ep) => {
            const isLong = ep.side === 'long';
            const management = ep.management_mode ?? 'AUTO';
            const isManual = management === 'MANUAL';
            const isReviewRequired = management === 'REVIEW_REQUIRED';

            return (
              <div
                key={ep.ticket_id}
                data-ticket-id={ep.ticket_id}
                className="group relative rounded-lg border border-border bg-surface p-4 hover:border-brand/40 hover:bg-surface-elevated/40 transition-all shadow-2xs"
              >
                {/* Main Card Row */}
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
                  {/* Left: Direction + Symbol + Strategy + Management Mode */}
                  <div className="flex items-start sm:items-center gap-3 min-w-0">
                    <div
                      className={`flex h-9 w-9 flex-none items-center justify-center rounded-lg ${
                        isLong
                          ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                          : 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20'
                      }`}
                    >
                      {isLong ? (
                        <ArrowUpRight className="h-5 w-5" />
                      ) : (
                        <ArrowDownRight className="h-5 w-5" />
                      )}
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
                        <span className="font-mono text-sm font-bold tracking-tight text-text-primary">
                          {ep.symbol}
                        </span>
                        <span
                          className={`font-mono text-[11px] font-bold px-2 py-0.5 rounded uppercase ${
                            isLong
                              ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                              : 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20'
                          }`}
                        >
                          {isLong ? '做多 (LONG)' : '做空 (SHORT)'}
                        </span>

                        {/* Management Authority Pill */}
                        {isManual ? (
                          <span className="inline-flex items-center gap-1 rounded bg-amber-500/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-amber-600 dark:text-amber-400 border border-amber-500/20">
                            <UserCheck className="h-3 w-3" />
                            整笔已转人工管理
                          </span>
                        ) : isReviewRequired ? (
                          <span className="inline-flex items-center gap-1 rounded bg-amber-500/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-amber-600 dark:text-amber-400 border border-amber-500/20">
                            <AlertTriangle className="h-3 w-3" />
                            接管待核实
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 rounded bg-surface-subtle px-2 py-0.5 font-mono text-[11px] font-medium text-text-secondary border border-border">
                            <Cpu className="h-3 w-3 text-brand" />
                            程序自动管理
                          </span>
                        )}

                        <span className="font-mono text-[11px] text-text-muted">
                          #{ep.ticket_id.slice(-8)}
                        </span>
                      </div>

                      <div className="flex flex-wrap items-center gap-1.5 mt-1 text-xs text-text-muted">
                        <span className="font-mono font-semibold text-brand">
                          {ep.strategy_id}
                        </span>
                        <span>·</span>
                        <span className="truncate">{ep.strategy_name_zh}</span>
                      </div>
                    </div>
                  </div>

                  {/* Right: Metrics & Action */}
                  <div className="flex flex-wrap items-center justify-between sm:justify-start gap-3 sm:gap-5 text-xs pt-3 border-t border-border/50 lg:border-t-0 lg:pt-0 w-full lg:w-auto">
                    {/* Lifecycle & Protection facts */}
                    <div>
                      <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">
                        当前生命周期
                      </div>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <Shield className="h-3.5 w-3.5 text-brand" />
                        <span className="font-semibold text-text-primary">
                          {ep.lifecycle_stage_zh}
                        </span>
                        <span className="font-mono text-[11px] text-text-muted">
                          ({ep.completed_stage_count}/{ep.total_stage_count})
                        </span>
                      </div>
                    </div>

                    {/* Protection Status (Separated from Authority) */}
                    <div>
                      <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">
                        保护状态事实
                      </div>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        {ep.is_protected ? (
                          <span className="inline-flex items-center gap-1 font-mono text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                            <ShieldCheck className="h-3.5 w-3.5" />
                            {ep.protection_state ?? '已确认保护'}
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 font-mono text-[11px] font-medium text-amber-600 dark:text-amber-400">
                            <ShieldAlert className="h-3.5 w-3.5" />
                            {ep.protection_state ?? '保护待核实'}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Issued Time */}
                    <div className="hidden sm:block">
                      <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">
                        发出时间
                      </div>
                      <div className="flex items-center gap-1 mt-0.5 text-text-secondary font-mono">
                        <Clock className="h-3 w-3 text-text-muted" />
                        <span>{ep.issued_at_formatted}</span>
                      </div>
                    </div>

                    {/* Financial return */}
                    {ep.net_r_formatted && ep.net_r_formatted !== '--' && (
                      <div>
                        <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">
                          已核实净 R
                        </div>
                        <div className="font-mono font-bold mt-0.5 text-xs text-text-primary">
                          {ep.net_r_formatted}
                        </div>
                      </div>
                    )}

                    {/* Action button */}
                    <div className="w-full sm:w-auto flex justify-end mt-1.5 sm:mt-0">
                      <button
                        type="button"
                        onClick={() => onSelectEpisode(ep)}
                        className="w-full sm:w-auto inline-flex items-center justify-center gap-1 rounded-md border border-border bg-surface px-3 py-1.5 text-xs font-semibold text-text-primary hover:border-brand hover:text-brand hover:bg-surface-elevated transition-colors shadow-2xs cursor-pointer"
                      >
                        <span>查看交易因果</span>
                        <ChevronRight className="h-3.5 w-3.5 text-text-muted group-hover:text-brand" />
                      </button>
                    </div>
                  </div>
                </div>

                {/* Manual Takeover Warning / Notice Strip */}
                {isManual && (
                  <div className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/5 p-2.5 text-xs text-amber-700 dark:text-amber-300 break-words">
                    <div className="font-semibold flex items-center gap-1.5">
                      <AlertTriangle className="h-3.5 w-3.5 flex-none text-amber-500" />
                      <span>整笔已转人工管理 · 外部干预已触发永久接管</span>
                    </div>
                    <p className="mt-0.5 text-[11px] opacity-90 leading-relaxed break-words">
                      既有挂单是否有效以交易所最新订单事实为准；程序不再自动退出或修改保护。
                      {ep.manual_risk_reason && (
                        <span className="block mt-0.5 text-rose-600 dark:text-rose-400 font-mono break-all">
                          新增开仓受限原因：{ep.manual_risk_reason}
                        </span>
                      )}
                    </p>
                  </div>
                )}

                {isReviewRequired && (
                  <div className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/5 p-2.5 text-xs text-amber-700 dark:text-amber-300">
                    <div className="font-semibold flex items-center gap-1.5">
                      <AlertTriangle className="h-3.5 w-3.5 flex-none text-amber-500" />
                      <span>接管待核实 · 自动处置已暂停</span>
                    </div>
                    <p className="mt-0.5 text-[11px] opacity-90 leading-relaxed">
                      订单或持仓事实待核实，程序已暂停该笔自动处置；以交易所最新对账为准。
                    </p>
                  </div>
                )}

                {/* Attention flags if any */}
                {Boolean(ep.attention_items && ep.attention_items.length > 0) && (
                  <div className="mt-2.5 flex items-center gap-1.5 rounded-md bg-amber-500/10 text-amber-600 dark:text-amber-400 px-2.5 py-1 text-[11px] border border-amber-500/20 font-mono">
                    <AlertTriangle className="h-3 w-3 flex-none" />
                    <span>关注项：{ep.attention_items!.join(' · ')}</span>
                  </div>
                )}
              </div>
            );
          })}

          {unloadedActiveCount > 0 && (
            <div className="mt-3 flex items-center justify-between rounded-md border border-border bg-surface-subtle p-3 text-xs text-text-secondary font-sans">
              <span>
                另有 <strong className="font-mono text-text-primary">{unloadedActiveCount}</strong> 笔在管持仓未在首页展示 (受首屏 100 笔限制，遵循分页契约)
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
