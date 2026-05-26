import React from 'react';
import { AlertCircle, CheckCircle2, Clock3, LockKeyhole, ShieldAlert } from 'lucide-react';
import { Badge } from '@/src/components/ui/Badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { cn } from '@/src/lib/utils';

export function StageStrip({
  current,
  next,
  global,
}: {
  current: string;
  next: string;
  global: string;
}) {
  const items = [
    ['当前阶段', current],
    ['下一步建议', next],
    ['全局规划阶段', global],
  ];
  return (
    <div className="grid grid-cols-1 gap-2 lg:grid-cols-3">
      {items.map(([label, value]) => (
        <Card key={label}>
          <CardHeader>
            <CardTitle>{label}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs leading-5 text-zinc-700 dark:text-zinc-300">{value}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export function StatusBadge({ state }: { state?: unknown }) {
  const text = String(state ?? 'unknown');
  const lower = text.toLowerCase();
  const variant = lower.includes('block') || lower.includes('lock') || lower.includes('fail')
    ? 'danger'
    : lower.includes('wait') || lower.includes('pending') || lower.includes('review')
      ? 'warning'
      : lower.includes('true') || lower.includes('ok') || lower.includes('complete') || lower.includes('safe')
        ? 'success'
        : 'outline';
  return <Badge variant={variant}>{text}</Badge>;
}

export function ExplanationCard({
  title,
  icon,
  children,
  tone = 'info',
}: {
  title: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
  tone?: 'info' | 'success' | 'warning' | 'danger' | 'neutral';
}) {
  const toneClass = {
    info: 'border-blue-500/20 bg-blue-500/[0.03]',
    success: 'border-emerald-500/20 bg-emerald-500/[0.03]',
    warning: 'border-amber-500/20 bg-amber-500/[0.04]',
    danger: 'border-rose-500/20 bg-rose-500/[0.04]',
    neutral: '',
  }[tone];
  return (
    <Card className={cn(toneClass)}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {icon}
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-xs leading-5 text-zinc-700 dark:text-zinc-300">{children}</div>
      </CardContent>
    </Card>
  );
}

export function JsonDetails({ data, label = '查看 JSON / Evidence' }: { data: unknown; label?: string }) {
  if (!data) return null;
  return (
    <details className="mt-3 rounded-sm border border-zinc-200 bg-zinc-50 p-2 dark:border-zinc-800 dark:bg-zinc-950">
      <summary className="cursor-pointer text-[11px] font-bold uppercase tracking-widest text-zinc-500">
        {label}
      </summary>
      <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap text-[11px] leading-5 text-zinc-700 dark:text-zinc-300">
        {JSON.stringify(data, null, 2)}
      </pre>
    </details>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-sm border border-dashed border-zinc-300 p-6 text-center dark:border-zinc-800">
      <p className="text-xs font-bold text-zinc-700 dark:text-zinc-300">{title}</p>
      <p className="mt-1 text-xs leading-5 text-zinc-500">{body}</p>
    </div>
  );
}

export function ErrorState({ error }: { error: unknown }) {
  const message = typeof error === 'object' && error && 'message' in error
    ? String((error as { message?: unknown }).message)
    : String(error);
  return (
    <ExplanationCard title="Blocked / 无法继续" icon={<ShieldAlert className="h-3.5 w-3.5" />} tone="danger">
      <p>系统没有继续执行。原因：{message}</p>
      <p className="mt-1">请先检查配置、登录状态、runtime profile 或确认短语。这里不会自动重试高风险动作。</p>
    </ExplanationCard>
  );
}

export function ChainExplanation({
  ownerText,
  intent,
  action,
  blocked,
}: {
  ownerText?: string;
  intent?: unknown;
  action?: unknown;
  blocked?: string;
}) {
  return (
    <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
      <ExplanationCard title="链路解释" icon={<Clock3 className="h-3.5 w-3.5" />}>
        <ul className="space-y-1">
          <li>Owner 原始输入：{ownerText || '尚未输入'}</li>
          <li>系统识别意图：{String(intent || '等待生成')}</li>
          <li>将要执行：只读 review/evidence 或固定受控 testnet workflow</li>
          <li>不会执行：真实实盘、提现/转账、自动 sizing、策略池执行</li>
          <li>结果写入：operator ledger、workflow run、review/evidence</li>
        </ul>
      </ExplanationCard>
      <ExplanationCard
        title={blocked ? '为什么不能做' : '为什么可以继续'}
        icon={blocked ? <AlertCircle className="h-3.5 w-3.5" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
        tone={blocked ? 'danger' : 'success'}
      >
        {blocked ? (
          <p>{blocked}</p>
        ) : (
          <p>当前只是在受控治理链路中推进。任何可变更动作都需要 Owner 手动输入确认短语。</p>
        )}
        <JsonDetails data={action} label="展开计划明细" />
      </ExplanationCard>
    </div>
  );
}

export function GuardNote() {
  return (
    <div className="flex items-start gap-2 rounded-sm border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs leading-5 text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-400">
      <LockKeyhole className="mt-0.5 h-3.5 w-3.5 text-zinc-500" />
      <span>控制台不会展示真实实盘、提现、转账、自动下单入口。受控 testnet 也只能通过固定 workflow 和手动确认进入。</span>
    </div>
  );
}
