import React from 'react';
import type { TradeEpisode } from '../../types/trades';
import {
  ArrowUpRight,
  ArrowDownRight,
  CheckCircle2,
  ChevronRight,
  Clock,
} from 'lucide-react';

interface CompletedTradeTableProps {
  episodes: TradeEpisode[];
  onSelectEpisode: (episode: TradeEpisode) => void;
}

export const CompletedTradeTable: React.FC<CompletedTradeTableProps> = ({
  episodes,
  onSelectEpisode,
}) => {
  if (episodes.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-surface p-8 text-center text-xs text-text-muted">
        <Clock className="mx-auto h-8 w-8 text-text-muted/50 mb-2" />
        <p className="font-semibold text-text-secondary">暂无已结束交易记录</p>
        <p className="mt-1 text-[11px]">当前过滤条件下未查询到已终结的交易事实。</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-xs">
      <div className="overflow-x-auto">
        <table data-testid="completed-trades-table" className="w-full text-left text-xs font-sans">
          <thead>
            <tr className="border-b border-border bg-surface-subtle font-mono text-[11px] uppercase tracking-wider text-text-muted">
              <th scope="col" className="px-4 py-3 font-semibold">
                策略与标的
              </th>
              <th scope="col" className="px-3 py-3 font-semibold">
                方向
              </th>
              <th scope="col" className="px-3 py-3 font-semibold">
                结果
              </th>
              <th scope="col" className="px-3 py-3 font-semibold text-right">
                净收益 (Net PnL)
              </th>
              <th scope="col" className="px-3 py-3 font-semibold text-right">
                回报 (Net R)
              </th>
              <th scope="col" className="px-4 py-3 font-semibold">
                退出原因
              </th>
              <th scope="col" className="px-3 py-3 font-semibold">
                生命周期
              </th>
              <th scope="col" className="px-3 py-3 font-semibold">
                耗时
              </th>
              <th scope="col" className="px-4 py-3 font-semibold">
                结清时间
              </th>
              <th scope="col" className="px-3 py-3 font-semibold text-right">
                因果追溯
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border font-sans">
            {episodes.map((ep) => {
              const isLong = ep.side === 'long';
              const isWin = ep.outcome === 'win';
              const isLoss = ep.outcome === 'loss';

              return (
                <tr
                  key={ep.ticket_id}
                  data-ticket-id={ep.ticket_id}
                  className="group hover:bg-surface-elevated transition-colors cursor-pointer"
                  onClick={() => onSelectEpisode(ep)}
                >
                  {/* 1. Strategy & Symbol */}
                  <td className="px-4 py-3">
                    <div className="flex flex-col">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono font-bold text-text-primary">
                          {ep.symbol}
                        </span>
                        <span className="rounded bg-brand/10 px-1.5 py-0.2 font-mono text-[10px] font-semibold text-brand">
                          {ep.strategy_id}
                        </span>
                      </div>
                      <span className="text-[11px] text-text-muted mt-0.5">
                        {ep.strategy_name_zh}
                      </span>
                    </div>
                  </td>

                  {/* 2. Side */}
                  <td className="px-3 py-3 whitespace-nowrap">
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
                          做多
                        </>
                      ) : (
                        <>
                          <ArrowDownRight className="h-3 w-3" />
                          做空
                        </>
                      )}
                    </span>
                  </td>

                  {/* 3. Outcome */}
                  <td className="px-3 py-3 whitespace-nowrap">
                    <span
                      className={`inline-flex items-center rounded px-2 py-0.5 font-mono text-[11px] font-semibold ${
                        isWin
                          ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400'
                          : isLoss
                          ? 'bg-rose-500/15 text-rose-700 dark:text-rose-400'
                          : 'bg-surface-subtle text-text-muted border border-border'
                      }`}
                    >
                      {ep.outcome_zh}
                    </span>
                  </td>

                  {/* 4. Net PnL */}
                  <td className="px-3 py-3 font-mono text-right font-bold tabular-nums whitespace-nowrap">
                    <span
                      className={
                        ep.net_pnl_is_positive === true
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : ep.net_pnl_is_positive === false
                          ? 'text-rose-600 dark:text-rose-400'
                          : 'text-text-muted font-normal'
                      }
                    >
                      {ep.net_pnl_formatted}
                    </span>
                    {ep.net_pnl_is_gross && <div className="text-[10px] font-normal text-text-muted" title="净收益仍未知；此处为未扣手续费和资金费的毛收益">毛收益 · 未扣手续费与资金费</div>}
                  </td>

                  {/* 5. Net R */}
                  <td className="px-3 py-3 font-mono text-right font-bold tabular-nums whitespace-nowrap">
                    <span
                      className={
                        ep.net_r_is_positive === true
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : ep.net_r_is_positive === false
                          ? 'text-rose-600 dark:text-rose-400'
                          : 'text-text-muted font-normal'
                      }
                    >
                      {ep.net_r_formatted}
                    </span>
                  </td>

                  {/* 6. Exit Reason */}
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span
                      className={`inline-flex items-center gap-1 font-mono text-[11px] ${
                        ep.exit_reason
                          ? 'text-text-secondary font-medium'
                          : 'text-text-muted'
                      }`}
                    >
                      {ep.exit_reason_zh}
                    </span>
                  </td>

                  {/* 7. Lifecycle */}
                  <td className="px-3 py-3 whitespace-nowrap">
                    <div className="flex items-center gap-1.5">
                      <CheckCircle2 className="h-3.5 w-3.5 text-status-green flex-none" />
                      <span className="font-semibold text-text-primary text-[11px]">
                        {ep.lifecycle_stage_zh}
                      </span>
                      <span className="font-mono text-[10px] text-text-muted">
                        ({ep.completed_stage_count}/{ep.total_stage_count})
                      </span>
                    </div>
                  </td>

                  {/* 8. Duration */}
                  <td className="px-3 py-3 font-mono text-[11px] text-text-secondary whitespace-nowrap">
                    {ep.duration_formatted}
                  </td>

                  {/* 9. Closed At */}
                  <td className="px-4 py-3 font-mono text-[11px] text-text-muted whitespace-nowrap">
                    {ep.closed_at_formatted ?? '—'}
                  </td>

                  {/* 10. Action Button */}
                  <td className="px-3 py-3 text-right whitespace-nowrap">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectEpisode(ep);
                      }}
                      className="inline-flex items-center gap-1 rounded border border-border bg-surface px-2.5 py-1 text-[11px] font-medium text-text-primary shadow-xs transition-colors hover:border-brand hover:text-brand"
                    >
                      <span>因果详情</span>
                      <ChevronRight className="h-3 w-3 text-text-muted group-hover:text-brand" />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
