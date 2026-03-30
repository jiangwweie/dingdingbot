import { useEffect, useRef, useState } from 'react';
import { createChart, createSeriesMarkers, IChartApi, ISeriesApi, CandlestickData, UTCTimestamp, CandlestickSeries, SeriesMarker, ColorType } from 'lightweight-charts';
import { X, TrendingUp, TrendingDown, Target, Shield, Zap, Clock, BarChart3 } from 'lucide-react';
import { cn } from '../lib/utils';
import { fetchSignalContext, Signal } from '../lib/api';
import { format } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import { toZonedTime } from 'date-fns-tz';

interface SignalDetailsModalProps {
  signalId: string;
  isOpen: boolean;
  onClose: () => void;
}

// Apple Design colors
const APPLE_GREEN = '#34C759';
const APPLE_RED = '#FF3B30';
const APPLE_GRAY = '#86868B';
const APPLE_BLUE = '#007AFF';

export default function SignalDetailsModal({ signalId, isOpen, onClose }: SignalDetailsModalProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const markersApiRef = useRef<ReturnType<typeof createSeriesMarkers> | null>(null);
  const [data, setData] = useState<{ signal: Signal; klines: number[][] } | null>(null);
  const [loading, setLoading] = useState(false);

  // Fetch data when drawer opens
  useEffect(() => {
    if (isOpen && signalId) {
      setLoading(true);
      fetchSignalContext(signalId).then((result) => {
        setData(result);
        setLoading(false);
      });
    }
  }, [isOpen, signalId]);

  // Initialize chart when data is loaded
  useEffect(() => {
    if (!isOpen || !data || !chartContainerRef.current) return;

    // Create chart with Tokyo timezone configuration
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#FFFFFF' },
        textColor: APPLE_GRAY,
        fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif',
      },
      grid: {
        vertLines: { color: '#F0F0F0' },
        horzLines: { color: '#F0F0F0' },
      },
      width: chartContainerRef.current.clientWidth,
      height: 400,
      rightPriceScale: {
        borderVisible: false,
      },
      timeScale: {
        borderVisible: false,
        timeVisible: true,
        secondsVisible: false,
        // Set timezone to Tokyo (JST, UTC+9) to match Binance app
        timeZone: 'Asia/Tokyo',
      },
      crosshair: {
        vertLine: {
          width: 1,
          color: '#D0D0D0',
          style: 3,
        },
        horzLine: {
          width: 1,
          color: '#D0D0D0',
          style: 3,
        },
      },
    });

    chartRef.current = chart;

    // Create candlestick series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: APPLE_GREEN,
      downColor: APPLE_RED,
      borderUpColor: APPLE_GREEN,
      borderDownColor: APPLE_RED,
      wickUpColor: APPLE_GREEN,
      wickDownColor: APPLE_RED,
    });

    candleSeriesRef.current = candleSeries;

    // Prepare data - lightweight-charts will handle timezone conversion via timeScale.timeZone config
    // K-line timestamps from API are already in UTC milliseconds (exchange standard)
    const klineData: CandlestickData[] = data.klines.map((k) => ({
      time: (k[0] / 1000) as UTCTimestamp, // Convert ms to seconds for lightweight-charts
      open: k[1],
      high: k[2],
      low: k[3],
      close: k[4],
    }));

    candleSeries.setData(klineData);

    // Find the exact signal candle by timestamp (UTC seconds)
    const signalTimestamp = data.signal.kline_timestamp
      ? Math.floor(data.signal.kline_timestamp / 1000)
      : null;
      
    const signalCandle = signalTimestamp 
      ? klineData.find(k => Number(k.time) === signalTimestamp)
      : null;

    if (signalCandle) {
      const isLong = data.signal.direction === 'long';

      const markersApi = createSeriesMarkers(candleSeries, [
        {
          time: signalCandle.time,
          position: isLong ? 'belowBar' : 'aboveBar',
          color: isLong ? APPLE_GREEN : APPLE_RED,
          shape: isLong ? 'arrowUp' : 'arrowDown',
          text: isLong ? '多 (入场)' : '空 (入场)',
          size: 2,
        },
      ]);

      markersApiRef.current = markersApi;
    } else if (klineData.length > 0) {
      // Fallback for legacy data
      const fallbackCandle = klineData[Math.floor(klineData.length / 2)];
      const isLong = data.signal.direction === 'long';
      const markersApi = createSeriesMarkers(candleSeries, [
        {
          time: fallbackCandle.time,
          position: isLong ? 'belowBar' : 'aboveBar',
          color: isLong ? APPLE_GREEN : APPLE_RED,
          shape: isLong ? 'arrowUp' : 'arrowDown',
          text: isLong ? '多 (预估)' : '空 (预估)',
          size: 2,
        },
      ]);
      markersApiRef.current = markersApi;
    }

    // Add visual horizontal lines for Entry Price and Stop Loss
    if (data.signal.entry_price) {
      candleSeries.createPriceLine({
        price: Number(data.signal.entry_price),
        color: APPLE_BLUE,
        lineWidth: 2,
        lineStyle: 3, // Dotted
        axisLabelVisible: true,
        title: '入场价',
      });
    }

    if (data.signal.stop_loss) {
      candleSeries.createPriceLine({
        price: Number(data.signal.stop_loss),
        color: APPLE_RED,
        lineWidth: 1,
        lineStyle: 2, // Dashed
        axisLabelVisible: true,
        title: '止损价',
      });
    }

    // S6-3: Add visual horizontal lines for Take Profit levels (green dashed lines)
    if (data.signal.take_profit_levels && data.signal.take_profit_levels.length > 0) {
      data.signal.take_profit_levels.forEach((tp) => {
        candleSeries.createPriceLine({
          price: Number(tp.price_level),
          color: APPLE_GREEN,
          lineWidth: 1,
          lineStyle: 2, // Dashed
          axisLabelVisible: true,
          title: `${tp.tp_id} (${Number(tp.position_ratio) * 100}%)`,
        });
      });
    }

    // Fit content
    chart.timeScale().fitContent();

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current && chart) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      markersApiRef.current?.detach();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      markersApiRef.current = null;
    };
  }, [data, isOpen]);

  const translateStrategy = (strategy?: string | null): string => {
    if (!strategy) return '-';
    const key = strategy.toLowerCase();
    if (key === 'pinbar') return 'Pinbar';
    if (key === 'engulfing') return 'Engulfing';
    return strategy;
  };

  const getStrategyBadgeClass = (strategy?: string | null): string => {
    if (!strategy) return 'bg-gray-100 text-gray-500';
    const key = strategy.toLowerCase();
    const colors: Record<string, string> = {
      pinbar: 'bg-purple-100 text-purple-700',
      engulfing: 'bg-orange-100 text-orange-700',
    };
    return colors[key] || 'bg-gray-100 text-gray-500';
  };

  const renderScore = (score?: number | string | null): string | number => {
    if (!score || Number(score) === 0) return '-';
    const scoreNum = typeof score === 'string' ? parseFloat(score) : score;
    if (isNaN(scoreNum) || scoreNum <= 0) return '-';
    return Math.round(scoreNum * 100) + '%';
  };

  const translateDirection = (dir: string) => (dir === 'long' ? '做多' : '做空');
  const translateEmaTrend = (trend: string) => {
    if (trend === 'bullish') return '多头趋势';
    if (trend === 'bearish') return '空头趋势';
    return trend;
  };
  const translateMtfStatus = (status: string) => {
    switch (status) {
      case 'confirmed': return '已确认';
      case 'rejected': return '已拒绝';
      case 'disabled': return '已禁用';
      case 'unavailable': return '数据未就绪';
      default: return status;
    }
  };
  const translateStatus = (status: string) => {
    switch (status) {
      case 'pending': return '监控中';
      case 'won': return '止盈';
      case 'lost': return '止损';
      default: return status;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'pending': return 'bg-gray-100 text-gray-600';
      case 'won': return 'bg-apple-green/10 text-apple-green';
      case 'lost': return 'bg-apple-red/10 text-apple-red';
      default: return 'bg-gray-100 text-gray-600';
    }
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className={cn(
          "fixed inset-0 bg-black/20 backdrop-blur-sm z-50 transition-opacity duration-300",
          isOpen ? "opacity-100" : "opacity-0"
        )}
        onClick={onClose}
      />

      {/* Modal */}
      <div
        className={cn(
          "fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2",
          "w-[90%] h-[85%] max-w-[1400px] max-h-[900px]",
          "z-50 bg-white/90 backdrop-blur-xl rounded-2xl shadow-2xl",
          "border border-gray-100/50",
          "transition-all duration-300",
          isOpen ? "opacity-100 scale-100" : "opacity-0 scale-95"
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100/50">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">信号详情</h2>
            <p className="text-sm text-gray-500 mt-1">交易复盘与数据分析</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl hover:bg-gray-100/50 transition-colors"
          >
            <X className="w-5 h-5 text-gray-400" />
          </button>
        </div>

        {/* Content */}
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-apple-blue border-t-transparent" />
          </div>
        ) : data ? (
          <div className="h-[calc(100%-73px)] overflow-y-auto p-6">
            {/* Top Row: Core Info Cards (5 cards horizontally) */}
            <div className="grid grid-cols-5 gap-4 mb-6">
              {/* Time */}
              <div className="bg-white/60 rounded-xl p-4 shadow-sm border border-gray-100/50">
                <div className="flex items-center gap-2 mb-2">
                  <Clock className="w-4 h-4 text-gray-400" />
                  <span className="text-xs text-gray-500 uppercase">时间</span>
                </div>
                <div className="text-sm font-mono text-gray-900 truncate">
                  {(() => {
                    const ts = data.signal.kline_timestamp || data.signal.created_at;
                    const tokyoTime = toZonedTime(new Date(ts), 'Asia/Tokyo');
                    return format(tokyoTime, 'MM-dd HH:mm');
                  })()}
                </div>
              </div>

              {/* Symbol */}
              <div className="bg-white/60 rounded-xl p-4 shadow-sm border border-gray-100/50">
                <div className="flex items-center gap-2 mb-2">
                  <Target className="w-4 h-4 text-gray-400" />
                  <span className="text-xs text-gray-500 uppercase">币种</span>
                </div>
                <div className="text-sm font-semibold text-gray-900 truncate">
                  {data.signal.symbol.replace(':USDT', '')}
                </div>
              </div>

              {/* Entry Price */}
              <div className="bg-white/60 rounded-xl p-4 shadow-sm border border-gray-100/50">
                <div className="flex items-center gap-2 mb-2">
                  <Zap className="w-4 h-4 text-gray-400" />
                  <span className="text-xs text-gray-500 uppercase">入场价</span>
                </div>
                <div className="text-sm font-mono text-gray-900">
                  {data.signal.entry_price ? Number(data.signal.entry_price).toFixed(2) : '-'}
                </div>
              </div>

              {/* Stop Loss */}
              <div className="bg-white/60 rounded-xl p-4 shadow-sm border border-gray-100/50">
                <div className="flex items-center gap-2 mb-2">
                  <Shield className="w-4 h-4 text-gray-400" />
                  <span className="text-xs text-gray-500 uppercase">止损价</span>
                </div>
                <div className="text-sm font-mono text-apple-red">
                  {data.signal.stop_loss ? Number(data.signal.stop_loss).toFixed(2) : '-'}
                </div>
              </div>

              {/* Take Profit - S6-3 Multi-Level */}
              <div className="bg-white/60 rounded-xl p-4 shadow-sm border border-gray-100/50">
                <div className="flex items-center gap-2 mb-2">
                  <TrendingUp className="w-4 h-4 text-gray-400" />
                  <span className="text-xs text-gray-500 uppercase">止盈目标</span>
                </div>
                {data.signal.take_profit_levels && data.signal.take_profit_levels.length > 0 ? (
                  <div className="space-y-1">
                    {data.signal.take_profit_levels.map((tp) => (
                      <div key={tp.id} className="flex justify-between text-xs">
                        <span className="text-gray-500">{tp.tp_id}:</span>
                        <span className="font-mono text-apple-green">
                          {Number(tp.price_level).toFixed(2)}
                          <span className="text-gray-400 ml-1">
                            ({Number(tp.position_ratio) * 100}% @ 1:{Number(tp.risk_reward)})
                          </span>
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-sm font-mono text-apple-green">
                    {data.signal.take_profit ? Number(data.signal.take_profit).toFixed(2) : '-'}
                  </div>
                )}
              </div>
            </div>

            {/* Main Content: K-line Chart (80%) + Data Panel (20%) */}
            <div className="grid grid-cols-[80%_20%] gap-6 h-[calc(100%-140px)]">
              {/* Left: K-line Chart */}
              <div className="bg-white/60 rounded-xl border border-gray-100/50 flex flex-col overflow-hidden">
                <div className="px-4 py-3 border-b border-gray-100/50 flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-medium text-gray-700">K 线复盘</h3>
                    <p className="text-xs text-gray-400 mt-0.5">信号前后各 10 根 K 线</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={cn(
                      "px-2 py-1 rounded text-xs font-medium",
                      data.signal.direction === 'long'
                        ? "bg-apple-green/10 text-apple-green"
                        : "bg-apple-red/10 text-apple-red"
                    )}>
                      {translateDirection(data.signal.direction)}
                    </span>
                    <span className={cn(
                      "px-2 py-1 rounded text-xs font-medium",
                      getStatusColor(data.signal.status)
                    )}>
                      {translateStatus(data.signal.status)}
                    </span>
                  </div>
                </div>
                <div className="flex-1 p-4">
                  <div
                    ref={chartContainerRef}
                    className="w-full h-full rounded-lg overflow-hidden border border-gray-100"
                  />
                </div>
              </div>

              {/* Right: Data Panel (20%, 2-column grid) */}
              <div className="bg-white/60 rounded-xl border border-gray-100/50 p-4 overflow-y-auto">
                <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">
                  数据详情
                </h4>
                <div className="grid grid-cols-2 gap-3">
                  {/* Direction */}
                  <div className="bg-white/80 rounded-lg p-3 border border-gray-100/50">
                    <div className="text-xs text-gray-400 mb-1">方向</div>
                    <div className={cn(
                      "text-sm font-medium",
                      data.signal.direction === 'long'
                        ? "text-apple-green"
                        : "text-apple-red"
                    )}>
                      {translateDirection(data.signal.direction)}
                    </div>
                  </div>

                  {/* Status */}
                  <div className="bg-white/80 rounded-lg p-3 border border-gray-100/50">
                    <div className="text-xs text-gray-400 mb-1">状态</div>
                    <div className={cn(
                      "text-sm font-medium",
                      getStatusColor(data.signal.status)
                    )}>
                      {translateStatus(data.signal.status)}
                    </div>
                  </div>

                  {/* Timeframe */}
                  <div className="bg-white/80 rounded-lg p-3 border border-gray-100/50">
                    <div className="text-xs text-gray-400 mb-1">周期</div>
                    <div className="text-sm font-mono text-gray-900">
                      {data.signal.timeframe}
                    </div>
                  </div>

                  {/* Strategy */}
                  <div className="bg-white/80 rounded-lg p-3 border border-gray-100/50">
                    <div className="text-xs text-gray-400 mb-1">策略</div>
                    <div className={cn(
                      "text-sm font-medium",
                      getStrategyBadgeClass(data.signal.strategy_name)
                    )}>
                      {translateStrategy(data.signal.strategy_name)}
                    </div>
                  </div>

                  {/* Score */}
                  <div className="bg-white/80 rounded-lg p-3 border border-gray-100/50">
                    <div className="text-xs text-gray-400 mb-1">评分</div>
                    <div className="text-sm font-mono text-gray-900">
                      {renderScore(data.signal.score)}
                    </div>
                  </div>

                  {/* Position Size */}
                  <div className="bg-white/80 rounded-lg p-3 border border-gray-100/50">
                    <div className="text-xs text-gray-400 mb-1">仓位</div>
                    <div className="text-sm font-mono text-gray-900">
                      {data.signal.position_size}
                    </div>
                  </div>

                  {/* Leverage */}
                  <div className="bg-white/80 rounded-lg p-3 border border-gray-100/50">
                    <div className="text-xs text-gray-400 mb-1">杠杆</div>
                    <div className="text-sm font-mono text-gray-900">
                      {data.signal.leverage}x
                    </div>
                  </div>

                  {/* PnL Ratio */}
                  <div className="bg-white/80 rounded-lg p-3 border border-gray-100/50">
                    <div className="text-xs text-gray-400 mb-1">盈亏比</div>
                    <div className={cn(
                      "text-sm font-mono",
                      data.signal.pnl_ratio !== undefined && data.signal.pnl_ratio !== null
                        ? (Number(data.signal.pnl_ratio) >= 0 ? "text-apple-green" : "text-apple-red")
                        : "text-gray-400"
                    )}>
                      {data.signal.pnl_ratio !== undefined && data.signal.pnl_ratio !== null
                        ? `${Number(data.signal.pnl_ratio) > 0 ? '+' : ''}${Number(data.signal.pnl_ratio).toFixed(2)}`
                        : '-'}
                    </div>
                  </div>

                  {/* EMA Trend */}
                  <div className="bg-white/80 rounded-lg p-3 border border-gray-100/50">
                    <div className="text-xs text-gray-400 mb-1">EMA</div>
                    <div className={cn(
                      "text-sm font-medium",
                      data.signal.ema_trend === 'bullish'
                        ? "text-apple-green"
                        : "text-apple-red"
                    )}>
                      {translateEmaTrend(data.signal.ema_trend)}
                    </div>
                  </div>

                  {/* MTF Status */}
                  <div className="bg-white/80 rounded-lg p-3 border border-gray-100/50">
                    <div className="text-xs text-gray-400 mb-1">MTF</div>
                    <div className="text-sm text-gray-600">
                      {translateMtfStatus(data.signal.mtf_status)}
                    </div>
                  </div>

                  {/* S6-3: Take Profit Levels - Full Grid Display */}
                  {data.signal.take_profit_levels && data.signal.take_profit_levels.length > 0 && (
                    <>
                      <div className="bg-white/80 rounded-lg p-3 border border-gray-100/50 col-span-2">
                        <div className="text-xs text-gray-400 mb-2 flex items-center gap-1">
                          <TrendingUp className="w-3 h-3" />
                          止盈目标
                        </div>
                        <div className="space-y-1.5">
                          {data.signal.take_profit_levels.map((tp) => (
                            <div key={tp.id} className="flex justify-between items-center text-xs bg-apple-green/5 rounded px-2 py-1">
                              <span className="font-medium text-gray-600">{tp.tp_id}</span>
                              <div className="text-right">
                                <div className="font-mono text-apple-green">
                                  {Number(tp.price_level).toFixed(2)}
                                </div>
                                <div className="text-gray-400 text-[10px]">
                                  {Number(tp.position_ratio) * 100}% @ 1:{Number(tp.risk_reward)}
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </>
  );
}
