import { OrderResponse, OrderStatus, OrderRole } from '../../types/order';
import { OrderStatusBadge } from './OrderStatusBadge';
import { OrderRoleBadge } from './OrderRoleBadge';
import { DirectionBadge } from './DirectionBadge';
import { DecimalDisplay } from './DecimalDisplay';
import { format } from 'date-fns';
import { ArrowRight } from 'lucide-react';
import { cn } from '../../lib/utils';

interface OrdersTableProps {
  orders: OrderResponse[];
  isLoading?: boolean;
  onOrderClick?: (orderId: string) => void;
}

export function OrdersTable({ orders, isLoading, onOrderClick }: OrdersTableProps) {
  if (isLoading) {
    return (
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <table className="w-full text-sm text-left">
          <thead className="text-xs text-gray-500 bg-gray-50/50 uppercase border-b border-gray-100">
            <tr>
              <th className="px-6 py-4 font-medium">订单 ID</th>
              <th className="px-6 py-4 font-medium">币种</th>
              <th className="px-6 py-4 font-medium">类型</th>
              <th className="px-6 py-4 font-medium">角色</th>
              <th className="px-6 py-4 font-medium">方向</th>
              <th className="px-6 py-4 font-medium">数量</th>
              <th className="px-6 py-4 font-medium">价格</th>
              <th className="px-6 py-4 font-medium">状态</th>
              <th className="px-6 py-4 font-medium">创建时间</th>
              <th className="px-6 py-4 font-medium">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {[...Array(10)].map((_, i) => (
              <tr key={i} className="animate-pulse">
                {[...Array(10)].map((_, j) => (
                  <td key={j} className="px-6 py-4">
                    <div className="h-4 bg-gray-100 rounded w-20" />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (orders.length === 0) {
    return (
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="px-6 py-20 text-center text-gray-400">
          没有找到订单记录
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
      <table className="w-full text-sm text-left whitespace-nowrap">
        <thead className="text-xs text-gray-500 bg-gray-50/50 uppercase border-b border-gray-100">
          <tr>
            <th className="px-6 py-4 font-medium">订单 ID</th>
            <th className="px-6 py-4 font-medium">币种</th>
            <th className="px-6 py-4 font-medium">类型</th>
            <th className="px-6 py-4 font-medium">角色</th>
            <th className="px-6 py-4 font-medium">方向</th>
            <th className="px-6 py-4 font-medium">数量</th>
            <th className="px-6 py-4 font-medium">价格</th>
            <th className="px-6 py-4 font-medium">状态</th>
            <th className="px-6 py-4 font-medium">创建时间</th>
            <th className="px-6 py-4 font-medium">操作</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {orders.map((order) => (
            <tr
              key={order.order_id}
              onClick={() => onOrderClick?.(order.order_id)}
              className="hover:bg-gray-50/50 transition-colors cursor-pointer group"
            >
              <td className="px-6 py-4">
                <span className="font-mono text-xs text-gray-600">
                  {order.order_id.slice(0, 8)}...{order.order_id.slice(-4)}
                </span>
              </td>
              <td className="px-6 py-4">
                <span className="font-semibold text-gray-900">
                  {order.symbol.replace(':USDT', '')}
                </span>
              </td>
              <td className="px-6 py-4">
                <span className="px-2 py-1 bg-gray-100 text-gray-600 rounded text-xs font-mono">
                  {order.order_type}
                </span>
              </td>
              <td className="px-6 py-4">
                <OrderRoleBadge role={order.role} />
              </td>
              <td className="px-6 py-4">
                <DirectionBadge direction={order.direction} />
              </td>
              <td className="px-6 py-4 text-right">
                <DecimalDisplay value={order.amount} decimals={4} />
              </td>
              <td className="px-6 py-4 text-right">
                <DecimalDisplay value={order.average_exec_price || order.price || order.trigger_price} decimals={2} />
              </td>
              <td className="px-6 py-4">
                <OrderStatusBadge status={order.status} />
              </td>
              <td className="px-6 py-4 text-gray-500">
                {format(new Date(order.created_at), 'MM-dd HH:mm:ss')}
              </td>
              <td className="px-6 py-4">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onOrderClick?.(order.order_id);
                  }}
                  className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1 text-xs text-apple-blue hover:underline"
                >
                  详情 <ArrowRight className="w-3 h-3" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
