import { useState } from 'react';
import { Calendar, Clock, ChevronRight } from 'lucide-react';
import { cn } from '../lib/utils';
import { format, subDays, subMonths, startOfYear, startOfDay } from 'date-fns';

interface QuickDateRangePickerProps {
  startTime: number | null;  // UNIX 毫秒戳
  endTime: number | null;
  onStartChange: (ts: number | null) => void;
  onEndChange: (ts: number | null) => void;
}

interface QuickOption {
  type: string;
  label: string;
  category?: 'common' | 'extended';
}

const QUICK_OPTIONS: QuickOption[] = [
  // 常用选项
  { type: 'today', label: '今天', category: 'common' },
  { type: '7days', label: '最近 7 天', category: 'common' },
  { type: '30days', label: '最近 30 天', category: 'common' },
  // 扩展选项
  { type: '3days', label: '3 天', category: 'extended' },
  { type: '14days', label: '14 天', category: 'extended' },
  { type: '3months', label: '3 个月', category: 'extended' },
  { type: '6months', label: '6 个月', category: 'extended' },
  { type: 'ytd', label: '今年至今', category: 'extended' },
  { type: 'custom', label: '自定义', category: 'extended' },
];

export default function QuickDateRangePicker({
  startTime,
  endTime,
  onStartChange,
  onEndChange,
}: QuickDateRangePickerProps) {
  const [isCustom, setIsCustom] = useState(false);
  const [showExtended, setShowExtended] = useState(false);

  // Format timestamp to YYYY-MM-DD HH:mm
  const formatTimestamp = (ts: number | null): string => {
    if (!ts) return '-';
    return format(new Date(ts), 'yyyy-MM-dd HH:mm');
  };

  // Handle quick option selection
  const handleOptionClick = (optionType: string) => {
    if (optionType === 'custom') {
      setIsCustom(true);
      setShowExtended(true);
      return;
    }

    setIsCustom(optionType === 'custom');
    const now = new Date();
    const today = startOfDay(now);

    let startTs: Date;

    switch (optionType) {
      case 'today':
        startTs = today;
        break;
      case '3days':
        startTs = startOfDay(subDays(now, 3));
        break;
      case '7days':
        startTs = startOfDay(subDays(now, 7));
        break;
      case '14days':
        startTs = startOfDay(subDays(now, 14));
        break;
      case '30days':
        startTs = startOfDay(subDays(now, 30));
        break;
      case '3months':
        startTs = startOfDay(subMonths(now, 3));
        break;
      case '6months':
        startTs = startOfDay(subMonths(now, 6));
        break;
      case 'ytd':
        startTs = startOfYear(now);
        break;
      default:
        startTs = today;
    }

    onStartChange(startTs.getTime());
    onEndChange(now.getTime());
  };

  // Handle custom datetime input
  const handleCustomStartChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const date = new Date(e.target.value);
    onStartChange(date.getTime());
  };

  const handleCustomEndChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const date = new Date(e.target.value);
    onEndChange(date.getTime());
  };

  // Convert timestamp to datetime-local format
  const timestampToDateTimeLocal = (ts: number | null): string => {
    if (!ts) return '';
    return format(new Date(ts), "yyyy-MM-dd'T'HH:mm");
  };

  // Get duration description
  const getDurationDesc = (): string => {
    if (!startTime || !endTime) return '未选择时间范围';
    const duration = endTime - startTime;
    const days = Math.floor(duration / (1000 * 60 * 60 * 24));
    const hours = Math.floor((duration % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    
    if (days > 0) {
      return `${days}天${hours > 0 ? hours + '小时' : ''}`;
    }
    return `${hours}小时`;
  };

  return (
    <div className="space-y-3">
      {/* Quick option buttons - Common options always visible */}
      <div className="flex flex-wrap gap-2">
        {QUICK_OPTIONS.filter(opt => opt.category === 'common').map((option) => (
          <button
            key={option.type}
            onClick={() => handleOptionClick(option.type)}
            className={cn(
              'px-3 py-1.5 text-sm font-medium rounded-lg transition-all border',
              !isCustom && !showExtended
                ? 'bg-black text-white border-black shadow-sm'
                : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50 hover:border-gray-400'
            )}
          >
            {option.label}
          </button>
        ))}
        
        {/* Extended options toggle */}
        <button
          onClick={() => setShowExtended(!showExtended)}
          className={cn(
            'px-3 py-1.5 text-sm font-medium rounded-lg transition-all border flex items-center gap-1',
            showExtended
              ? 'bg-gray-100 text-gray-900 border-gray-400'
              : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50 hover:border-gray-400'
          )}
        >
          更多
          <ChevronRight className={cn('w-3.5 h-3.5 transition-transform', showExtended && 'rotate-90')} />
        </button>
      </div>

      {/* Extended options */}
      {showExtended && (
        <div className="flex flex-wrap gap-2 pt-2 border-t border-gray-100">
          {QUICK_OPTIONS.filter(opt => opt.category === 'extended').map((option) => (
            <button
              key={option.type}
              onClick={() => handleOptionClick(option.type)}
              className={cn(
                'px-3 py-1.5 text-sm font-medium rounded-lg transition-all border',
                (isCustom && option.type === 'custom')
                  ? 'bg-black text-white border-black shadow-sm'
                  : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50 hover:border-gray-400'
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}

      {/* Custom datetime inputs */}
      {isCustom && (
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              起始时间
            </label>
            <input
              type="datetime-local"
              value={timestampToDateTimeLocal(startTime)}
              onChange={handleCustomStartChange}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-black transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              结束时间
            </label>
            <input
              type="datetime-local"
              value={timestampToDateTimeLocal(endTime)}
              onChange={handleCustomEndChange}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-black transition-colors"
            />
          </div>
        </div>
      )}

      {/* Display current selected range */}
      <div className="flex items-center justify-between bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg px-3 py-2.5 border border-blue-100">
        <div className="flex items-center gap-2 text-xs text-gray-700">
          <Clock className="w-3.5 h-3.5 text-blue-600" />
          <span className="font-medium">
            {formatTimestamp(startTime)}
          </span>
          <span className="text-gray-400 mx-1">→</span>
          <span className="font-medium">
            {formatTimestamp(endTime)}
          </span>
        </div>
        {(startTime && endTime) && (
          <span className="text-xs font-medium text-blue-600 bg-blue-100 px-2 py-0.5 rounded-full">
            {getDurationDesc()}
          </span>
        )}
      </div>
    </div>
  );
}
