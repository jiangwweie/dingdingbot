import { cn } from '../../lib/utils';
import { OrderStatus } from '../../types/order';

interface OrderStatusBadgeProps {
  status: OrderStatus | string;
  className?: string;
}

const statusConfig: Record<OrderStatus, { label: string; className: string }> = {
  CREATED: {
    label: '已创建',
    className: 'bg-gray-100 text-gray-700',
  },
  SUBMITTED: {
    label: '已提交',
    className: 'bg-blue-100 text-blue-700',
  },
  PENDING: {
    label: '待处理',
    className: 'bg-gray-100 text-gray-700',
  },
  OPEN: {
    label: '进行中',
    className: 'bg-blue-100 text-blue-700',
  },
  FILLED: {
    label: '已成交',
    className: 'bg-green-100 text-green-700',
  },
  CANCELED: {
    label: '已取消',
    className: 'bg-orange-100 text-orange-700',
  },
  REJECTED: {
    label: '已拒绝',
    className: 'bg-red-100 text-red-700',
  },
  EXPIRED: {
    label: '已过期',
    className: 'bg-purple-100 text-purple-700',
  },
  PARTIALLY_FILLED: {
    label: '部分成交',
    className: 'bg-yellow-100 text-yellow-700',
  },
};

export function OrderStatusBadge({ status, className }: OrderStatusBadgeProps) {
  const config = statusConfig[status as OrderStatus] || {
    label: status,
    className: 'bg-gray-100 text-gray-700',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
        config.className,
        className
      )}
    >
      {config.label}
    </span>
  );
}
