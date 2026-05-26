import React from 'react';
import { AlertCircle, ArrowRight, CheckCircle2, Clock3, LockKeyhole, ShieldAlert } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Badge } from '@/src/components/ui/Badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { cn } from '@/src/lib/utils';
import type { ReadinessAction } from '@/src/services/api';

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

export function OwnerSummary({
  conclusion,
  why,
  canDo,
  cannotDo,
  accountImpact,
  next,
  tone = 'info',
}: {
  conclusion: string;
  why: string;
  canDo: string;
  cannotDo: string;
  accountImpact: string;
  next: string;
  tone?: 'info' | 'success' | 'warning' | 'danger';
}) {
  const toneClass = {
    info: 'border-blue-500/30 bg-blue-500/[0.04]',
    success: 'border-emerald-500/30 bg-emerald-500/[0.04]',
    warning: 'border-amber-500/30 bg-amber-500/[0.05]',
    danger: 'border-rose-500/30 bg-rose-500/[0.05]',
  }[tone];
  return (
    <div className={cn('rounded-sm border p-4', toneClass)}>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">当前结论</p>
          <h2 className="mt-1 text-lg font-bold text-zinc-900 dark:text-zinc-100">{conclusion}</h2>
          <p className="mt-2 text-sm leading-6 text-zinc-700 dark:text-zinc-300">原因：{why}</p>
        </div>
        <div className="rounded-sm border border-zinc-200 bg-white/60 px-3 py-2 text-xs leading-5 text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950/50 dark:text-zinc-300">
          <p className="font-bold">是否影响真实账户</p>
          <p>{accountImpact}</p>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-1 gap-2 lg:grid-cols-3">
        <SummaryBlock label="你现在可以做" value={canDo} />
        <SummaryBlock label="你现在不能做" value={cannotDo} />
        <SummaryBlock label="下一步" value={next} />
      </div>
    </div>
  );
}

function SummaryBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-sm border border-zinc-200 bg-white/50 p-3 dark:border-zinc-800 dark:bg-zinc-950/40">
      <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">{label}</p>
      <p className="mt-1 text-xs leading-5 text-zinc-700 dark:text-zinc-300">{value}</p>
    </div>
  );
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

export function DeveloperDetails({ data, label = 'Developer detail（技术详情）' }: { data: unknown; label?: string }) {
  if (!data) return null;
  return (
    <details className="rounded-sm border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-950">
      <summary className="cursor-pointer text-[11px] font-bold uppercase tracking-widest text-zinc-500">
        {label}
      </summary>
      <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap text-[11px] leading-5 text-zinc-700 dark:text-zinc-300">
        {JSON.stringify(data, null, 2)}
      </pre>
    </details>
  );
}

export function ActionCard({ action }: { action: ReadinessAction }) {
  const tone = action.enabled
    ? action.risk_level === 'controlled_testnet'
      ? 'border-amber-500/30 bg-amber-500/[0.04]'
      : 'border-emerald-500/30 bg-emerald-500/[0.04]'
    : 'border-zinc-200 bg-zinc-50 opacity-80 dark:border-zinc-800 dark:bg-zinc-900/50';
  const riskLabel = {
    read_only: 'Read-only（只读）',
    controlled_testnet: 'Controlled Testnet（受控测试网）',
    blocked: 'Unavailable（当前不可用）',
  }[action.risk_level];
  return (
    <Card className={tone}>
      <CardHeader>
        <CardTitle className="flex items-center justify-between gap-2">
          <span>{action.title}</span>
          <StatusBadge state={action.enabled ? riskLabel : 'disabled'} />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
        <p>{action.description}</p>
        <p>
          <span className="font-bold">点击后会发生：</span>
          {action.what_happens}
        </p>
        <p>
          <span className="font-bold">不会发生：</span>
          {action.what_will_not_happen}
        </p>
        <p>
          <span className="font-bold">账户影响：</span>
          {action.account_impact}
        </p>
        {!action.enabled && (
          <p className="rounded-sm border border-amber-500/30 bg-amber-500/[0.05] px-2 py-1 text-amber-700 dark:text-amber-300">
            当前不可用：{action.disabled_reason || 'readiness 未确认此动作可用。'}
          </p>
        )}
        {action.route && action.enabled ? (
          <Link
            to={action.route}
            className="mt-2 inline-flex items-center gap-2 rounded-sm border border-blue-500 bg-blue-600 px-3 py-2 text-[11px] font-bold uppercase tracking-widest text-white"
          >
            {action.button_label}
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        ) : (
          <button
            className="mt-2 inline-flex cursor-not-allowed items-center gap-2 rounded-sm border border-zinc-300 px-3 py-2 text-[11px] font-bold uppercase tracking-widest text-zinc-500 dark:border-zinc-700"
            disabled
          >
            {action.button_label}
          </button>
        )}
      </CardContent>
    </Card>
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
  const isRuntimeControlDisabled = message.includes('RUNTIME_CONTROL_API_ENABLED')
    || message.includes('Runtime control API disabled');
  const userMessage = isRuntimeControlDisabled
    ? '当前无法执行需要 runtime 控制开关的动作。只读计划不应依赖这个开关；如果你仍看到此提示，请刷新页面或确认后端已更新。'
    : message;
  return (
    <ExplanationCard title="Blocked / 无法继续" icon={<ShieldAlert className="h-3.5 w-3.5" />} tone="danger">
      <p>系统没有继续执行。原因：{userMessage}</p>
      <p className="mt-1">这不会触发任何交易风险。请先查看“当前结论”和“下一步”，必要时再展开开发者详情。</p>
      <DeveloperDetails data={{ message }} />
    </ExplanationCard>
  );
}

export function ChainExplanation({
  ownerText,
  intent,
  action,
  blocked,
  mode = 'readonly',
}: {
  ownerText?: string;
  intent?: unknown;
  action?: unknown;
  blocked?: string;
  mode?: 'readonly' | 'testnet' | 'forbidden';
}) {
  const modeLabel = {
    readonly: 'Read-only（只读检查）',
    testnet: 'Controlled Testnet（受控测试网）',
    forbidden: 'Forbidden（禁止）',
  }[mode];
  const requirement = {
    readonly: '输入 CONFIRM_READ_ONLY_BRC 后，只读取 review/evidence/eligibility。',
    testnet: '输入 CONFIRM_BRC_TESTNET_REHEARSAL 前，还必须满足 runtime/testnet/profile/guard 条件。',
    forbidden: '不会生成可执行计划，需要修改意图或停留在只读复盘。',
  }[mode];
  return (
    <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
      <ExplanationCard title="系统理解" icon={<Clock3 className="h-3.5 w-3.5" />}>
        <ul className="space-y-1">
          <li>Owner 原始输入：{ownerText || '尚未输入'}</li>
          <li>系统识别意图：{String(intent || '等待生成')}</li>
          <li>风险分类：{modeLabel}</li>
          <li>需要确认：{requirement}</li>
        </ul>
      </ExplanationCard>
      <ExplanationCard
        title={blocked ? '为什么不能做' : '确认前检查'}
        icon={blocked ? <AlertCircle className="h-3.5 w-3.5" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
        tone={blocked ? 'danger' : 'success'}
      >
        {blocked ? (
          <p>{blocked}</p>
        ) : (
          <div className="space-y-1">
            <p>计划执行内容：读取 BRC 复盘/证据/下一轮资格，或进入固定受控 testnet workflow。</p>
            <p>不会执行：真实实盘、提现/转账、自动 sizing、策略池执行、任意下单。</p>
            <p>结果写入：operator ledger、workflow run、review/evidence。</p>
          </div>
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
