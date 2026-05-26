import { useEffect, useState } from 'react';
import { HelpCircle, ShieldCheck } from 'lucide-react';
import { brcApi, DashboardResponse, RuntimeSafetyResponse } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { ErrorState, GuardNote, JsonDetails, OwnerSummary, StageStrip, StatusBadge } from './ConsolePrimitives';

export default function Dashboard() {
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [safety, setSafety] = useState<RuntimeSafetyResponse | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    Promise.all([brcApi.dashboard(), brcApi.runtimeSafety()])
      .then(([dashboardPayload, safetyPayload]) => {
        setDashboard(dashboardPayload);
        setSafety(safetyPayload);
      })
      .catch(setError);
  }, []);

  if (error) return <ErrorState error={error} />;
  if (!dashboard) return <div className="text-xs text-zinc-500">加载 BRC 控制台状态...</div>;

  return (
    <div className="space-y-4">
      <StageStrip
        current={dashboard.current_stage}
        next={dashboard.next_recommended_step}
        global={dashboard.global_planning_stage}
      />
      <OwnerSummary
        conclusion={safety?.runtime_bound ? '可以做治理操作；testnet 取决于运行安全检查' : '只能查看和生成只读计划，不能执行 testnet'}
        why={safety?.runtime_bound
          ? 'Runtime 已连接，但仍需要 profile、testnet、GKS 和 Startup Guard 同时满足要求。'
          : 'Runtime 未绑定，系统无法确认 testnet/profile/仓位状态，因此不会进入任何交易相关流程。'}
        canDo="查看说明、生成只读操作计划、查看 ledger/review/evidence。"
        cannotDo="不能执行 testnet 演练，不能真实下单、提现、转账或启用自动策略。"
        accountImpact="不会影响真实账户。当前页面只展示治理状态和只读操作入口。"
        next="先查看 Runtime Control，再进入 Operator 生成只读操作计划。"
        tone={safety?.runtime_bound ? 'warning' : 'info'}
      />
      <GuardNote />

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />
              Runtime Control（运行控制）
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-xs leading-5 text-zinc-700 dark:text-zinc-300">
              {safety?.human_summary || 'Runtime 状态暂不可用。'}
            </p>
            <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
              <Metric label="Runtime（运行时连接）" value={<StatusBadge state={safety?.runtime_bound} />} help="false 表示没有连接运行时，因此不会触发交易流程。" />
              <Metric label="Testnet（测试网）" value={<StatusBadge state={safety?.testnet} />} help="unknown 表示当前无法确认是否处于测试网环境。" />
              <Metric label="GKS（全局安全开关）" value={<StatusBadge state={safety?.gks_active ? 'blocked' : 'not blocked'} />} help="GKS active 才是强制阻断；not blocked 仍需结合 runtime 判断。" />
              <Metric label="Startup Guard（启动保护）" value={<StatusBadge state={safety?.startup_guard_armed ? 'armed' : 'blocked'} />} help="blocked 表示启动保护正在阻止运行时自动进入交易状态。" />
            </div>
            <JsonDetails data={safety} label="展开运行状态 JSON" />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <HelpCircle className="h-3.5 w-3.5 text-blue-500" />
              Owner 关心的问题
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
              {dashboard.owner_questions.map((question) => (
                <li key={question}>• {question}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>术语解释</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {Object.entries(dashboard.terminology).map(([term, explanation]) => (
              <div key={term} className="rounded-sm border border-zinc-200 p-3 dark:border-zinc-800">
                <p className="text-xs font-bold text-zinc-800 dark:text-zinc-200">{term}</p>
                <p className="mt-1 text-xs leading-5 text-zinc-500">{explanation}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function Metric({ label, value, help }: { label: string; value: React.ReactNode; help: string }) {
  return (
    <div className="rounded-sm border border-zinc-200 p-2 dark:border-zinc-800">
      <p className="mb-1 text-[10px] font-bold uppercase tracking-widest text-zinc-500">{label}</p>
      {value}
      <p className="mt-2 text-[11px] leading-4 text-zinc-500">{help}</p>
    </div>
  );
}
