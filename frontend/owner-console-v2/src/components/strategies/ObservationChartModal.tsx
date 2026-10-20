import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchMarketCandles, marketCandlesQueryKey } from '../../api/marketApi';
import {
  computeObservationChartWindow,
  observationPriceLevels,
  formatChartPrice,
  getOutOfWindowAnnotations,
  type StrategyObservationListItem,
} from '../../mapping/chartAdapter';
import { formatFirstPathLabel, formatObservationMetric } from '../../mapping/strategyMapping';
import { cleanSymbol } from '../../utils/symbol';
import { useDrawerDismiss } from '../../hooks/useDrawerDismiss';
import { CausalityChart } from '../charts/CausalityChart';
import {
  X,
  AlertCircle,
  AlertTriangle,
  Info,
  RefreshCw,
  ExternalLink,
  Compass,
  ArrowUpRight,
  ArrowDownRight,
} from 'lucide-react';

export interface ObservationChartModalProps {
  observation: StrategyObservationListItem | null;
  isOpen: boolean;
  onClose: () => void;
  onSelectTicketId?: (ticketId: string) => void;
  drawerId?: string;
}

export const ObservationChartModal: React.FC<ObservationChartModalProps> = ({
  observation,
  isOpen,
  onClose,
  onSelectTicketId,
  drawerId = 'observation-chart-modal',
}) => {
  useDrawerDismiss({
    isOpen,
    onClose,
    drawerId,
  });

  const chartWin = useMemo(() => {
    if (!observation) return null;
    return computeObservationChartWindow(observation);
  }, [observation]);

  const priceLevels = useMemo(() => {
    if (!observation) return [];
    return observationPriceLevels(observation);
  }, [observation]);

  const exchangeInstrumentId = observation?.exchange_instrument_id ?? '';
  const isUnavailable = observation?.status === 'unavailable';

  const {
    data: candleEnvelope,
    isLoading: isCandlesLoading,
    isError: isCandlesError,
    error: candlesError,
    refetch: refetchCandles,
  } = useQuery({
    queryKey:
      observation && chartWin && !isUnavailable
        ? marketCandlesQueryKey({
            exchange_instrument_id: exchangeInstrumentId,
            timeframe: '15m',
            closed_at_ms: chartWin.closedAtMs,
            limit: chartWin.limit,
          })
        : ['owner', 'market', 'candles', 'disabled'],
    queryFn: ({ signal }) =>
      fetchMarketCandles(
        {
          exchange_instrument_id: exchangeInstrumentId,
          timeframe: '15m',
          closed_at_ms: chartWin!.closedAtMs,
          limit: chartWin!.limit,
        },
        signal
      ),
    enabled: isOpen && Boolean(observation) && !isUnavailable && Boolean(chartWin),
    staleTime: 60_000,
  });

  const candles = candleEnvelope?.data?.candles ?? [];
  const outOfWindowAnnotations = useMemo(
    () => getOutOfWindowAnnotations(observation?.annotations ?? [], candles),
    [observation?.annotations, candles]
  );

  if (!isOpen || !observation) return null;

  const isLong = observation.position_side === 'long';
  const symbolClean = cleanSymbol(observation.exchange_instrument_id);

  return (
    <div
      data-testid="observation-chart-modal"
      className="fixed inset-0 z-[80] overflow-hidden bg-black/80 backdrop-blur-sm flex items-center justify-center p-3 md:p-6 animate-in fade-in duration-200"
      role="dialog"
      aria-modal="true"
      aria-labelledby="obs-chart-modal-title"
      onClick={onClose}
    >
      <div
        className="w-full h-full max-h-[calc(100vh-24px)] md:max-h-[calc(100vh-48px)] max-w-7xl rounded-xl border border-border bg-surface shadow-2xl flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 1. Header */}
        <div className="flex min-h-14 items-center justify-between gap-3 border-b border-border bg-surface-subtle px-5 py-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand/10 text-brand border border-brand/20 shrink-0">
              <Compass className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2 id="obs-chart-modal-title" className="text-sm font-bold text-text-primary truncate font-mono">
                  {symbolClean} · 15m 影子观察轨迹
                </h2>
                <span
                  className={`inline-flex items-center gap-0.5 rounded px-1.5 py-0.2 font-mono text-[10px] font-semibold uppercase ${
                    isLong
                      ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                      : 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
                  }`}
                >
                  {isLong ? <ArrowUpRight className="h-2.5 w-2.5" /> : <ArrowDownRight className="h-2.5 w-2.5" />}
                  {isLong ? '做多 (LONG)' : '做空 (SHORT)'}
                </span>
                <span className="font-mono text-[10px] text-text-muted hidden sm:inline">
                  #{observation.shadow_outcome_id.slice(-8)}
                </span>
              </div>
              <div className="flex items-center gap-2 text-[11px] text-text-muted mt-0.5 font-mono truncate">
                <span>发生: {new Date(observation.occurred_at_ms).toLocaleString('zh-CN', { hour12: false })}</span>
                <span>·</span>
                <span>路径: {formatFirstPathLabel(observation.first_path)}</span>
                {observation.observed_bar_count != null && (
                  <>
                    <span>·</span>
                    <span>{observation.observed_bar_count} bars 跟踪</span>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {observation.ticket_id && onSelectTicketId && (
              <button
                type="button"
                onClick={() => {
                  onClose();
                  onSelectTicketId(observation.ticket_id!);
                }}
                className="inline-flex items-center gap-1 rounded border border-brand/30 bg-brand/10 px-2.5 py-1 text-xs font-semibold text-brand hover:bg-brand/20 transition-colors shadow-xs cursor-pointer"
                title={`查看关联实盘 Ticket 因果链 (#${observation.ticket_id})`}
                data-testid="view-real-ticket-btn"
              >
                <ExternalLink className="h-3 w-3" />
                <span className="hidden sm:inline">查看真实 Ticket</span>
                <span className="sm:hidden">Ticket</span>
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              className="rounded p-1.5 text-text-muted hover:bg-surface-elevated hover:text-text-primary transition-colors cursor-pointer"
              aria-label="关闭观察图表"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* 2. Research & Shadow Trajectory Disclaimer Banner */}
        <div className="flex items-center gap-2 border-b border-amber-500/20 bg-amber-500/10 px-5 py-2 text-xs text-amber-800 dark:text-amber-300">
          <Info className="h-3.5 w-3.5 shrink-0 text-amber-600 dark:text-amber-400" />
          <span className="font-medium">
            <strong>影子假设检验轨迹 (Shadow Trajectory)：</strong>
            纯观察记录，<strong>非实盘成交</strong>，绝不产生资金变动，绝不计入真实 PnL 与 R。
          </span>
        </div>

        {/* 2b. Out-of-window warning if any annotation is outside the candle window */}
        {outOfWindowAnnotations.length > 0 && (
          <div
            data-testid="observation-modal-out-of-window-banner"
            className="flex items-center gap-2 border-b border-amber-500/30 bg-amber-500/10 px-5 py-2 text-xs text-amber-700 dark:text-amber-300 font-sans"
          >
            <AlertTriangle className="h-4 w-4 shrink-0 text-amber-500" />
            <span>
              提示: {outOfWindowAnnotations.length} 个事件标注发生时间超出当前 K 线窗口范围（已在图表中隐藏，但完整保留在原始记录中）
            </span>
          </div>
        )}

        {/* 3. Facts Ribbon (Price Plan & Metrics) */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2 p-3 bg-surface-subtle border-b border-border text-[11px] font-mono">
          <div className="rounded border border-border bg-surface p-2">
            <span className="text-[10px] text-text-muted block uppercase font-sans">计划参考 Entry</span>
            <span className="font-bold text-amber-600 dark:text-amber-400 mt-0.5 block truncate">
              {formatChartPrice(observation.entry_reference_price)}
            </span>
          </div>
          <div className="rounded border border-border bg-surface p-2">
            <span className="text-[10px] text-text-muted block uppercase font-sans">初始止损 (Stop)</span>
            <span className="font-bold text-rose-600 dark:text-rose-400 mt-0.5 block truncate">
              {formatChartPrice(observation.initial_stop_price)}
            </span>
          </div>
          <div className="rounded border border-border bg-surface p-2">
            <span className="text-[10px] text-text-muted block uppercase font-sans">目标止盈 (TP1)</span>
            <span className="font-bold text-teal-600 dark:text-teal-400 mt-0.5 block truncate">
              {formatChartPrice(observation.take_profit_price)}
            </span>
          </div>
          <div className="rounded border border-border bg-surface p-2">
            <span className="text-[10px] text-text-muted block uppercase font-sans">首小时边界</span>
            <span className="font-bold text-purple-600 dark:text-purple-400 mt-0.5 block truncate">
              {formatChartPrice(observation.opening_range_boundary_price)}
            </span>
          </div>
          <div className="rounded border border-border bg-surface p-2">
            <span className="text-[10px] text-text-muted block uppercase font-sans">最大有利 (MFE)</span>
            <span className="font-bold text-emerald-600 dark:text-emerald-400 mt-0.5 block">
              {formatObservationMetric(observation.mfe_r, ' R')}
            </span>
          </div>
          <div className="rounded border border-border bg-surface p-2">
            <span className="text-[10px] text-text-muted block uppercase font-sans">最大不利 (MAE)</span>
            <span className="font-bold text-rose-600 dark:text-rose-400 mt-0.5 block">
              {formatObservationMetric(observation.mae_r, ' R')}
            </span>
          </div>
          <div className="rounded border border-border bg-surface p-2">
            <span className="text-[10px] text-text-muted block uppercase font-sans">价差 / 指数基差</span>
            <span className="font-bold text-text-primary mt-0.5 block truncate">
              {formatObservationMetric(observation.spread_bps, ' bps')}
            </span>
          </div>
          <div className="rounded border border-border bg-surface p-2">
            <span className="text-[10px] text-text-muted block uppercase font-sans">实盘关联</span>
            {observation.ticket_id ? (
              <button
                type="button"
                onClick={() => {
                  onClose();
                  onSelectTicketId?.(observation.ticket_id!);
                }}
                className="inline-flex items-center gap-1 font-bold text-brand hover:underline mt-0.5 block truncate cursor-pointer"
                title={`查看关联实盘 Ticket 因果链 (#${observation.ticket_id})`}
                data-testid="view-associated-ticket-btn"
              >
                <span>#{observation.ticket_id.slice(-8)}</span>
                <ExternalLink className="h-3 w-3" />
              </button>
            ) : (
              <span className="font-bold text-text-muted mt-0.5 block truncate" title="未生成实盘 Ticket (纯影子观察)">
                未成交 (无关联 Ticket)
              </span>
            )}
          </div>
        </div>

        {/* 4. Chart Canvas Body */}
        <div className="flex-1 min-h-0 p-4 bg-background relative flex flex-col justify-center">
          {isUnavailable ? (
            <div className="text-center py-16 space-y-2">
              <AlertCircle className="mx-auto h-8 w-8 text-amber-500" />
              <p className="font-semibold text-text-primary text-sm">观察计划不可用</p>
              <p className="text-xs text-text-muted font-mono">
                {observation.completion_reason ?? '缺少冻结价格事实或超出观测窗口'}
              </p>
            </div>
          ) : isCandlesLoading ? (
            <div className="text-center py-16 space-y-3">
              <div className="inline-block h-6 w-6 border-2 border-brand/30 border-t-brand rounded-full animate-spin" />
              <p className="text-xs text-text-secondary font-medium">正在读取 15m 公共 K 线数据...</p>
            </div>
          ) : isCandlesError ? (
            <div className="text-center py-16 space-y-3">
              <AlertCircle className="mx-auto h-8 w-8 text-danger" />
              <p className="font-semibold text-text-primary text-sm">公共 K 线数据读取失败</p>
              <p className="text-xs text-danger font-mono">
                {candlesError instanceof Error ? candlesError.message : '网络或行情服务异常'}
              </p>
              <p className="text-[11px] text-text-muted">
                冻结 Observation 价格计划、边界与 MFE/MAE 判定仍可阅读。
              </p>
              <button
                type="button"
                onClick={() => refetchCandles()}
                className="inline-flex items-center gap-1.5 rounded bg-brand px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand/90 transition-colors shadow-xs cursor-pointer"
              >
                <RefreshCw className="h-3 w-3" />
                <span>重试读取 K 线</span>
              </button>
            </div>
          ) : candles.length === 0 ? (
            <div className="text-center py-16 text-xs text-text-muted">
              该时间窗口内暂无 15m K 线数据返回
            </div>
          ) : (
            <CausalityChart
              candles={candles}
              annotations={observation.annotations}
              priceLevels={priceLevels}
              fullscreen
            />
          )}
        </div>
      </div>
    </div>
  );
};
