import React from 'react';
import { useStrategyObservationsData } from '../../hooks/useStrategiesData.ts';
import type { StrategyObservationFirstPath } from '../../types/strategies.ts';
import { formatFirstPathLabel, formatObservationMetric } from '../../mapping/strategyMapping.ts';
import { cleanSymbol } from '../../utils/symbol.ts';
import {
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw,
  Info,
  AlertCircle,
  Compass,
} from 'lucide-react';

interface StrategyObservationsTabProps {
  strategyVersionId: string;
}

export const StrategyObservationsTab: React.FC<StrategyObservationsTabProps> = ({
  strategyVersionId,
}) => {
  const {
    items,
    firstPath,
    setFirstPath,
    isLoading,
    isFetchingNextPage,
    hasNextPage,
    isFetchNextPageError,
    error,
    fetchNextPage,
  } = useStrategyObservationsData(strategyVersionId);

  return (
    <div className="space-y-4">
      {/* 1. Observation Boundary Disclaimer Banner */}
      <div className="flex items-start gap-2.5 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3.5 text-xs text-amber-800 dark:text-amber-300">
        <Info className="h-4 w-4 shrink-0 mt-0.5 text-amber-600 dark:text-amber-400" />
        <div className="leading-relaxed">
          <strong className="font-semibold">研究观察与影子假设检验声明：</strong>
          <span className="opacity-90 ml-1">
            Observation 属于信号发出后的纯观察与 MFE/MAE 轨迹跟踪事实，<strong>绝非实际成交交易</strong>。
            观察收益不产生账户资金变动，亦不得混入生产实盘盈亏统计。
          </span>
        </div>
      </div>

      {/* 2. First Path Filter Pills */}
      <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-border bg-surface p-3 text-xs font-mono">
        <span className="text-[11px] text-text-muted mr-1 font-sans">First Path 路径:</span>
        {(
          [
            { id: null, label: '全部' },
            { id: 'tp1_first', label: 'TP1 先到达' },
            { id: 'initial_stop_first', label: '止损先到达' },
            { id: 'opening_range_failure', label: '开盘区间失效' },
            { id: 'ambiguous_same_bar', label: '同 Bar 歧义' },
            { id: 'time_stop', label: 'Time Stop' },
            { id: 'session_exit', label: 'Session Exit' },
            { id: 'horizon_complete', label: '周期完成' },
          ] as const
        ).map((item) => (
          <button
            key={item.label}
            type="button"
            onClick={() => setFirstPath(item.id as StrategyObservationFirstPath | null)}
            className={`rounded px-2.5 py-1 text-xs transition-colors ${
              firstPath === item.id
                ? 'bg-brand/10 text-brand font-bold border border-brand/30'
                : 'bg-surface-subtle text-text-muted hover:text-text-primary border border-border'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {/* 3. Observations List */}
      {isLoading ? (
        <div className="py-16 text-center">
          <div className="inline-block h-6 w-6 border-2 border-brand/30 border-t-brand rounded-full animate-spin mb-2" />
          <p className="text-xs text-text-secondary">正在读取版本 Observation 证据...</p>
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-lg border border-border bg-surface p-8 text-center text-xs text-text-muted">
          <Compass className="mx-auto h-8 w-8 text-text-muted/50 mb-2" />
          <p className="font-semibold text-text-secondary">当前筛选条件下无 Observation 记录</p>
          <p className="mt-1 text-[11px]">请调整 First Path 路径过滤条件。</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-xs">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-sans">
              <thead>
                <tr className="border-b border-border bg-surface-subtle font-mono text-[11px] uppercase tracking-wider text-text-muted">
                  <th scope="col" className="px-4 py-2.5 font-semibold">标的 / 方向</th>
                  <th scope="col" className="px-3 py-2.5 font-semibold">First Path 判定</th>
                  <th scope="col" className="px-3 py-2.5 font-semibold text-right">MFE (R)</th>
                  <th scope="col" className="px-3 py-2.5 font-semibold text-right">MAE (R)</th>
                  <th scope="col" className="px-3 py-2.5 font-semibold text-right">价差 (bps)</th>
                  <th scope="col" className="px-3 py-2.5 font-semibold">观察状态</th>
                  <th scope="col" className="px-3 py-2.5 font-semibold">发生时间</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border font-sans font-mono">
                {items.map((obs) => {
                  const isLong = obs.position_side === 'long';
                  const symbolClean = cleanSymbol(obs.exchange_instrument_id);
                  const isTp1First = obs.first_path === 'tp1_first';
                  const isStopFirst = obs.first_path === 'initial_stop_first';

                  return (
                    <tr key={obs.shadow_outcome_id} className="hover:bg-surface-elevated transition-colors">
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
                            {isLong ? '多' : '空'}
                          </span>
                        </div>
                        <div className="text-[10px] text-text-muted mt-0.5 truncate max-w-[140px]" title={obs.shadow_outcome_id}>
                          {obs.shadow_outcome_id}
                        </div>
                      </td>

                      {/* First Path */}
                      <td className="px-3 py-2.5 whitespace-nowrap font-sans">
                        <span
                          className={`inline-flex items-center rounded px-2 py-0.5 text-[10px] font-semibold ${
                            isTp1First
                              ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400'
                              : isStopFirst
                              ? 'bg-rose-500/15 text-rose-700 dark:text-rose-400'
                              : 'bg-surface-subtle text-text-secondary border border-border'
                          }`}
                        >
                          {formatFirstPathLabel(obs.first_path)}
                        </span>
                      </td>

                      {/* MFE (R) */}
                      <td className="px-3 py-2.5 text-right font-bold tabular-nums whitespace-nowrap text-emerald-600 dark:text-emerald-400">
                        {formatObservationMetric(obs.mfe_r, ' R')}
                      </td>

                      {/* MAE (R) */}
                      <td className="px-3 py-2.5 text-right font-bold tabular-nums whitespace-nowrap text-rose-600 dark:text-rose-400">
                        {formatObservationMetric(obs.mae_r, ' R')}
                      </td>

                      {/* Spread bps */}
                      <td className="px-3 py-2.5 text-right tabular-nums whitespace-nowrap text-text-secondary">
                        {formatObservationMetric(obs.spread_bps, ' bps')}
                      </td>

                      {/* Status */}
                      <td className="px-3 py-2.5 whitespace-nowrap font-sans">
                        <span
                          className={`inline-flex items-center gap-1 text-[11px] font-medium ${
                            obs.status === 'completed'
                              ? 'text-emerald-600 dark:text-emerald-400'
                              : obs.status === 'unavailable'
                              ? 'text-rose-600 dark:text-rose-400'
                              : 'text-text-muted'
                          }`}
                        >
                          <span
                            className={`h-1.5 w-1.5 rounded-full ${
                              obs.status === 'completed'
                                ? 'bg-emerald-500'
                                : obs.status === 'unavailable'
                                ? 'bg-rose-500'
                                : 'bg-amber-500'
                            }`}
                          />
                          {obs.status === 'completed'
                            ? '已完成'
                            : obs.status === 'unavailable'
                            ? '不可用'
                            : obs.status === 'claimed'
                            ? '认领中'
                            : '待处理'}
                        </span>
                      </td>

                      {/* Occurred At */}
                      <td className="px-3 py-2.5 text-[11px] text-text-muted whitespace-nowrap font-sans">
                        {new Date(obs.occurred_at_ms).toLocaleString('zh-CN', {
                          month: '2-digit',
                          day: '2-digit',
                          hour: '2-digit',
                          minute: '2-digit',
                          hour12: false,
                        })}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination Footer */}
          {hasNextPage ? (
            <div className="flex items-center justify-between border-t border-border bg-surface-subtle p-3 text-xs">
              <span className="text-text-muted">已加载前 {items.length} 笔观察记录</span>
              <button
                type="button"
                onClick={() => fetchNextPage()}
                disabled={isFetchingNextPage}
                className="inline-flex items-center gap-1.5 rounded border border-border bg-surface px-3 py-1.5 text-xs font-semibold text-text-primary hover:bg-surface-elevated transition-colors shadow-xs disabled:opacity-50"
              >
                <RefreshCw className={`h-3 w-3 ${isFetchingNextPage ? 'animate-spin text-brand' : ''}`} />
                <span>{isFetchingNextPage ? '正在加载...' : '加载更多观察 (Next Cursor)'}</span>
              </button>
            </div>
          ) : (
            <div className="border-t border-border py-2 text-center text-[11px] text-text-muted bg-surface-subtle">
              已加载全部观察记录 (共 {items.length} 笔)
            </div>
          )}

          {isFetchNextPageError && (
            <div className="p-3 bg-danger/10 text-danger text-xs text-center border-t border-danger/20 flex items-center justify-center gap-1.5">
              <AlertCircle className="h-4 w-4" />
              <span>加载下一页观察失败: {error instanceof Error ? error.message : '网络或服务异常'}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
