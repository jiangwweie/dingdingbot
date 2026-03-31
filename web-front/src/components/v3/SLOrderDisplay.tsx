import { OrderResponse, OrderStatus } from '../../types/order';
import { OrderStatusBadge } from './OrderStatusBadge';
import { DecimalDisplay } from './DecimalDisplay';
import { Shield, AlertTriangle, Check, ArrowRightLeft } from 'lucide-react';
import { cn } from '../../lib/utils';

interface SLOrderDisplayProps {
  slOrder: OrderResponse | null;
  entryPrice: string;
  direction: 'LONG' | 'SHORT';
  markPrice?: string | null; // 当前标记价格
}

/**
 * 止损订单展示组件
 * 显示 SL 止损订单的状态、执行情况和止损距离
 *
 * 功能:
 * - 止损订单基本信息（触发价、数量、状态）
 * - 止损距离百分比（当前价到止损价的距离）
 * - 止损进度条可视化
 */
export function SLOrderDisplay({ slOrder, entryPrice, direction, markPrice }: SLOrderDisplayProps) {
  if (!slOrder) {
    return (
      <div className="text-sm text-gray-400 italic flex items-center gap-2">
        <AlertTriangle className="w-4 h-4" />
        暂无止损订单
      </div>
    );
  }

  const isFilled = slOrder.status === OrderStatus.FILLED;
  const isPartiallyFilled = slOrder.status === OrderStatus.PARTIALLY_FILLED;
  const isPending = slOrder.status === OrderStatus.PENDING || slOrder.status === OrderStatus.OPEN;
  const isTriggered = isFilled || isPartiallyFilled;

  // 计算止损距离百分比
  const triggerPrice = slOrder.trigger_price ? parseFloat(slOrder.trigger_price) : null;
  const currentPrice = markPrice ? parseFloat(markPrice) : (triggerPrice ? triggerPrice * (direction === 'LONG' ? 0.99 : 1.01) : null);

  let stopLossDistance = 0;
  let distanceToStop = 0;

  if (triggerPrice && currentPrice) {
    if (direction === 'LONG') {
      // 做多止损：止损价低于当前价，距离 = (当前价 - 止损价) / 当前价 * 100
      stopLossDistance = ((currentPrice - triggerPrice) / currentPrice) * 100;
      distanceToStop = stopLossDistance;
    } else {
      // 做空止损：止损价高于当前价，距离 = (止损价 - 当前价) / 当前价 * 100
      stopLossDistance = ((triggerPrice - currentPrice) / currentPrice) * 100;
      distanceToStop = stopLossDistance;
    }
  }

  // 计算止损进度（价格接近止损价的程度）
  const stopLossProgress = currentPrice && triggerPrice && entryPrice
    ? direction === 'LONG'
      ? Math.min(100, Math.max(0, ((parseFloat(entryPrice) - currentPrice) / (parseFloat(entryPrice) - triggerPrice)) * 100))
      : Math.min(100, Math.max(0, ((currentPrice - parseFloat(entryPrice)) / (triggerPrice - parseFloat(entryPrice))) * 100))
    : 0;

  return (
    <div className="space-y-3">
      {/* 标题 */}
      <div className="flex items-center gap-2">
        <Shield className={cn(
          "w-4 h-4",
          isFilled ? "text-apple-green" : isPartiallyFilled ? "text-yellow-600" : "text-red-500"
        )} />
        <span className="text-sm font-semibold text-gray-700">
          止损订单
        </span>
      </div>

      {/* 止损订单卡片 */}
      <div className={cn(
        "p-4 rounded-xl border-2 transition-colors",
        isFilled
          ? "bg-green-50 border-green-200"
          : isPartiallyFilled
            ? "bg-yellow-50 border-yellow-200"
            : "bg-red-50 border-red-200"
      )}>
        <div className="space-y-3">
          {/* 订单基本信息 */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className={cn(
                "w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm",
                isFilled
                  ? "bg-apple-green text-white"
                  : isPartiallyFilled
                    ? "bg-yellow-500 text-white"
                    : "bg-red-500 text-white"
              )}>
                {isFilled ? (
                  <Check className="w-5 h-5" />
                ) : isPartiallyFilled ? (
                  <AlertTriangle className="w-5 h-5" />
                ) : (
                  <Shield className="w-5 h-5" />
                )}
              </div>
              <div>
                <div className="text-sm font-medium text-gray-900">
                  止损触发价
                </div>
                <div className="flex items-center gap-2 text-xs text-gray-500">
                  <span>触发价：</span>
                  <DecimalDisplay
                    value={slOrder.trigger_price}
                    decimals={2}
                    className="text-sm font-semibold text-red-600"
                  />
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <OrderStatusBadge status={slOrder.status} />
            </div>
          </div>

          {/* 订单详情网格 */}
          <div className="pt-3 border-t border-red-200 grid grid-cols-3 gap-4 text-xs">
            <div>
              <div className="text-gray-500 mb-1">订单数量</div>
              <div className="font-mono text-gray-900 font-medium">
                <DecimalDisplay value={slOrder.amount} decimals={4} />
              </div>
            </div>
            <div>
              <div className="text-gray-500 mb-1">已成交</div>
              <div className={cn(
                "font-mono font-medium",
                isTriggered ? "text-red-600" : "text-gray-400"
              )}>
                <DecimalDisplay value={slOrder.filled_amount} decimals={4} />
              </div>
            </div>
            <div>
              <div className="text-gray-500 mb-1">订单类型</div>
              <div className="font-mono text-gray-900 font-medium">
                {slOrder.order_type.replace('_', ' ')}
              </div>
            </div>
          </div>

          {/* 止损距离显示 */}
          {!isTriggered && currentPrice && triggerPrice && (
            <div className="bg-white rounded-lg p-3 border border-red-100">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2 text-xs text-gray-600">
                  <ArrowRightLeft className="w-3 h-3" />
                  <span>当前价格</span>
                  <DecimalDisplay value={markPrice} decimals={2} className="font-semibold" />
                </div>
                <div className="text-right">
                  <div className="text-xs text-gray-500">止损距离</div>
                  <div className={cn(
                    "text-sm font-bold",
                    stopLossDistance > 5
                      ? "text-green-600"
                      : stopLossDistance > 2
                        ? "text-yellow-600"
                        : "text-red-600"
                  )}>
                    {stopLossDistance.toFixed(2)}%
                  </div>
                </div>
              </div>

              {/* 止损进度条 */}
              <div className="relative h-2 bg-gray-100 rounded-full overflow-hidden">
                {/* 安全区域（绿色） */}
                <div
                  className="absolute h-full bg-gradient-to-r from-green-400 to-yellow-400 transition-all duration-500"
                  style={{ width: `${Math.min(100, stopLossProgress)}%` }}
                />
                {/* 危险区域（红色） */}
                <div
                  className="absolute h-full bg-red-500 transition-all duration-500"
                  style={{
                    left: `${Math.min(100, stopLossProgress)}%`,
                    width: `${Math.max(0, 100 - stopLossProgress)}%`
                  }}
                />
              </div>
              <div className="flex justify-between text-xs mt-1">
                <span className="text-green-600">安全</span>
                <span className="text-red-600">触发</span>
              </div>
            </div>
          )}

          {/* 状态提示 */}
          {isFilled && (
            <div className="flex items-center gap-2 text-xs text-apple-green bg-white p-2 rounded border border-green-100">
              <Check className="w-4 h-4" />
              止损已完全执行，仓位已关闭
            </div>
          )}
          {isPartiallyFilled && (
            <div className="flex items-center gap-2 text-xs text-yellow-600 bg-white p-2 rounded border border-yellow-100">
              <AlertTriangle className="w-4 h-4" />
              止损正在执行中，请尽快关注
            </div>
          )}
          {isPending && (
            <div className="flex items-center gap-2 text-xs text-gray-500 bg-white p-2 rounded border border-gray-100">
              <Shield className="w-4 h-4" />
              止损待命中，保护您的仓位
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
