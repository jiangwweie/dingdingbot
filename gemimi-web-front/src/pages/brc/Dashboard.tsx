import { useEffect, useState } from 'react';
import { HelpCircle, ShieldCheck } from 'lucide-react';
import { brcApi, DashboardResponse, RuntimeSafetyResponse } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { ErrorState, GuardNote, JsonDetails, StageStrip, StatusBadge } from './ConsolePrimitives';

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
      <GuardNote />

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />
              Runtime Safety（运行安全）
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-xs leading-5 text-zinc-700 dark:text-zinc-300">
              {safety?.human_summary || 'Runtime 状态暂不可用。'}
            </p>
            <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
              <Metric label="Runtime Bound" value={<StatusBadge state={safety?.runtime_bound} />} />
              <Metric label="Testnet" value={<StatusBadge state={safety?.testnet} />} />
              <Metric label="GKS" value={<StatusBadge state={safety?.gks_active ? 'blocked' : 'not blocked'} />} />
              <Metric label="Startup Guard" value={<StatusBadge state={safety?.startup_guard_armed ? 'armed' : 'blocked'} />} />
            </div>
            <JsonDetails data={safety} label="展开 runtime safety JSON" />
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

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-sm border border-zinc-200 p-2 dark:border-zinc-800">
      <p className="mb-1 text-[10px] font-bold uppercase tracking-widest text-zinc-500">{label}</p>
      {value}
    </div>
  );
}
