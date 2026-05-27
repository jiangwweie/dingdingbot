import React from 'react';
import { AlertCircle, ArrowRight, CheckCircle2, Clock3, LockKeyhole, ShieldAlert, X } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Badge } from '@/src/components/ui/Badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { cn } from '@/src/lib/utils';
import type { BrcActionCard, ReadinessAction } from '@/src/services/api';

export type CapabilityStatus =
  | 'Available now'
  | 'Operation Preflight available'
  | 'Preflight planning'
  | 'Legacy/dev path'
  | 'Requires Operation Layer'
  | 'Design surface'
  | 'Unavailable'
  | 'Forbidden';

export function CapabilityBadge({ status }: { status: CapabilityStatus }) {
  const variant: Record<CapabilityStatus, 'success' | 'info' | 'warning' | 'danger' | 'outline'> = {
    'Available now': 'success',
    'Operation Preflight available': 'success',
    'Preflight planning': 'warning',
    'Legacy/dev path': 'info',
    'Requires Operation Layer': 'warning',
    'Design surface': 'outline',
    Unavailable: 'danger',
    Forbidden: 'danger',
  };
  return <Badge variant={variant[status]}>{status}</Badge>;
}

export function capabilityForActionCard(action: BrcActionCard): CapabilityStatus {
  if (!action.enabled) return 'Unavailable';
  if (action.action_type === 'testnet_rehearsal') return 'Legacy/dev path';
  if (
    action.action_type === 'enter_monitor'
    || action.action_type === 'pause_new_entries'
    || action.action_type === 'emergency_stop_runtime'
    || action.action_type === 'emergency_flatten'
  ) {
    return 'Requires Operation Layer';
  }
  return 'Design surface';
}

