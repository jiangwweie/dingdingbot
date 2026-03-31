import { useState } from 'react';
import { X, AlertCircle } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { cn } from '../../lib/utils';
import {
  OrderType,
  OrderRole,
  Direction,
  OrderRequest,
  OrderCheckRequest,
  CapitalProtectionCheckResult,
} from '../../types/order';
import { checkOrderCapital as apiCheckOrder, createOrder as apiCreateOrder } from '../../lib/api';

interface CreateOrderModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: (order: OrderRequest) => void;
}

interface OrderFormData {
  symbol: string;
  order_type: OrderType;
  order_role: OrderRole;
  direction: Direction;
  quantity: string;
  price?: string;
  trigger_price?: string;
  reduce_only: boolean;
  stop_loss?: string;
  take_profit?: string;
}

const symbolOptions = [
  { value: 'BTC/USDT:USDT', label: 'BTC/USDT' },
  { value: 'ETH/USDT:USDT', label: 'ETH/USDT' },
  { value: 'SOL/USDT:USDT', label: 'SOL/USDT' },
  { value: 'BNB/USDT:USDT', label: 'BNB/USDT' },
];

const orderTypeOptions = [
  { value: OrderType.MARKET, label: '市价单', description: '按市场最优价格立即成交' },
  { value: OrderType.LIMIT, label: '限价单', description: '指定价格或更优价格成交' },
  { value: OrderType.STOP_MARKET, label: '止损市价单', description: '触发后按市价成交' },
  { value: OrderType.STOP_LIMIT, label: '止损限价单', description: '触发后按限价成交' },
];

const orderRoleOptions = [
  { value: OrderRole.ENTRY, label: '入场开仓', description: '新建仓位' },
  { value: OrderRole.TP1, label: '止盈 1', description: '第一目标位止盈 (25%)' },
  { value: OrderRole.TP2, label: '止盈 2', description: '第二目标位止盈 (25%)' },
  { value: OrderRole.TP3, label: '止盈 3', description: '第三目标位止盈 (25%)' },
  { value: OrderRole.TP4, label: '止盈 4', description: '第四目标位止盈 (25%)' },
  { value: OrderRole.TP5, label: '止盈 5', description: '第五目标位止盈' },
  { value: OrderRole.SL, label: '止损', description: '止损平仓' },
];

const directionOptions = [
  { value: Direction.LONG, label: '做多', description: '买入开多' },
  { value: Direction.SHORT, label: '做空', description: '卖出开空' },
];

