import React, { useEffect, useState } from 'react';
import { getCandidateDetail } from '@/src/services/mockApi';
import { CandidateDetail as ICandidateDetail } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Loader2, ArrowLeft, PlayIcon } from 'lucide-react';
import { useParams, Link } from 'react-router-dom';

export default function CandidateDetail() {
  const { candidate_name } = useParams<{ candidate_name: string }>();
  const { refreshCount } = useRefreshContext();
  const [data, setData] = useState<ICandidateDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!candidate_name) return;
    let active = true;
    setLoading(true);
    getCandidateDetail(candidate_name).then(res => {
      if (active) {
        setData(res);
        setLoading(false);
      }
    });
    return () => { active = false; };
  }, [candidate_name, refreshCount]);

  if (loading) return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;
  if (!data) return <div className="text-rose-400">未找到候选策略。</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link to="/research/candidates" className="text-zinc-500 hover:text-zinc-300 transition-colors p-2 -ml-2 rounded-lg hover:bg-zinc-800">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <div>
           <h2 className="text-xl font-bold tracking-tight text-blue-400 font-mono">{data.candidate_name}</h2>
           <p className="text-zinc-500 text-xs">通过解析 JSON 实验产物获取的只读详情</p>
        </div>
        <div className="ml-auto">
           <Link to={`/research/replay/${data.candidate_name}`} className="flex items-center gap-1.5 text-sm font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-200 px-3 py-1.5 rounded transition">
             <PlayIcon className="w-4 h-4 text-emerald-400" />
             回测上下文 (Replay Context)
           </Link>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="col-span-1 lg:col-span-2">
          <CardHeader><CardTitle>严格评审基准检测结果 (Strict Rubric Evaluation)</CardTitle></CardHeader>
          <CardContent>
             <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {Object.entries(data.rubric_evaluation).map(([key, val]) => (
                  <div key={key} className="bg-zinc-950 border border-zinc-800 p-3 rounded-lg">
                    <div className="text-[10px] uppercase text-zinc-500 font-bold mb-1">{key.replace('_', ' ')}</div>
                    <div className="text-lg font-mono text-zinc-200">{val.toString()}</div>
                  </div>
                ))}
             </div>
          </CardContent>
        </Card>

        <Card className="col-span-1">
           <CardHeader><CardTitle>运行参数覆写 (Runtime Overrides)</CardTitle></CardHeader>
           <CardContent className="bg-zinc-950 p-4 font-mono text-xs text-blue-300 m-4 rounded overflow-auto">
             <pre>
               {JSON.stringify(data.runtime_overrides, null, 2)}
             </pre>
           </CardContent>
        </Card>

        <Card className="col-span-1 lg:col-span-2">
          <CardHeader><CardTitle>表现最佳的试验记录参考 (Top Trials Reference)</CardTitle></CardHeader>
          <CardContent className="p-0">
             <table className="w-full text-sm text-left">
               <thead className="bg-zinc-900 border-b border-zinc-800 text-zinc-500 font-medium">
                 <tr>
                   <th className="px-4 py-2">试验编号 (Trial #)</th>
                   <th className="px-4 py-2">对应度量值 (Value)</th>
                 </tr>
               </thead>
               <tbody>
                  {data.top_trials.map((trial, i) => (
                    <tr key={i} className="border-b border-zinc-800/50 last:border-0 hover:bg-zinc-800/20">
                      <td className="px-4 py-2 font-mono text-zinc-400">{trial.number}</td>
                      <td className="px-4 py-2 font-mono text-emerald-400">{trial.value}</td>
                    </tr>
                  ))}
               </tbody>
             </table>
          </CardContent>
        </Card>

        <Card className="col-span-1">
           <CardHeader><CardTitle>被解析的系统请求约束</CardTitle></CardHeader>
           <CardContent className="text-xs text-zinc-400 space-y-2">
              <p>请求说明: {data.resolved_request}</p>
              <div className="mt-4 pt-4 border-t border-zinc-800">
                <p className="font-semibold text-zinc-300 mb-2">硬约束条件 (Hard Constraints)</p>
                <ul className="list-disc pl-4 space-y-1">
                  {Object.entries(data.constraints).map(([k,v]) => (
                    <li key={k}>{k}: <span className="font-mono text-amber-500">{v}</span></li>
                  ))}
                </ul>
              </div>
           </CardContent>
        </Card>
      </div>
    </div>
  );
}
