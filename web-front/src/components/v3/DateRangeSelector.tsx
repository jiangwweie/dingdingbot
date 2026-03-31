import { cn } from '../../lib/utils';

export type DateRangeType = '7days' | '30days' | '90days';

interface DateRangeSelectorProps {
  value: DateRangeType;
  onChange: (range: DateRangeType) => void;
  className?: string;
}

const dateRangeOptions: { value: DateRangeType; label: string }[] = [
  { value: '7days', label: '7 天' },
  { value: '30days', label: '30 天' },
  { value: '90days', label: '90 天' },
];

/**
 * 日期范围选择器组件
 * 支持 7 天/30 天/90 天快捷选择
 */
export function DateRangeSelector({ value, onChange, className }: DateRangeSelectorProps) {
  return (
    <div className={cn('inline-flex rounded-lg bg-gray-100 p-1', className)}>
      {dateRangeOptions.map((option) => (
        <button
          key={option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            'px-3 py-1.5 text-sm font-medium rounded-md transition-all',
            value === option.value
              ? 'bg-white text-gray-900 shadow-sm'
              : 'text-gray-500 hover:text-gray-700'
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
