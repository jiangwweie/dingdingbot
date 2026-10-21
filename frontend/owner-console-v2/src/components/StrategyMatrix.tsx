import React from 'react';
import type { StrategyControlItem } from '../types/controls';
import { Pause, Play, AlertTriangle, CheckCircle2, HelpCircle } from 'lucide-react';
import { useStrategyControl } from '../hooks/useStrategyControl';
import { TotpActionModal } from './TotpActionModal';

interface StrategyMatrixProps {
  strategies: StrategyControlItem[];
  onToggleStrategy?: (strategy: StrategyControlItem) => void;
  onSelectTicket?: (ticketId: string) => void;
  onSuccess?: (message: string) => void;
}

export const StrategyMatrix: React.FC<StrategyMatrixProps> = ({
  strategies,
  onToggleStrategy,
  onSelectTicket,
  onSuccess,
}) => {
  const { modalProps, requestToggle } = useStrategyControl({
    onSuccess: (msg) => {
      onSuccess?.(msg);
    },
  });

  const handleToggle = (strategy: StrategyControlItem) => {
    const hasControlFact =
      (strategy.configured_state === 'enabled' || strategy.configured_state === 'paused') &&
      typeof strategy.control_version === 'number' &&
      Number.isFinite(strategy.control_version);
    if (!hasControlFact) return;

    if (onToggleStrategy) {
      onToggleStrategy(strategy);
    }
    requestToggle({
      strategy_group_id: strategy.strategy_group_id,
      configured_state: strategy.configured_state,
      control_version: strategy.control_version,
      name_zh: strategy.name_zh,
      is_retired: strategy.is_retired || strategy.strategy_group_id === 'SOR-001',
    });
  };

  return (
    <div className="rounded border border-border bg-surface shadow-xs">
      <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
        <div>
          <h2 className="text-xs font-bold uppercase tracking-wider text-text-primary">
            策略独立控制矩阵
          </h2>
          <p className="mt-0.5 text-xs text-text-secondary">
            区分配置启用状态、实时准入诊断与实际在管持仓；暂停新准入不影响存量持仓保护与退出。
          </p>
        </div>
        <span className="font-mono text-xs text-text-muted">5 个在役策略 · 1 个退役归档</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-border bg-surface-subtle text-xs font-semibold text-text-muted">
              <th className="py-2.5 pl-5 pr-4 w-[28%]">策略组 (StrategyGroup)</th>
              <th className="px-4 py-2.5 w-[14%]">配置与有效状态</th>
              <th className="px-4 py-2.5 w-[32%]">实际准入诊断 (来自事实)</th>
              <th className="px-4 py-2.5 w-[14%]">在管持仓占用</th>
              <th className="py-2.5 pl-4 pr-5 text-right w-[12%]">控制操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {strategies.map((strategy) => {
              const isEnabled = strategy.configured_state === 'enabled';
              const isRetired = strategy.is_retired || strategy.strategy_group_id === 'SOR-001';
              const isPausedByGlobal = strategy.effective_state === 'paused_by_global';
              const hasControlFact =
                (strategy.configured_state === 'enabled' || strategy.configured_state === 'paused') &&
                typeof strategy.control_version === 'number' &&
                Number.isFinite(strategy.control_version);

              return (
                <tr
                  key={strategy.strategy_group_id}
                  data-strategy-id={strategy.strategy_group_id}
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
                      <div className="mt-0.5 flex flex-wrap items-center gap-2">
                        <span className="text-xs text-text-secondary">{strategy.name_zh}</span>
                        {strategy.strategy_version_id && (
                          <>
                            <span className="text-text-muted opacity-40">·</span>
                            <span
                              className="font-mono text-[11px] text-text-muted"
                              title="真实策略版本号 (strategy_version_id)"
                            >
                              {strategy.strategy_version_id}
                            </span>
                          </>
                        )}
                        <span className="text-text-muted opacity-40">·</span>
                        <span
                          className="font-mono text-[11px] text-text-muted"
                          title="控制记录版本与原因"
                        >
                          控制: v{strategy.control_version} ({strategy.reason_label})
                        </span>
                      </div>
                    </div>
                  </td>

                  {/* Configured State & Effective State */}
                  <td className="px-4 py-2.5">
                    {isRetired ? (
                      <span className="inline-flex items-center rounded border border-border bg-surface-subtle px-2 py-0.5 font-mono text-xs text-text-muted">
                        已退役 (RETIRED)
                      </span>
                    ) : (
                      <div className="flex flex-col gap-1">
                        <div>
                          {isEnabled ? (
                            <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-status-green">
                              <span className="h-2 w-2 rounded-full bg-status-green" />
                              配置: 已启用
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-text-muted">
                              <span className="h-2 w-2 rounded-full bg-slate-400 dark:bg-slate-500" />
                              配置: 已暂停
                            </span>
                          )}
                        </div>
                        {isPausedByGlobal && (
                          <span
                            className="inline-flex items-center rounded bg-amber-500/10 px-1.5 py-0.5 font-mono text-[10px] font-medium text-amber-600 dark:text-amber-400 border border-amber-500/20"
                            title="全局 ENTRY 暂停生效中：新入场通道被动阻断，但策略自身配置仍为已启用"
                          >
                            全局暂停生效中
                          </span>
                        )}
                      </div>
                    )}
                  </td>

                  {/* Actual Admission Health */}
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
                          <button
                            type="button"
                            key={t.ticket_id}
                            data-ticket-id={t.ticket_id}
                            onClick={() => onSelectTicket?.(t.ticket_id)}
                            className="inline-flex items-center gap-1.5 rounded border border-border-strong bg-surface-subtle px-2 py-0.5 text-xs font-mono hover:border-brand hover:bg-surface-elevated transition-colors cursor-pointer"
                            title={`点击查看 ${t.symbol} 交易因果`}
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
                          </button>
                        ))}
                      </div>
                    ) : strategy.active_ticket_count && strategy.active_ticket_count > 0 ? (
                      <span
                        className="inline-flex items-center rounded border border-border bg-surface-subtle px-2 py-0.5 font-mono text-xs text-status-amber"
                        title="账户容量事实记录在管持仓，当前首屏未加载详细 Ticket 实例"
                      >
                        {strategy.active_ticket_count} 个占用
                      </span>
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
                        title="SOR-001 已永久退役，禁止恢复新准入"
                        className="rounded border border-border bg-surface-subtle px-3 py-1.5 text-xs text-text-disabled cursor-not-allowed"
                      >
                        已退役 (禁止恢复)
                      </button>
                    ) : !hasControlFact ? (
                      <button
                        type="button"
                        disabled
                        title="缺少真实控制事实 (configured_state / control_version)，禁止操作"
                        className="inline-flex items-center gap-1.5 rounded border border-border bg-surface-subtle px-3 py-1.5 text-xs font-medium text-text-disabled cursor-not-allowed shadow-xs"
                      >
                        控制事实不可用
                      </button>
                    ) : isEnabled ? (
                      <button
                        type="button"
                        onClick={() => handleToggle(strategy)}
                        className="inline-flex items-center gap-1.5 rounded border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text-primary hover:border-amber-500/50 hover:bg-amber-500/10 hover:text-amber-500 transition-colors cursor-pointer shadow-xs"
                        title="暂停该策略新准入 (存量持仓继续受保护)"
                      >
                        <Pause className="h-3.5 w-3.5 text-amber-500" />
                        暂停新准入
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => handleToggle(strategy)}
                        className="inline-flex items-center gap-1.5 rounded border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text-primary hover:border-brand/50 hover:bg-brand/10 hover:text-brand transition-colors cursor-pointer shadow-xs"
                        title="恢复该策略新准入 (需 TOTP 验证)"
                      >
                        <Play className="h-3.5 w-3.5 text-emerald-500" />
                        恢复新准入
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Confirmation & TOTP Step-Up Modal */}
      <TotpActionModal {...modalProps} />
    </div>
  );
};
