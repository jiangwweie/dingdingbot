import React from 'react';
import type { TradeEpisodeSummary } from '../../types/overview';
import { Shield, ArrowUpRight, ArrowDownRight, Clock, ChevronRight } from 'lucide-react';

interface ActiveEpisodesSectionProps {
  episodes: TradeEpisodeSummary[];
  onSelectEpisode: (episode: TradeEpisodeSummary) => void;
}

export const ActiveEpisodesSection: React.FC<ActiveEpisodesSectionProps> = ({
  episodes,
  onSelectEpisode,
}) => {
  return (
    <div className="rounded-lg border border-border bg-surface p-4 shadow-sm">
      <div className="flex items-center justify-between pb-3 border-b border-border">
        <div className="flex items-center gap-2">
          <h3 className="text-xs font-bold uppercase tracking-wider text-text-primary">
            当前在管交易 (Active Trade Episodes)
          </h3>
          <span className="inline-flex items-center rounded-full bg-brand/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-brand">
            {episodes.length} 笔在管
          </span>
        </div>
        <span className="text-[11px] text-text-muted">
          严格遵循独立 Netting Domain · 均已安装交易所保护单
        </span>
      </div>

      {episodes.length === 0 ? (
        <div className="py-8 text-center">
          <p className="text-xs font-medium text-text-secondary">
            当前市场无活动持仓
          </p>
          <p className="mt-1 text-[11px] text-text-muted">
            5 个生产策略组正在 Observation 链路中持续扫描行情机会
          </p>
        </div>
      ) : (
        <div className="mt-3 space-y-2.5">
          {episodes.map((ep) => {
            const isLong = ep.side === 'long';
            const isPnlPositive = ep.pnl_r >= 0;

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

                {/* 2. 入场与盈亏 */}
                <div className="flex items-center gap-6 text-xs">
                  <div>
                    <div className="text-[10px] text-text-muted uppercase">入场 / 现价</div>
                    <div className="font-mono font-medium text-text-primary">
                      {ep.entry_price} <span className="text-text-muted">→</span> {ep.current_price}
                    </div>
                  </div>

                  <div>
                    <div className="text-[10px] text-text-muted uppercase">当前浮盈 (R / $)</div>
                    <div className="flex items-baseline gap-1 font-mono font-bold">
                      <span
                        className={
                          isPnlPositive
                            ? 'text-emerald-600 dark:text-emerald-400'
                            : 'text-rose-600 dark:text-rose-400'
                        }
                      >
                        {isPnlPositive ? `+${ep.pnl_r.toFixed(2)}` : ep.pnl_r.toFixed(2)} R
                      </span>
                      <span className="text-[11px] font-normal text-text-muted">
                        ({isPnlPositive ? `+$${ep.pnl_usd.toFixed(2)}` : `-$${Math.abs(ep.pnl_usd).toFixed(2)}`})
                      </span>
                    </div>
                  </div>

                  {/* 3. 保护状态 */}
                  <div className="hidden md:block">
                    <div className="text-[10px] text-text-muted uppercase">保护机制</div>
                    <div className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                      <Shield className="h-3 w-3" />
                      <span>{ep.protection_label}</span>
                      <span className="font-mono text-text-muted">({ep.stop_price})</span>
                    </div>
                  </div>

                  {/* 4. 持仓时长与因果详情按钮 */}
                  <div className="flex items-center gap-3">
                    <div className="hidden lg:flex items-center gap-1 text-[11px] text-text-muted">
                      <Clock className="h-3 w-3" />
                      <span className="font-mono">{ep.duration_formatted}</span>
                    </div>

                    <button
                      type="button"
                      onClick={() => onSelectEpisode(ep)}
                      className="inline-flex items-center gap-1 rounded border border-border bg-surface px-2.5 py-1 text-xs font-medium text-text-primary hover:border-brand hover:text-brand transition-colors"
                    >
                      <span>查看交易因果</span>
                      <ChevronRight className="h-3 w-3 text-text-muted group-hover:text-brand" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