export function CreateOrderModal({ isOpen, onClose, onSuccess }: CreateOrderModalProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isChecking, setIsChecking] = useState(false);
  const [capitalCheckResult, setCapitalCheckResult] = useState<CapitalProtectionCheckResult | null>(null);
  const [showCapitalCheck, setShowCapitalCheck] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
    reset,
    setValue,
  } = useForm<OrderFormData>({
    defaultValues: {
      symbol: 'BTC/USDT:USDT',
      order_type: OrderType.MARKET,
      order_role: OrderRole.ENTRY,
      direction: Direction.LONG,
      quantity: '',
      price: '',
      trigger_price: '',
      reduce_only: false,
      stop_loss: '',
      take_profit: '',
    },
  });

  const orderType = watch('order_type');
  const orderRole = watch('order_role');
  const direction = watch('direction');
  const quantity = watch('quantity');
  const price = watch('price');
  const triggerPrice = watch('trigger_price');
  const symbol = watch('symbol');
  const stopLoss = watch('stop_loss');
  const orderTypeVal = watch('order_type');
  const orderRoleVal = watch('order_role');
  const directionVal = watch('direction');

  // Auto-set reduce_only for TP/SL orders
  useState(() => {
    if ([OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5, OrderRole.SL].includes(orderRoleVal)) {
      setValue('reduce_only', true);
    }
  });

  // Validation rules
  const validationRules = {
    quantity: {
      required: '数量必填',
      pattern: {
        value: /^\d+(\.\d+)?$/,
        message: '数量必须为正数',
      },
      validate: (v: string) => parseFloat(v) > 0 || '数量必须大于 0',
    },
    price: {
      required: orderTypeVal === OrderType.LIMIT || orderTypeVal === OrderType.STOP_LIMIT
        ? '限价单价格必填'
        : false,
      pattern: {
        value: /^\d+(\.\d+)?$/,
        message: '价格格式不正确',
      },
    },
    trigger_price: {
      required: orderTypeVal === OrderType.STOP_MARKET || orderTypeVal === OrderType.STOP_LIMIT
        ? '止损单触发价必填'
        : false,
      pattern: {
        value: /^\d+(\.\d+)?$/,
        message: '触发价格式不正确',
      },
    },
  };

  // Capital protection check before submit
  const handleCapitalCheck = async () => {
    if (!quantity || parseFloat(quantity) <= 0) {
      alert('请输入有效的数量');
      return;
    }

    setIsChecking(true);
    try {
      const checkRequest: OrderCheckRequest = {
        symbol,
        order_type: orderTypeVal,
        order_role: orderRoleVal,
        direction: directionVal,
        quantity,
        price: price || undefined,
        trigger_price: triggerPrice || undefined,
        stop_loss: stopLoss || undefined,
      };

      const result = await apiCheckOrder(checkRequest);
      setCapitalCheckResult(result);
      setShowCapitalCheck(true);
    } catch (error) {
      console.error('Capital check failed:', error);
      alert('资金保护检查失败，请检查账户余额和风控设置');
    } finally {
      setIsChecking(false);
    }
  };

  const onSubmit = async (data: OrderFormData) => {
    setIsSubmitting(true);
    try {
      const orderRequest: OrderRequest = {
        symbol: data.symbol,
        order_type: data.order_type,
        order_role: data.order_role,
        direction: data.direction,
        quantity: data.quantity,
        price: data.price || undefined,
        trigger_price: data.trigger_price || undefined,
        reduce_only: data.reduce_only,
        stop_loss: data.stop_loss || undefined,
        take_profit: data.take_profit || undefined,
      };

      await apiCreateOrder(orderRequest);
      onSuccess?.(orderRequest);
      reset();
      onClose();
    } catch (error: any) {
      console.error('Failed to create order:', error);
      const errorMsg = error?.info?.detail || error?.message || '下单失败，请重试';
      alert(`下单失败：${errorMsg}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    reset();
    setCapitalCheckResult(null);
    setShowCapitalCheck(false);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/20 z-40" onClick={handleClose} />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
            <h2 className="text-lg font-semibold text-gray-900">创建订单</h2>
            <button
              onClick={handleClose}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <X className="w-5 h-5 text-gray-500" />
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-6">
            <form id="create-order-form" onSubmit={handleSubmit(onSubmit)} className="space-y-5">
              {/* Symbol */}
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-gray-700">币种</label>
                <select
                  {...register('symbol')}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-apple-blue/20 focus:border-apple-blue"
                >
                  {symbolOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>

              {/* Order Type */}
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-gray-700">订单类型</label>
                <div className="grid grid-cols-2 gap-2">
                  {orderTypeOptions.map((opt) => (
                    <label
                      key={opt.value}
                      className={cn(
                        'p-3 border rounded-lg cursor-pointer transition-colors',
                        orderType === opt.value
                          ? 'border-apple-blue bg-blue-50'
                          : 'border-gray-200 hover:border-gray-300'
                      )}
                    >
                      <input
                        type="radio"
                        {...register('order_type')}
                        value={opt.value}
                        className="sr-only"
                      />
                      <div className="text-sm font-medium text-gray-900">{opt.label}</div>
                      <div className="text-xs text-gray-500 mt-0.5">{opt.description}</div>
                    </label>
                  ))}
                </div>
              </div>

              {/* Order Role */}
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-gray-700">订单角色</label>
                <select
                  {...register('order_role')}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-apple-blue/20 focus:border-apple-blue"
                >
                  {orderRoleOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>

              {/* Direction */}
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-gray-700">方向</label>
                <div className="grid grid-cols-2 gap-2">
                  {directionOptions.map((opt) => (
                    <label
                      key={opt.value}
                      className={cn(
                        'p-3 border rounded-lg cursor-pointer transition-colors text-center',
                        direction === opt.value
                          ? opt.value === Direction.LONG
                            ? 'border-green-500 bg-green-50'
                            : 'border-red-500 bg-red-50'
                          : 'border-gray-200 hover:border-gray-300'
                      )}
                    >
                      <input
                        type="radio"
                        {...register('direction')}
                        value={opt.value}
                        className="sr-only"
                      />
                      <div className={cn(
                        'text-sm font-semibold',
                        opt.value === Direction.LONG ? 'text-green-600' : 'text-red-600'
                      )}>
                        {opt.label}
                      </div>
                      <div className="text-xs text-gray-500 mt-0.5">{opt.description}</div>
                    </label>
                  ))}
                </div>
              </div>

              {/* Quantity */}
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-gray-700">数量</label>
                <input
                  type="text"
                  {...register('quantity', validationRules.quantity)}
                  placeholder="0.00"
                  className={cn(
                    'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-apple-blue/20 focus:border-apple-blue',
                    errors.quantity ? 'border-red-300' : 'border-gray-200'
                  )}
                />
                {errors.quantity && (
                  <p className="text-xs text-red-500">{errors.quantity.message}</p>
                )}
              </div>

              {/* Price (conditional) */}
              {(orderType === OrderType.LIMIT || orderType === OrderType.STOP_LIMIT) && (
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-gray-700">限价 <span className="text-red-500">*</span></label>
                  <input
                    type="text"
                    {...register('price', validationRules.price)}
                    placeholder="0.00"
                    className={cn(
                      'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-apple-blue/20 focus:border-apple-blue',
                      errors.price ? 'border-red-300' : 'border-gray-200'
                    )}
                  />
                  {errors.price && (
                    <p className="text-xs text-red-500">{errors.price.message}</p>
                  )}
                </div>
              )}

              {/* Trigger Price (conditional) */}
              {(orderType === OrderType.STOP_MARKET || orderType === OrderType.STOP_LIMIT) && (
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-gray-700">触发价格 <span className="text-red-500">*</span></label>
                  <input
                    type="text"
                    {...register('trigger_price', validationRules.trigger_price)}
                    placeholder="0.00"
                    className={cn(
                      'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-apple-blue/20 focus:border-apple-blue',
                      errors.trigger_price ? 'border-red-300' : 'border-gray-200'
                    )}
                  />
                  {errors.trigger_price && (
                    <p className="text-xs text-red-500">{errors.trigger_price.message}</p>
                  )}
                </div>
              )}

              {/* Reduce Only */}
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  {...register('reduce_only')}
                  id="reduce_only"
                  className="w-4 h-4 text-apple-blue border-gray-300 rounded focus:ring-apple-blue"
                />
                <label htmlFor="reduce_only" className="text-sm text-gray-700">
                  仅减仓模式 (平仓单请勾选)
                </label>
              </div>

              {/* Stop Loss & Take Profit (optional) */}
              <div className="grid grid-cols-2 gap-4 pt-4 border-t border-gray-100">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-gray-700">止损价格 (可选)</label>
                  <input
                    type="text"
                    {...register('stop_loss')}
                    placeholder="0.00"
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-apple-blue/20 focus:border-apple-blue"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-gray-700">止盈价格 (可选)</label>
                  <input
                    type="text"
                    {...register('take_profit')}
                    placeholder="0.00"
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-apple-blue/20 focus:border-apple-blue"
                  />
                </div>
              </div>
            </form>

            {/* Capital Protection Check Result */}
            {showCapitalCheck && capitalCheckResult && (
              <div className={cn(
                'mt-4 p-4 rounded-lg border',
                capitalCheckResult.allowed
                  ? 'bg-green-50 border-green-200'
                  : 'bg-red-50 border-red-200'
              )}>
                <div className="flex items-start gap-3">
                  <AlertCircle className={cn(
                    'w-5 h-5 flex-shrink-0',
                    capitalCheckResult.allowed ? 'text-green-600' : 'text-red-600'
                  )} />
                  <div className="flex-1">
                    <h4 className={cn(
                      'text-sm font-semibold',
                      capitalCheckResult.allowed ? 'text-green-800' : 'text-red-800'
                    )}>
                      {capitalCheckResult.allowed ? '资金检查通过' : '资金检查未通过'}
                    </h4>
                    {!capitalCheckResult.allowed && capitalCheckResult.reason_message && (
                      <p className="text-xs text-red-600 mt-1">{capitalCheckResult.reason_message}</p>
                    )}
                    {capitalCheckResult.allowed && (
                      <div className="mt-2 text-xs text-green-700 space-y-1">
                        {capitalCheckResult.single_trade_check !== null && (
                          <p>✓ 单笔交易限制检查通过</p>
                        )}
                        {capitalCheckResult.position_limit_check !== null && (
                          <p>✓ 仓位限制检查通过</p>
                        )}
                        {capitalCheckResult.daily_loss_check !== null && (
                          <p>✓ 每日亏损限制检查通过</p>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-6 py-4 border-t border-gray-100 bg-gray-50 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={handleCapitalCheck}
              disabled={isChecking || !quantity}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isChecking ? '检查中...' : '资金保护检查'}
            </button>
            <button
              type="button"
              onClick={handleClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
            >
              取消
            </button>
            <button
              type="submit"
              form="create-order-form"
              disabled={isSubmitting}
              className="px-4 py-2 text-sm font-medium text-white bg-apple-blue rounded-lg hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isSubmitting ? '提交中...' : '确认下单'}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
