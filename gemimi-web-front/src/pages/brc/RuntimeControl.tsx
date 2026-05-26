import { useEffect, useState } from 'react';
import { ShieldAlert } from 'lucide-react';
import { brcApi, ReadinessResponse, RuntimeSafetyResponse } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { ApplicationActionCard, DeveloperDetails, ErrorState, JsonDetails, MainFlowCard, OwnerSummary, StageStrip, StatusBadge } from './ConsolePrimitives';
import { actionCardDisabledReason, isActionCardEnabled, whyText } from './readiness';

export default function RuntimeControl() {
  const [safety, setSafety] = useState<RuntimeSafetyResponse | null>(null);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    Promise.all([brcApi.runtimeSafety(), brcApi.readiness()])
      .then(([safetyPayload, readinessPayload]) => {
        setSafety(safetyPayload);
        setReadiness(readinessPayload);
      })
      .catch(setError);
  }, []);

  if (error) return <ErrorState error={error} />;
  if (!safety) return <div className="text-xs text-zinc-500">正在读取运行控制状态...</div>;
  const mainFlowReady = isActionCardEnabled(readiness, 'testnet_rehearsal');
  const mainFlowDisabledReason = actionCardDisabledReason(readiness, 'testnet_rehearsal');
  const environment = readiness?.environment_boundary || {};
  const futureLive = recordAt(environment, 'future_live');

  return (
    <div className="space-y-4">
      <StageStrip
        current="Runtime Control 运行控制"
        next="查看当前状态、允许的状态变化和全局安全按钮。"
        global="这里只控制本地/testnet 边界；live 是不可用边界，不是开关。"
      />
      <OwnerSummary
        conclusion={readiness?.current_conclusion || (safety.runtime_bound ? '运行时已连接，但还要继续检查' : '当前不能执行交易相关动作')}
        why={readiness
          ? whyText(readiness)
          : safety.runtime_bound
          ? 'Runtime 已连接；是否能 testnet 还取决于 profile、testnet、GKS 和启动保护。'
          : 'Runtime 未连接，系统不能证明现在安全。'}
        canDo={mainFlowReady ? '进入 LLM Copilot，按固定 testnet 流程准备验收。' : '查看运行状态和缺失门槛。'}
        cannotDo="不能真实实盘、提现/转账、自动调仓、策略池执行或任意人工下单。"
        accountImpact="不会影响真实账户。这个页面主要展示状态和安全按钮。"
        next={mainFlowReady ? '去 LLM Copilot 创建受控 testnet workflow 并手动确认。' : `先处理缺失门槛：${mainFlowDisabledReason}`}
        tone={mainFlowReady ? 'success' : safety.runtime_bound ? 'warning' : 'danger'}
      />

      <MainFlowCard enabled={mainFlowReady} disabledReason={mainFlowDisabledReason} />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldAlert className="h-3.5 w-3.5 text-amber-500" />
            运行状态
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs leading-5 text-zinc-700 dark:text-zinc-300">{safety.human_summary}</p>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-4">
            <Metric label="Profile" value={safety.profile || 'unknown'} help="必须是固定 testnet profile，才能进入本轮验收。" />
            <Metric label="Testnet" value={<StatusBadge state={safety.testnet} />} help="必须明确为 true；unknown/false 都不能继续 testnet。" />
            <Metric label="GKS" value={<StatusBadge state={safety.gks_active ? 'blocked' : 'not blocked'} />} help="blocked 表示阻断新动作；not blocked 仍要看其他门槛。" />
            <Metric label="Startup Guard" value={<StatusBadge state={safety.startup_guard_armed ? 'armed' : 'blocked'} />} help="启动保护避免系统自动进入危险动作。" />
          </div>
          <JsonDetails data={safety} label="展开运行状态明细" />
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[0.9fr_1.1fr]">
        <Card>
          <CardHeader>
            <CardTitle>环境边界</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
            <Row label="当前环境" value={stringAt(environment, 'current', 'simulation')} />
            <Row label="交易所模式" value={stringAt(environment, 'exchange_mode', 'unknown')} />
            <Row label="可用范围" value={arrayAt(environment, 'executable_modes').join(', ') || 'local/mock/testnet'} />
            <Row label="Live 是否可用" value={<StatusBadge state={valueAt(futureLive, 'available', false)} />} />
            <p className="rounded-sm border border-zinc-200 p-2 text-[11px] leading-4 text-zinc-500 dark:border-zinc-800">
              live 不是切换开关。没有单独生产授权前，控制台不会开放 real live。
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>状态机</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
            <Row label="当前状态" value={<StatusBadge state={readiness?.runtime_state || 'observe'} />} />
            <Row label="v0 状态" value="observe / monitor / testnet_rehearsal / paused / stopped / flattening / attention_required" />
            <Row label="不用的词" value="v0 不用 trade；未来 live 另行授权后才可能出现 live_trade" />
          </CardContent>
        </Card>
      </div>

      <section className="space-y-2">
        <h3 className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">全局安全按钮</h3>
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
          {(readiness?.global_cutoff_controls || []).map((action) => (
            <ApplicationActionCard key={action.action_card_id} action={action} />
          ))}
        </div>
      </section>

      <DeveloperDetails data={readiness} label="展开 readiness 技术数据" />
    </div>
  );
}

function Metric({ label, value, help }: { label: string; value: React.ReactNode; help: string }) {
  return (
    <div className="rounded-sm border border-zinc-200 p-3 dark:border-zinc-800">
      <p className="mb-1 text-[10px] font-bold uppercase tracking-widest text-zinc-500">{label}</p>
      <div className="text-xs text-zinc-700 dark:text-zinc-300">{value}</div>
      <p className="mt-2 text-[11px] leading-4 text-zinc-500">{help}</p>
    </div>
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
