import { useEffect, useState } from 'react';
import { ShieldAlert } from 'lucide-react';
import { brcApi, RuntimeSafetyResponse } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { ErrorState, JsonDetails, StageStrip, StatusBadge } from './ConsolePrimitives';

export default function RuntimeSafety() {
  const [safety, setSafety] = useState<RuntimeSafetyResponse | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    brcApi.runtimeSafety().then(setSafety).catch(setError);
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
            <Metric label="Profile" value={safety.profile || 'unknown'} />
            <Metric label="Testnet" value={<StatusBadge state={safety.testnet} />} />
            <Metric label="GKS" value={<StatusBadge state={safety.gks_active ? 'blocked' : 'not blocked'} />} />
            <Metric label="Startup Guard" value={<StatusBadge state={safety.startup_guard_armed ? 'armed' : 'blocked'} />} />
          </div>
          <JsonDetails data={safety} />
        </CardContent>
      </Card>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-sm border border-zinc-200 p-3 dark:border-zinc-800">
      <p className="mb-1 text-[10px] font-bold uppercase tracking-widest text-zinc-500">{label}</p>
      <div className="text-xs text-zinc-700 dark:text-zinc-300">{value}</div>
    </div>
  );
}
