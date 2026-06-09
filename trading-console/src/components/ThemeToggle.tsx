import { Moon, Sun } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTheme } from '@/lib/theme';

export function ThemeToggle({
  compact = false,
  className,
}: {
  compact?: boolean;
  className?: string;
}) {
  const { isDark, toggleTheme } = useTheme();
  const Icon = isDark ? Sun : Moon;
  const targetLabel = isDark ? '白天模式' : '暗黑模式';
  const currentLabel = isDark ? '暗黑' : '白天';

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={`切换到${targetLabel}`}
      aria-pressed={isDark}
      title={`切换到${targetLabel}`}
      data-testid="theme-toggle"
      className={cn(
        'inline-flex min-h-9 cursor-pointer items-center justify-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100 hover:text-slate-950 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100',
        compact && 'min-h-9 w-9 px-0',
        className,
      )}
    >
      <Icon className="h-4 w-4" />
      {!compact && (
        <span>
          {currentLabel}
          <span className="text-slate-400 dark:text-slate-500"> / 切换</span>
        </span>
      )}
    </button>
  );
}
