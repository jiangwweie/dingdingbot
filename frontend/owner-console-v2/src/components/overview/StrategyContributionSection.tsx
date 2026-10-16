import React from 'react';
import type { StrategyPerformanceItem } from '../../types/overview';
import { Layers } from 'lucide-react';

interface StrategyContributionSectionProps {
  strategies: StrategyPerformanceItem[];
}

export const StrategyContributionSection: React.FC<StrategyContributionSectionProps> = ({
  strategies,
}) => {
  // Find max R for proportional bar visualization
  const maxAbsR = Math.max(...strategies.map((s) => Math.abs(s.today_r)), 1.5);

  return (
    <div className="rounded-lg border border-border bg-surface p-4 shadow-sm">
      <div className="flex items-center justify-between pb-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-brand" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-text-primary">
            今日策略表现 (Strategy Matrix & Contribution)
          </h3>
          <span className="text-xs text-text-muted">
            ({strategies.length} 个生产策略组)
          </span>
        </div>
        <span className="text-[11px] text-text-muted">
          动态可扩展矩阵 · 实时汇总结算 R 收益
        </span>
      </div>

      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-border/60 text-[10px] font-bold uppercase tracking-wider text-text-muted">
              <th className="py-2 pr-3">策略组</th>
              <th className="py-2 px-3">准入诊断</th>
              <th className="py-2 px-3 text-right">今日 R 贡献</th>
              <th className="py-2 px-3 w-32 hidden sm:table-cell">贡献占比</th>
              <th className="py-2 px-3 text-right">已完结交易</th>
              <th className="py-2 pl-3 text-right">活动持仓</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40 font-mono">
            {strategies.map((st) => {
              const isPositive = st.today_r > 0;
              const isNegative = st.today_r < 0;
              const barPercent = Math.min(100, Math.round((Math.abs(st.today_r) / maxAbsR) * 100));

              return (
                <tr key={st.strategy_id} className="hover:bg-surface-subtle transition-colors">
                  {/* 1. 策略名与 ID */}
                  <td className="py-2.5 pr-3 font-sans">
                    <div className="font-mono text-xs font-bold text-text-primary">
                      {st.strategy_id}
                    </div>
                    <div className="text-[11px] text-text-muted">
                      {st.name_zh} · {st.timeframe}
                    </div>
                  </td>

                  {/* 2. 准入诊断 (人话) */}
                  <td className="py-2.5 px-3 font-sans text-xs">
                    <span
                      className={`inline-flex items-center gap-1.5 ${
                        st.status === 'blocked'
                          ? 'text-amber-600 dark:text-amber-400 font-medium'
                          : 'text-text-secondary'
                      }`}
                    >
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${
                          st.status === 'blocked' ? 'bg-amber-500' : 'bg-emerald-500'
                        }`}
                      />
                      {st.status_label}
                    </span>
                  </td>

                  {/* 3. 今日 R 贡献 */}
                  <td className="py-2.5 px-3 text-right">
                    <span
                      className={`font-bold ${
                        isPositive
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : isNegative
                          ? 'text-rose-600 dark:text-rose-400'
                          : 'text-text-muted'
                      }`}
                    >
                      {isPositive ? `+${st.today_r.toFixed(2)}` : st.today_r.toFixed(2)} R
                    </span>
                  </td>

                  {/* 4. 贡献条 */}
                  <td className="py-2.5 px-3 hidden sm:table-cell align-middle">
                    <div className="h-1.5 w-full rounded-full bg-surface-subtle overflow-hidden">
                      <div
                        className={`h-full rounded-full ${
                          isPositive
                            ? 'bg-emerald-500'
                            : isNegative
                            ? 'bg-rose-500'
                            : 'bg-transparent'
                        }`}
                        style={{ width: `${barPercent}%` }}
                      />
                    </div>
                  </td>

                  {/* 5. 已完结交易 */}
                  <td className="py-2.5 px-3 text-right text-text-secondary">
                    <span>{st.today_trades_count} 笔</span>
                    <span className="text-[10px] text-text-muted ml-1">
                      ({st.win_count}W/{st.loss_count}L)
                    </span>
                  </td>

                  {/* 6. 在管活动 Ticket */}
                  <td className="py-2.5 pl-3 text-right">
                    {st.active_tickets_count > 0 ? (
                      <span className="inline-flex items-center rounded bg-brand/10 px-1.5 py-0.5 text-[11px] font-bold text-brand">
                        {st.active_tickets_count} 占用
                      </span>
                    ) : (
                      <span className="text-text-muted">0</span>
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
