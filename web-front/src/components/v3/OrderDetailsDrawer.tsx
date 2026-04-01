import { useState, useEffect, JSX } from 'react';
import { OrderResponse, OrderStatus, OrderType } from '../../types/order';
import { X, Clock, CheckCircle, AlertCircle, XCircle, Timer, TrendingUp, TrendingDown, Activity } from 'lucide-react';
import { format } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import { cn } from '../../lib/utils';
import { DecimalDisplay } from './DecimalDisplay';
import { OrderStatusBadge } from './OrderStatusBadge';
import { OrderRoleBadge } from './OrderRoleBadge';
import { DirectionBadge } from './DirectionBadge';
import { fetchOrderKlineContext } from '../../lib/api';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceDot,
} from 'recharts';

interface OrderDetailsDrawerProps {
  order: OrderResponse | null;
  isOpen: boolean;
  onClose: () => void;
  onCancelOrder?: (orderId: string, symbol: string) => Promise<void>;
  showKlineChart?: boolean;  // 是否显示 K 线图
}

interface KlineDataPoint {
  timestamp: number;
  date: string;
  price: number;
  high: number;
  low: number;
  open: number;
  close: number;
  volume: number;
}

interface OrderMarker {
  timestamp: number;
  price: number;
  type: 'entry' | 'tp' | 'sl' | 'exit';
  label: string;
}

const statusIcon: Record<OrderStatus, JSX.Element> = {
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
 * Get marker color by type
 */
function getMarkerColor(type: 'entry' | 'tp' | 'sl' | 'exit'): string {
  switch (type) {
    case 'entry':
      return '#000000'; // Black for entry
    case 'tp':
      return '#16a34a'; // Green for take profit
    case 'sl':
      return '#dc2626'; // Red for stop loss
    case 'exit':
      return '#6b7280'; // Gray for exit
    default:
      return '#9ca3af';
  }
}

/**
 * Custom tooltip for kline chart
 */
function KlineTooltip({ active, payload, label }: any) {
  if (active && payload && payload.length) {
    const price = payload[0]?.value;
    const open = payload[0]?.payload.open;
    const high = payload[0]?.payload.high;
    const low = payload[0]?.payload.low;
    const close = payload[0]?.payload.close;
    const isUp = close >= open;

    return (
      <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-3 text-xs">
        <p className="font-medium text-gray-700 mb-2">{label}</p>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          <span className="text-gray-500">开：</span>
          <span className="font-medium">{open?.toFixed(2)}</span>
          <span className="text-gray-500">高：</span>
          <span className="font-medium">{high?.toFixed(2)}</span>
          <span className="text-gray-500">低：</span>
          <span className="font-medium">{low?.toFixed(2)}</span>
          <span className="text-gray-500">收：</span>
          <span className={cn('font-medium', isUp ? 'text-green-600' : 'text-red-600')}>
            {close?.toFixed(2)}
          </span>
        </div>
      </div>
    );
  }
  return null;
}

export function OrderDetailsDrawer({
  order,
  isOpen,
  onClose,
  onCancelOrder,
  showKlineChart = true,
}: OrderDetailsDrawerProps) {
  const [klineData, setKlineData] = useState<KlineDataPoint[]>([]);
  const [orderMarkers, setOrderMarkers] = useState<OrderMarker[]>([]);
  const [isLoadingKline, setIsLoadingKline] = useState(false);
  const [klineError, setKlineError] = useState<string | null>(null);

  // Fetch kline data when order changes and drawer opens
  useEffect(() => {
    if (!isOpen || !order || !showKlineChart) return;

    const fetchKlineData = async () => {
      setIsLoadingKline(true);
      setKlineError(null);
      try {
        const result = await fetchOrderKlineContext(order.order_id, order.symbol);

        // Transform kline data
        const klines: KlineDataPoint[] = result.klines.map((k: number[]) => ({
          timestamp: k[0],
          date: format(new Date(k[0]), 'MM-dd HH:mm'),
          price: k[4], // close price
          open: k[1],
          high: k[2],
          low: k[3],
          close: k[4],
          volume: k[5],
        }));

        setKlineData(klines);

        // Build order markers
        const markers: OrderMarker[] = [];

        // Entry marker
        if (result.order.average_exec_price || result.order.price) {
          const entryPrice = parseFloat(result.order.average_exec_price || result.order.price || '0');
          const entryTime = result.order.filled_at || result.order.created_at;
          markers.push({
            timestamp: entryTime,
            price: entryPrice,
            type: 'entry',
            label: `入场 ${order.direction === 'LONG' ? '📈' : '📉'}`,
          });
        }

        // Stop loss marker
        if (order.stop_loss) {
          markers.push({
            timestamp: klines[klines.length - 1]?.timestamp || Date.now(),
            price: parseFloat(order.stop_loss),
            type: 'sl',
            label: '止损',
          });
        }

        // Take profit marker
        if (order.take_profit) {
          markers.push({
            timestamp: klines[klines.length - 1]?.timestamp || Date.now(),
            price: parseFloat(order.take_profit),
            type: 'tp',
            label: '止盈',
          });
        }

        setOrderMarkers(markers);
      } catch (err: any) {
        console.error('Failed to fetch kline data:', err);
        setKlineError(err.message || '加载 K 线数据失败');
      } finally {
        setIsLoadingKline(false);
      }
    };

    fetchKlineData();
  }, [order, isOpen, showKlineChart]);

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
              ) : klineData.length === 0 ? (
                <div className="h-[300px] flex items-center justify-center">
                  <div className="text-center text-gray-400">
                    <Activity className="w-8 h-8 mx-auto mb-2 opacity-20" />
                    <p className="text-sm">暂无 K 线数据</p>
                  </div>
                </div>
              ) : (
                <div className="h-[300px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={klineData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                      <XAxis
                        dataKey="date"
                        tick={{ fontSize: 10, fill: '#6b7280' }}
                        tickFormatter={(value) => value.slice(0, 5)}
                        minTickGap={30}
                      />
                      <YAxis
                        tick={{ fontSize: 10, fill: '#6b7280' }}
                        tickFormatter={(value) => value.toFixed(2)}
                        domain={['dataMin', 'dataMax']}
                        width={60}
                      />
                      <Tooltip
                        content={<KlineTooltip />}
                        labelFormatter={(label) => `时间：${label}`}
                      />
                      <Line
                        type="monotone"
                        dataKey="price"
                        name="价格"
                        stroke="#000000"
                        strokeWidth={1.5}
                        dot={false}
                        isAnimationActive={false}
                      />
                      {/* Order markers */}
                      {orderMarkers.map((marker, index) => (
                        <ReferenceDot
                          key={`${marker.type}-${index}`}
                          x={marker.timestamp}
                          y={marker.price}
                          r={6}
                          fill={getMarkerColor(marker.type)}
                          stroke={getMarkerColor(marker.type)}
                          strokeWidth={2}
                          label={{
                            value: marker.label,
                            position: 'top',
                            fill: getMarkerColor(marker.type),
                            fontSize: 11,
                            fontWeight: 500,
                          }}
                        />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
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
