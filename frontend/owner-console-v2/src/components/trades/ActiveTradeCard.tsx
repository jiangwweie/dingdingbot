import React from 'react';
import type { TradeEpisode } from '../../types/trades';
import {
  Shield,
  ShieldAlert,
  ArrowUpRight,
  ArrowDownRight,
  Clock,
  ChevronRight,
  AlertTriangle,
  Layers,
} from 'lucide-react';

interface ActiveTradeCardProps {
  episode: TradeEpisode;
  onSelectEpisode: (episode: TradeEpisode) => void;
}

export const ActiveTradeCard: React.FC<ActiveTradeCardProps> = ({
  episode,
  onSelectEpisode,
}) => {
  const isLong = episode.side === 'long';

  return (
    <div
      data-testid="active-trade-card"
      data-ticket-id={episode.ticket_id}
      className="group relative flex flex-col justify-between rounded-lg border border-border bg-surface p-4 shadow-xs transition-all hover:border-brand/50 hover:shadow-sm"
    >
      <div>
        {/* Row 1: Strategy, Symbol, Direction & Protection */}
        <div className="flex items-center justify-between gap-2 border-b border-border/60 pb-3">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center rounded bg-brand/10 px-2 py-0.5 font-mono text-xs font-bold text-brand">
              {episode.strategy_id}
            </span>
            <span className="font-mono text-sm font-bold text-text-primary">
              {episode.symbol}
            </span>
            <span
              className={`inline-flex items-center gap-1 rounded px-2 py-0.5 font-mono text-[11px] font-semibold uppercase ${
                isLong
                  ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                  : 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
              }`}
            >
              {isLong ? (
                <>
                  <ArrowUpRight className="h-3 w-3" />
                  做多 (LONG)
                </>
              ) : (
                <>
                  <ArrowDownRight className="h-3 w-3" />
                  做空 (SHORT)
                </>
              )}
            </span>
          </div>

          {/* Protection Badge */}
          <div className="flex items-center gap-1.5">
            {episode.is_protected ? (
              <span className="inline-flex items-center gap-1 rounded border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-emerald-600 dark:text-emerald-400">
                <Shield className="h-3 w-3" />
                已安装保护
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-amber-600 dark:text-amber-400">
                <ShieldAlert className="h-3 w-3" />
                {episode.protection_state}
              </span>
            )}
          </div>
        </div>

        {/* Row 2: Lifecycle Stepper & Progress */}
        <div className="mt-3.5 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-1.5">
              <Layers className="h-3.5 w-3.5 text-brand" />
              <span className="text-[11px] text-text-secondary uppercase">当前生命周期:</span>
              <span className="font-semibold text-text-primary">
                {episode.lifecycle_stage_zh}
              </span>
            </div>
            <span className="font-mono text-[11px] text-text-muted">
              阶段进度: {episode.completed_stage_count}/{episode.total_stage_count}
            </span>
          </div>

          {/* Mini Stepper Track */}
          <div className="flex items-center gap-1 font-mono text-[10px]">
            <span
              className={`flex-1 rounded py-1 text-center font-medium ${
                episode.completed_stage_count >= 3
                  ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400'
                  : 'bg-brand/15 text-brand font-bold'
              }`}
            >
              入场 (Entry)
            </span>
            <span className="text-text-muted">→</span>
            <span
              className={`flex-1 rounded py-1 text-center font-medium ${
                episode.completed_stage_count >= 4
                  ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400'
                  : episode.completed_stage_count === 3
                  ? 'bg-brand/15 text-brand font-bold ring-1 ring-brand/30'
                  : 'bg-surface-subtle text-text-muted border border-border'
              }`}
            >
              保护 (Protection)
            </span>
            <span className="text-text-muted">→</span>
            <span
              className={`flex-1 rounded py-1 text-center font-medium ${
                episode.completed_stage_count >= 5
                  ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400'
                  : 'bg-surface-subtle text-text-muted border border-border'
              }`}
            >
              止盈 (TP/Runner)
            </span>
          </div>
        </div>

        {/* Row 3: Economics & Timing Facts */}
        <div className="mt-3.5 grid grid-cols-2 gap-2 rounded border border-border bg-surface-subtle p-2.5 text-xs font-mono">
          <div>
            <div className="text-[10px] text-text-muted uppercase">发出时间</div>
            <div className="flex items-center gap-1 mt-0.5 text-text-secondary font-medium">
              <Clock className="h-3 w-3 text-text-muted" />
              <span>{episode.issued_at_formatted}</span>
            </div>
          </div>

          <div>
            <div className="text-[10px] text-text-muted uppercase">在管时长</div>
            <div className="font-semibold text-text-primary mt-0.5">
              {episode.duration_formatted}
            </div>
          </div>
        </div>

        {/* Attention Items Alert if any */}
        {episode.attention_items.length > 0 && (
          <div className="mt-2.5 flex items-center gap-1.5 rounded border border-amber-500/20 bg-amber-500/10 px-2.5 py-1.5 text-xs text-amber-600 dark:text-amber-400">
            <AlertTriangle className="h-3.5 w-3.5 flex-none" />
            <span className="text-[11px] leading-tight">
              {episode.attention_items.join(' · ')}
            </span>
          </div>
        )}
      </div>

      {/* Row 4: Ticket ID & Action CTA */}
      <div className="mt-4 flex items-center justify-between border-t border-border/60 pt-3 text-xs">
        <span className="font-mono text-[11px] text-text-muted" title={episode.ticket_id}>
          Ticket: {episode.ticket_id.slice(0, 16)}...
        </span>

        <button
          type="button"
          onClick={() => onSelectEpisode(episode)}
          className="inline-flex items-center gap-1 rounded border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text-primary shadow-xs transition-colors hover:border-brand hover:text-brand"
        >
          <span>查看交易因果</span>
          <ChevronRight className="h-3.5 w-3.5 text-text-muted group-hover:text-brand" />
        </button>
      </div>
    </div>
  );
};
