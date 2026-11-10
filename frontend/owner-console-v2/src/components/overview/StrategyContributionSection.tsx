import React from 'react';
import type { StrategyPerformanceItem } from '../../types/overview';
import { Layers } from 'lucide-react';

interface StrategyContributionSectionProps {
  strategies: StrategyPerformanceItem[];
}

export const StrategyContributionSection: React.FC<StrategyContributionSectionProps> = ({
  strategies,
}) => {
  return (
    <div className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-xs transition-all">
      <div className="flex flex-col sm:flex-row sm:items-baseline justify-between pb-3.5 border-b border-border/80 gap-1 sm:gap-2">
        <div className="flex items-center gap-2.5">
          <Layers className="h-4 w-4 text-brand flex-none" />
          <h2 className="text-sm font-bold tracking-tight text-text-primary">
            今日策略表现
          </h2>
          <span className="text-xs text-text-muted font-medium">
            ({strategies.length} 个生产策略组)
          </span>
        </div>
        <span className="text-[11px] sm:text-xs text-text-muted break-words">
          来自总览已核实复盘统计（上海今日终态）
        </span>
      </div>

      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-border/70 text-[11px] font-bold uppercase tracking-wider text-text-muted">
              <th className="py-2.5 pr-3">策略组</th>
              <th className="py-2.5 px-3">状态</th>
              <th className="py-2.5 px-3 text-right">今日 R 贡献</th>
              <th className="py-2.5 px-3 text-right">已结算盈亏</th>
              <th className="py-2.5 px-3 text-right">结算交易</th>
              <th className="py-2.5 pl-3 text-right">在管持仓</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50 font-mono">
            {strategies.map((st) => {
              const netR = st.net_r_formatted ?? '--';
              const isPositive = netR.startsWith('+');
              const isNegative = netR.startsWith('-');
              const ticketCount = st.ticket_count ?? 0;

              return (
                <tr key={st.strategy_id} className="hover:bg-surface-elevated/40 transition-colors">
                  {/* 1. 策略名与 ID */}
                  <td className="py-3 pr-3 font-sans">
                    <div className="font-mono text-xs font-bold text-text-primary">
                      {st.strategy_id}
                    </div>
                    <div className="text-[11px] text-text-muted mt-0.5">
                      {st.name_zh} · {st.timeframe}
                    </div>
                    {st.strategy_version_id && (
                      <div className="font-mono text-[10px] text-text-muted opacity-80 mt-0.5" title="真实策略版本号 (strategy_version_id)">
                        {st.strategy_version_id}
                      </div>
                    )}
                  </td>

                  {/* 2. 状态 */}
                  <td className="py-3 px-3 font-sans text-xs">
                    <span
                      className={`inline-flex items-center gap-1.5 ${
                        st.status === 'paused'
                          ? 'text-amber-600 dark:text-amber-400 font-medium'
                          : 'text-text-secondary'
                      }`}
                    >
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${
                          st.status === 'paused' ? 'bg-amber-500' : 'bg-emerald-500'
                        }`}
                      />
                      {st.status_label}
                    </span>
                  </td>

                  {/* 3. 今日 R 贡献 */}
                  <td className="py-3 px-3 text-right">
                    <span
                      className={`font-bold font-mono ${
                        isPositive
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : isNegative
                          ? 'text-rose-600 dark:text-rose-400'
                          : 'text-text-muted'
                      }`}
                    >
                      {netR}
                    </span>
                  </td>

                  {/* 4. 已结算盈亏 */}
                  <td className="py-3 px-3 text-right text-text-secondary font-mono">
                    <span>{st.net_pnl_formatted ?? '--'}</span>
                  </td>

                  {/* 5. 结算交易 */}
                  <td className="py-3 px-3 text-right text-text-muted font-mono">
                    <span>{ticketCount} 笔</span>
                  </td>

                  {/* 6. 在管持仓 */}
                  <td className="py-3 pl-3 text-right">
                    {st.active_tickets_count > 0 ? (
                      <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-brand/10 text-brand font-bold font-mono text-xs">
                        {st.active_tickets_count} 占用
                      </span>
                    ) : (
                      <span className="text-text-muted font-mono">0</span>
                    )}
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
