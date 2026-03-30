import { useState } from 'react';
import { Calendar, Clock } from 'lucide-react';
import { cn, formatBeijingTime } from '../lib/utils';

interface QuickDateRangePickerProps {
  startTime: number | null;  // UNIX 毫秒戳
  endTime: number | null;
  onStartChange: (ts: number | null) => void;
  onEndChange: (ts: number | null) => void;
}

interface QuickOption {
  type: string;
  label: string;
}

const QUICK_OPTIONS: QuickOption[] = [
  { type: 'today', label: '今天' },
  { type: '3days', label: '近 3 天' },
  { type: '7days', label: '近 1 周' },
  { type: '14days', label: '近 2 周' },
  { type: '30days', label: '近 1 个月' },
  { type: 'custom', label: '自定义' },
];

export default function QuickDateRangePicker({
  startTime,
  endTime,
  onStartChange,
  onEndChange,
}: QuickDateRangePickerProps) {
  const [isCustom, setIsCustom] = useState(false);

  // Format timestamp to YYYY-MM-DD HH:mm (Beijing Time)
  const formatTimestamp = (ts: number | null): string => {
    if (!ts) return '-';
    return formatBeijingTime(ts, 'date') + ' ' + formatBeijingTime(ts, 'time').replace(' (CST)', '');
  };

  // Handle quick option selection
  const handleOptionClick = (optionType: string) => {
    if (optionType === 'custom') {
      setIsCustom(true);
      return;
    }

    setIsCustom(false);
    const now = Date.now();
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    let startTs: number;

    switch (optionType) {
      case 'today':
        startTs = today.getTime();
        break;
      case '3days':
        startTs = new Date(now - 3 * 24 * 60 * 60 * 1000).setHours(0, 0, 0, 0);
        break;
      case '7days':
        startTs = new Date(now - 7 * 24 * 60 * 60 * 1000).setHours(0, 0, 0, 0);
        break;
      case '14days':
        startTs = new Date(now - 14 * 24 * 60 * 60 * 1000).setHours(0, 0, 0, 0);
        break;
      case '30days':
        startTs = new Date(now - 30 * 24 * 60 * 60 * 1000).setHours(0, 0, 0, 0);
        break;
      default:
        startTs = today.getTime();
    }

    onStartChange(startTs);
    onEndChange(now);
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
    const date = new Date(ts);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day}T${hours}:${minutes}`;
  };

  return (
    <div className="space-y-3">
      {/* Quick option buttons */}
      <div className="flex flex-wrap gap-2">
        {QUICK_OPTIONS.map((option) => (
          <button
            key={option.type}
            onClick={() => handleOptionClick(option.type)}
            className={cn(
              'px-3 py-1.5 text-sm font-medium rounded-lg transition-all border',
              isCustom && option.type === 'custom'
                ? 'bg-black text-white border-black'
                : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
            )}
          >
            {option.label}
          </button>
        ))}
      </div>

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
      <div className="flex items-center gap-2 text-xs text-gray-600 bg-gray-50 rounded-lg px-3 py-2">
        <Clock className="w-3.5 h-3.5" />
        <span>
          {formatTimestamp(startTime)} → {formatTimestamp(endTime)}
        </span>
      </div>
    </div>
  );
}
