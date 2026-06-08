import React from 'react';
import { cn } from '@/lib/utils';
import { AlertTriangle, XCircle } from 'lucide-react';
import type { Envelope } from '@/types';
import { hasUnsafeNoActionFlag } from '@/lib/tradingConsoleApi';
import { blockingReasonLabel, dataStatusLabel, pageMoodClasses, type PageMood } from '@/lib/ownerViewModel';

export const Card = ({ className, children, ...props }: React.ComponentProps<'div'>) => (
  <div className={cn("bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm rounded-lg overflow-hidden", className)} {...props}>
    {children}
  </div>
);

export const Badge = ({ children, variant = 'normal', className, ...props }: { children: React.ReactNode; variant?: 'normal' | 'warning' | 'danger' | 'caution' | 'muted'; className?: string } & React.ComponentProps<'span'>) => {
  const variants = {
    normal: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300",
    warning: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300",
    danger: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300",
    caution: "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-300",
    muted: "bg-slate-50 text-slate-500 dark:bg-slate-800/50 dark:text-slate-400"
  };
  return <span className={cn("px-2.5 py-0.5 rounded-full text-xs font-medium", variants[variant], className)} {...props}>{children}</span>;
};

export const FreshnessBadge = ({ status }: { status: string }) => {
  const map: Record<string, { label: string; variant: any }> = {
    'fresh': { label: '数据已同步', variant: 'normal' },
    'warning': { label: '需关注', variant: 'warning' },
    'degraded': { label: '部分同步', variant: 'warning' },
    'not_live_connected': { label: '未同步', variant: 'caution' },
    'unknown': { label: '无法确认', variant: 'caution' }
  };
  const config = map[status] || map.unknown;
  return <Badge variant={config.variant}>{config.label}</Badge>;
};

export const SourceBadge = ({ source }: { source: string }) => {
  const map: Record<string, string> = {
    'pg': '本地系统', 'exchange': '交易所', 'exchange_normal': '交易所普通挂单',
    'exchange_stop': '交易所条件单', 'read_model': '系统汇总',
    'not_available': '暂无数据', 'unknown': '无法判断'
  };
  const label = map[source] || source;
  const isDanger = source === 'not_available' || source === 'unknown';
  return <Badge variant={isDanger ? 'danger' : 'caution'}>{label}</Badge>;
};

export const NotAvailableValue = () => <span className="text-slate-400 dark:text-slate-500 text-xs">暂无数据</span>;

export const PageHeader = ({
  title,
  subtitle,
  status,
  children,
}: {
  title: string;
  subtitle: string;
  status?: string;
  children?: React.ReactNode;
}) => (
  <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <p className="text-sm text-slate-500 mt-1">{subtitle}</p>
    </div>
    <div className="flex flex-wrap items-center gap-2">
      {status && <FreshnessBadge status={status} />}
      {children}
    </div>
  </div>
);

export const PageSummary = ({
  mood,
  title,
  description,
  children,
}: {
  mood: PageMood;
  title: string;
  description: string;
  children?: React.ReactNode;
}) => (
  <div className={cn("border rounded-lg p-4", pageMoodClasses(mood))}>
    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
      <div>
        <div className="text-base font-semibold">{title}</div>
        <p className="text-sm opacity-80 mt-1">{description}</p>
      </div>
      {children && <div className="shrink-0">{children}</div>}
    </div>
  </div>
);

export const Panel = ({ title, items, icon: Icon, variant = 'warning' }: { title: string, items: any[], icon: any, variant?: 'warning'|'danger'|'muted' }) => {
  if (!items || items.length === 0) return null;
  const v = {
    warning: "bg-amber-50 border-amber-200 dark:bg-amber-950/20 dark:border-amber-900/50 text-amber-800 dark:text-amber-300",
    danger: "bg-red-50 border-red-200 dark:bg-red-950/20 dark:border-red-900/50 text-red-800 dark:text-red-300",
    muted: "bg-slate-100 border-slate-300 dark:bg-slate-900 dark:border-slate-700 text-slate-800 dark:text-slate-300"
  };
  return (
    <div className={cn("border rounded-md p-4 mb-4 shadow-sm", v[variant])}>
      <div className="flex items-center gap-2 mb-2 font-semibold">
        <Icon className="w-5 h-5 flex-shrink-0" />
        <span>{title}</span>
      </div>
      <ul className="list-disc list-inside space-y-1.5 text-sm ml-1">
        {items.map((item, i) => (
          <li key={i} className="opacity-90">{blockingReasonLabel(item.message || item.error || item.code || 'unknown')}</li>
        ))}
      </ul>
    </div>
  );
};

export const WarningPanel = ({ warnings }: { warnings: any[] }) => <Panel title="需要关注的事项" items={warnings} icon={AlertTriangle} variant="warning" />;
export const BlockerPanel = ({ blockers }: { blockers: any[] }) => <Panel title="阻断事项" items={blockers} icon={XCircle} variant="danger" />;

export const ReadModelErrorPanel = ({ error }: { error: string | null }) => {
  if (!error) return null;
  return (
    <div className="border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-950/20 text-red-800 dark:text-red-300 rounded-md p-4 text-sm shadow-sm">
      <div className="font-semibold">当前内容暂不可用</div>
    </div>
  );
};

export const EnvelopeStatus = ({ envelope, error }: { envelope: Envelope<any> | null; error?: string | null }) => (
  <div className="space-y-3">
    <ReadModelErrorPanel error={error || null} />
    {hasUnsafeNoActionFlag(envelope) && (
      <Panel
        title="安全状态异常"
        items={[{ message: '控制台安全状态无法确认。' }]}
        icon={XCircle}
        variant="danger"
      />
    )}
    <BlockerPanel blockers={envelope?.blockers || []} />
    <WarningPanel warnings={envelope?.warnings || []} />
  </div>
);

export const DeferredActionSlot = ({ actionName, reason, ...props }: { actionName: string, reason?: string } & React.ComponentProps<'button'>) => (
  <button disabled className="w-full py-2 px-4 rounded-md border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 text-slate-400 dark:text-slate-500 text-sm cursor-not-allowed text-center transition-colors" {...props}>
    <div className="font-medium">{actionName}</div>
    <div className="text-xs mt-0.5">{reason || "当前版本不可操作"}</div>
  </button>
);

export const TechnicalDetails = ({ title = '技术信息', children }: { title?: string; children: React.ReactNode }) => (
  <details className="border border-slate-200 dark:border-slate-800 rounded-md bg-slate-50 dark:bg-slate-900/70 p-3">
    <summary className="cursor-pointer text-sm font-medium text-slate-600 dark:text-slate-300">{title}</summary>
    <div className="mt-3 text-xs text-slate-600 dark:text-slate-400">{children}</div>
  </details>
);

export const DataStatusLine = ({ envelope }: { envelope: Envelope<any> | null }) => (
  <span className="text-slate-500 dark:text-slate-400">
    数据状态：{dataStatusLabel(envelope?.freshness_status)}
  </span>
);
