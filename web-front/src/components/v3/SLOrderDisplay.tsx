import { OrderResponse, OrderStatus } from '../../types/order';
import { OrderStatusBadge } from './OrderStatusBadge';
import { DecimalDisplay } from './DecimalDisplay';
import { Shield, AlertTriangle, Check } from 'lucide-react';

interface SLOrderDisplayProps {
  slOrder: OrderResponse | null;
  entryPrice: string;
  direction: 'LONG' | 'SHORT';
}

/**
 * 止损订单展示组件
 * 显示 SL 止损订单的状态和执行情况
 */
export function SLOrderDisplay({ slOrder, entryPrice, direction }: SLOrderDisplayProps) {
  if (!slOrder) {
    return (
      <div className="text-sm text-gray-400 italic flex items-center gap-2">
        <AlertTriangle className="w-4 h-4" />
        暂无止损订单
      </div>
    );
  }

  const isFilled = slOrder.status === 'FILLED';
  const isPartiallyFilled = slOrder.status === 'PARTIALLY_FILLED';
  const isTriggered = isFilled || isPartiallyFilled;

  return (
    <div className="space-y-3">
      <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide flex items-center gap-2">
        <Shield className="w-4 h-4" />
        止损订单
      </div>

      <div className="p-4 bg-red-50 rounded-lg border border-red-100">
        <div className="space-y-3">
          {/* 订单基本信息 */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex items-center justify-center w-10 h-10 rounded-full bg-red-100 text-red-700 font-bold text-sm">
                SL
              </div>
              <div>
                <div className="text-sm font-medium text-gray-900">
                  止损价格
                </div>
                <div className="flex items-center gap-2 text-xs text-gray-500">
                  <span>触发价：</span>
                  <DecimalDisplay value={slOrder.trigger_price} decimals={2} className="text-sm font-semibold text-red-600" />
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {isFilled ? (
                <Check className="w-6 h-6 text-apple-green" />
              ) : isPartiallyFilled ? (
                <AlertTriangle className="w-6 h-6 text-yellow-500" />
              ) : (
                <Shield className="w-6 h-6 text-gray-400" />
              )}
              <OrderStatusBadge status={slOrder.status} />
            </div>
          </div>

          {/* 订单详情 */}
          <div className="pt-3 border-t border-red-100 grid grid-cols-3 gap-4 text-xs">
            <div>
              <div className="text-gray-500">订单数量</div>
              <div className="font-mono text-gray-900">
                <DecimalDisplay value={slOrder.amount} decimals={4} />
              </div>
            </div>
            <div>
              <div className="text-gray-500">已成交</div>
              <div className={isTriggered ? "font-mono text-red-600" : "font-mono text-gray-400"}>
                <DecimalDisplay value={slOrder.filled_amount} decimals={4} />
              </div>
            </div>
            <div>
              <div className="text-gray-500">订单类型</div>
              <div className="font-mono text-gray-900">
                {slOrder.order_type}
              </div>
            </div>
          </div>

          {/* 止损状态提示 */}
          {isFilled && (
            <div className="flex items-center gap-2 text-xs text-apple-green bg-green-50 p-2 rounded">
              <Check className="w-4 h-4" />
              止损已触发并完全成交
            </div>
          )}
          {isPartiallyFilled && (
            <div className="flex items-center gap-2 text-xs text-yellow-600 bg-yellow-50 p-2 rounded">
              <AlertTriangle className="w-4 h-4" />
              止损正在执行中...
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
