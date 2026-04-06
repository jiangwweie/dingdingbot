import { useState, useEffect, useRef, JSX } from 'react';
import {
  createChart,
  createSeriesMarkers,
  IChartApi,
  ISeriesApi,
  CandlestickData,
  UTCTimestamp,
  CandlestickSeries,
  SeriesMarker,
  ColorType,
  SeriesMarkerPosition,
} from 'lightweight-charts';
import { OrderResponse, OrderStatus, OrderType, OrderRole } from '../../types/order';
import { X, Clock, CheckCircle, AlertCircle, XCircle, Timer, Activity } from 'lucide-react';
import { format } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import { cn } from '../../lib/utils';
import { DecimalDisplay } from './DecimalDisplay';
import { OrderStatusBadge } from './OrderStatusBadge';
import { OrderRoleBadge } from './OrderRoleBadge';
import { DirectionBadge } from './DirectionBadge';
import { fetchOrderKlineContext } from '../../lib/api';

// Apple Design colors
const APPLE_GREEN = '#34C759';
const APPLE_RED = '#FF3B30';
const APPLE_GRAY = '#86868B';
const APPLE_BLUE = '#007AFF';

interface OrderDetailsDrawerProps {
  order: OrderResponse | null;
  isOpen: boolean;
  onClose: () => void;
  onCancelOrder?: (orderId: string, symbol: string) => Promise<void>;
  showKlineChart?: boolean;
}

const statusIcon: Record<OrderStatus, JSX.Element> = {
  CREATED: <Timer className="w-5 h-5" />,
  SUBMITTED: <Activity className="w-5 h-5" />,
  PENDING: <Timer className="w-5 h-5" />,
  OPEN: <Clock className="w-5 h-5" />,
  FILLED: <CheckCircle className="w-5 h-5" />,
  CANCELED: <XCircle className="w-5 h-5" />,
  REJECTED: <AlertCircle className="w-5 h-5" />,
  EXPIRED: <Timer className="w-5 h-5" />,
  PARTIALLY_FILLED: <Clock className="w-5 h-5" />,
};

const orderTypeLabels: Record<OrderType, string> = {
  MARKET: '市价单',
  LIMIT: '限价单',
  STOP_MARKET: '止损市价单',
  STOP_LIMIT: '止损限价单',
};

/**
 * Get marker label by order role
 */
function getOrderRoleLabel(role: string): string {
  const labels: Record<string, string> = {
    ENTRY: '入场',
    TP1: 'TP1',
    TP2: 'TP2',
    TP3: 'TP3',
    TP4: 'TP4',
    TP5: 'TP5',
    SL: '止损',
  };
  return labels[role] || role;
}

/**
 * Get color by order role and direction
 */
function getOrderRoleColor(role: string, direction: 'LONG' | 'SHORT'): string {
  if (role === 'ENTRY') {
    return direction === 'LONG' ? APPLE_GREEN : APPLE_RED;
  }
  if (role.startsWith('TP')) {
    return APPLE_GREEN;
  }
  if (role === 'SL') {
    return APPLE_RED;
  }
  return APPLE_GRAY;
}

/**
 * Get marker shape by order role
 */
function getMarkerShape(role: string): 'arrowUp' | 'circle' {
  return role === 'ENTRY' ? 'arrowUp' : 'circle';
}

/**
 * Get marker position by order role and direction
 */
function getMarkerPosition(role: string, direction: 'LONG' | 'SHORT'): SeriesMarkerPosition {
  if (role === 'ENTRY') {
    return direction === 'LONG' ? 'belowBar' : 'aboveBar';
  }
  return direction === 'LONG' ? 'aboveBar' : 'belowBar';
}

interface OrderKlineData {
  order: OrderResponse;
  klines: number[][]; // [timestamp_ms, open, high, low, close, volume]
}

