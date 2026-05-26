import { useEffect, useState } from 'react';
import { Activity, CircleDollarSign, GitBranch, ShieldAlert, ShieldCheck } from 'lucide-react';
import { brcApi, ReadinessResponse } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import {
  ApplicationActionCard,
  DeveloperDetails,
  ErrorState,
  GuardNote,
  OwnerSummary,
  StageStrip,
  StatusBadge,
} from './ConsolePrimitives';
import { whyText } from './readiness';

export default function CommandCenter() {
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    brcApi.readiness().then(setReadiness).catch(setError);
  }, []);

  if (error) return <ErrorState error={error} />;
  if (!readiness) return <div className="text-xs text-zinc-500">正在读取控制台状态...</div>;

  const riskAccount = readiness.risk_account_summary || {};
  const exposure = recordAt(riskAccount, 'exposure_orders');
  const playbook = readiness.strategy_playbook_summary || readiness.playbook_summary || {};
  const environment = readiness.environment_boundary || {};
  const futureLive = recordAt(environment, 'future_live');
  const enabledActions = readiness.action_cards.filter((action) => action.enabled).map((action) => action.title);
  const canDo = enabledActions.length ? enabledActions.join('；') : '先看状态，不做动作。';
  const latestAudit = readiness.latest_audit;

  return (
    <div className="space-y-4">
      <StageStrip
        current="Command Center 控制台"
        next={readiness.next_step}
        global="先把本地控制台理顺，再推进 R5 全链路。"
      />
      <OwnerSummary
        conclusion={`现在系统状态：${readiness.current_conclusion}`}
        why={whyText(readiness)}
        canDo={canDo}
        cannotDo="不能开 real live/mainnet，不能提现/转账，不能自动下单，也不能跳过 Owner 确认。"
        accountImpact={readiness.account_impact}
        next="先在 LLM Copilot 里说你的想法；真正能点的动作只看右侧 Action Card。"
        tone={readiness.risk_decision === 'ALLOW_MONITOR' ? 'success' : readiness.risk_decision === 'ALLOW_READ' ? 'info' : 'warning'}
      />
      <GuardNote />

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-4">
        <MetricCard
          icon={<ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />}
          title="Risk Decision"
          rows={[
            ['系统判断', <StatusBadge state={readiness.risk_decision} />],
            ['运行状态', <StatusBadge state={readiness.runtime_state} />],
            ['当前模式', readiness.mode],
          ]}
        />
        <MetricCard
          icon={<Activity className="h-3.5 w-3.5 text-blue-500" />}
          title="环境边界"
          rows={[
            ['当前环境', stringAt(environment, 'current', 'simulation')],
            ['交易所模式', stringAt(environment, 'exchange_mode', 'unknown')],
            ['Live', stringAt(futureLive, 'display', 'disabled_boundary')],
          ]}
        />
        <MetricCard
          icon={<GitBranch className="h-3.5 w-3.5 text-violet-500" />}
          title="打法 / Playbook"
          rows={[
            ['Playbook', stringAt(playbook, 'current_playbook_id', 'PB-000-OBSERVE-ONLY')],
            ['当前状态', stringAt(playbook, 'current_mode', readiness.runtime_state)],
            ['R5', stringAt(recordAt(playbook, 'r5_carrier'), 'implementation_status', 'later_slice')],
          ]}
        />
        <MetricCard
          icon={<CircleDollarSign className="h-3.5 w-3.5 text-amber-500" />}
          title="账户 / 仓位"
          rows={[
            ['持仓', String(valueAt(exposure, 'active_position_count', 0))],
            ['挂单', String(valueAt(exposure, 'open_order_count', 0))],
            ['是否空仓', <StatusBadge state={stringAt(recordAt(exposure, 'flatness_proof'), 'all_local_flat', 'unknown')} />],
          ]}
        />
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[1.1fr_0.9fr]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldAlert className="h-3.5 w-3.5 text-amber-500" />
              风险与账户概览
            </CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300 md:grid-cols-2">
            <Row label="真实账户影响" value={stringAt(recordAt(riskAccount, 'account_state'), 'real_account_impact', 'none')} />
            <Row label="订单来源" value={stringAt(exposure, 'order_source', 'unknown')} />
            <Row label="是否有未知风险" value={<StatusBadge state={valueAt(exposure, 'unknown_exposure', 'unknown')} />} />
            <Row label="审计可写" value={<StatusBadge state={valueAt(riskAccount, 'audit_writable', 'unknown')} />} />
            <Row label="急停可用" value={<StatusBadge state={valueAt(riskAccount, 'cutoff_available', 'unknown')} />} />
            <Row label="最近记录" value={latestAudit ? stringAt(latestAudit, 'title', stringAt(latestAudit, 'type', 'event')) : '暂无'} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>哪些环境能用</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
            <Row label="可用范围" value={arrayAt(environment, 'executable_modes').join(', ') || 'local/mock/testnet'} />
            <Row label="Live 是否可用" value={<StatusBadge state={valueAt(futureLive, 'available', false)} />} />
            <Row label="是否生产授权" value={<StatusBadge state={valueAt(environment, 'production_authorized', false)} />} />
            <p className="rounded-sm border border-zinc-200 p-2 text-[11px] leading-4 text-zinc-500 dark:border-zinc-800">
              live 这里只是提醒“未来有这个边界”，不是开关；v0 不会用 trade 这个状态名。
            </p>
          </CardContent>
        </Card>
      </div>

      <section className="space-y-2">
        <h3 className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">Action Card：可考虑的动作</h3>
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
          {readiness.action_cards.map((action) => (
            <ApplicationActionCard key={action.action_card_id} action={action} />
          ))}
        </div>
      </section>

      <section className="space-y-2">
        <h3 className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">全局安全按钮</h3>
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
          {readiness.global_cutoff_controls.map((action) => (
            <ApplicationActionCard key={action.action_card_id} action={action} />
          ))}
        </div>
      </section>

      <DeveloperDetails data={readiness} label="展开完整技术数据" />
    </div>
  );
}

function MetricCard({
  icon,
  title,
  rows,
}: {
  icon: React.ReactNode;
  title: string;
  rows: Array<[string, React.ReactNode]>;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">{icon}{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
        {rows.map(([label, value]) => (
          <Row key={label} label={label} value={value} />
        ))}
      </CardContent>
    </Card>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-zinc-100 pb-2 last:border-0 last:pb-0 dark:border-zinc-800">
      <span className="text-zinc-500">{label}</span>
      <span className="max-w-[65%] text-right font-medium">{value}</span>
    </div>
  );
}

function recordAt(source: Record<string, unknown> | undefined | null, key: string): Record<string, unknown> {
  const value = source?.[key];
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function valueAt(source: Record<string, unknown> | undefined | null, key: string, fallback: unknown): unknown {
  return source && key in source ? source[key] : fallback;
}

function stringAt(source: Record<string, unknown> | undefined | null, key: string, fallback: string): string {
  const value = valueAt(source, key, fallback);
  return typeof value === 'string' ? value : String(value);
}

function arrayAt(source: Record<string, unknown> | undefined | null, key: string): string[] {
  const value = source?.[key];
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}
