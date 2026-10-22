import { formatReviewExitReason } from '../../mapping/reviewMapping.ts';
import React from 'react';
import { useStrategyTicketsData } from '../../hooks/useStrategiesData.ts';
import type { StrategyTicketListItem, StrategyTicketExitPath } from '../../types/strategies.ts';
import { formatStrategyMoneyMetric } from '../../mapping/strategyMapping.ts';
import { cleanSymbol } from '../../utils/symbol.ts';
import { ApiError } from '../../api/errors.ts';
import {
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw,
  Clock,
  ChevronRight,
  AlertCircle,
  Info,
} from 'lucide-react';

const getErrorMessage = (err: unknown): string => {
  if (err instanceof ApiError) {
    return `[HTTP ${err.status} ${err.code}] ${err.message}`;
  }
  if (err instanceof Error) {
    return err.message;
  }
  return '网络或服务异常，未能获取 Ticket 记录';
};

interface StrategyTicketsTabProps {
  strategyVersionId: string;
  onSelectTicket: (ticket: StrategyTicketListItem) => void;
  from_ms?: number;
  to_ms?: number;
  scope?: 'natural' | 'all';
  exit_path?: StrategyTicketExitPath | null;
  onScopeChange?: (scope: 'natural' | 'all') => void;
  onExitPathChange?: (exitPath: StrategyTicketExitPath | null) => void;
  onTicketFiltersChange?: (filters: { scope?: 'natural' | 'all'; exit_path?: StrategyTicketExitPath | null }) => void;
}

