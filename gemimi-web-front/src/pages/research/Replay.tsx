import React, { useEffect, useState } from 'react';
import { getReplayContext } from '@/src/services/mockApi';
import { ReplayContext as IReplayContext } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Loader2, Terminal, Info } from 'lucide-react';
import { useParams, Link } from 'react-router-dom';

export default function Replay() {
  const { candidate_name } = useParams<{ candidate_name: string }>();
  const { refreshCount } = useRefreshContext();
  const [data, setData] = useState<IReplayContext | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!candidate_name) return;
    let active = true;
    setLoading(true);
    getReplayContext(candidate_name).then(res => {
      if (active) {
        setData(res);
        setLoading(false);
      }
    });
    return () => { active = false; };
  }, [candidate_name, refreshCount]);

  if (loading) return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;
  if (!data) return <div className="text-rose-400">未找到回测上下文。</div>;

  return (
    <div className="space-y-6 max-w-5xl">
       <div className="mb-8">
          <h2 className="text-xl font-bold tracking-tight">回测上下文 (Replay Context)</h2>
          <p className="text-xs text-zinc-400 mt-2 font-mono">{data.candidate_name}</p>
       </div>

       <div className="bg-blue-950/20 border border-blue-900/40 p-4 rounded-lg flex gap-3 text-blue-300">
         <Info className="w-5 h-5 shrink-0 mt-0.5" />
         <div className="text-sm">
           <p className="font-semibold mb-1">仅限回测上下文与指令 (Replay Context Only)</p>
           <p className="text-zinc-400">此页面提供了重现候选策略本地实验所需的控制面板参数与终端指令。K 线级别的可视化回放操作在本版本的控制台中由于作用域范围（Out of Scope）被暂时禁用。</p>
         </div>
       </div>

       <Card>
          <CardHeader><CardTitle className="flex flex-row items-center gap-2"><Terminal className="w-4 h-4"/> 策略重现指令 (Reproduce Command)</CardTitle></CardHeader>
          <CardContent className="bg-zinc-950 rounded m-4 border border-zinc-800 p-4">
             <code className="text-emerald-400 font-mono text-sm break-all select-all">
                {data.reproduce_cmd}
             </code>
          </CardContent>
       </Card>

       <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card>
             <CardHeader><CardTitle>解析后得出的参数集定义</CardTitle></CardHeader>
             <CardContent className="bg-zinc-950 p-4 text-xs font-mono text-zinc-300 rounded m-4 border border-zinc-800 overflow-auto">
               <pre>{JSON.stringify(data.resolved_request, null, 2)}</pre>
             </CardContent>
          </Card>

          <Card>
             <CardHeader><CardTitle>运行时参数覆写集 (Runtime Overrides)</CardTitle></CardHeader>
             <CardContent className="bg-zinc-950 p-4 text-xs font-mono text-amber-300 rounded m-4 border border-zinc-800 overflow-auto">
               <pre>{JSON.stringify(data.runtime_overrides, null, 2)}</pre>
             </CardContent>
          </Card>
       </div>
    </div>
  );
}
