import { OrderResponse, OrderStatus } from '../../types/order';
import { Target, Check, Loader } from 'lucide-react';
import { cn } from '../../lib/utils';

interface TPProgressBarProps {
  order: OrderResponse;
  direction: 'LONG' | 'SHORT';
  entryPrice: string;
}

/**
 * 单个止盈订单进度条组件
 * 显示 TP 订单的成交进度和盈亏情况
 */
export function TPProgressBar({ order, direction, entryPrice }: TPProgressBarProps) {
  const orderPrice = order.price ? parseFloat(order.price) : null;
  const orderAmount = parseFloat(order.amount);
  const filledAmount = parseFloat(order.filled_amount);

  // 计算进度百分比
  const progressPercent = orderAmount > 0 ? (filledAmount / orderAmount) * 100 : 0;
  const isFilled = order.status === OrderStatus.FILLED;
  const isPartiallyFilled = order.status === OrderStatus.PARTIALLY_FILLED;
  const isPending = order.status === OrderStatus.PENDING || order.status === OrderStatus.OPEN;

  // 计算盈亏比例（基于入场价和止盈价）
  let pnlPercent = 0;
  if (orderPrice && entryPrice) {
    if (direction === 'LONG') {
      pnlPercent = ((orderPrice - parseFloat(entryPrice)) / parseFloat(entryPrice)) * 100;
    } else {
      pnlPercent = ((parseFloat(entryPrice) - orderPrice) / parseFloat(entryPrice)) * 100;
    }
  }

  const isProfitable = pnlPercent >= 0;

  return (
    <div className="space-y-2">
      {/* 订单基本信息行 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className={cn(
            "w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold",
            isFilled
              ? "bg-apple-green text-white"
              : isPartiallyFilled
                ? "bg-yellow-100 text-yellow-700"
                : "bg-gray-100 text-gray-500"
          )}>
            {isFilled ? (
              <Check className="w-3 h-3" />
            ) : isPartiallyFilled ? (
              <Loader className="w-3 h-3 animate-spin" />
            ) : (
              <Target className="w-3 h-3" />
            )}
          </div>
          <span className="text-sm font-semibold text-gray-700">
            {order.role}
          </span>
          {orderPrice && (
            <span className="text-xs text-gray-500">
              目标价：${orderPrice.toFixed(2)}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {orderPrice && (
            <span className={cn(
              "text-xs font-medium px-1.5 py-0.5 rounded",
              isProfitable
                ? "bg-green-50 text-green-700"
                : "bg-red-50 text-red-700"
            )}>
              {isProfitable ? '+' : ''}{pnlPercent.toFixed(2)}%
            </span>
          )}
        </div>
      </div>

      {/* 进度条 */}
      <div className="relative">
        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
          <div
            className={cn(
              "h-full transition-all duration-500 ease-out",
              isFilled
                ? "bg-apple-green"
                : isPartiallyFilled
                  ? "bg-yellow-500"
                  : "bg-gray-300"
            )}
            style={{ width: `${progressPercent}%` }}
          />
        </div>

        {/* 进度百分比标签 */}
        <div className="absolute -top-5 right-0 text-xs font-medium text-gray-500">
          {progressPercent.toFixed(0)}%
        </div>
      </div>

      {/* 成交详情 */}
      <div className="flex items-center justify-between text-xs text-gray-500">
        <span>
          已成交：{filledAmount.toFixed(4)} / {orderAmount.toFixed(4)}
        </span>
        {isFilled && (
          <span className="text-apple-green font-medium">
            已完成
          </span>
        )}
        {isPartiallyFilled && (
          <span className="text-yellow-600 font-medium">
            执行中...
          </span>
        )}
        {isPending && (
          <span className="text-gray-400 font-medium">
            等待触发
          </span>
        )}
      </div>
    </div>
  );
}