export function ActionCardSummaryModal({
  action,
  onClose,
}: {
  action: BrcActionCard | null;
  onClose: () => void;
}) {
  if (!action) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/70 p-4">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-auto rounded-sm border border-zinc-200 bg-white shadow-xl dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex items-start justify-between gap-3 border-b border-zinc-200 p-4 dark:border-zinc-800">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Action Card Summary</p>
            <h2 className="mt-1 text-base font-bold text-zinc-950 dark:text-zinc-100">{actionTitle(action)}</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-sm border border-zinc-300 p-1.5 text-zinc-600 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
            title="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-3 p-4 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
          <div className="rounded-sm border border-amber-500/30 bg-amber-500/[0.05] p-3 text-amber-800 dark:text-amber-200">
            Phase 0 Action Card Summary. This is assembled from current readiness data.
            Generic backend Operation Preflight is not enabled yet.
          </div>
          <div className="flex flex-wrap gap-2">
            <CapabilityBadge status={capabilityForActionCard(action)} />
            <StatusBadge state={action.enabled ? 'enabled by readiness' : 'disabled by readiness'} />
            {action.final_state_proof_required && <Badge variant="warning">final-state proof</Badge>}
          </div>
          <QuickFact label="Current state" value={action.current_state} />
          <QuickFact label="Allowed next states" value={action.allowed_next_states.join(', ') || 'none'} />
          <QuickFact label="Blocked next states" value={action.blocked_next_states.join(', ') || 'none'} />
          <QuickFact label="What will change" value={action.what_will_change} />
          <QuickFact label="What will not change" value={action.what_will_not_change} />
          <QuickFact label="Account impact" value={action.account_impact} />
          {action.confirmation_phrase && (
            <QuickFact label="Confirmation phrase" value={<span className="font-mono">{action.confirmation_phrase}</span>} />
          )}
          {action.disabled_reason && (
            <div className="rounded-sm border border-rose-500/30 bg-rose-500/[0.05] p-3 text-rose-700 dark:text-rose-300">
              Disabled reason: {action.disabled_reason}
            </div>
          )}
          {action.advisory_warnings.length > 0 && (
            <div>
              <p className="mb-1 text-[10px] font-bold uppercase tracking-widest text-zinc-500">Advisory warnings</p>
              <ul className="list-disc space-y-1 pl-5">
                {action.advisory_warnings.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>
          )}
          {action.hard_blocks.length > 0 && (
            <div>
              <p className="mb-1 text-[10px] font-bold uppercase tracking-widest text-zinc-500">Hard blocks</p>
              <ul className="list-disc space-y-1 pl-5">
                {action.hard_blocks.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>
          )}
          <JsonDetails data={action} label="Readiness action card JSON" />
        </div>
      </div>
    </div>
  );
}

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
    ['现在', current],
    ['下一步', next],
    ['项目节奏', global],
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

export function ConsoleStatusBar({
  items,
}: {
  items: Array<{ label: string; value: React.ReactNode; tone?: 'info' | 'success' | 'warning' | 'danger' | 'outline' }>;
}) {
  return (
    <div className="grid grid-cols-2 gap-2 xl:grid-cols-5">
      {items.map((item) => (
        <div key={item.label} className="rounded-sm border border-zinc-200 bg-white px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900">
          <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">{item.label}</p>
          <div className="mt-1 text-sm font-bold text-zinc-900 dark:text-zinc-100">
            {typeof item.value === 'string' ? <Badge variant={item.tone || 'outline'}>{item.value}</Badge> : item.value}
          </div>
        </div>
      ))}
    </div>
  );
}

export function PrimaryActionPanel({
  title,
  subtitle,
  to,
  buttonLabel,
  enabled = true,
  disabledReason,
}: {
  title: string;
  subtitle: string;
  to: string;
  buttonLabel: string;
  enabled?: boolean;
  disabledReason?: string;
}) {
  return (
    <Card className="border-blue-500/30 bg-blue-500/[0.04]">
      <CardContent className="flex flex-col gap-4 p-4 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-blue-500">Next</p>
          <h2 className="mt-1 text-xl font-bold text-zinc-950 dark:text-zinc-100">{title}</h2>
          <p className="mt-1 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">{subtitle}</p>
          {!enabled && disabledReason && (
            <p className="mt-2 text-xs font-medium text-amber-600 dark:text-amber-300">{disabledReason}</p>
          )}
        </div>
        {enabled ? (
          <Link
            to={to}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-sm bg-blue-600 px-4 py-2 text-sm font-bold text-white hover:bg-blue-500"
          >
            {buttonLabel}
            <ArrowRight className="h-4 w-4" />
          </Link>
        ) : (
          <button
            className="inline-flex min-h-11 cursor-not-allowed items-center justify-center rounded-sm border border-zinc-300 px-4 py-2 text-sm font-bold text-zinc-500 dark:border-zinc-700"
            disabled
          >
            当前不可用
          </button>
        )}
      </CardContent>
    </Card>
  );
}

export function SafetyControlBar({ actions }: { actions: BrcActionCard[] }) {
  return (
    <div className="grid grid-cols-1 gap-2 lg:grid-cols-3">
      {actions.map((action) => (
        <ApplicationActionCard key={action.action_card_id} action={action} compact />
      ))}
    </div>
  );
}

export function QuickFact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex min-h-9 items-center justify-between gap-3 border-b border-zinc-100 py-2 last:border-0 dark:border-zinc-800">
      <span className="text-xs text-zinc-500">{label}</span>
      <span className="min-w-0 text-right text-sm font-semibold text-zinc-900 dark:text-zinc-100">{value}</span>
    </div>
  );
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
      <p className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">系统现在怎么样</p>
          <h2 className="mt-1 text-lg font-bold text-zinc-900 dark:text-zinc-100">{conclusion}</h2>
          <p className="mt-2 text-sm leading-6 text-zinc-700 dark:text-zinc-300">原因：{why}</p>
        </div>
        <div className="rounded-sm border border-zinc-200 bg-white/60 px-3 py-2 text-xs leading-5 text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950/50 dark:text-zinc-300">
          <p className="font-bold">会不会影响真实账户</p>
          <p>{accountImpact}</p>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-1 gap-2 lg:grid-cols-3">
        <SummaryBlock label="现在可以做" value={canDo} />
        <SummaryBlock label="现在不能做" value={cannotDo} />
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

