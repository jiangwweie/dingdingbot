import React from 'react';
import { useStrategyTicketsData } from '../../hooks/useStrategiesData.ts';
import type { StrategyTicketListItem, StrategyTicketExitPath } from '../../types/strategies.ts';
import { cleanSymbol } from '../../utils/symbol.ts';
import {
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw,
  Clock,
  ChevronRight,
  AlertCircle,
} from 'lucide-react';

interface StrategyTicketsTabProps {
  strategyVersionId: string;
  onSelectTicket: (ticket: StrategyTicketListItem) => void;
}

export const StrategyTicketsTab: React.FC<StrategyTicketsTabProps> = ({
  strategyVersionId,
  onSelectTicket,
}) => {
  const {
    items,
    scope,
    setScope,
    exitPath,
    setExitPath,
    isLoading,
    isFetchingNextPage,
    hasNextPage,
    isFetchNextPageError,
    error,
    fetchNextPage,
  } = useStrategyTicketsData(strategyVersionId);

  return (
    <div className="space-y-4">
      {/* 1. Filter Switcher */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface p-3">
        {/* Scope Switcher: Natural vs All */}
        <div className="flex items-center gap-1 rounded-md border border-border bg-surface-subtle p-1 text-xs">
          <button
            type="button"
            onClick={() => setScope('natural')}
            className={`rounded px-2.5 py-1 font-mono font-medium transition-colors ${
              scope === 'natural'
                ? 'bg-surface text-brand font-bold shadow-xs border border-border'
                : 'text-text-muted hover:text-text-primary'
            }`}
          >
            自然终态 (Natural)
          </button>
          <button
            type="button"
            onClick={() => setScope('all')}
            className={`rounded px-2.5 py-1 font-mono font-medium transition-colors ${
              scope === 'all'
                ? 'bg-surface text-brand font-bold shadow-xs border border-border'
                : 'text-text-muted hover:text-text-primary'
            }`}
          >
            全部包含受控 (All)
          </button>
        </div>

        {/* Path Filter Pills */}
        <div className="flex flex-wrap items-center gap-1.5 text-xs font-mono">
          <span className="text-[11px] text-text-muted mr-1 font-sans">退出路径:</span>
          {(
            [
              { id: null, label: '全部' },
              { id: 'tp1_reached', label: '达到 TP1' },
              { id: 'tp1_not_reached', label: '未达 TP1' },
              { id: 'controlled_exit', label: '受控退出' },
            ] as const
          ).map((item) => (
            <button
              key={item.label}
              type="button"
              onClick={() => setExitPath(item.id as StrategyTicketExitPath | null)}
              className={`rounded px-2.5 py-1 text-xs transition-colors ${
                exitPath === item.id
                  ? 'bg-brand/10 text-brand font-bold border border-brand/30'
                  : 'bg-surface-subtle text-text-muted hover:text-text-primary border border-border'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {/* 2. Tickets Table */}
      {isLoading ? (
        <div className="py-16 text-center">
          <div className="inline-block h-6 w-6 border-2 border-brand/30 border-t-brand rounded-full animate-spin mb-2" />
          <p className="text-xs text-text-secondary">正在读取版本 Ticket 证据...</p>
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-lg border border-border bg-surface p-8 text-center text-xs text-text-muted">
          <Clock className="mx-auto h-8 w-8 text-text-muted/50 mb-2" />
          <p className="font-semibold text-text-secondary">当前筛选条件下无 Ticket 记录</p>
          <p className="mt-1 text-[11px]">请调整退出路径或范围筛选条件。</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-xs">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-sans">
              <thead>
                <tr className="border-b border-border bg-surface-subtle font-mono text-[11px] uppercase tracking-wider text-text-muted">
                  <th scope="col" className="px-4 py-2.5 font-semibold">标的 / 方向</th>
                  <th scope="col" className="px-3 py-2.5 font-semibold">路径分类</th>
                  <th scope="col" className="px-3 py-2.5 font-semibold text-right">净收益 (PnL)</th>
                  <th scope="col" className="px-3 py-2.5 font-semibold text-right">净回报 (R)</th>
                  <th scope="col" className="px-3 py-2.5 font-semibold">退出原因</th>
                  <th scope="col" className="px-3 py-2.5 font-semibold">发出时间</th>
                  <th scope="col" className="px-3 py-2.5 font-semibold text-right">因果追溯</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border font-sans">
                {items.map((ticket) => {
                  const isLong = ticket.position_side === 'long';
                  const symbolClean = cleanSymbol(ticket.exchange_instrument_id);
                  const pnlVal = ticket.net_pnl?.value;
                  const rVal = ticket.net_r?.value;
                  const hasPnl = pnlVal != null && !ticket.net_pnl?.unavailable_reason;
                  const isPnlPositive = hasPnl && Number(pnlVal) > 0;
                  const isPnlNegative = hasPnl && Number(pnlVal) < 0;

                  return (
                    <tr
                      key={ticket.ticket_id}
                      onClick={() => onSelectTicket(ticket)}
                      className="group hover:bg-surface-elevated transition-colors cursor-pointer"
                    >
                      {/* Symbol & Side */}
                      <td className="px-4 py-2.5 font-mono">
                        <div className="flex items-center gap-1.5">
                          <span className="font-bold text-text-primary">{symbolClean}</span>
                          <span
                            className={`inline-flex items-center gap-0.5 rounded px-1.5 py-0.2 text-[10px] font-semibold uppercase ${
                              isLong
                                ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                                : 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
                            }`}
                          >
                            {isLong ? <ArrowUpRight className="h-2.5 w-2.5" /> : <ArrowDownRight className="h-2.5 w-2.5" />}
                            {isLong ? '做多' : '做空'}
                          </span>
                        </div>
                        <div className="text-[10px] text-text-muted mt-0.5 truncate max-w-[140px]" title={ticket.ticket_id}>
                          {ticket.ticket_id}
                        </div>
                      </td>

                      {/* Path Evaluation */}
                      <td className="px-3 py-2.5 whitespace-nowrap font-mono">
                        <span
                          className={`inline-flex items-center rounded px-2 py-0.5 text-[10px] font-semibold ${
                            ticket.evaluation_path === 'tp1_reached'
                              ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400'
                              : ticket.evaluation_path === 'controlled_exit'
                              ? 'bg-amber-500/15 text-amber-700 dark:text-amber-400'
                              : 'bg-surface-subtle text-text-secondary border border-border'
                          }`}
                        >
                          {ticket.evaluation_path === 'tp1_reached'
                            ? '已达 TP1'
                            : ticket.evaluation_path === 'tp1_not_reached'
                            ? '未达 TP1'
                            : ticket.evaluation_path === 'controlled_exit'
                            ? '受控退出'
                            : '未平仓终态'}
                        </span>
                      </td>

                      {/* Net PnL */}
                      <td className="px-3 py-2.5 font-mono text-right font-bold tabular-nums whitespace-nowrap">
                        <span
                          className={
                            isPnlPositive
                              ? 'text-emerald-600 dark:text-emerald-400'
                              : isPnlNegative
                              ? 'text-rose-600 dark:text-rose-400'
                              : 'text-text-muted font-normal'
                          }
                        >
                          {hasPnl ? `${Number(pnlVal) > 0 ? '+' : ''}${Number(pnlVal).toFixed(2)} USDT` : '—'}
                        </span>
                      </td>

                      {/* Net R */}
                      <td className="px-3 py-2.5 font-mono text-right font-bold tabular-nums whitespace-nowrap">
                        <span
                          className={
                            isPnlPositive
                              ? 'text-emerald-600 dark:text-emerald-400'
                              : isPnlNegative
                              ? 'text-rose-600 dark:text-rose-400'
                              : 'text-text-muted font-normal'
                          }
                        >
                          {rVal != null && !ticket.net_r?.unavailable_reason
                            ? `${Number(rVal) > 0 ? '+' : ''}${Number(rVal).toFixed(2)} R`
                            : '—'}
                        </span>
                      </td>

                      {/* Exit Reason */}
                      <td className="px-3 py-2.5 text-[11px] text-text-secondary whitespace-nowrap">
                        {ticket.exit_reason || ticket.exit_reason_unavailable_reason || '—'}
                      </td>

                      {/* Issued At */}
                      <td className="px-3 py-2.5 font-mono text-[11px] text-text-muted whitespace-nowrap">
                        {new Date(ticket.issued_at_ms).toLocaleString('zh-CN', {
                          month: '2-digit',
                          day: '2-digit',
                          hour: '2-digit',
                          minute: '2-digit',
                          hour12: false,
                        })}
                      </td>

                      {/* Causality Link */}
                      <td className="px-3 py-2.5 text-right">
                        <button
                          type="button"
                          className="inline-flex items-center gap-1 text-[11px] font-semibold text-brand hover:underline"
                        >
                          <span>因果</span>
                          <ChevronRight className="h-3 w-3" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination / Load More Footer */}
          {hasNextPage ? (
            <div className="flex items-center justify-between border-t border-border bg-surface-subtle p-3 text-xs">
              <span className="text-text-muted">已加载前 {items.length} 笔 Ticket 证据</span>
              <button
                type="button"
                onClick={() => fetchNextPage()}
                disabled={isFetchingNextPage}
                className="inline-flex items-center gap-1.5 rounded border border-border bg-surface px-3 py-1.5 text-xs font-semibold text-text-primary hover:bg-surface-elevated transition-colors shadow-xs disabled:opacity-50"
              >
                <RefreshCw className={`h-3 w-3 ${isFetchingNextPage ? 'animate-spin text-brand' : ''}`} />
                <span>{isFetchingNextPage ? '正在加载...' : '加载更多 Ticket (Next Cursor)'}</span>
              </button>
            </div>
          ) : (
            <div className="border-t border-border py-2 text-center text-[11px] text-text-muted bg-surface-subtle">
              已加载全部 Ticket 记录 (共 {items.length} 笔)
            </div>
          )}

          {isFetchNextPageError && (
            <div className="p-3 bg-danger/10 text-danger text-xs text-center border-t border-danger/20 flex items-center justify-center gap-1.5">
              <AlertCircle className="h-4 w-4" />
              <span>加载下一页 Ticket 失败: {error instanceof Error ? error.message : '网络或服务异常'}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
