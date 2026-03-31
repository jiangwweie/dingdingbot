import { OrderResponse, OrderStatus } from '../../types/order';
import { TrendingUp, TrendingDown, DollarSign, Percent, Target, Check } from 'lucide-react';
import { cn } from '../../lib/utils';

interface TakeProfitStatsProps {
  tpOrders: OrderResponse[];
  entryPrice: string;
  direction: 'LONG' | 'SHORT';
}

/**
 * 止盈统计卡片组件
 * 显示已实现止盈、未实现止盈、执行进度等统计信息
 */
export function TakeProfitStats({ tpOrders, entryPrice, direction }: TakeProfitStatsProps) {
  const entryPriceNum = parseFloat(entryPrice);

  // 分类订单
  const filledOrders = tpOrders.filter(o => o.status === OrderStatus.FILLED);
  const partiallyFilledOrders = tpOrders.filter(o => o.status === OrderStatus.PARTIALLY_FILLED);
  const pendingOrders = tpOrders.filter(o => o.status === OrderStatus.PENDING || o.status === OrderStatus.OPEN);

  // 计算已实现止盈（已成交订单的盈亏）
  let realizedProfit = 0;
  filledOrders.forEach(order => {
    if (order.price && order.filled_qty) {
      const orderPrice = parseFloat(order.price);
      const filledQty = parseFloat(order.filled_qty);
      if (direction === 'LONG') {
        realizedProfit += (orderPrice - entryPriceNum) * filledQty;
      } else {
        realizedProfit += (entryPriceNum - orderPrice) * filledQty;
      }
    }
  });

  // 计算未实现止盈（部分成交订单的未成交部分）
  let unrealizedProfit = 0;
  partiallyFilledOrders.forEach(order => {
    if (order.price && order.quantity && order.filled_qty) {
      const orderPrice = parseFloat(order.price);
      const remainingQty = parseFloat(order.quantity) - parseFloat(order.filled_qty);
      if (direction === 'LONG') {
        unrealizedProfit += (orderPrice - entryPriceNum) * remainingQty;
      } else {
        unrealizedProfit += (entryPriceNum - orderPrice) * remainingQty;
      }
    }
  });

  // 计算总止盈目标（所有订单完全成交的理论盈亏）
  let totalTargetProfit = 0;
  tpOrders.forEach(order => {
    if (order.price && order.quantity) {
      const orderPrice = parseFloat(order.price);
      const qty = parseFloat(order.quantity);
      if (direction === 'LONG') {
        totalTargetProfit += (orderPrice - entryPriceNum) * qty;
      } else {
        totalTargetProfit += (entryPriceNum - orderPrice) * qty;
      }
    }
  });

  // 计算执行进度
  const totalAmount = tpOrders.reduce((sum, o) => sum + parseFloat(o.quantity), 0);
  const filledAmount = tpOrders.reduce((sum, o) => sum + parseFloat(o.filled_qty), 0);
  const executionProgress = totalAmount > 0 ? (filledAmount / totalAmount) * 100 : 0;

  const isProfit = realizedProfit >= 0;
  const isUnrealizedProfit = unrealizedProfit >= 0;
  const isTotalTargetProfit = totalTargetProfit >= 0;

  return (
    <div className="space-y-3">
      {/* 统计卡片网格 */}
      <div className="grid grid-cols-2 gap-3">
        {/* 已实现止盈 */}
        <div className="bg-gradient-to-br from-green-50 to-emerald-50 rounded-xl p-4 border border-green-100">
          <div className="flex items-center gap-2 mb-2">
            <Check className="w-4 h-4 text-green-600" />
            <span className="text-xs font-medium text-gray-600">已实现止盈</span>
          </div>
          <div className={cn(
            "text-lg font-bold font-mono",
            isProfit ? "text-apple-green" : "text-apple-red"
          )}>
            {isProfit ? '+' : ''}{realizedProfit.toFixed(2)} USDT
          </div>
          <div className="text-xs text-gray-500 mt-0.5">
            {filledOrders.length} 单已完成
          </div>
        </div>

        {/* 未实现止盈 */}
        <div className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-xl p-4 border border-blue-100">
          <div className="flex items-center gap-2 mb-2">
            <Target className="w-4 h-4 text-blue-600" />
            <span className="text-xs font-medium text-gray-600">未实现止盈</span>
          </div>
          <div className={cn(
            "text-lg font-bold font-mono",
            isUnrealizedProfit ? "text-blue-600" : "text-red-500"
          )}>
            {isUnrealizedProfit ? '+' : ''}{unrealizedProfit.toFixed(2)} USDT
          </div>
          <div className="text-xs text-gray-500 mt-0.5">
            {partiallyFilledOrders.length} 单执行中
          </div>
        </div>

        {/* 总目标止盈 */}
        <div className="bg-gradient-to-br from-purple-50 to-violet-50 rounded-xl p-4 border border-purple-100">
          <div className="flex items-center gap-2 mb-2">
            <DollarSign className="w-4 h-4 text-purple-600" />
            <span className="text-xs font-medium text-gray-600">总目标止盈</span>
          </div>
          <div className={cn(
            "text-lg font-bold font-mono",
            isTotalTargetProfit ? "text-purple-600" : "text-red-500"
          )}>
            {isTotalTargetProfit ? '+' : ''}{totalTargetProfit.toFixed(2)} USDT
          </div>
          <div className="text-xs text-gray-500 mt-0.5">
            理论最大盈亏
          </div>
        </div>

        {/* 执行进度 */}
        <div className="bg-gradient-to-br from-orange-50 to-amber-50 rounded-xl p-4 border border-orange-100">
          <div className="flex items-center gap-2 mb-2">
            <Percent className="w-4 h-4 text-orange-600" />
            <span className="text-xs font-medium text-gray-600">执行进度</span>
          </div>
          <div className="text-lg font-bold text-orange-600">
            {executionProgress.toFixed(1)}%
          </div>
          <div className="text-xs text-gray-500 mt-0.5">
            {filledAmount.toFixed(4)} / {totalAmount.toFixed(4)}
          </div>
        </div>
      </div>

      {/* 详细进度条 */}
      <div className="pt-3 border-t border-gray-100">
        <div className="flex items-center justify-between text-xs text-gray-500 mb-2">
          <span>总体执行进度</span>
          <span className="font-medium">
            {filledOrders.length}/{tpOrders.length} 已完成
          </span>
        </div>
        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
          <div
            className={cn(
              "h-full transition-all duration-500 ease-out",
              executionProgress === 100
                ? "bg-apple-green"
                : executionProgress > 0
                  ? "bg-gradient-to-r from-apple-green to-emerald-500"
                  : "bg-gray-300"
            )}
            style={{ width: `${executionProgress}%` }}
          />
        </div>
      </div>
    </div>
  );
}
