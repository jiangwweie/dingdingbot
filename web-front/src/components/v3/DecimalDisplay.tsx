import { cn } from '../../lib/utils';

interface DecimalDisplayProps {
  value: string | number | null | undefined;
  className?: string;
  prefix?: string;
  suffix?: string;
  decimals?: number;
  fieldType?: string;
}

/**
 * 通用 Decimal 格式化显示组件
 * 用于订单金额、价格等 Decimal 字段的显示
 *
 * 精度规则：
 * - 未传入 decimals 时，根据常见场景自动推断：
 *   - 价格 (price)：2 位小数
 *   - 金额/价值 (value/equity/balance)：2 位小数
 *   - 数量 (quantity/qty)：4 位小数
 *   - 比率/百分比 (rate/ratio/pct)：2 位小数
 *   - 其他：4 位小数
 */
export function DecimalDisplay({
  value,
  className,
  prefix,
  suffix,
  decimals,
  fieldType,
}: DecimalDisplayProps) {
  if (value === null || value === undefined || value === '') {
    return <span className={cn('text-gray-400', className)}>-</span>;
  }

  const numValue = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(numValue)) {
    return <span className={cn('text-gray-400', className)}>-</span>;
  }

  // 动态计算精度：传入 props 优先，否则根据 fieldType 推断，默认 4 位
  const effectiveDecimals = decimals ?? getDecimalsForFieldType(fieldType);

  const formatted = numValue.toLocaleString('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: effectiveDecimals,
  });

  return (
    <span className={cn('font-mono text-gray-900', className)}>
      {prefix}{formatted}{suffix}
    </span>
  );
}

/**
 * 根据字段类型推断精度
 */
function getDecimalsForFieldType(fieldType?: string): number {
  if (!fieldType) return 4;

  const type = fieldType.toLowerCase();

  // 价格、金额、价值类：2 位小数
  if (type.includes('price') || type.includes('value') || type.includes('equity') || type.includes('balance') || type.includes('pnl') || type.includes('fee')) {
    return 2;
  }

  // 比率、百分比类：2 位小数
  if (type.includes('rate') || type.includes('ratio') || type.includes('pct') || type.includes('percent')) {
    return 2;
  }

  // 数量类：4 位小数（加密货币通常支持 4-8 位）
  if (type.includes('quantity') || type.includes('qty') || type.includes('amount')) {
    return 4;
  }

  // 默认 4 位小数
  return 4;
}