export function ApplicationActionCard({ action, compact = false }: { action: BrcActionCard; compact?: boolean }) {
  const tone = action.enabled
    ? action.final_state_proof_required
      ? 'border-amber-500/30 bg-amber-500/[0.04]'
      : 'border-emerald-500/30 bg-emerald-500/[0.04]'
    : 'border-zinc-200 bg-zinc-50 opacity-80 dark:border-zinc-800 dark:bg-zinc-900/50';
  const isDanger = action.action_type === 'emergency_stop_runtime' || action.action_type === 'emergency_flatten';
  const buttonClass = isDanger
    ? 'border-rose-600 bg-rose-600 text-white hover:bg-rose-500'
    : action.final_state_proof_required
      ? 'border-amber-500 bg-amber-500 text-white hover:bg-amber-400'
      : 'border-blue-600 bg-blue-600 text-white hover:bg-blue-500';

  return (
    <Card className={tone}>
      <CardHeader>
        <CardTitle className="flex items-center justify-between gap-2">
          <span>{actionTitle(action)}</span>
          <CapabilityBadge status={capabilityForActionCard(action)} />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
        {!compact && <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{shortActionLine(action)}</p>}
        {!action.enabled && (
          <p className="rounded-sm border border-amber-500/30 bg-amber-500/[0.05] px-2 py-1 text-xs text-amber-700 dark:text-amber-300">
            {action.disabled_reason || '应用检查未放行。'}
          </p>
        )}
        {action.route && action.enabled ? (
          <Link
            to={action.route}
            className={`mt-1 inline-flex min-h-9 w-full items-center justify-center gap-2 rounded-sm border px-3 py-2 text-xs font-bold ${buttonClass}`}
          >
            {buttonLabel(action)}
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        ) : (
          <button
            className="mt-1 inline-flex min-h-9 w-full cursor-not-allowed items-center justify-center rounded-sm border border-zinc-300 px-3 py-2 text-xs font-bold text-zinc-500 dark:border-zinc-700"
            disabled
          >
            {action.enabled ? buttonLabel(action) : '当前不可点'}
          </button>
        )}
        {!compact && (
          <details className="rounded-sm border border-zinc-200 bg-white/50 p-2 dark:border-zinc-800 dark:bg-zinc-950/40">
            <summary className="cursor-pointer text-[11px] font-bold uppercase tracking-widest text-zinc-500">
              Details
            </summary>
            <div className="mt-2 space-y-1">
              <p>状态：<span className="font-mono">{action.current_state}</span></p>
              <p>影响：{action.account_impact}</p>
              <p>会改变：{action.what_will_change}</p>
              <p>不会改变：{action.what_will_not_change}</p>
              {action.confirmation_phrase && <p>确认短语：<span className="font-mono">{action.confirmation_phrase}</span></p>}
              <p>依据：<span className="font-mono">{action.fact_snapshot_id}</span></p>
              <p>检查：<span className="font-mono">{action.preflight_result_id}</span></p>
            </div>
          </details>
        )}
      </CardContent>
    </Card>
  );
}

function actionTitle(action: BrcActionCard): string {
  const labels: Record<BrcActionCard['action_type'], string> = {
    read_status: '看当前状态',
    enter_monitor: '进入监控 monitor',
    testnet_rehearsal: '准备 testnet 演练',
    pause_new_entries: '暂停新开仓',
    emergency_stop_runtime: '停止 runtime',
    emergency_flatten: 'Flatten dry-run',
  };
  return labels[action.action_type] || action.title;
}

