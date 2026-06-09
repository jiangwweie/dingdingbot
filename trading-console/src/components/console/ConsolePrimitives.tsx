import type { ReactNode } from 'react';
import { ChevronRight, Info } from 'lucide-react';
import { cn } from '@/lib/utils';

export type ConsoleTone = 'normal' | 'attention' | 'intervention' | 'blocked' | 'unavailable';

const toneStyles: Record<ConsoleTone, {
  text: string;
  border: string;
  bg: string;
  dot: string;
  chip: string;
}> = {
  normal: {
    text: 'text-emerald-300',
    border: 'border-emerald-500/35',
    bg: 'bg-emerald-500/10',
    dot: 'bg-emerald-400',
    chip: 'border-emerald-400/40 bg-emerald-500/10 text-emerald-200',
  },
  attention: {
    text: 'text-amber-300',
    border: 'border-amber-500/35',
    bg: 'bg-amber-500/10',
    dot: 'bg-amber-400',
    chip: 'border-amber-400/40 bg-amber-500/10 text-amber-200',
  },
  intervention: {
    text: 'text-rose-300',
    border: 'border-rose-500/35',
    bg: 'bg-rose-500/10',
    dot: 'bg-rose-400',
    chip: 'border-rose-400/40 bg-rose-500/10 text-rose-200',
  },
  blocked: {
    text: 'text-red-300',
    border: 'border-red-500/35',
    bg: 'bg-red-500/10',
    dot: 'bg-red-400',
    chip: 'border-red-400/40 bg-red-500/10 text-red-200',
  },
  unavailable: {
    text: 'text-slate-300',
    border: 'border-slate-500/35',
    bg: 'bg-slate-500/10',
    dot: 'bg-slate-400',
    chip: 'border-slate-500/45 bg-slate-800/80 text-slate-300',
  },
};

export function toneClass(tone: ConsoleTone, part: keyof typeof toneStyles.normal): string {
  return toneStyles[tone][part];
}

export function ConsolePanel({
  title,
  caption,
  action,
  children,
  className,
}: {
  title?: string;
  caption?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn('overflow-hidden rounded-md border border-slate-700/70 bg-slate-900/55 shadow-[0_1px_0_rgba(255,255,255,0.04)_inset]', className)}>
      {(title || caption || action) && (
        <div className="flex min-h-12 items-center justify-between gap-3 border-b border-slate-700/70 px-4 py-3">
          <div className="min-w-0">
            {title && <h2 className="truncate text-sm font-semibold text-slate-100">{title}</h2>}
            {caption && <p className="mt-0.5 truncate text-xs text-slate-500">{caption}</p>}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function StatusChip({
  tone,
  children,
  className,
}: {
  tone: ConsoleTone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span className={cn('inline-flex h-7 items-center gap-1.5 rounded-full border px-3 text-xs font-medium', toneClass(tone, 'chip'), className)}>
      <span className={cn('h-1.5 w-1.5 rounded-full', toneClass(tone, 'dot'))} />
      {children}
    </span>
  );
}

export function MetricRailItem({
  label,
  value,
  tone = 'unavailable',
  sub,
  icon,
}: {
  label: string;
  value: string | number;
  tone?: ConsoleTone;
  sub?: string;
  icon?: ReactNode;
}) {
  return (
    <div className="min-h-20 border-r border-slate-700/70 px-5 py-4 last:border-r-0">
      <div className="flex items-center gap-2 text-[11px] font-medium uppercase text-slate-400">
        {icon}
        <span className={cn('h-2 w-2 rounded-sm', toneClass(tone, 'dot'))} />
        <span>{label}</span>
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="font-mono text-3xl font-semibold text-slate-100">{value}</span>
        {sub && <span className="text-xs text-slate-500">{sub}</span>}
      </div>
    </div>
  );
}

export function EntityRow({
  title,
  subtitle,
  cells,
  tone = 'unavailable',
  active = false,
  action,
}: {
  title: string;
  subtitle?: string;
  cells: Array<{ label: string; value: ReactNode; className?: string }>;
  tone?: ConsoleTone;
  active?: boolean;
  action?: ReactNode;
}) {
  return (
    <div className={cn(
      'grid min-h-20 grid-cols-1 gap-2 border-b border-slate-800/90 px-4 py-3 text-sm last:border-b-0 md:grid-cols-[minmax(160px,1.2fr)_repeat(4,minmax(0,0.78fr))_auto]',
      active && 'bg-emerald-500/7 shadow-[3px_0_0_#7ddc96_inset]',
    )}>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className={cn('h-2 w-2 rounded-full', toneClass(tone, 'dot'))} />
          <div className="truncate font-medium text-slate-100">{title}</div>
        </div>
        {subtitle && <div className="mt-1 truncate text-xs text-slate-500">{subtitle}</div>}
      </div>
      {cells.slice(0, 4).map((cell) => (
        <div key={cell.label} className="min-w-0">
          <div className="text-[11px] text-slate-500">{cell.label}</div>
          <div className={cn('mt-1 truncate text-slate-300', cell.className)}>{cell.value}</div>
        </div>
      ))}
      <div className="flex items-center justify-start md:justify-end">
        {action || <ChevronRight className="h-4 w-4 text-slate-600" />}
      </div>
    </div>
  );
}

export function InspectorPanel({
  title = '状态说明',
  items,
  footer,
}: {
  title?: string;
  items: Array<{
    title: string;
    body: string;
    tone?: ConsoleTone;
    action?: ReactNode;
  }>;
  footer?: ReactNode;
}) {
  return (
    <ConsolePanel title={title}>
      <div className="divide-y divide-slate-800/90">
        {items.map((item) => (
          <div key={item.title} className="flex gap-3 px-4 py-4">
            <div className={cn('mt-1 h-8 w-8 shrink-0 rounded-full border p-1.5', toneClass(item.tone || 'unavailable', 'border'), toneClass(item.tone || 'unavailable', 'bg'))}>
              <Info className={cn('h-4 w-4', toneClass(item.tone || 'unavailable', 'text'))} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium text-slate-100">{item.title}</div>
              <p className="mt-1 text-xs leading-5 text-slate-400">{item.body}</p>
              {item.action && <div className="mt-3">{item.action}</div>}
            </div>
          </div>
        ))}
      </div>
      {footer && <div className="border-t border-slate-800/90 px-4 py-3">{footer}</div>}
    </ConsolePanel>
  );
}

export function ActionNudge({
  tone = 'attention',
  text,
  action,
  onDismiss,
}: {
  tone?: ConsoleTone;
  text: string;
  action?: ReactNode;
  onDismiss?: () => void;
}) {
  return (
    <div className={cn('flex min-h-14 items-center justify-between gap-3 rounded-md border px-4 py-3 text-sm', toneClass(tone, 'border'), toneClass(tone, 'bg'))}>
      <div className="flex min-w-0 items-center gap-3">
        <span className={cn('h-2.5 w-2.5 shrink-0 rounded-sm', toneClass(tone, 'dot'))} />
        <span className="truncate text-slate-200">{text}</span>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {action}
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="cursor-pointer rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-400 transition hover:bg-slate-800 hover:text-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-500"
          >
            关闭
          </button>
        )}
      </div>
    </div>
  );
}
