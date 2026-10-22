import { priceFacts } from '../../mapping/tradeTruth';
import React, { useState, useMemo, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchTicketCausality, causalityQueryKey } from '../../api/ticketsApi';
import { fetchMarketCandles, marketCandlesQueryKey, type CandleTimeframe } from '../../api/marketApi';
import {
  computeChartWindow,
  ticketPriceLevels,
  getOutOfWindowAnnotations,
} from '../../mapping/chartAdapter';
import { CausalityChart } from '../charts/CausalityChart';
import { ChartModal } from '../charts/ChartModal';
import type { TradeEpisodeSummary } from '../../types/overview';
import type { TradeEpisode } from '../../types/trades';
import { mapTradeListItemToEpisode } from '../../mapping/tradeEpisodeMapping';
import { cleanSymbol } from '../../utils/symbol';
import { useDrawerDismiss } from '../../hooks/useDrawerDismiss';
import {
  X,
  CheckCircle2,
  CircleDot,
  Copy,
  Check,
  AlertTriangle,
  Code,
  Terminal,
  FileText,
  CandlestickChart,
  Maximize2,
  RefreshCw,
} from 'lucide-react';

export interface CausalityDrawerProps {
  isOpen?: boolean;
  onClose: () => void;
  episode?: TradeEpisodeSummary | TradeEpisode | null;
  ticketId?: string | null;
}

const STAGE_LABELS_ZH: Record<string, string> = {
  signal: '信号 (Signal)',
  admission: '准入评估 (Admission)',
  entry: '入场下单 (Entry)',
  protection: '保护安装 (Protection)',
  tp_runner: '止盈 / Runner (TP/Runner)',
  exit: '退出执行 (Exit)',
  reconciliation: '账本对账 (Reconciliation)',
  review: '事后复盘 (Review)',
};

