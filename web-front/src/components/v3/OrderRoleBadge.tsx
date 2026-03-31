import { cn } from '../../lib/utils';
import { OrderRole } from '../../types/order';

interface OrderRoleBadgeProps {
  role: OrderRole | string;
  className?: string;
}

const roleConfig: Record<OrderRole, { label: string; className: string }> = {
  ENTRY: {
    label: '开仓',
    className: 'bg-indigo-100 text-indigo-700',
  },
  TP1: {
    label: '止盈 1',
    className: 'bg-emerald-100 text-emerald-700',
  },
  TP2: {
    label: '止盈 2',
    className: 'bg-teal-100 text-teal-700',
  },
  TP3: {
    label: '止盈 3',
    className: 'bg-cyan-100 text-cyan-700',
  },
  TP4: {
    label: '止盈 4',
    className: 'bg-sky-100 text-sky-700',
  },
  TP5: {
    label: '止盈 5',
    className: 'bg-blue-100 text-blue-700',
  },
  SL: {
    label: '止损',
    className: 'bg-rose-100 text-rose-700',
  },
};

export function OrderRoleBadge({ role, className }: OrderRoleBadgeProps) {
  const config = roleConfig[role as OrderRole] || {
    label: role,
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
