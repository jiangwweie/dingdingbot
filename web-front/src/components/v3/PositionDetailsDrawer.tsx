import { PositionInfo, OrderResponse } from '../../types/order';
import { DirectionBadge } from './DirectionBadge';
import { PnLBadge } from './PnLBadge';
import { DecimalDisplay } from './DecimalDisplay';
import { TPChainDisplay } from './TPChainDisplay';
import { SLOrderDisplay } from './SLOrderDisplay';
import { format } from 'date-fns';
import {
  X,
  TrendingUp,
  Calendar,
  Clock,
  DollarSign,
  Percent,
  Activity,
  Shield,
  Target,
} from 'lucide-react';
import { cn } from '../../lib/utils';

interface PositionDetailsDrawerProps {
  position: PositionInfo | null;
  isOpen: boolean;
  onClose: () => void;
  tpOrders?: OrderResponse[];
  slOrder?: OrderResponse | null;
  onQuickClose?: () => void;
}

export function PositionDetailsDrawer({
  position,
  isOpen,
  onClose,
  tpOrders = [],
  slOrder = null,
  onQuickClose,
}: PositionDetailsDrawerProps) {
  if (!isOpen || !position) return null;

  const entryPrice = parseFloat(position.entry_price);
  const markPrice = position.mark_price ? parseFloat(position.mark_price) : null;
  const pnl = parseFloat(position.unrealized_pnl);

  // 计算盈亏比例
  const pnlPercent = markPrice && entryPrice
    ? ((markPrice - entryPrice) / entryPrice) * 100 * (position.direction === 'LONG' ? 1 : -1)
    : 0;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/30 z-40 transition-opacity"
        onClick={onClose}
      />

      {/* Drawer */}
      <div className="fixed inset-y-0 right-0 w-full max-w-2xl bg-white shadow-2xl z-50 overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              仓位详情
            </h2>
            <p className="text-sm text-gray-500 mt-0.5">
              {position.symbol.replace(':USDT', '')}
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
          {/* 基础信息卡片 */}
          <div className="bg-gradient-to-br from-gray-50 to-white rounded-2xl p-6 border border-gray-100">
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className={cn(
                  "w-12 h-12 rounded-full flex items-center justify-center",
                  position.direction === 'LONG'
                    ? "bg-green-100 text-green-700"
                    : "bg-red-100 text-red-700"
                )}>
                  <TrendingUp className="w-6 h-6" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-lg font-semibold text-gray-900">
                      {position.direction === 'LONG' ? '做多' : '做空'}
                    </span>
                    <DirectionBadge direction={position.direction} className="text-sm" />
                  </div>
                  <div className="text-sm text-gray-500 mt-0.5">
                    杠杆 {position.leverage}x · {position.margin_mode === 'CROSS' ? '全仓' : '逐仓'}
                  </div>
                </div>
              </div>
              <div className="text-right">
                <div className="text-sm text-gray-500">未实现盈亏</div>
                <PnLBadge pnl={pnl} className="text-lg mt-1" showSign />
                <div className={cn(
                  "text-xs font-medium mt-1",
                  pnlPercent >= 0 ? "text-apple-green" : "text-apple-red"
                )}>
                  {pnlPercent >= 0 ? '+' : ''}{pnlPercent.toFixed(2)}%
                </div>
              </div>
            </div>

            {/* 价格信息网格 */}
            <div className="grid grid-cols-2 gap-4 pt-4 border-t border-gray-100">
              <div>
                <div className="text-xs text-gray-500 flex items-center gap-1 mb-1">
                  <DollarSign className="w-3 h-3" />
                  入场价格
                </div>
                <div className="text-base font-mono font-semibold text-gray-900">
                  <DecimalDisplay value={position.entry_price} decimals={2} />
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-500 flex items-center gap-1 mb-1">
                  <Activity className="w-3 h-3" />
                  标记价格
                </div>
                <div className="text-base font-mono font-semibold text-gray-900">
                  <DecimalDisplay value={position.mark_price} decimals={2} />
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-500 flex items-center gap-1 mb-1">
                  <Target className="w-3 h-3" />
                  持仓数量
                </div>
                <div className="text-base font-mono text-gray-900">
                  <DecimalDisplay value={position.current_qty} decimals={4} />
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-500 flex items-center gap-1 mb-1">
                  <Shield className="w-3 h-3" />
                  强平价格
                </div>
                <div className="text-base font-mono text-red-600">
                  <DecimalDisplay value={position.liquidation_price} decimals={2} />
                </div>
              </div>
            </div>
          </div>

          {/* 止盈订单链 */}
          <div className="bg-white rounded-xl border border-gray-100 p-5">
            <TPChainDisplay
              tpOrders={tpOrders}
              entryPrice={position.entry_price}
              direction={position.direction}
            />
          </div>

          {/* 止损订单 */}
          <div className="bg-white rounded-xl border border-gray-100 p-5">
            <SLOrderDisplay
              slOrder={slOrder}
              entryPrice={position.entry_price}
              direction={position.direction}
            />
          </div>

          {/* 其他信息 */}
          <div className="space-y-3">
            <div className="flex items-center justify-between text-sm py-2 border-b border-gray-50">
              <span className="text-gray-500 flex items-center gap-2">
                <Calendar className="w-4 h-4" />
                开仓时间
              </span>
              <span className="font-mono text-gray-900">
                {format(new Date(position.opened_at), 'yyyy-MM-dd HH:mm:ss')}
              </span>
            </div>
            {position.closed_at && (
              <div className="flex items-center justify-between text-sm py-2 border-b border-gray-50">
                <span className="text-gray-500 flex items-center gap-2">
                  <Clock className="w-4 h-4" />
                  平仓时间
                </span>
                <span className="font-mono text-gray-900">
                  {format(new Date(position.closed_at), 'yyyy-MM-dd HH:mm:ss')}
                </span>
              </div>
            )}
            <div className="flex items-center justify-between text-sm py-2 border-b border-gray-50">
              <span className="text-gray-500 flex items-center gap-2">
                <Percent className="w-4 h-4" />
                累计手续费
              </span>
              <span className="font-mono text-gray-900">
                <DecimalDisplay value={position.total_fees_paid} decimals={4} />
              </span>
            </div>
            {position.strategy_name && (
              <div className="flex items-center justify-between text-sm py-2 border-b border-gray-50">
                <span className="text-gray-500 flex items-center gap-2">
                  <Activity className="w-4 h-4" />
                  关联策略
                </span>
                <span className="px-2 py-1 bg-indigo-50 text-indigo-700 rounded text-xs font-medium">
                  {position.strategy_name}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Footer Actions */}
        <div className="p-6 border-t border-gray-100 bg-gray-50">
          {!position.is_closed ? (
            <button
              onClick={onQuickClose}
              className="w-full py-3 px-4 bg-red-600 hover:bg-red-700 text-white font-medium rounded-xl transition-colors flex items-center justify-center gap-2"
            >
              <TrendingUp className="w-5 h-5" />
              平仓
            </button>
          ) : (
            <div className="text-center text-sm text-gray-500">
              此仓位已平仓
            </div>
          )}
        </div>
      </div>
    </>
  );
}