export const CausalityDrawer: React.FC<CausalityDrawerProps> = ({
  episode,
  ticketId: propTicketId,
  isOpen: propIsOpen,
  onClose,
}) => {
  const effectiveTicketId = propTicketId || episode?.ticket_id || '';
  const isDrawerOpen = propIsOpen !== undefined ? propIsOpen : Boolean(effectiveTicketId);

  useDrawerDismiss({
    isOpen: isDrawerOpen,
    onClose,
    drawerId: 'causality-drawer',
  });

  const [activeTab, setActiveTab] = useState<'timeline' | 'chart' | 'commands' | 'events' | 'evidence'>('timeline');
  const [timeframe, setTimeframe] = useState<CandleTimeframe>('1h');
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [copied, setCopied] = useState(false);

  // P2-1: Synchronous render-time state reset whenever effectiveTicketId changes.
  // This guarantees that activeTab is 'timeline', timeframe is '1h', and isFullscreen is false
  // BEFORE query hooks or children evaluate, completely preventing stale data inheritance,
  // redundant dual-timeframe requests, or cross-ticket state bleeding.
  const [prevTicketId, setPrevTicketId] = useState(effectiveTicketId);
  if (prevTicketId !== effectiveTicketId) {
    setPrevTicketId(effectiveTicketId);
    setActiveTab('timeline');
    setIsFullscreen(false);
    setTimeframe('1h');
    setCopied(false);
  }

  const {
    data,
    isLoading,
    isError,
    error,
    refetch: refetchCausality,
  } = useQuery({
    queryKey: causalityQueryKey(effectiveTicketId),
    queryFn: () => fetchTicketCausality(effectiveTicketId),
    enabled: Boolean(effectiveTicketId),
    staleTime: 10_000,
  });

  // Verify causality belongs to current ticket to prevent cross-ticket state leakage
  const causality =
    data?.data && data.data.trade?.ticket_id === effectiveTicketId
      ? data.data
      : null;

  // Initialize timeframe from verified price plan
  useEffect(() => {
    if (causality?.price_plan?.strategy_timeframe) {
      const tf = causality.price_plan.strategy_timeframe;
      if (tf === '1h' || tf === '15m') {
        setTimeframe(tf);
      }
    }
  }, [causality?.price_plan?.strategy_timeframe]);

  const resolvedEpisode = useMemo<TradeEpisode | null>(() => {
    if (causality?.trade) {
      return mapTradeListItemToEpisode(causality.trade);
    }
    if (episode && episode.symbol) {
      return episode as TradeEpisode;
    }
    return null;
  }, [causality?.trade, episode]);

  const chartWin = useMemo(() => {
    if (!causality) return null;
    return computeChartWindow({
      data: causality,
      generatedAt: data?.generated_at,
      timeframe,
    });
  }, [causality, data?.generated_at, timeframe]);

  const priceLevels = useMemo(() => {
    if (!causality?.price_plan) return [];
    return ticketPriceLevels(causality.price_plan);
  }, [causality?.price_plan]);

  const exchangeInstrumentId = causality?.trade?.exchange_instrument_id || episode?.symbol || '';
  const isChartActive = activeTab === 'chart';

  const {
    data: candleEnvelope,
    isLoading: isCandlesLoading,
    isError: isCandlesError,
    error: candlesError,
    refetch: refetchCandles,
  } = useQuery({
    queryKey:
      chartWin && exchangeInstrumentId
        ? marketCandlesQueryKey({
            exchange_instrument_id: exchangeInstrumentId,
            timeframe,
            closed_at_ms: chartWin.closedAtMs,
            limit: chartWin.limit,
          })
        : ['owner', 'market', 'candles', 'disabled'],
    queryFn: ({ signal }) =>
      fetchMarketCandles(
        {
          exchange_instrument_id: exchangeInstrumentId,
          timeframe,
          closed_at_ms: chartWin!.closedAtMs,
          limit: chartWin!.limit,
        },
        signal
      ),
    enabled: isChartActive && Boolean(chartWin) && Boolean(exchangeInstrumentId),
    staleTime: 60_000,
  });

  if (!isDrawerOpen || !effectiveTicketId) return null;

  const candles = candleEnvelope?.data?.candles ?? [];
  const outOfWindowAnnotations = causality
    ? getOutOfWindowAnnotations(causality.annotations, candles)
    : [];

  const hasConfirmedIdentity = Boolean(resolvedEpisode || causality?.trade);
  const positionSide = causality?.trade?.position_side ?? resolvedEpisode?.side ?? null;
  const isLong = positionSide === 'long';
  const displayStrategy = causality?.trade?.strategy_group_id ?? resolvedEpisode?.strategy_id ?? 'Ticket';
  const rawSymbol = causality?.trade?.exchange_instrument_id ?? resolvedEpisode?.symbol ?? '';
  const displaySymbol = cleanSymbol(rawSymbol);
  const displayStage = causality?.current_stage
    ? STAGE_LABELS_ZH[causality.current_stage] ?? causality.current_stage
    : resolvedEpisode?.lifecycle_stage_zh ?? (isLoading ? '正在核验...' : '待核验');

  const handleCopyJson = () => {
    if (!causality) return;
    navigator.clipboard.writeText(JSON.stringify(causality, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      id="causality-drawer"
      data-testid="causality-drawer"
      className="fixed inset-0 z-[70] overflow-hidden bg-black/60 backdrop-blur-sm transition-opacity animate-in fade-in duration-200"
      aria-labelledby="slide-over-title"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div className="absolute inset-y-0 right-0 flex max-w-full pl-10">
        <div
          className="w-screen max-w-2xl bg-surface border-l border-border shadow-2xl flex flex-col h-full"
          onClick={(e) => e.stopPropagation()}
        >
          {/* 1. Header */}
          <div className="border-b border-border bg-surface-subtle p-5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1 rounded bg-brand/10 px-2 py-0.5 font-mono text-xs font-bold text-brand">
                  {displayStrategy}
                </span>
                <span className="font-mono text-sm font-bold text-text-primary">
                  {displaySymbol || (isLoading ? '正在核验...' : '—')}
                </span>
                {hasConfirmedIdentity && positionSide ? (
                  <span
                    className={`font-mono text-[11px] font-semibold px-2 py-0.5 rounded uppercase ${
                      isLong
                        ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                        : 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
                    }`}
                  >
                    {isLong ? '做多 (LONG)' : '做空 (SHORT)'}
                  </span>
                ) : (
                  <span className="font-mono text-[11px] font-medium px-2 py-0.5 rounded bg-surface border border-border text-text-muted">
                    {isLoading ? '核验身份中...' : '身份未知'}
                  </span>
                )}
                <span className="font-mono text-xs text-text-muted" title={effectiveTicketId} data-ticket-id={effectiveTicketId}>
                  #{effectiveTicketId.slice(-8)}
                </span>
              </div>

              <button
                type="button"
                onClick={onClose}
                className="rounded p-1 text-text-muted hover:bg-surface-elevated hover:text-text-primary transition-colors cursor-pointer"
                aria-label="关闭抽屉"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Subheader facts */}
            <div className="mt-2.5 flex flex-wrap items-baseline justify-between text-xs gap-2">
              <div className="flex flex-wrap items-center gap-2 text-text-secondary">
                <span>{resolvedEpisode?.strategy_name_zh ?? displayStrategy}</span>
                <span>·</span>
                <span>
                  当前阶段:{' '}
                  <strong data-testid="causality-current-stage" className="text-brand font-semibold">
                    {displayStage}
                  </strong>
                </span>
                {causality?.exit_reason && (
                  <span className="inline-flex items-center rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-[11px] text-text-muted">
                    退出原因: {causality.exit_reason.label || '退出原因未识别'}
                    {causality.exit_reason.detail && <p className="mt-1 text-text-muted">{causality.exit_reason.detail}</p>}
                  </span>
                )}
                {resolvedEpisode?.net_r_formatted &&
                  resolvedEpisode.net_r_formatted !== '—' &&
                  resolvedEpisode.net_r_formatted !== '持仓中 · 未结' && (
                    <span className="font-mono font-bold text-text-primary">
                      {resolvedEpisode.net_r_formatted} ({resolvedEpisode.net_pnl_formatted})
                    </span>
                  )}
              </div>
              <span className="font-mono text-text-muted text-[11px]" title={effectiveTicketId} data-ticket-id={effectiveTicketId}>
                Ticket ID: {effectiveTicketId} · 发出时间: {resolvedEpisode?.issued_at_formatted ?? '—'}
              </span>
            </div>

            {/* Price Plan Quick Bar (if available from real causality) */}
            {causality?.price_plan && (
              <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] font-mono">
                <div data-testid="causality-entry-price" className="rounded border border-border bg-surface p-2">
                  <div className="text-[10px] text-text-muted uppercase">实际入场执行价</div>
                  <div data-testid="plan-value" className="font-bold text-text-primary mt-0.5">
                    {priceFacts(causality.price_plan).actual}
                  </div>
                </div>
                <div className="rounded border border-border bg-surface p-2">
                  <div className="text-text-muted">计划参考入场价</div>
                  <div data-testid="causality-reference-price">{priceFacts(causality.price_plan).reference}</div>
                </div>
                <div data-testid="causality-initial-stop" className="rounded border border-border bg-surface p-2">
                  <div className="text-[10px] text-text-muted uppercase">初始止损价</div>
                  <div data-testid="plan-value" className="font-bold text-rose-600 dark:text-rose-400 mt-0.5">
                    {priceFacts(causality.price_plan).initialStop}
                  </div>
                </div>
                <div data-testid="causality-active-stop" className="rounded border border-border bg-surface p-2">
                  <div className="text-[10px] text-text-muted uppercase">当前活动止损</div>
                  <div data-testid="plan-value" className="font-bold text-emerald-600 dark:text-emerald-400 mt-0.5">
                    {priceFacts(causality.price_plan).activeStop}
                  </div>
                </div>
                <div data-testid="causality-quantity" className="rounded border border-border bg-surface p-2">
                  <div className="text-[10px] text-text-muted uppercase">头寸数量</div>
                  <div data-testid="plan-value" className="font-bold text-text-primary mt-0.5">
                    {causality.price_plan.ticket_quantity ?? '未取得'}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* 2. Navigation Tabs */}
          <div className="flex border-b border-border bg-surface px-5 text-xs overflow-x-auto">
            <button
              type="button"
              onClick={() => setActiveTab('timeline')}
              className={`py-2.5 px-3 font-medium border-b-2 transition-colors whitespace-nowrap ${
                activeTab === 'timeline'
                  ? 'border-brand text-brand font-semibold'
                  : 'border-transparent text-text-secondary hover:text-text-primary'
              }`}
            >
              8 阶段时间线
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('chart')}
              className={`py-2.5 px-3 font-medium border-b-2 transition-colors whitespace-nowrap flex items-center gap-1.5 ${
                activeTab === 'chart'
                  ? 'border-brand text-brand font-semibold'
                  : 'border-transparent text-text-secondary hover:text-text-primary'
              }`}
            >
              <CandlestickChart className="h-3.5 w-3.5" />
              <span>K 线复盘</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('commands')}
              className={`py-2.5 px-3 font-medium border-b-2 transition-colors whitespace-nowrap flex items-center gap-1.5 ${
                activeTab === 'commands'
                  ? 'border-brand text-brand font-semibold'
                  : 'border-transparent text-text-secondary hover:text-text-primary'
              }`}
            >
              <Terminal className="h-3.5 w-3.5" />
              <span>底层命令 ({causality?.raw_commands?.length ?? 0})</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('events')}
              className={`py-2.5 px-3 font-medium border-b-2 transition-colors whitespace-nowrap flex items-center gap-1.5 ${
                activeTab === 'events'
                  ? 'border-brand text-brand font-semibold'
                  : 'border-transparent text-text-secondary hover:text-text-primary'
              }`}
            >
              <FileText className="h-3.5 w-3.5" />
              <span>事件证据 ({causality?.raw_events?.length ?? 0})</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('evidence')}
              className={`py-2.5 px-3 font-medium border-b-2 transition-colors whitespace-nowrap flex items-center gap-1.5 ${
                activeTab === 'evidence'
                  ? 'border-brand text-brand font-semibold'
                  : 'border-transparent text-text-secondary hover:text-text-primary'
              }`}
            >
              <Code className="h-3.5 w-3.5" />
              <span>审计证据</span>
            </button>
          </div>

          {/* 3. Main Body */}
          <div className="flex-1 overflow-y-auto p-5">
            {isLoading ? (
              <div className="py-20 text-center">
                <div className="inline-block h-6 w-6 border-2 border-brand/30 border-t-brand rounded-full animate-spin mb-3" />
                <p className="text-xs text-text-secondary font-medium">
                  正在读取 /tickets/{effectiveTicketId}/causality 真实因果链...
                </p>
              </div>
            ) : isError || !causality ? (
              <div className="rounded-lg border border-danger/30 bg-danger/10 p-6 text-center space-y-3">
                <AlertTriangle className="mx-auto h-8 w-8 text-danger" />
                <h3 className="font-bold text-text-primary text-sm font-sans">未找到可关联的真实 Ticket</h3>
                <p className="text-xs text-text-muted font-mono">Ticket ID: {effectiveTicketId}</p>
                <p className="text-xs text-danger font-mono">
                  {error instanceof Error ? error.message : '该 Ticket 因果数据不存在或读取失败'}
                </p>
                <div className="flex justify-center gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => refetchCausality()}
                    className="inline-flex items-center gap-1 rounded bg-brand px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand/90 transition-colors shadow-xs cursor-pointer font-sans"
                  >
                    <RefreshCw className="h-3 w-3" />
                    <span>重试加载</span>
                  </button>
                  <button
                    type="button"
                    onClick={onClose}
                    className="rounded border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text-primary hover:bg-surface-elevated transition-colors font-sans cursor-pointer"
                  >
                    关闭抽屉
                  </button>
                </div>
              </div>
            ) : (
              <>
                {/* TAB 1: 8 Stages Timeline */}
                {activeTab === 'timeline' && (
                  <div className="space-y-4">
                    <div className="relative pl-6 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-border">
                      {causality.stages.map((st, idx) => {
                        const isComplete = st.status === 'complete';
                        const isCurrent = st.status === 'current';
                        const isSkipped = st.status === 'skipped';


                        return (
                          <div key={st.key} className="relative mb-5 last:mb-0 group">
                            {/* Circle Node Icon */}
                            <div
                              className={`absolute -left-6 top-0 flex h-4 w-4 items-center justify-center rounded-full bg-surface border-2 ${
                                isComplete
                                  ? 'border-emerald-500 text-emerald-500'
                                  : isCurrent
                                  ? 'border-brand text-brand ring-4 ring-brand/10'
                                  : isSkipped
                                  ? 'border-text-muted text-text-muted'
                                  : 'border-border text-border'
                              }`}
                            >
                              {isComplete ? (
                                <CheckCircle2 className="h-3 w-3 fill-emerald-500 text-surface" />
                              ) : isCurrent ? (
                                <CircleDot className="h-3 w-3 fill-brand text-surface animate-pulse" />
                              ) : (
                                <span className="h-1.5 w-1.5 rounded-full bg-border" />
                              )}
                            </div>

                            {/* Stage Content */}
                            <div className="rounded border border-border bg-surface-subtle p-3 hover:border-brand/40 transition-colors">
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  <span className="font-mono text-[11px] font-bold text-text-primary">
                                    Stage {idx + 1}: {STAGE_LABELS_ZH[st.key] ?? st.label}
                                  </span>
                                  <span
                                    className={`font-mono text-[10px] font-semibold px-1.5 py-0.2 rounded uppercase ${
                                      isComplete
                                        ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                                        : isCurrent
                                        ? 'bg-brand/10 text-brand'
                                        : 'bg-surface text-text-muted border border-border'
                                    }`}
                                  >
                                    {st.status}
                                  </span>
                                </div>
                                {st.duration_ms !== null && (
                                  <span className="font-mono text-[10px] text-text-muted">
                                    耗时: {st.duration_ms}ms
                                  </span>
                                )}
                              </div>

                              <p className="mt-1 text-xs text-text-secondary leading-relaxed">
                                {st.summary}
                              </p>

                              {st.started_at_ms && (
                                <div className="mt-2 flex items-center gap-3 text-[10px] text-text-muted font-mono">
                                  <span>
                                    触发: {new Date(st.started_at_ms).toLocaleTimeString('zh-CN', { hour12: false })}
                                  </span>
                                  {st.completed_at_ms && (
                                    <span>
                                      完成: {new Date(st.completed_at_ms).toLocaleTimeString('zh-CN', { hour12: false })}
                                    </span>
                                  )}
                                  {st.evidence?.length > 0 && (
                                    <span>{st.evidence.length} 项证据锚点</span>
                                  )}
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* TAB 2: K-line Causality Review */}
                {activeTab === 'chart' && (
                  <div data-testid="causality-chart-tab" className="space-y-3 font-mono text-xs">
                    {/* Controls Bar */}
                    <div className="flex flex-wrap items-center justify-between gap-2 rounded border border-border bg-surface-subtle p-2.5">
                      <div className="flex items-center gap-2">
                        <span className="font-sans text-[11px] font-semibold text-text-secondary">
                          周期:
                        </span>
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            onClick={() => setTimeframe('1h')}
                            className={`rounded px-2.5 py-0.5 text-xs transition-colors ${
                              timeframe === '1h'
                                ? 'bg-brand/10 text-brand font-bold border border-brand/30'
                                : 'bg-surface text-text-muted hover:text-text-primary border border-border'
                            }`}
                          >
                            1h 策略复盘
                          </button>
                          <button
                            type="button"
                            onClick={() => setTimeframe('15m')}
                            className={`rounded px-2.5 py-0.5 text-xs transition-colors ${
                              timeframe === '15m'
                                ? 'bg-brand/10 text-brand font-bold border border-brand/30'
                                : 'bg-surface text-text-muted hover:text-text-primary border border-border'
                            }`}
                          >
                            15m 执行细节
                          </button>
                        </div>
                        {candles.length > 0 && (
                          <span className="text-[10px] text-text-muted hidden sm:inline">
                            · {candles.length} 根 K 线
                          </span>
                        )}
                      </div>

                      <button
                        type="button"
                        disabled={candles.length === 0}
                        onClick={() => setIsFullscreen(true)}
                        className="inline-flex items-center gap-1.5 rounded border border-border bg-surface px-2.5 py-1 text-xs font-semibold text-brand hover:bg-surface-elevated transition-colors shadow-xs disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
                        aria-label="全屏复盘"
                      >
                        <Maximize2 className="h-3 w-3" />
                        <span>全屏复盘</span>
                      </button>
                    </div>

                    {outOfWindowAnnotations.length > 0 && (
                      <div className="flex items-center gap-2 rounded border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300 font-sans">
                        <AlertTriangle className="h-4 w-4 shrink-0 text-amber-500" />
                        <span>
                          提示: {outOfWindowAnnotations.length} 个事件标注发生时间超出当前 K 线窗口范围（已在图表中隐藏，但完整保留在因果时间线与审计中）
                        </span>
                      </div>
                    )}

                    {/* Chart Body */}
                    <div className="rounded-lg border border-border bg-surface overflow-hidden">
                      {isCandlesLoading ? (
                        <div className="py-20 text-center">
                          <div className="inline-block h-6 w-6 border-2 border-brand/30 border-t-brand rounded-full animate-spin mb-2" />
                          <p className="text-xs text-text-secondary font-medium font-sans">
                            正在按需读取 {timeframe} 公共行情 K 线...
                          </p>
                        </div>
                      ) : isCandlesError ? (
                        <div className="p-6 text-center space-y-2">
                          <AlertTriangle className="mx-auto h-7 w-7 text-danger" />
                          <p className="font-semibold text-text-primary font-sans">行情 K 线数据读取失败</p>
                          <p className="text-xs text-danger font-mono">
                            {candlesError instanceof Error ? candlesError.message : '网络或服务异常'}
                          </p>
                          <p className="text-[11px] text-text-muted font-sans">
                            已保留全部价格计划、执行价和 8 阶段生命周期审计事实。
                          </p>
                          <button
                            type="button"
                            onClick={() => refetchCandles()}
                            className="mt-2 inline-flex items-center gap-1.5 rounded bg-brand px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand/90 transition-colors shadow-xs cursor-pointer font-sans"
                          >
                            <RefreshCw className="h-3 w-3" />
                            <span>重试加载 K 线</span>
                          </button>
                        </div>
                      ) : candles.length === 0 ? (
                        <div className="py-20 text-center text-text-muted text-xs font-sans">
                          当前交易时间窗口内暂无 K 线数据返回
                        </div>
                      ) : (
                        <div className="p-2">
                          <CausalityChart
                            candles={candles}
                            annotations={causality.annotations}
                            priceLevels={priceLevels}
                          />
                        </div>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center justify-between text-[10px] text-text-muted px-1 gap-1 font-sans">
                      <span>标注（Signal / Entry / Stop / TP1）自动锚定至对应 Bar 时间戳</span>
                      <span>绿线: 实际 Entry · 黄线: 计划 Entry · 红线: 止损 · 青线: TP1</span>
                    </div>
                  </div>
                )}

                {/* TAB 3: Raw Commands */}
                {activeTab === 'commands' && (
                  <div className="space-y-2 font-mono text-xs">
                    {causality.raw_commands.length === 0 ? (
                      <div className="py-10 text-center text-text-muted font-sans">
                        暂无底层交易所命令生成
                      </div>
                    ) : (
                      causality.raw_commands.map((cmd) => (
                        <div key={cmd.command_id} className="rounded border border-border bg-surface-subtle p-3">
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-bold text-text-primary">{cmd.command_kind}</span>
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface border border-border text-brand font-semibold">
                              {cmd.status}
                            </span>
                          </div>
                          <div className="text-[11px] text-text-secondary space-y-0.5">
                            <div>Command ID: {cmd.command_id} · Gen: {cmd.generation}</div>
                            <div className="text-text-muted">
                              时间: {cmd.created_at_ms ? new Date(cmd.created_at_ms).toLocaleTimeString() : '--'}
                            </div>
                            {cmd.request_payload && (
                              <pre className="mt-1 p-1.5 rounded bg-surface border border-border text-[10px] overflow-x-auto text-text-muted">
                                {JSON.stringify(cmd.request_payload, null, 2)}
                              </pre>
                            )}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                )}

                {/* TAB 3: Raw Events */}
                {activeTab === 'events' && (
                  <div className="space-y-2 font-mono text-xs">
                    {causality.raw_events.length === 0 ? (
                      <div className="py-10 text-center text-text-muted font-sans">
                        暂无生命周期事件记录
                      </div>
                    ) : (
                      causality.raw_events.map((evt) => (
                        <div key={evt.event_id} className="rounded border border-border bg-surface-subtle p-3">
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-bold text-text-primary">
                              {evt.event_type} <span className="text-text-muted text-[10px]">({evt.stage})</span>
                            </span>
                            <span className="text-[10px] text-text-muted">
                              {evt.occurred_at_ms ? new Date(evt.occurred_at_ms).toLocaleTimeString() : '--'}
                            </span>
                          </div>
                          {evt.payload && (
                            <pre className="mt-1 p-1.5 rounded bg-surface border border-border text-[10px] overflow-x-auto text-text-muted">
                              {JSON.stringify(evt.payload, null, 2)}
                            </pre>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                )}


                {/* TAB 4: Evidence Refs & Raw JSON */}
                {activeTab === 'evidence' && (
                  <div className="space-y-3 font-mono text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-sans text-xs font-bold text-text-primary">
                        完整审计证据引用与 JSON 快照
                      </span>
                      <button
                        type="button"
                        onClick={handleCopyJson}
                        className="inline-flex items-center gap-1.5 rounded border border-border bg-surface px-2.5 py-1 text-xs text-text-secondary hover:text-text-primary transition-colors"
                      >
                        {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
                        <span>{copied ? '已复制' : '复制 JSON'}</span>
                      </button>
                    </div>

                    <pre className="max-h-96 overflow-auto rounded border border-border bg-surface-subtle p-3 text-[11px] text-text-secondary">
                      {JSON.stringify(causality, null, 2)}
                    </pre>
                  </div>
                )}
              </>
            )}
          </div>

          {/* 4. Footer */}
          <div className="border-t border-border bg-surface-subtle p-4 flex items-center justify-between text-xs">
            <span className="text-[11px] text-text-muted">
              遵循 L1 → L2 → L3 → L4 渐进披露 · 真实不可变因果链
            </span>
            <button
              type="button"
              onClick={onClose}
              className="rounded border border-border bg-surface px-4 py-1.5 text-xs font-medium text-text-primary hover:bg-surface-elevated transition-colors"
            >
              关闭
            </button>
          </div>
        </div>
      </div>

      {/* Fullscreen Chart Modal */}
      <ChartModal
        isOpen={isFullscreen}
        onClose={() => setIsFullscreen(false)}
        title={`${displaySymbol || effectiveTicketId} · ${hasConfirmedIdentity && positionSide ? (isLong ? '做多 (LONG)' : '做空 (SHORT)') : '核验中'} · #${effectiveTicketId.slice(-8)}`}
        subtitle={`周期: ${timeframe} · 实际 Entry: ${priceFacts(causality?.price_plan ?? {}).actual} · 计划 Entry: ${priceFacts(causality?.price_plan ?? {}).reference} · Initial Stop: ${priceFacts(causality?.price_plan ?? {}).initialStop}`}
        candles={candles}
        annotations={causality?.annotations ?? []}
        priceLevels={priceLevels}
        drawerId="chart-fullscreen-modal"
      />
    </div>
  );
};
