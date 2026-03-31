import { JSX } from 'react';
import { OrderResponse, OrderStatus, OrderType } from '../../types/order';
import { X, Clock, CheckCircle, AlertCircle, XCircle, Timer } from 'lucide-react';
import { format } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import { cn } from '../../lib/utils';
import { DecimalDisplay } from './DecimalDisplay';
import { OrderStatusBadge } from './OrderStatusBadge';
import { OrderRoleBadge } from './OrderRoleBadge';
import { DirectionBadge } from './DirectionBadge';

interface OrderDetailsDrawerProps {
  order: OrderResponse | null;
  isOpen: boolean;
  onClose: () => void;
  onCancelOrder?: (orderId: string, symbol: string) => Promise<void>;
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

export function OrderDetailsDrawer({
  order,
  isOpen,
  onClose,
  onCancelOrder,
}: OrderDetailsDrawerProps) {
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
