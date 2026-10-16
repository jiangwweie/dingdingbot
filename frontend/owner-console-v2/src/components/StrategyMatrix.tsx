import React from 'react';
import type { StrategyControlItem } from '../types/controls';
import { Pause, Play, AlertTriangle, CheckCircle2, HelpCircle } from 'lucide-react';

interface StrategyMatrixProps {
  strategies: StrategyControlItem[];
  onToggleStrategy: (strategy: StrategyControlItem) => void;
}

export const StrategyMatrix: React.FC<StrategyMatrixProps> = ({
  strategies,
  onToggleStrategy,
}) => {
  return (
    <div className="rounded border border-border-base bg-surface-1 shadow-sm">
      <div className="flex items-center justify-between border-b border-border-base px-4 py-3">
        <div>
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-200">
            策略独立控制矩阵
          </h2>
          <p className="mt-0.5 text-[11px] text-slate-400">
            区分配置启用状态、实时准入诊断与实际在管持仓；策略暂停不影响已有持仓退出。
          </p>
        </div>
        <span className="font-mono text-[11px] text-slate-500">5 个在役策略 · 1 个退役归档</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-border-base bg-surface-2/60 text-[11px] font-semibold text-slate-400">
              <th className="py-2.5 pl-4 pr-3">策略组 (StrategyGroup)</th>
              <th className="px-3 py-2.5">配置状态</th>
              <th className="px-3 py-2.5">实际准入诊断 (来自事实)</th>
              <th className="px-3 py-2.5">在管持仓占用</th>
              <th className="px-3 py-2.5 font-mono">版本 / 变更</th>
              <th className="py-2.5 pl-3 pr-4 text-right">控制操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-base">
            {strategies.map((strategy) => {
              const isEnabled = strategy.configured_state === 'enabled';
              const isRetired = strategy.is_retired;

              return (
                <tr
                  key={strategy.strategy_group_id}
                  className={`transition-colors hover:bg-surface-2/40 ${
                    isRetired ? 'opacity-60 bg-surface-1/40' : ''
                  }`}
                >
                  {/* Strategy ID and Name */}
                  <td className="py-3 pl-4 pr-3">
                    <div className="flex flex-col">
                      <div className="flex items-center gap-2">
                        <strong className="font-mono text-xs font-bold text-slate-100">
                          {strategy.strategy_group_id}
                        </strong>
                        <span className="font-mono text-[10px] text-slate-500">
                          {strategy.timeframe}
                        </span>
                      </div>
                      <span className="text-[11px] text-slate-400">{strategy.name_zh}</span>
                    </div>
                  </td>

                  {/* Configured State */}
                  <td className="px-3 py-3">
                    {isRetired ? (
                      <span className="inline-flex items-center rounded border border-slate-700 bg-slate-800/80 px-2 py-0.5 text-[11px] font-mono text-slate-400">
                        已退役 (RETIRED)
                      </span>
                    ) : isEnabled ? (
                      <span className="inline-flex items-center gap-1.5 font-medium text-status-green">
                        <span className="h-1.5 w-1.5 rounded-full bg-status-green" />
                        已启用
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 font-medium text-slate-400">
                        <span className="h-1.5 w-1.5 rounded-full bg-slate-500" />
                        已暂停
                      </span>
                    )}
                  </td>

                  {/* Actual Admission Health (Strictly distinguished from configured state) */}
                  <td className="px-3 py-3">
                    <div className="flex items-center gap-1.5">
                      {strategy.admission_health.status === 'cleared' && (
                        <CheckCircle2 className="h-3.5 w-3.5 text-status-green flex-none" />
                      )}
                      {strategy.admission_health.status === 'blocked' && (
                        <AlertTriangle className="h-3.5 w-3.5 text-status-amber flex-none" />
                      )}
                      {strategy.admission_health.status === 'unknown' && (
                        <HelpCircle className="h-3.5 w-3.5 text-slate-500 flex-none" />
                      )}

                      <span
                        className={`text-[11px] ${
                          strategy.admission_health.status === 'blocked'
                            ? 'font-medium text-status-amber'
                            : strategy.admission_health.status === 'cleared'
                            ? 'text-slate-300'
                            : 'text-slate-500'
                        }`}
                      >
                        {strategy.admission_health.summary}
                      </span>
                    </div>
                  </td>

                  {/* Active Positions in Flight */}
                  <td className="px-3 py-3">
                    {strategy.active_tickets.length > 0 ? (
                      <div className="flex flex-wrap gap-1.5">
                        {strategy.active_tickets.map((t) => (
                          <span
                            key={t.ticket_id}
                            className="inline-flex items-center gap-1 rounded border border-border-strong bg-surface-2 px-1.5 py-0.5 text-[11px] font-mono"
                          >
                            <span
                              className={
                                t.side === 'long' ? 'text-status-green' : 'text-status-red'
                              }
                            >
                              {t.side.toUpperCase()}
                            </span>
                            <span className="text-slate-200">{t.symbol}</span>
                            <span
                              className={`tabular-numbers font-medium ${
                                t.pnl_r.startsWith('+') ? 'text-status-green' : 'text-status-red'
                              }`}
                            >
                              {t.pnl_r}
                            </span>
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-[11px] text-slate-500 font-mono">0 个占用</span>
                    )}
                  </td>

                  {/* Version & Reason */}
                  <td className="px-3 py-3 font-mono text-[11px] text-slate-400">
                    <div>v{strategy.control_version}</div>
                    <div className="text-[10px] text-slate-500">{strategy.reason_label}</div>
                  </td>

                  {/* Toggle Button */}
                  <td className="py-3 pl-3 pr-4 text-right">
                    {isRetired ? (
                      <button
                        type="button"
                        disabled
                        className="rounded border border-border-base bg-surface-2/40 px-2.5 py-1 text-[11px] text-slate-600 cursor-not-allowed"
                      >
                        禁止恢复
                      </button>
                    ) : isEnabled ? (
                      <button
                        type="button"
                        onClick={() => onToggleStrategy(strategy)}
                        className="inline-flex items-center gap-1 rounded border border-border-strong bg-surface-2 px-2.5 py-1 text-[11px] font-medium text-slate-300 hover:bg-surface-3 hover:text-white transition-colors"
                      >
                        <Pause className="h-3 w-3 text-status-amber" />
                        暂停策略
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => onToggleStrategy(strategy)}
                        className="inline-flex items-center gap-1 rounded border border-status-green/40 bg-status-green-bg px-2.5 py-1 text-[11px] font-medium text-status-green hover:bg-status-green/20 transition-colors"
                      >
                        <Play className="h-3 w-3" />
                        恢复运行
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
