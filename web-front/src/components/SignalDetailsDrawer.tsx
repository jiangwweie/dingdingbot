import { useEffect, useRef, useState } from 'react';
import { createChart, createSeriesMarkers, IChartApi, ISeriesApi, CandlestickData, UTCTimestamp, CandlestickSeries, SeriesMarker, ColorType } from 'lightweight-charts';
import { X, TrendingUp, TrendingDown, Target, Shield, Zap, Clock, BarChart3 } from 'lucide-react';
import { cn } from '../lib/utils';
import { fetchSignalContext, Signal } from '../lib/api';
import { format } from 'date-fns';
import { zhCN } from 'date-fns/locale';

interface SignalDetailsDrawerProps {
  signalId: string;
  isOpen: boolean;
  onClose: () => void;
}

// Apple Design colors
const APPLE_GREEN = '#34C759';
const APPLE_RED = '#FF3B30';
const APPLE_GRAY = '#86868B';
const APPLE_BLUE = '#007AFF';

export default function SignalDetailsDrawer({ signalId, isOpen, onClose }: SignalDetailsDrawerProps) {
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

    // Create chart
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

    // Prepare data
    // lightweight-charts displays UTC by default. We shift the timestamp to show local browser time.
    const tzOffsetMs = new Date().getTimezoneOffset() * 60 * 1000;

    const klineData: CandlestickData[] = data.klines.map((k) => ({
      time: ((k[0] - tzOffsetMs) / 1000) as UTCTimestamp,
      open: k[1],
      high: k[2],
      low: k[3],
      close: k[4],
    }));

    candleSeries.setData(klineData);

    // Find the exact signal candle by shifted timestamp
    const signalTimestamp = data.signal.kline_timestamp 
      ? Math.floor((data.signal.kline_timestamp - tzOffsetMs) / 1000) 
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

      {/* Drawer */}
      <div
        className={cn(
          "fixed top-0 right-0 h-full w-[85%] max-w-[900px] z-50",
          "bg-white/80 backdrop-blur-xl border-l border-gray-100/50 shadow-2xl",
          "transition-transform duration-500 ease-out",
          isOpen ? "translate-x-0" : "translate-x-full"
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-100/50">
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
          <div className="flex h-[calc(100%-90px)]">
            {/* Left: K-line Chart (65%) */}
            <div className="w-[65%] border-r border-gray-100/50 flex flex-col">
              <div className="p-4 border-b border-gray-100/50">
                <h3 className="text-sm font-medium text-gray-700">K 线复盘</h3>
                <p className="text-xs text-gray-400 mt-0.5">
                  信号前后各 10 根 K 线
                </p>
              </div>
              <div className="flex-1 p-4">
                <div
                  ref={chartContainerRef}
                  className="w-full h-full rounded-xl overflow-hidden border border-gray-100"
                />
              </div>
            </div>

            {/* Right: Data Panel (35%) */}
            <div className="w-[35%] flex flex-col overflow-y-auto">
              <div className="p-4 space-y-4">
                {/* Basic Info Card */}
                <div className="bg-white/60 rounded-2xl p-4 shadow-sm border border-gray-100/50">
                  <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">
                    基本信息
                  </h4>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-400">交易对</span>
                      <span className="text-sm font-semibold text-gray-900">
                        {data.signal.symbol.replace(':USDT', '')}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-400">周期</span>
                      <span className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs font-mono">
                        {data.signal.timeframe}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-400">方向</span>
                      <span className={cn(
                        "px-2 py-1 rounded text-xs font-medium",
                        data.signal.direction === 'long'
                          ? "bg-apple-green/10 text-apple-green"
                          : "bg-apple-red/10 text-apple-red"
                      )}>
                        {translateDirection(data.signal.direction)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-400">状态</span>
                      <span className={cn(
                        "px-2 py-1 rounded text-xs font-medium",
                        getStatusColor(data.signal.status)
                      )}>
                        {translateStatus(data.signal.status)}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Price Info Card */}
                <div className="bg-white/60 rounded-2xl p-4 shadow-sm border border-gray-100/50">
                  <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">
                    <Shield className="w-3 h-3 inline mr-1" />
                    价格信息
                  </h4>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-400">入场价</span>
                      <span className="text-sm font-mono text-gray-900">
                        {data.signal.entry_price ? Number(data.signal.entry_price).toFixed(2) : '-'}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-400">止损价</span>
                      <span className="text-sm font-mono text-apple-red">
                        {data.signal.stop_loss ? Number(data.signal.stop_loss).toFixed(2) : '-'}
                      </span>
                    </div>
                    {data.signal.take_profit && (
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-gray-400">止盈价</span>
                        <span className="text-sm font-mono text-apple-green">
                          {Number(data.signal.take_profit).toFixed(2)}
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Risk Info Card */}
                <div className="bg-white/60 rounded-2xl p-4 shadow-sm border border-gray-100/50">
                  <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">
                    <Target className="w-3 h-3 inline mr-1" />
                    风控参数
                  </h4>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-400">建议仓位</span>
                      <span className="text-sm font-mono text-gray-900">
                        {data.signal.position_size}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-400">杠杆</span>
                      <span className="text-sm font-mono text-gray-900">
                        {data.signal.leverage}x
                      </span>
                    </div>
                    {data.signal.pnl_ratio !== undefined && (
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-gray-400">盈亏比</span>
                        <span className={cn(
                          "text-sm font-mono",
                          Number(data.signal.pnl_ratio) >= 0
                            ? "text-apple-green"
                            : "text-apple-red"
                        )}>
                          {Number(data.signal.pnl_ratio) > 0 ? '+' : ''}
                          {Number(data.signal.pnl_ratio).toFixed(2)}
                        </span>
                      </div>
                    )}
                    {data.signal.win_rate && (
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-gray-400">胜率评估</span>
                        <span className="text-sm font-mono text-apple-blue">
                          {(data.signal.win_rate * 100).toFixed(1)}%
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Strategy Info Card */}
                <div className="bg-white/60 rounded-2xl p-4 shadow-sm border border-gray-100/50">
                  <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">
                    <Zap className="w-3 h-3 inline mr-1" />
                    策略信号
                  </h4>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-400">触发策略</span>
                      <span className={cn(
                        "px-2 py-1 rounded text-xs font-medium",
                        getStrategyBadgeClass(data.signal.strategy_name)
                      )}>
                        {translateStrategy(data.signal.strategy_name)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-400">形态打分</span>
                      <span className="text-sm font-mono text-gray-900">
                        {renderScore(data.signal.score)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-400">EMA 趋势</span>
                      <span className={cn(
                        "text-xs font-medium",
                        data.signal.ema_trend === 'bullish'
                          ? "text-apple-green"
                          : "text-apple-red"
                      )}>
                        {translateEmaTrend(data.signal.ema_trend)}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Time Info */}
                <div className="bg-white/60 rounded-2xl p-4 shadow-sm border border-gray-100/50">
                  <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">
                    <Clock className="w-3 h-3 inline mr-1" />
                    时间信息
                  </h4>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-400">K 线时间</span>
                      <span className="text-xs font-mono text-gray-600">
                        {data.signal.kline_timestamp
                          ? format(new Date(data.signal.kline_timestamp), 'MM-dd HH:mm:ss', { locale: zhCN })
                          : format(new Date(data.signal.created_at), 'MM-dd HH:mm:ss', { locale: zhCN })
                        }
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-400">创建时间</span>
                      <span className="text-xs font-mono text-gray-600">
                        {format(new Date(data.signal.created_at), 'MM-dd HH:mm:ss', { locale: zhCN })}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </>
  );
}
