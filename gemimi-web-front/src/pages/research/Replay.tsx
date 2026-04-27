import React, { useEffect, useState } from 'react';
import { getReplayContext } from '@/src/services/api';
import { ReplayContext as IReplayContext } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Loader2, AlertCircle, Terminal } from 'lucide-react';
import { useParams } from 'react-router-dom';
import { fmtDash } from '@/src/lib/console-utils';

export default function Replay() {
  const { candidate_name } = useParams<{ candidate_name: string }>();
  const { refreshCount } = useRefreshContext();
  const [data, setData] = useState<IReplayContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!candidate_name) return;
    let active = true;
    setLoading(true);
    setError(false);
    getReplayContext(candidate_name).then(res => {
      if (active) { setData(res); setLoading(false); }
    }).catch(() => {
      if (active) { setError(true); setLoading(false); }
    });
    return () => { active = false; };
  }, [candidate_name, refreshCount]);

  if (loading) return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;
  if (error && !data) return <div className="flex h-32 items-center justify-center text-rose-400 gap-2"><AlertCircle className="w-5 h-5" /><span>回测上下文加载失败</span></div>;
  if (!data) return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold tracking-tight">回测上下文</h2>
      <Card><CardContent className="py-10 text-center text-zinc-500">暂无数据</CardContent></Card>
    </div>
  );

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="mb-4">
        <h2 className="text-xl font-bold tracking-tight">回测上下文</h2>
        <p className="text-xs text-zinc-500 mt-1 font-mono">{data.candidate_name}</p>
      </div>

      <Card>
        <CardHeader><CardTitle className="flex flex-row items-center gap-2"><Terminal className="w-4 h-4"/> 重现指令</CardTitle></CardHeader>
        <CardContent className="bg-white dark:bg-zinc-950 rounded m-4 border border-zinc-200 dark:border-zinc-800 p-4">
          <code className="text-emerald-400 font-mono text-sm break-all select-all">
            {fmtDash(data.reproduce_cmd)}
          </code>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card className="col-span-1 md:col-span-2">
          <CardHeader><CardTitle>元数据</CardTitle></CardHeader>
          <CardContent className="bg-white dark:bg-zinc-950 p-4 text-xs font-mono text-blue-300 rounded m-4 border border-zinc-200 dark:border-zinc-800 overflow-auto">
            <pre>{Object.keys(data.metadata || {}).length > 0 ? JSON.stringify(data.metadata, null, 2) : '--'}</pre>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Resolved Request</CardTitle></CardHeader>
          <CardContent className="bg-white dark:bg-zinc-950 p-4 text-xs font-mono text-zinc-700 dark:text-zinc-300 rounded m-4 border border-zinc-200 dark:border-zinc-800 overflow-auto">
            <pre>{Object.keys(data.resolved_request || {}).length > 0 ? JSON.stringify(data.resolved_request, null, 2) : '--'}</pre>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Runtime Overrides</CardTitle></CardHeader>
          <CardContent className="bg-white dark:bg-zinc-950 p-4 text-xs font-mono text-amber-300 rounded m-4 border border-zinc-200 dark:border-zinc-800 overflow-auto">
            <pre>{Object.keys(data.runtime_overrides || {}).length > 0 ? JSON.stringify(data.runtime_overrides, null, 2) : '--'}</pre>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}