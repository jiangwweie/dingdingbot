import { cn } from '../../lib/utils';

interface DecimalDisplayProps {
  value: string | number | null | undefined;
  className?: string;
  prefix?: string;
  suffix?: string;
  decimals?: number;
}

/**
 * 通用 Decimal 格式化显示组件
 * 用于订单金额、价格等 Decimal 字段的显示
 */
export function DecimalDisplay({
  value,
  className,
  prefix,
  suffix,
  decimals = 4,
}: DecimalDisplayProps) {
  if (value === null || value === undefined || value === '') {
    return <span className={cn('text-gray-400', className)}>-</span>;
  }

  const numValue = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(numValue)) {
    return <span className={cn('text-gray-400', className)}>-</span>;
  }

  const formatted = numValue.toLocaleString('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: decimals,
  });

  return (
    <span className={cn('font-mono text-gray-900', className)}>
      {prefix}{formatted}{suffix}
    </span>
  );
}