export function OrderDetailsDrawer({
  order,
  isOpen,
  onClose,
  onCancelOrder,
  showKlineChart = true,
}: OrderDetailsDrawerProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const [klineData, setKlineData] = useState<OrderKlineData | null>(null);
  const [isLoadingKline, setIsLoadingKline] = useState(false);
  const [klineError, setKlineError] = useState<string | null>(null);

  // Fetch kline data when drawer opens
  useEffect(() => {
    if (!isOpen || !order || !showKlineChart) return;

    const fetchKlineData = async () => {
      setIsLoadingKline(true);
      setKlineError(null);
      try {
        const result = await fetchOrderKlineContext(order.order_id, order.symbol);
        setKlineData(result);
      } catch (err: any) {
        console.error('Failed to fetch kline data:', err);
        setKlineError(err.message || '加载 K 线数据失败');
      } finally {
        setIsLoadingKline(false);
      }
    };

    fetchKlineData();
  }, [order, isOpen, showKlineChart]);

  // Initialize chart when data is loaded
  useEffect(() => {
    if (!isOpen || !klineData || !chartContainerRef.current) return;

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
      height: 300,
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

    // Prepare K-line data - convert to local browser time
    const tzOffsetMs = new Date().getTimezoneOffset() * 60 * 1000;

    const candleData: CandlestickData[] = klineData.klines.map((k) => ({
      time: ((k[0] - tzOffsetMs) / 1000) as UTCTimestamp,
      open: k[1],
      high: k[2],
      low: k[3],
      close: k[4],
    }));

    candleSeries.setData(candleData);

    // Find the order candle by filled_at or created_at timestamp
    const orderTimestamp = klineData.order.filled_at || klineData.order.created_at;
    const shiftedOrderTimestamp = Math.floor((orderTimestamp - tzOffsetMs) / 1000);
    const orderCandle = candleData.find(k => Number(k.time) === shiftedOrderTimestamp);

    if (orderCandle) {
      const direction = klineData.order.direction as 'LONG' | 'SHORT';
      const orderRole = klineData.order.order_role as string;

      // Create order markers using TradingView SeriesMarker API
      const markers: SeriesMarker<UTCTimestamp>[] = [
        {
          time: orderCandle.time as UTCTimestamp,
          position: getMarkerPosition('ENTRY', direction),
          color: getOrderRoleColor('ENTRY', direction),
          shape: getMarkerShape('ENTRY'),
          text: '入场',
          size: 2,
        },
      ];

      const markersApi = createSeriesMarkers(candleSeries, markers);

      // Add entry price horizontal line
      const entryPrice = parseFloat(
        klineData.order.average_exec_price || klineData.order.price || '0'
      );
      if (entryPrice > 0) {
        candleSeries.createPriceLine({
          price: entryPrice,
          color: APPLE_BLUE,
          lineWidth: 2,
          lineStyle: 3, // Dotted
          axisLabelVisible: true,
          title: '入场价',
        });
      }

      // Add stop loss horizontal line
      if (klineData.order.stop_loss) {
        candleSeries.createPriceLine({
          price: parseFloat(klineData.order.stop_loss),
          color: APPLE_RED,
          lineWidth: 1,
          lineStyle: 2, // Dashed
          axisLabelVisible: true,
          title: '止损价',
        });
      }

      // Add take profit horizontal line
      if (klineData.order.take_profit) {
        candleSeries.createPriceLine({
          price: parseFloat(klineData.order.take_profit),
          color: APPLE_GREEN,
          lineWidth: 1,
          lineStyle: 2, // Dashed
          axisLabelVisible: true,
          title: '止盈价',
        });
      }
    }

    // Fit content to show all candles
    chart.timeScale().fitContent();

    // Handle window resize
    const handleResize = () => {
      if (chartContainerRef.current && chart) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
    };
  }, [klineData, isOpen]);

  if (!isOpen || !order) return null;

  const isCancellable = order.status === 'OPEN' || order.status === 'PENDING' || order.status === 'PARTIALLY_FILLED';
  const filledPercent = order.quantity !== '0'
    ? (parseFloat(order.filled_qty || '0') / parseFloat(order.quantity) * 100)
    : 0;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/20 z-40"
        onClick={onClose}
      />

      {/* Drawer */}
      <div className="fixed right-0 top-0 h-full w-full max-w-lg bg-white shadow-2xl z-50 overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">订单详情</h2>
            <p className="text-xs text-gray-500 mt-0.5">
              {order.order_id.slice(0, 8)}...{order.order_id.slice(-4)}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Status & Basic Info */}
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              {statusIcon[order.status]}
              <OrderStatusBadge status={order.status} />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <div className="text-xs text-gray-500">币种</div>
                <div className="text-base font-semibold text-gray-900">
                  {order.symbol.replace(':USDT', '')}
                </div>
              </div>
              <div className="space-y-1">
                <div className="text-xs text-gray-500">订单类型</div>
                <div className="text-base text-gray-900">
                  {orderTypeLabels[order.order_type as OrderType]}
                </div>
              </div>
            </div>
          </div>

          {/* Order Role & Direction */}
          <div className="flex items-center gap-3">
            <OrderRoleBadge role={order.order_role} />
            <DirectionBadge direction={order.direction} />
          </div>

          {/* Order Parameters */}
          <div className="bg-gray-50 rounded-xl p-4 space-y-3">
            <h3 className="text-sm font-semibold text-gray-900">订单参数</h3>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <div className="text-xs text-gray-500">订单数量</div>
                <DecimalDisplay value={order.quantity} decimals={4} className="text-base" />
              </div>
              <div className="space-y-1">
                <div className="text-xs text-gray-500">已成交数量</div>
                <DecimalDisplay value={order.filled_qty} decimals={4} className="text-base" />
              </div>
              <div className="space-y-1">
                <div className="text-xs text-gray-500">
                  {order.order_type === 'MARKET' || order.order_type === 'STOP_MARKET' ? '执行价格' : '限价'}
                </div>
                <DecimalDisplay value={order.price} decimals={2} className="text-base" />
              </div>
              <div className="space-y-1">
                <div className="text-xs text-gray-500">触发价格</div>
                <DecimalDisplay value={order.trigger_price} decimals={2} className="text-base" />
              </div>
            </div>

            {order.average_exec_price && (
              <div className="space-y-1 pt-2 border-t border-gray-200">
                <div className="text-xs text-gray-500">平均成交价格</div>
                <DecimalDisplay value={order.average_exec_price} decimals={2} className="text-base" />
              </div>
            )}

            {order.fee_paid && (
              <div className="space-y-1">
                <div className="text-xs text-gray-500">手续费</div>
                <DecimalDisplay value={order.fee_paid} decimals={4} className="text-base" />
              </div>
            )}
          </div>

          {/* Progress Bar */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-gray-500">成交进度</span>
              <span className="font-medium text-gray-900">{filledPercent.toFixed(1)}%</span>
            </div>
            <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
              <div
                className={cn(
                  'h-full rounded-full transition-all',
                  filledPercent === 100 ? 'bg-green-500' :
                  filledPercent > 0 ? 'bg-blue-500' :
                  'bg-gray-300'
                )}
                style={{ width: `${filledPercent}%` }}
              />
            </div>
          </div>

          {/* Reduce Only */}
          {order.reduce_only && (
            <div className="flex items-center gap-2 text-xs">
              <span className="px-2 py-1 bg-orange-100 text-orange-700 rounded font-medium">
                仅减仓模式
              </span>
            </div>
          )}

          {/* Client Order ID */}
          {order.client_order_id && (
            <div className="space-y-1">
              <div className="text-xs text-gray-500">客户端订单 ID</div>
              <div className="text-xs font-mono text-gray-700">{order.client_order_id}</div>
            </div>
          )}

          {/* Strategy Name */}
          {order.strategy_name && (
            <div className="space-y-1">
              <div className="text-xs text-gray-500">关联策略</div>
              <div className="text-sm text-gray-900">{order.strategy_name}</div>
            </div>
          )}

          {/* Stop Loss & Take Profit */}
          <div className="grid grid-cols-2 gap-4">
            {order.stop_loss && (
              <div className="space-y-1">
                <div className="text-xs text-gray-500">止损价格</div>
                <DecimalDisplay value={order.stop_loss} decimals={2} className="text-base text-apple-red" />
              </div>
            )}
            {order.take_profit && (
              <div className="space-y-1">
                <div className="text-xs text-gray-500">止盈价格</div>
                <DecimalDisplay value={order.take_profit} decimals={2} className="text-base text-apple-green" />
              </div>
            )}
          </div>

          {/* Timestamps */}
          <div className="space-y-3 pt-4 border-t border-gray-200">
            <div className="flex items-center justify-between text-xs">
              <span className="text-gray-500">创建时间</span>
              <span className="font-mono text-gray-700">
                {format(new Date(order.created_at), 'yyyy-MM-dd HH:mm:ss', { locale: zhCN })}
              </span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-gray-500">更新时间</span>
              <span className="font-mono text-gray-700">
                {format(new Date(order.updated_at), 'yyyy-MM-dd HH:mm:ss', { locale: zhCN })}
              </span>
            </div>
          </div>

          {/* K-line Chart */}
          {showKlineChart && (
            <div className="pt-4 border-t border-gray-200">
              <h3 className="text-sm font-semibold text-gray-900 mb-4 flex items-center gap-2">
                <Activity className="w-4 h-4" />
                K 线走势图
              </h3>

              {isLoadingKline ? (
                <div className="h-[300px] flex items-center justify-center">
                  <div className="text-center">
                    <div className="w-6 h-6 border-2 border-gray-300 border-t-black rounded-full animate-spin mx-auto" />
                    <p className="text-xs text-gray-500 mt-2">加载 K 线数据...</p>
                  </div>
                </div>
              ) : klineError ? (
                <div className="h-[300px] flex items-center justify-center">
                  <div className="text-center text-red-500">
                    <AlertCircle className="w-8 h-8 mx-auto mb-2" />
                    <p className="text-sm">{klineError}</p>
                  </div>
                </div>
              ) : !klineData || klineData.klines.length === 0 ? (
                <div className="h-[300px] flex items-center justify-center">
                  <div className="text-center text-gray-400">
                    <Activity className="w-8 h-8 mx-auto mb-2 opacity-20" />
                    <p className="text-sm">暂无 K 线数据</p>
                  </div>
                </div>
              ) : (
                <div className="h-[300px]">
                  <div
                    ref={chartContainerRef}
                    className="w-full h-full rounded-lg overflow-hidden border border-gray-100"
                  />
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer Actions */}
        {isCancellable && onCancelOrder && (
          <div className="p-6 border-t border-gray-100 bg-gray-50">
            <button
              onClick={async () => {
                try {
                  await onCancelOrder(order.order_id, order.symbol);
                  onClose();
                } catch (error) {
                  console.error('Failed to cancel order:', error);
                }
              }}
              className="w-full py-2.5 px-4 bg-apple-red text-white rounded-lg font-medium hover:bg-red-600 transition-colors"
            >
              取消订单
            </button>
          </div>
        )}
      </div>
    </>
  );
}
