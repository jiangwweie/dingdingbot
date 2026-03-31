import { useState } from 'react';
import { PositionInfo, OrderType, ClosePositionRequest } from '../../types/order';
import { X, AlertTriangle, TrendingUp, DollarSign, Percent } from 'lucide-react';
import { cn } from '../../lib/utils';

interface ClosePositionModalProps {
  position: PositionInfo | null;
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (payload: ClosePositionRequest) => Promise<void>;
  isLoading?: boolean;
}

export function ClosePositionModal({
  position,
  isOpen,
  onClose,
  onSubmit,
  isLoading,
}: ClosePositionModalProps) {
  const [closeRatio, setCloseRatio] = useState(1.0); // 默认 100%
  const [orderType, setOrderType] = useState<OrderType>(OrderType.MARKET);
  const [limitPrice, setLimitPrice] = useState('');

  if (!isOpen || !position) return null;

  const handleSubmit = async () => {
    const payload: ClosePositionRequest = {
      close_ratio: closeRatio,
      order_type: orderType,
    };

    if (orderType === OrderType.LIMIT && limitPrice) {
      payload.price = limitPrice;
    }

    await onSubmit(payload);
  };

  const currentQty = parseFloat(position.current_qty);
  const closeQty = currentQty * closeRatio;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/30 z-40 transition-opacity"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed inset-0 flex items-center justify-center z-50 p-4">
        <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
            <h3 className="text-lg font-semibold text-gray-900">
              平仓确认
            </h3>
            <button
              onClick={onClose}
              disabled={isLoading}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
            >
              <X className="w-5 h-5 text-gray-500" />
            </button>
          </div>

          {/* Content */}
          <div className="p-6 space-y-5">
            {/* 仓位信息 */}
            <div className="bg-gradient-to-br from-gray-50 to-white rounded-xl p-4 border border-gray-100">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium text-gray-900">
                  {position.symbol.replace(':USDT', '')}
                </span>
                <span className={cn(
                  "px-2 py-1 rounded text-xs font-medium",
                  position.direction === 'LONG'
                    ? "bg-green-100 text-green-700"
                    : "bg-red-100 text-red-700"
                )}>
                  {position.direction === 'LONG' ? '做多' : '做空'}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-3 text-xs">
                <div>
                  <div className="text-gray-500 mb-1">持仓数量</div>
                  <div className="font-mono font-medium text-gray-900">
                    {currentQty.toFixed(4)}
                  </div>
                </div>
                <div>
                  <div className="text-gray-500 mb-1">入场价格</div>
                  <div className="font-mono font-medium text-gray-900">
                    ${parseFloat(position.entry_price).toFixed(2)}
                  </div>
                </div>
                <div>
                  <div className="text-gray-500 mb-1">未实现盈亏</div>
                  <div className={cn(
                    "font-mono font-medium",
                    parseFloat(position.unrealized_pnl) >= 0
                      ? "text-apple-green"
                      : "text-apple-red"
                  )}>
                    {parseFloat(position.unrealized_pnl) >= 0 ? '+' : ''}
                    ${parseFloat(position.unrealized_pnl).toFixed(2)}
                  </div>
                </div>
              </div>
            </div>

            {/* 平仓比例选择 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                平仓比例
              </label>
              <div className="grid grid-cols-4 gap-2">
                {[0.25, 0.5, 0.75, 1.0].map((ratio) => (
                  <button
                    key={ratio}
                    onClick={() => setCloseRatio(ratio)}
                    className={cn(
                      "py-2 px-3 rounded-lg text-sm font-medium border transition-colors",
                      closeRatio === ratio
                        ? "bg-apple-blue border-apple-blue text-white"
                        : "bg-white border-gray-200 text-gray-700 hover:bg-gray-50"
                    )}
                  >
                    {ratio * 100}%
                  </button>
                ))}
              </div>
              <div className="mt-3 p-3 bg-gray-50 rounded-lg">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-500 flex items-center gap-1">
                    <TrendingUp className="w-4 h-4" />
                    平仓数量
                  </span>
                  <span className="font-mono font-medium text-gray-900">
                    {closeQty.toFixed(4)}
                  </span>
                </div>
              </div>
            </div>

            {/* 订单类型选择 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                订单类型
              </label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => setOrderType(OrderType.MARKET)}
                  className={cn(
                    "py-3 px-4 rounded-lg text-sm font-medium border transition-colors",
                    orderType === OrderType.MARKET
                      ? "bg-apple-blue border-apple-blue text-white"
                      : "bg-white border-gray-200 text-gray-700 hover:bg-gray-50"
                  )}
                >
                  <div className="font-medium">市价单</div>
                  <div className="text-xs opacity-75 mt-0.5">快速成交</div>
                </button>
                <button
                  onClick={() => setOrderType(OrderType.LIMIT)}
                  className={cn(
                    "py-3 px-4 rounded-lg text-sm font-medium border transition-colors",
                    orderType === OrderType.LIMIT
                      ? "bg-apple-blue border-apple-blue text-white"
                      : "bg-white border-gray-200 text-gray-700 hover:bg-gray-50"
                  )}
                >
                  <div className="font-medium">限价单</div>
                  <div className="text-xs opacity-75 mt-0.5">指定价格</div>
                </button>
              </div>
            </div>

            {/* 限价单价格输入 */}
            {orderType === OrderType.LIMIT && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  限价价格
                </label>
                <div className="relative">
                  <DollarSign className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                  <input
                    type="number"
                    value={limitPrice}
                    onChange={(e) => setLimitPrice(e.target.value)}
                    placeholder="输入限价价格"
                    className="w-full pl-10 pr-4 py-2.5 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-apple-blue focus:border-transparent text-sm font-mono"
                    step="0.01"
                  />
                </div>
              </div>
            )}

            {/* 风险提示 */}
            <div className="flex items-start gap-3 p-3 bg-amber-50 border border-amber-100 rounded-lg">
              <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
              <div className="text-xs text-amber-800">
                <p className="font-medium mb-1">注意</p>
                <p>
                  {orderType === OrderType.MARKET
                    ? '市价单将以当前市场最优价格快速成交，但实际成交价可能与预期有偏差。'
                    : '限价单可能无法立即成交，需要等待市场价格达到指定价格。'}
                </p>
              </div>
            </div>
          </div>

          {/* Footer Actions */}
          <div className="flex items-center gap-3 px-6 py-4 bg-gray-50 border-t border-gray-100">
            <button
              onClick={onClose}
              disabled={isLoading}
              className="flex-1 py-2.5 px-4 bg-white border border-gray-200 text-gray-700 font-medium rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50"
            >
              取消
            </button>
            <button
              onClick={handleSubmit}
              disabled={isLoading || (orderType === OrderType.LIMIT && !limitPrice)}
              className={cn(
                "flex-1 py-2.5 px-4 font-medium rounded-lg transition-colors flex items-center justify-center gap-2",
                isLoading
                  ? "bg-gray-300 text-gray-500 cursor-not-allowed"
                  : "bg-red-600 hover:bg-red-700 text-white"
              )}
            >
              {isLoading ? (
                <>
                  <div className="w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin" />
                  平仓中...
                </>
              ) : (
                <>
                  <TrendingUp className="w-4 h-4" />
                  确认平仓
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
