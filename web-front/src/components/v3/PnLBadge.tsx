import { cn } from '../../lib/utils';

interface PnLBadgeProps {
  pnl: string | number;
  className?: string;
  showSign?: boolean;
}

export function PnLBadge({ pnl, className, showSign = true }: PnLBadgeProps) {
  const pnlNum = typeof pnl === 'string' ? parseFloat(pnl) : pnl;
  const isPositive = pnlNum > 0;
  const isZero = pnlNum === 0;

  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-1 rounded text-xs font-medium font-mono',
        isZero
          ? 'bg-gray-100 text-gray-600'
          : isPositive
          ? 'bg-apple-green/10 text-apple-green'
          : 'bg-apple-red/10 text-apple-red',
        className
      )}
    >
      {showSign && !isZero && (isPositive ? '+' : '')}
      {typeof pnl === 'string' ? pnl : pnlNum.toFixed(2)}
    </span>
  );
}
