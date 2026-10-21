import React from 'react';
import type { EnrichedStrategyVersion } from '../../types/strategies.ts';
import { ChevronRight, Layers } from 'lucide-react';

interface StrategyMatrixTableProps {
  strategies: EnrichedStrategyVersion[];
  onSelectStrategy: (strategy: EnrichedStrategyVersion) => void;
}

export const StrategyMatrixTable: React.FC<StrategyMatrixTableProps> = ({
  strategies,
  onSelectStrategy,
}) => {
  if (strategies.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-surface p-12 text-center text-xs text-text-muted">
        <Layers className="mx-auto h-8 w-8 text-text-muted/50 mb-2" />
        <p className="font-semibold text-text-secondary">当前视图无策略记录</p>
        <p className="mt-1 text-[11px]">未查询到匹配版本的策略事实。</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-xs">
      <div className="overflow-x-auto">
        <table data-testid="strategies-matrix-table" className="w-full text-left text-xs font-sans">
          <thead>
            <tr className="border-b border-border bg-surface-subtle font-mono text-[11px] uppercase tracking-wider text-text-muted">
              <th scope="col" className="px-4 py-3 font-semibold">策略 / 版本</th>
              <th scope="col" className="px-3 py-3 font-semibold">运行时控制</th>
              <th scope="col" className="px-3 py-3 font-semibold text-right">查询范围自然净盈亏</th>
              <th scope="col" className="px-3 py-3 font-semibold text-right">自然净 R</th>
              <th scope="col" className="px-3 py-3 font-semibold text-right">自然胜率</th>
              <th scope="col" className="px-3 py-3 font-semibold">终态构成 (自然 / 受控)</th>
              <th scope="col" className="px-3 py-3 font-semibold">复盘审计 (Review)</th>
              <th scope="col" className="px-3 py-3 font-semibold">TP1 达成</th>
              <th scope="col" className="px-4 py-3 font-semibold text-right">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border font-sans">
            {strategies.map((st) => {
              const { summary } = st;
              const isPnlPositive = st.netPnlIsPositive === true;
              const isPnlNegative = st.netPnlIsPositive === false;
              const isRPositive = st.netRIsPositive === true;
              const isRNegative = st.netRIsPositive === false;

              return (
                <tr
                  key={summary.strategy_version_id}
                  data-strategy-version-id={summary.strategy_version_id}
                  data-strategy-group-id={summary.strategy_group_id}
                  onClick={() => onSelectStrategy(st)}
                  className="group hover:bg-surface-elevated transition-colors cursor-pointer"
                >
                  {/* 1. Strategy Group & Version */}
                  <td className="px-4 py-3 font-sans">
                    <div className="flex items-center gap-1.5">
                      <span className="font-bold text-text-primary text-xs">{st.displayNameZh}</span>
                      <span className="rounded bg-brand/10 px-1.5 py-0.2 font-mono text-[10px] font-bold text-brand">
                        {summary.strategy_group_id}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5 mt-1 font-mono text-[11px] text-text-muted">
                      <span
                        className={`inline-flex items-center rounded px-1.5 py-0.2 text-[10px] font-semibold ${
                          summary.is_current
                            ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                            : 'bg-surface-subtle text-text-muted border border-border'
                        }`}
                      >
                        v{summary.version} · {summary.is_current ? '当前有效' : '历史版本'}
                      </span>
                      <span>·</span>
                      <span>{st.timeframe}</span>
                    </div>
                  </td>

                  {/* 2. Runtime Controls & Active Tickets */}
                  <td className="px-3 py-3 whitespace-nowrap">
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`h-2 w-2 rounded-full shrink-0 ${
                          st.runtimeStatus === 'enabled'
                            ? 'bg-emerald-500'
                            : st.runtimeStatus === 'paused'
                            ? 'bg-amber-500'
                            : 'bg-rose-500'
                        }`}
                      />
                      <span className="font-medium text-text-primary">{st.runtimeStatusLabel}</span>
                    </div>
                    <div className="font-mono text-[11px] text-text-muted mt-0.5">
                      {st.activeTicketCount > 0 ? (
                        <span className="text-brand font-semibold">{st.activeTicketCount} 笔在管持仓</span>
                      ) : (
                        <span>{st.isCurrent ? '当前在管 0' : '历史版本 · 不归属当前持仓'}</span>
                      )}
                    </div>
                  </td>

                  {/* 3. Natural Net PnL */}
                  <td className="px-3 py-3 font-mono text-right font-bold tabular-nums whitespace-nowrap">
                    <span
                      className={
                        isPnlPositive
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : isPnlNegative
                          ? 'text-rose-600 dark:text-rose-400'
                          : 'text-text-muted font-normal'
                      }
                    >
                      {st.netPnlFormatted}
                    </span>
                    {!st.hasConfirmedReview && (
                      <div className="text-[10px] text-text-muted font-sans font-normal mt-0.5">
                        待结清评审
                      </div>
                    )}
                  </td>

                  {/* 4. Natural Net R */}
                  <td className="px-3 py-3 font-mono text-right font-bold tabular-nums whitespace-nowrap">
                    <span
                      className={
                        isRPositive
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : isRNegative
                          ? 'text-rose-600 dark:text-rose-400'
                          : 'text-text-muted font-normal'
                      }
                    >
                      {st.netRFormatted}
                    </span>
                  </td>

                  {/* 5. Win Rate */}
                  <td className="px-3 py-3 font-mono text-right tabular-nums whitespace-nowrap">
                    <div className="font-bold text-text-primary">
                      {st.winRatePercent != null ? `${st.winRatePercent}%` : '—'}
                    </div>
                    <div className="text-[10px] text-text-muted mt-0.5">
                      {summary.win_count + summary.loss_count > 0 ? (
                        `${summary.win_count} 胜 / ${summary.loss_count} 负`
                      ) : (
                        '不可评价'
                      )}
                    </div>
                  </td>

                  {/* 6. Terminal Composition (Natural vs Controlled) */}
                  <td className="px-3 py-3 font-mono whitespace-nowrap">
                    <div className="text-text-primary font-semibold">
                      {st.naturalTerminals} <span className="font-sans text-[11px] text-text-muted font-normal">自然</span>
                    </div>
                    <div className="text-[10px] text-text-muted mt-0.5">
                      {st.controlledExits > 0 ? (
                        <span className="text-amber-600 dark:text-amber-400 font-medium">
                          {st.controlledExits} 受控退出
                        </span>
                      ) : (
                        '0 受控退出'
                      )}
                    </div>
                  </td>

                  {/* 7. Review Audit */}
                  <td className="px-3 py-3 font-mono whitespace-nowrap">
                    <div className="text-emerald-600 dark:text-emerald-400 font-semibold">
                      {st.confirmedReviews} 已确认
                    </div>
                    <div className="text-[10px] text-text-muted mt-0.5">
                      {st.pendingReviews} 待确认
                    </div>
                  </td>

                  {/* 8. TP1 Reach */}
                  <td className="px-3 py-3 font-mono whitespace-nowrap">
                    <div className="text-text-primary">
                      {st.tp1Reached} <span className="font-sans text-[11px] text-text-muted">达成</span>
                    </div>
                    <div className="text-[10px] text-text-muted mt-0.5">
                      {st.tp1NotReached} 未达
                    </div>
                  </td>

                  {/* 9. Action */}
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 rounded border border-border bg-surface-subtle px-2.5 py-1 text-xs font-semibold text-text-primary group-hover:bg-brand group-hover:text-white group-hover:border-brand transition-colors shadow-xs"
                    >
                      <span>详情</span>
                      <ChevronRight className="h-3 w-3" />
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
