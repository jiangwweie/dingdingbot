import { OrderResponse, OrderStatus } from '../../types/order';
import { OrderStatusBadge } from './OrderStatusBadge';
import { DecimalDisplay } from './DecimalDisplay';
import { TPProgressBar } from './TPProgressBar';
import { TakeProfitStats } from './TakeProfitStats';
import { Target, TrendingUp } from 'lucide-react';
import { cn } from '../../lib/utils';

interface TPChainDisplayProps {
  tpOrders: OrderResponse[];
  entryPrice: string;
  direction: 'LONG' | 'SHORT';
}

/**
 * 止盈订单链展示组件
 * 显示 TP1-TP5 的止盈订单状态和执行情况
 *
 * 功能:
 * - 止盈统计卡片（已实现/未实现/总目标）
 * - TP1-TP5 订单列表（价格、数量、状态、进度条）
 * - 执行进度可视化
 */
export function TPChainDisplay({ tpOrders, entryPrice, direction }: TPChainDisplayProps) {
  if (!tpOrders || tpOrders.length === 0) {
    return (
      <div className="text-sm text-gray-400 italic flex items-center gap-2">
        <Target className="w-4 h-4" />
        暂无止盈订单
      </div>
    );
  }

  // 按订单角色排序：TP1 -> TP2 -> TP3 -> TP4 -> TP5
  const sortedOrders = [...tpOrders].sort((a, b) => {
    const orderA = a.order_role.replace('TP', '');
    const orderB = b.order_role.replace('TP', '');
    return parseInt(orderA) - parseInt(orderB);
  });

  return (
    <div className="space-y-4">
      {/* 标题 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Target className="w-4 h-4 text-emerald-600" />
          <span className="text-sm font-semibold text-gray-700">
            止盈订单链
          </span>
        </div>
        <div className="text-xs text-gray-500">
          {sortedOrders.length} 个止盈目标
        </div>
      </div>

      {/* 止盈统计卡片 */}
      <TakeProfitStats
        tpOrders={tpOrders}
        entryPrice={entryPrice}
        direction={direction}
      />

      {/* TP 订单列表 */}
      <div className="space-y-3 pt-3 border-t border-gray-100">
        <div className="text-xs font-medium text-gray-500 uppercase tracking-wide">
          止盈订单明细
        </div>
        <div className="space-y-2">
          {sortedOrders.map((order) => (
            <div
              key={order.order_id}
              className="p-4 bg-gradient-to-br from-gray-50 to-white rounded-xl border border-gray-100 shadow-sm"
            >
              <TPProgressBar
                order={order}
                direction={direction}
                entryPrice={entryPrice}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
