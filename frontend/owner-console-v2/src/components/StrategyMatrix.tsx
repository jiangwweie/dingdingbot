import React from 'react';
import type { StrategyControlItem } from '../types/controls';
import { Pause, Play, AlertTriangle, CheckCircle2, HelpCircle } from 'lucide-react';

interface StrategyMatrixProps {
  strategies: StrategyControlItem[];
  onToggleStrategy?: (strategy: StrategyControlItem) => void;
}

export const StrategyMatrix: React.FC<StrategyMatrixProps> = ({
  strategies,
}) => {

  return (
    <div className="rounded border border-border bg-surface shadow-xs">
      <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
        <div>
          <h2 className="text-xs font-bold uppercase tracking-wider text-text-primary">
            策略独立控制矩阵
          </h2>
          <p className="mt-0.5 text-xs text-text-secondary">
            区分配置启用状态、实时准入诊断与实际在管持仓；策略暂停不影响已有持仓退出。
          </p>
        </div>
        <span className="font-mono text-xs text-text-muted">5 个在役策略 · 1 个退役归档</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-border bg-surface-subtle text-xs font-semibold text-text-muted">
              <th className="py-2.5 pl-5 pr-4 w-[28%]">策略组 (StrategyGroup)</th>
              <th className="px-4 py-2.5 w-[14%]">配置状态</th>
              <th className="px-4 py-2.5 w-[32%]">实际准入诊断 (来自事实)</th>
              <th className="px-4 py-2.5 w-[14%]">在管持仓占用</th>
              <th className="py-2.5 pl-4 pr-5 text-right w-[12%]">控制操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {strategies.map((strategy) => {
              const isEnabled = strategy.configured_state === 'enabled';
              const isRetired = strategy.is_retired;

              return (
                <tr
                  key={strategy.strategy_group_id}
                  className={`transition-colors hover:bg-surface-subtle/80 ${
                    isRetired ? 'opacity-60 bg-surface-subtle/30' : ''
                  }`}
                >
                  {/* Strategy ID, Name & Integrated Version/Change */}
                  <td className="py-2.5 pl-5 pr-4">
                    <div className="flex flex-col">
                      <div className="flex items-center gap-2">
                        <strong className="font-mono text-sm font-bold text-text-primary">
                          {strategy.strategy_group_id}
                        </strong>
                        <span className="font-mono text-xs font-medium text-text-muted">
                          {strategy.timeframe}
                        </span>
                      </div>
                      <div className="mt-0.5 flex items-center gap-2">
                        <span className="text-xs text-text-secondary">{strategy.name_zh}</span>
                        <span className="text-text-muted opacity-40">·</span>
                        <span className="font-mono text-[11px] text-text-muted">
                          v{strategy.control_version} ({strategy.reason_label})
                        </span>
                      </div>
                    </div>
                  </td>

                  {/* Configured State */}
                  <td className="px-4 py-2.5">
                    {isRetired ? (
                      <span className="inline-flex items-center rounded border border-border bg-surface-subtle px-2 py-0.5 font-mono text-xs text-text-muted">
                        已退役 (RETIRED)
                      </span>
                    ) : isEnabled ? (
                      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-status-green">
                        <span className="h-2 w-2 rounded-full bg-status-green" />
                        已启用
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-text-muted">
                        <span className="h-2 w-2 rounded-full bg-slate-400 dark:bg-slate-500" />
                        已暂停
                      </span>
                    )}
                  </td>

                  {/* Actual Admission Health (Expanded horizontal space for Chinese readability) */}
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      {strategy.admission_health.status === 'cleared' && (
                        <CheckCircle2 className="h-4 w-4 text-status-green flex-none" />
                      )}
                      {strategy.admission_health.status === 'blocked' && (
                        <AlertTriangle className="h-4 w-4 text-status-amber flex-none" />
                      )}
                      {strategy.admission_health.status === 'unknown' && (
                        <HelpCircle className="h-4 w-4 text-text-muted flex-none" />
                      )}

                      <span
                        className={`text-xs ${
                          strategy.admission_health.status === 'blocked'
                            ? 'font-medium text-status-amber'
                            : strategy.admission_health.status === 'cleared'
                            ? 'text-text-primary'
                            : 'text-text-muted'
                        }`}
                      >
                        {strategy.admission_health.summary}
                      </span>
                    </div>
                  </td>

                  {/* Active Positions in Flight */}
                  <td className="px-4 py-2.5">
                    {strategy.active_tickets.length > 0 ? (
                      <div className="flex flex-wrap gap-1.5">
                        {strategy.active_tickets.map((t) => (
                          <span
                            key={t.ticket_id}
                            className="inline-flex items-center gap-1.5 rounded border border-border-strong bg-surface-subtle px-2 py-0.5 text-xs font-mono"
                          >
                            <span
                              className={`font-bold ${
                                t.side === 'long' ? 'text-status-green' : 'text-status-red'
                              }`}
                            >
                              {t.side.toUpperCase()}
                            </span>
                            <span className="text-text-primary font-medium">{t.symbol}</span>
                            <span
                              className={`tabular-numbers font-semibold ${
                                t.pnl_r.startsWith('+') ? 'text-status-green' : 'text-status-red'
                              }`}
                            >
                              {t.pnl_r}
                            </span>
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-xs text-text-muted font-mono">0 个占用</span>
                    )}
                  </td>

                  {/* Toggle Button */}
                  <td className="py-2.5 pl-4 pr-5 text-right">
                    {isRetired ? (
                      <button
                        type="button"
                        disabled
                        className="rounded border border-border bg-surface-subtle px-3 py-1.5 text-xs text-text-disabled cursor-not-allowed"
                      >
                        禁止恢复
                      </button>
                    ) : isEnabled ? (
                      <button
                        type="button"
                        disabled
                        title="Phase 1 · 只读模式 (写操作未开放)"
                        className="inline-flex items-center gap-1.5 rounded border border-border bg-surface-subtle px-3 py-1.5 text-xs font-medium text-text-muted opacity-60 cursor-not-allowed"
                      >
                        <Pause className="h-3.5 w-3.5 text-text-muted" />
                        暂停 (只读)
                      </button>
                    ) : (
                      <button
                        type="button"
                        disabled
                        title="Phase 1 · 只读模式 (写操作未开放)"
                        className="inline-flex items-center gap-1.5 rounded border border-border bg-surface-subtle px-3 py-1.5 text-xs font-medium text-text-muted opacity-60 cursor-not-allowed"
                      >
                        <Play className="h-3.5 w-3.5 text-text-muted" />
                        恢复 (只读)
                      </button>
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

