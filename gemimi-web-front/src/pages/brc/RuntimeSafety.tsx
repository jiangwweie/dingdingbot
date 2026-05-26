import { useEffect, useState } from 'react';
import { ShieldAlert } from 'lucide-react';
import { brcApi, ReadinessResponse, RuntimeSafetyResponse } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { DeveloperDetails, ErrorState, JsonDetails, OwnerSummary, StageStrip, StatusBadge } from './ConsolePrimitives';
import { whyText } from './readiness';

export default function RuntimeSafety() {
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
  if (!safety) return <div className="text-xs text-zinc-500">加载 Runtime Safety...</div>;

  return (
    <div className="space-y-4">
      <StageStrip
        current={safety.current_stage}
        next={safety.next_recommended_step}
        global={safety.global_planning_stage}
      />
      <OwnerSummary
        conclusion={readiness?.current_conclusion || (safety.runtime_bound ? '运行时已连接，但仍需逐项检查' : '当前不可执行任何交易相关动作')}
        why={readiness
          ? whyText(readiness)
          : safety.runtime_bound
          ? 'Runtime 已绑定；是否能 testnet 还取决于 profile、testnet、GKS 和 Startup Guard。'
          : 'Runtime 未绑定，Testnet 状态未知，系统不能确认当前是否安全。'}
        canDo="查看运行安全状态，回到 Operator 生成只读计划。"
        cannotDo="不能进入 testnet 演练，不能下单、平仓、提现、转账或修改仓位。"
        accountImpact="不会影响真实账户。这个页面只读，不会发送交易指令。"
        next="如果要做 testnet 验收，先启动正确 runtime profile，再回到本页确认状态。"
        tone={safety.runtime_bound ? 'warning' : 'danger'}
      />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldAlert className="h-3.5 w-3.5 text-amber-500" />
            Runtime Safety（运行安全）
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs leading-5 text-zinc-700 dark:text-zinc-300">{safety.human_summary}</p>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-4">
            <Metric label="Profile（运行配置）" value={safety.profile || 'unknown'} help="必须是 brc_btc_eth_testnet_runtime 才能进入固定 BRC testnet 演练。" />
            <Metric label="Testnet（测试网）" value={<StatusBadge state={safety.testnet} />} help="true 才表示后端确认当前是测试网；unknown/false 都不能继续 testnet。" />
            <Metric label="GKS（全局安全开关）" value={<StatusBadge state={safety.gks_active ? 'blocked' : 'not blocked'} />} help="blocked 表示全局阻断新动作；not blocked 不等于可以交易，还要看其他门槛。" />
            <Metric label="Startup Guard（启动保护）" value={<StatusBadge state={safety.startup_guard_armed ? 'armed' : 'blocked'} />} help="blocked 是保护状态，表示系统不会自动进入交易动作。" />
          </div>
          <JsonDetails data={safety} />
          <DeveloperDetails data={readiness} label="Readiness 技术详情" />
        </CardContent>
      </Card>
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
