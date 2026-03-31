import { cn } from '../../lib/utils';
import { Direction } from '../../types/order';

interface DirectionBadgeProps {
  direction: Direction | string;
  className?: string;
}

const directionConfig: Record<Direction, { label: string; className: string }> = {
  LONG: {
    label: '多',
    className: 'bg-green-100 text-green-700',
  },
  SHORT: {
    label: '空',
    className: 'bg-red-100 text-red-700',
  },
};

export function DirectionBadge({ direction, className }: DirectionBadgeProps) {
  const config = directionConfig[direction as Direction] || {
    label: direction,
    className: 'bg-gray-100 text-gray-700',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-1 rounded text-xs font-medium',
        config.className,
        className
      )}
    >
      {config.label}
    </span>
  );
}