export const StrategyTicketsTab: React.FC<StrategyTicketsTabProps> = ({
  strategyVersionId,
  onSelectTicket,
  from_ms,
  to_ms,
  scope: externalScope,
  exit_path: externalExitPath,
  onScopeChange,
  onExitPathChange,
  onTicketFiltersChange,
}) => {
  const {
    items,
    excludedNonTerminalCount,
    scope,
    setScope,
    exitPath,
    setExitPath,
    isLoading,
    isFetchingNextPage,
    hasNextPage,
    isFetchNextPageError,
    isError,
    error,
    fetchNextPage,
    refetch,
  } = useStrategyTicketsData(strategyVersionId, {
    from_ms,
    to_ms,
    scope: externalScope,
    exit_path: externalExitPath,
  });

  // P1-3: Auto switch scope when selecting controlled_exit, or reset exitPath when selecting natural
  const handleScopeChange = (newScope: 'natural' | 'all') => {
    if (newScope === 'natural' && exitPath === 'controlled_exit') {
      setExitPath(null);
      if (onTicketFiltersChange) {
        onTicketFiltersChange({ scope: newScope, exit_path: null });
        return;
      }
      onExitPathChange?.(null);
    }
    setScope(newScope);
    onScopeChange?.(newScope);
  };

  const handleExitPathChange = (path: StrategyTicketExitPath | null) => {
    if (path === 'controlled_exit' && scope === 'natural') {
      setScope('all');
      setExitPath(path);
      if (onTicketFiltersChange) {
        onTicketFiltersChange({ scope: 'all', exit_path: path });
        return;
      }
      onScopeChange?.('all');
      onExitPathChange?.(path);
      return;
    }
    setExitPath(path);
    onExitPathChange?.(path);
  };

  return (
    <div className="space-y-4">
      {/* 1. Filter Switcher */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface p-3">
        {/* Scope Switcher: Natural vs All */}
        <div className="flex items-center gap-1 rounded-md border border-border bg-surface-subtle p-1 text-xs">
          <button
            type="button"
            onClick={() => handleScopeChange('natural')}
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
            onClick={() => handleScopeChange('all')}
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
              onClick={() => handleExitPathChange(item.id as StrategyTicketExitPath | null)}
              title={scope === 'natural' && item.id === 'controlled_exit' ? '选择受控退出将自动切换至全部版本 (All)' : undefined}
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

      {/* P1-2: Natural Scope Exclusion Banner */}
      {scope === 'natural' && excludedNonTerminalCount > 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-blue-500/30 bg-blue-500/10 p-3 text-xs text-blue-700 dark:text-blue-300">
          <Info className="h-4 w-4 shrink-0 text-blue-600 dark:text-blue-400" />
          <div>
            已排除 <strong className="font-semibold font-mono">{excludedNonTerminalCount}</strong> 笔未达终态在途记录（not_terminal），未计入自然终态列表。切换至“全部包含受控 (All)”可查看。
          </div>
        </div>
      )}

      {/* 2. Tickets Content */}
      {isLoading ? (
        <div className="py-16 text-center">
          <div className="inline-block h-6 w-6 border-2 border-brand/30 border-t-brand rounded-full animate-spin mb-2" />
          <p className="text-xs text-text-secondary">正在读取版本 Ticket 证据...</p>
        </div>
      ) : isError && !isFetchNextPageError && items.length === 0 ? (
        /* P1-1: Explicit Error Card when initial load fails */
        <div className="rounded-lg border border-danger/30 bg-surface p-8 text-center text-xs">
          <AlertCircle className="mx-auto h-8 w-8 text-danger mb-2" />
          <p className="font-semibold text-text-primary">Ticket 证据读取失败</p>
          <p className="mt-1 text-[11px] text-text-secondary font-mono">
            {getErrorMessage(error)}
          </p>
          <button
            type="button"
            onClick={() => refetch()}
            className="mt-4 inline-flex items-center gap-1.5 rounded bg-brand px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand/90 transition-colors shadow-xs cursor-pointer"
          >
            <RefreshCw className="h-3 w-3" />
            <span>重试加载</span>
          </button>
        </div>
      ) : items.length === 0 ? (
        hasNextPage ? (
          /* P1-2: Server has more pages even though current loaded page has 0 filtered terminal tickets */
          <div className="rounded-lg border border-border bg-surface p-6 text-center text-xs shadow-xs">
            <Clock className="mx-auto h-8 w-8 text-brand/70 mb-2" />
            <p className="font-semibold text-text-primary">当前已加载范围无已达成自然终态记录</p>
            <p className="mt-1 text-[11px] text-text-secondary">
              {scope === 'natural' && excludedNonTerminalCount > 0
                ? `当前已排除 ${excludedNonTerminalCount} 笔在途未达终态记录。服务端仍有后续分页数据，可继续加载下一页证据。`
                : '当前已加载数据未匹配筛选条件，但服务端仍有更多记录，可继续加载。'}
            </p>
            <div className="mt-4 flex items-center justify-center gap-2">
              <button
                type="button"
                onClick={() => fetchNextPage()}
                disabled={isFetchingNextPage}
                className="inline-flex items-center gap-1.5 rounded bg-brand px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-brand/90 transition-colors shadow-xs disabled:opacity-50 cursor-pointer"
              >
                <RefreshCw className={`h-3 w-3 ${isFetchingNextPage ? 'animate-spin' : ''}`} />
                <span>{isFetchingNextPage ? '正在加载...' : '加载更多 Ticket (Next Cursor)'}</span>
              </button>
            </div>
            {isFetchNextPageError && (
              <div className="mt-3 p-2.5 bg-danger/10 text-danger text-[11px] rounded border border-danger/20 flex items-center justify-between gap-2 text-left font-mono">
                <div className="flex items-center gap-1.5">
                  <AlertCircle className="h-3.5 w-3.5 shrink-0 font-sans" />
                  <span>加载下一页失败: {getErrorMessage(error)}</span>
                </div>
                <button
                  type="button"
                  onClick={() => fetchNextPage()}
                  disabled={isFetchingNextPage}
                  className="rounded border border-danger/30 bg-surface px-2 py-0.5 text-[11px] font-semibold text-danger hover:bg-danger/10 transition-colors cursor-pointer"
                >
                  重试
                </button>
              </div>
            )}
          </div>
        ) : (
          /* True Terminal Empty State (no items and no next page) */
          <div className="rounded-lg border border-border bg-surface p-8 text-center text-xs text-text-muted">
            <Clock className="mx-auto h-8 w-8 text-text-muted/50 mb-2" />
            <p className="font-semibold text-text-secondary">当前筛选条件下无 Ticket 记录</p>
            <p className="mt-1 text-[11px]">
              {scope === 'natural' && excludedNonTerminalCount > 0
                ? `已排除 ${excludedNonTerminalCount} 笔在途未达终态记录，当前查询范围内无已达成终态记录。`
                : '请调整退出路径或范围筛选条件。'}
            </p>
          </div>
        )
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
                  // P2-1: Exact Decimal formatting for MoneyMetric
                  const pnlMetric = formatStrategyMoneyMetric(ticket.net_pnl, '—');
                  const rMetric = formatStrategyMoneyMetric(ticket.net_r, '—');

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
                            : '未达终态 (在途)'}
                        </span>
                      </td>

                      {/* Net PnL (Exact Decimal) */}
                      <td className="px-3 py-2.5 font-mono text-right font-bold tabular-nums whitespace-nowrap">
                        <span
                          className={
                            pnlMetric.isPositive === true
                              ? 'text-emerald-600 dark:text-emerald-400'
                              : pnlMetric.isPositive === false
                              ? 'text-rose-600 dark:text-rose-400'
                              : 'text-text-muted font-normal'
                          }
                        >
                          {pnlMetric.formatted}
                        </span>
                      </td>

                      {/* Net R (Exact Decimal) */}
                      <td className="px-3 py-2.5 font-mono text-right font-bold tabular-nums whitespace-nowrap">
                        <span
                          className={
                            rMetric.isPositive === true
                              ? 'text-emerald-600 dark:text-emerald-400'
                              : rMetric.isPositive === false
                              ? 'text-rose-600 dark:text-rose-400'
                              : 'text-text-muted font-normal'
                          }
                        >
                          {rMetric.formatted}
                        </span>
                      </td>

                      {/* Exit Reason */}
                      <td className="px-3 py-2.5 text-[11px] text-text-secondary whitespace-nowrap">
                        {ticket.exit_attribution?.label ?? formatReviewExitReason(ticket.exit_reason ?? ticket.exit_reason_unavailable_reason).label}
                      </td>

                      {/* Issued At */}
                      <td className="px-3 py-2.5 font-mono text-[11px] text-text-muted whitespace-nowrap">
                        {new Date(ticket.issued_at_ms).toLocaleString('zh-CN', {
                          timeZone: 'Asia/Shanghai',
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
              <span className="text-text-muted">
                已加载前 {items.length} 笔 Ticket 证据
                {scope === 'natural' && excludedNonTerminalCount > 0
                  ? ` (已排除 ${excludedNonTerminalCount} 笔在途记录)`
                  : ''}
              </span>
              <button
                type="button"
                onClick={() => fetchNextPage()}
                disabled={isFetchingNextPage}
                className="inline-flex items-center gap-1.5 rounded border border-border bg-surface px-3 py-1.5 text-xs font-semibold text-text-primary hover:bg-surface-elevated transition-colors shadow-xs disabled:opacity-50 cursor-pointer"
              >
                <RefreshCw className={`h-3 w-3 ${isFetchingNextPage ? 'animate-spin text-brand' : ''}`} />
                <span>{isFetchingNextPage ? '正在加载...' : '加载更多 Ticket (Next Cursor)'}</span>
              </button>
            </div>
          ) : (
            <div className="border-t border-border py-2 text-center text-[11px] text-text-muted bg-surface-subtle">
              已加载全部 Ticket 记录 (共 {items.length} 笔已达成终态
              {scope === 'natural' && excludedNonTerminalCount > 0
                ? `，已排除 ${excludedNonTerminalCount} 笔在途记录`
                : ''}
              )
            </div>
          )}

          {/* P1-1: Next Page Fetch Error Bar with Retry */}
          {isFetchNextPageError && (
            <div className="p-3 bg-danger/10 text-danger text-xs border-t border-danger/20 flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 font-mono">
                <AlertCircle className="h-4 w-4 shrink-0 font-sans" />
                <span>加载下一页 Ticket 失败: {getErrorMessage(error)}</span>
              </div>
              <button
                type="button"
                onClick={() => fetchNextPage()}
                disabled={isFetchingNextPage}
                className="inline-flex items-center gap-1 rounded border border-danger/30 bg-surface px-2.5 py-1 text-xs font-semibold text-danger hover:bg-danger/10 transition-colors shadow-xs cursor-pointer"
              >
                <RefreshCw className={`h-3 w-3 ${isFetchingNextPage ? 'animate-spin' : ''}`} />
                <span>重试下一页</span>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
