import { OrderResponse, OrderStatus } from '../../types/order';
import { OrderStatusBadge } from './OrderStatusBadge';
import { DecimalDisplay } from './DecimalDisplay';
import { Check, X } from 'lucide-react';

interface TPChainDisplayProps {
  tpOrders: OrderResponse[];
  entryPrice: string;
  direction: 'LONG' | 'SHORT';
}

/**
 * 止盈订单链展示组件
 * 显示 TP1-TP5 的止盈订单状态和执行情况
 */
export function TPChainDisplay({ tpOrders, entryPrice, direction }: TPChainDisplayProps) {
  if (!tpOrders || tpOrders.length === 0) {
    return (
      <div className="text-sm text-gray-400 italic">
        暂无止盈订单
      </div>
    );
  }

  // 按订单角色排序：TP1 -> TP2 -> TP3 -> TP4 -> TP5
  const sortedOrders = [...tpOrders].sort((a, b) => {
    const orderA = a.role.replace('TP', '');
    const orderB = b.role.replace('TP', '');
    return parseInt(orderA) - parseInt(orderB);
  });

  return (
    <div className="space-y-3">
      <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
        止盈订单链
      </div>
      <div className="space-y-2">
        {sortedOrders.map((order) => {
          const isFilled = order.status === 'FILLED';
          const isPartiallyFilled = order.status === 'PARTIALLY_FILLED';

          return (
            <div
              key={order.order_id}
              className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-100"
            >
              <div className="flex items-center gap-3">
                <div className="flex items-center justify-center w-8 h-8 rounded-full bg-emerald-100 text-emerald-700 font-bold text-xs">
                  {order.role}
                </div>
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-gray-900">
                      止盈价格
                    </span>
                    <DecimalDisplay value={order.price} decimals={2} className="text-sm" />
                  </div>
                  <div className="flex items-center gap-3 text-xs text-gray-500">
                    <span>
                      数量：<DecimalDisplay value={order.amount} decimals={4} />
                    </span>
                    {isFilled && (
                      <span className="text-apple-green">
                        已成交：<DecimalDisplay value={order.filled_amount} decimals={4} />
                      </span>
                    )}
                    {isPartiallyFilled && (
                      <span className="text-yellow-600">
                        已成交：<DecimalDisplay value={order.filled_amount} decimals={4} /> / {order.amount}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-3">
                {isFilled ? (
                  <Check className="w-5 h-5 text-apple-green" />
                ) : isPartiallyFilled ? (
                  <div className="w-5 h-5 rounded-full border-2 border-yellow-500 border-t-transparent animate-spin" />
                ) : (
                  <div className="w-5 h-5 rounded-full border-2 border-gray-300" />
                )}
                <OrderStatusBadge status={order.status} />
              </div>
            </div>
          );
        })}
      </div>

      {/* 执行进度 */}
      <div className="pt-2 border-t border-gray-100">
        <div className="flex items-center justify-between text-xs">
          <span className="text-gray-500">执行进度</span>
          <span className="font-medium text-gray-900">
            {tpOrders.filter(o => o.status === 'FILLED').length} / {tpOrders.length} 已完成
          </span>
        </div>
        <div className="mt-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-emerald-500 transition-all duration-300"
            style={{
              width: `${(tpOrders.filter(o => o.status === 'FILLED').length / tpOrders.length) * 100}%`
            }}
          />
        </div>
      </div>
    </div>
  );
}
