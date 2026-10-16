import React from 'react';
import type { TradeEpisodeSummary } from '../../types/overview';
import {
  Shield,
  ArrowUpRight,
  ArrowDownRight,
  Clock,
  ChevronRight,
  AlertTriangle,
  AlertCircle,
  RefreshCw,
  Loader2,
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
    <div className="rounded-lg border border-border bg-surface p-4 shadow-sm">
      <div className="flex items-center justify-between pb-3 border-b border-border">
        <div className="flex items-center gap-2">
          <h3 className="text-xs font-bold uppercase tracking-wider text-text-primary">
            当前在管交易 (Active Trade Episodes)
          </h3>
          {isLoading ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-surface-subtle px-2 py-0.5 font-mono text-[11px] text-text-muted border border-border">
              <Loader2 className="h-3 w-3 animate-spin text-brand" />
              读取中...
            </span>
          ) : isError ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-danger/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-danger border border-danger/20">
              <AlertCircle className="h-3 w-3" />
              读取失败
            </span>
          ) : (
            <span className="inline-flex items-center rounded-full bg-brand/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-brand">
              {episodes.length} 笔在管
            </span>
          )}
        </div>
        <span className="text-[11px] text-text-muted">
          来自生产 Ticket 账本事实 · 严格遵循独立 Netting Domain
        </span>
      </div>

      {isLoading ? (
        <div className="py-8 text-center">
          <div className="inline-flex items-center justify-center gap-2 text-xs text-text-muted">
            <Loader2 className="h-4 w-4 animate-spin text-brand" />
            <span>正在读取在管持仓事实 (/api/owner/v1/tickets)...</span>
          </div>
        </div>
      ) : isError ? (
        <div className="my-3 flex items-center justify-between rounded border border-danger/30 bg-danger/5 p-3.5 text-xs">
          <div className="flex items-center gap-2 text-danger">
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
              className="inline-flex items-center gap-1 rounded border border-danger/30 bg-surface px-2.5 py-1 text-xs font-medium text-danger hover:bg-danger/10 transition-colors"
            >
              <RefreshCw className="h-3 w-3" />
              <span>重试</span>
            </button>
          )}
        </div>
      ) : episodes.length === 0 ? (
        <div className="py-8 text-center">
          <p className="text-xs font-medium text-text-secondary">
            当前市场无活动持仓
          </p>
          <p className="mt-1 text-[11px] text-text-muted">
            生产策略组正在 Observation 链路中持续扫描行情机会
          </p>
        </div>
      ) : (
        <div className="mt-3 space-y-2.5">
          {episodes.map((ep) => {
            const isLong = ep.side === 'long';

            return (
              <div
                key={ep.ticket_id}
                className="group flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded border border-border bg-surface-subtle p-3 hover:border-brand/40 hover:bg-surface-elevated transition-all"
              >
                {/* 1. 策略与标的方向 */}
                <div className="flex items-center gap-3">
                  <div
                    className={`flex h-8 w-8 flex-none items-center justify-center rounded ${
                      isLong
                        ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                        : 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20'
                    }`}
                  >
                    {isLong ? (
                      <ArrowUpRight className="h-4 w-4" />
                    ) : (
                      <ArrowDownRight className="h-4 w-4" />
                    )}
                  </div>

                  <div>
                    <div className="flex items-center gap-1.5">
                      <span className="font-mono text-xs font-bold text-text-primary">
                        {ep.symbol}
                      </span>
                      <span
                        className={`font-mono text-[10px] font-semibold px-1.5 py-0.2 rounded uppercase ${
                          isLong
                            ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                            : 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
                        }`}
                      >
                        {isLong ? '做多 (LONG)' : '做空 (SHORT)'}
                      </span>
                      <span className="font-mono text-[10px] text-text-muted">
                        #{ep.ticket_id.slice(-8)}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5 mt-0.5 text-[11px] text-text-muted">
                      <span className="font-mono text-brand font-medium">
                        {ep.strategy_id}
                      </span>
                      <span>·</span>
                      <span>{ep.strategy_name_zh}</span>
                    </div>
                  </div>
                </div>

                {/* 2. 真实生命周期进度与状态 */}
                <div className="flex flex-wrap items-center gap-4 text-xs">
                  <div>
                    <div className="text-[10px] text-text-muted uppercase">当前生命周期</div>
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

                  <div>
                    <div className="text-[10px] text-text-muted uppercase">发出时间</div>
                    <div className="flex items-center gap-1 mt-0.5 text-text-secondary">
                      <Clock className="h-3 w-3 text-text-muted" />
                      <span className="font-mono">{ep.issued_at_formatted}</span>
                    </div>
                  </div>

                  {ep.net_r_formatted && ep.net_r_formatted !== '--' && (
                    <div>
                      <div className="text-[10px] text-text-muted uppercase">浮动盈亏</div>
                      <div className="font-mono font-bold mt-0.5 text-xs text-text-primary">
                        {ep.net_r_formatted}
                      </div>
                    </div>
                  )}

                  {Boolean(ep.attention_items && ep.attention_items.length > 0) && (
                    <div className="flex items-center gap-1 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400 px-2 py-0.5 text-[11px] border border-amber-500/20">
                      <AlertTriangle className="h-3 w-3" />
                      <span>{ep.attention_items!.join(', ')}</span>
                    </div>
                  )}

                  {/* 3. 查看交易因果全链路按钮 */}
                  <div>
                    <button
                      type="button"
                      onClick={() => onSelectEpisode(ep)}
                      className="inline-flex items-center gap-1 rounded border border-border bg-surface px-2.5 py-1.5 text-xs font-medium text-text-primary hover:border-brand hover:text-brand transition-colors shadow-xs"
                    >
                      <span>查看交易因果</span>
                      <ChevronRight className="h-3.5 w-3.5 text-text-muted group-hover:text-brand" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
          {unloadedActiveCount > 0 && (
            <div className="mt-2.5 flex items-center justify-between rounded border border-border bg-surface-subtle p-3 text-xs text-text-secondary font-sans">
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