function buttonLabel(action: BrcActionCard): string {
  const labels: Record<BrcActionCard['action_type'], string> = {
    read_status: '查看状态',
    enter_monitor: '进入监控',
    testnet_rehearsal: 'Fixed rehearsal',
    pause_new_entries: 'Pause',
    emergency_stop_runtime: 'Stop',
    emergency_flatten: 'Dry-run plan',
  };
  return labels[action.action_type] || action.button_label;
}

function shortActionLine(action: BrcActionCard): string {
  if (!action.enabled) return '当前不能执行。';
  const labels: Record<BrcActionCard['action_type'], string> = {
    read_status: '只读查看，不改变账户。',
    enter_monitor: '进入监控，不开新仓。',
    testnet_rehearsal: '进入固定 testnet 演练流程。',
    pause_new_entries: '阻止新增风险。',
    emergency_stop_runtime: '停止 runtime 活动。',
    emergency_flatten: '仅生成 dry-run plan，不撤单、不平仓。',
  };
  return labels[action.action_type] || action.what_will_change;
}

export function MainFlowCard({
  enabled,
  disabledReason,
}: {
  enabled: boolean;
  disabledReason?: string;
}) {
  return (
    <Card className={enabled ? 'border-blue-500/30 bg-blue-500/[0.04]' : 'border-amber-500/30 bg-amber-500/[0.04]'}>
      <CardHeader>
        <CardTitle className="flex items-center justify-between gap-2">
          <span>主链路入口 Main Flow</span>
          <StatusBadge state={enabled ? 'ready' : 'not ready'} />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
        <p className="font-semibold text-zinc-900 dark:text-zinc-100">
          {enabled ? '现在可以准备受控 testnet 演练。' : '现在还不能准备受控 testnet 演练。'}
        </p>
        <ol className="list-decimal space-y-1 pl-4">
          <li>进入 LLM Copilot（唯一自然语言入口）。</li>
          <li>输入：帮我准备下一轮 testnet 演练。</li>
          <li>检查系统识别结果必须是 Controlled Testnet。</li>
          <li>手动输入 CONFIRM_BRC_TESTNET_REHEARSAL。</li>
          <li>执行后到 Review / Audit Trail 复盘证据链。</li>
        </ol>
        <p>
          不会发生：真实实盘、提现/转账、自动调仓或任意人工下单。
        </p>
        {!enabled && (
          <p className="rounded-sm border border-amber-500/30 bg-amber-500/[0.05] px-2 py-1 text-amber-700 dark:text-amber-300">
            当前缺失：{disabledReason || '系统还没确认 testnet workflow 可用。'}
          </p>
        )}
        {enabled ? (
          <Link
            to="/llm-copilot"
            className="inline-flex items-center gap-2 rounded-sm border border-blue-500 bg-blue-600 px-3 py-2 text-[11px] font-bold uppercase tracking-widest text-white"
          >
            进入 LLM Copilot
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        ) : (
          <Link
            to="/runtime-control"
            className="inline-flex items-center gap-2 rounded-sm border border-amber-500 px-3 py-2 text-[11px] font-bold uppercase tracking-widest text-amber-700 dark:text-amber-300"
          >
            查看缺失门槛
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
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
      <p>系统没有继续。原因：{userMessage}</p>
      <p className="mt-1">这不会触发交易风险。先看“现在”和“下一步”，必要时再展开技术数据。</p>
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
        <JsonDetails data={action} label="展开明细" />
      </ExplanationCard>
    </div>
  );
}

export function GuardNote() {
  return (
    <div className="flex items-start gap-2 rounded-sm border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs leading-5 text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-400">
      <LockKeyhole className="mt-0.5 h-3.5 w-3.5 text-zinc-500" />
      <span>控制台不会提供真实实盘、提现、转账、自动下单入口。受控 testnet 也必须走固定流程和手动确认。</span>
    </div>
  );
}
