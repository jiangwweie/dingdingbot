import React, { useEffect, useState } from 'react';
import { getReviewSummary } from '@/src/services/api';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Badge } from '@/src/components/ui/Badge';
import { Info, CheckCircle2, AlertTriangle, ShieldCheck, Loader2 } from 'lucide-react';
import { useParams, Link } from 'react-router-dom';

export default function ReviewSummary() {
  const { candidate_name } = useParams<{ candidate_name: string }>();
  const { refreshCount } = useRefreshContext();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!candidate_name) return;
    let active = true;
    setLoading(true);
    getReviewSummary(candidate_name).then(res => {
      if (active) {
        setData(res);
        setLoading(false);
      }
    }).catch(err => {
      if (active) {
        console.error("Failed to load review summary", err);
        setLoading(false);
      }
    });
    return () => { active = false; };
  }, [candidate_name, refreshCount]);

  if (loading && !data) return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;
  if (!data) return <div className="text-rose-400">未找到审查报告。</div>;

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex justify-between items-end border-b border-zinc-200 dark:border-zinc-800 mb-6 pb-4">
        <div>
           <h2 className="text-xl font-bold tracking-tight">审查报告 (Review Summary)</h2>
           <p className="text-xs text-zinc-500 mt-2 font-mono">
             Candidate: {data.candidate_name}
           </p>
        </div>
        <Badge variant={data.review_status === 'APPROVED' ? 'success' : 'warning'}>
          {data.review_status}
        </Badge>
      </div>

      <div className="bg-blue-950/20 border border-blue-900/40 p-4 rounded-lg flex gap-3 text-blue-300">
        <Info className="w-5 h-5 shrink-0 mt-0.5" />
        <div className="text-sm">
          <p className="font-semibold mb-1">第三批预留壳子 (Placeholder Shell)</p>
          <p className="text-zinc-600 dark:text-zinc-400">此页面包含策略人工审查需要的 checklist、边界参数检查以及只读的审查记录。当前展示的数据为静态占位结构。</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
           <CardHeader><CardTitle className="flex flex-row items-center gap-2"><ShieldCheck className="w-4 h-4"/> 严格检查表 (Strict v1 Checklist)</CardTitle></CardHeader>
           <CardContent className="space-y-3 text-sm">
             {(data.strict_v1_checklist || []).map((item: any, idx: number) => (
                <div key={idx} className="flex justify-between items-center border-b border-zinc-100 dark:border-zinc-800 pb-2 last:border-0">
                  <span className="text-zinc-700 dark:text-zinc-300">{item.gate} <span className="text-zinc-500 text-xs">({item.threshold})</span></span>
                  <Badge variant={item.passed ? 'success' : 'warning'} className="text-[10px]">
                    {item.passed ? <CheckCircle2 className="w-3 h-3 mr-1" /> : <AlertTriangle className="w-3 h-3 mr-1" />}
                    {item.passed ? 'PASS' : 'WARN'}
                  </Badge>
                </div>
             ))}
           </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
             <CardHeader><CardTitle className="flex flex-row items-center gap-2"><AlertTriangle className="w-4 h-4"/> 警告指标 (Warnings)</CardTitle></CardHeader>
             <CardContent className="space-y-2 text-sm">
               {(data.warnings && data.warnings.length > 0) ? (
                 data.warnings.map((warn: string, i: number) => (
                   <div key={i} className="text-rose-500 dark:text-rose-400 bg-rose-50 dark:bg-rose-950/20 px-3 py-2 rounded text-xs">
                     • {warn}
                   </div>
                 ))
               ) : (
                 <div className="text-zinc-500 text-xs">无明显异常</div>
               )}
             </CardContent>
          </Card>

          <Card>
             <CardHeader><CardTitle>边界参数提醒 (Params at Boundary)</CardTitle></CardHeader>
             <CardContent className="space-y-2 text-sm">
               {(data.params_at_boundary || []).map((p: string, i: number) => (
                 <div key={i} className="flex justify-between items-center text-xs bg-amber-50 dark:bg-amber-950/20 px-3 py-2 rounded">
                   <span className="font-mono text-amber-600 dark:text-amber-400">• {p}</span>
                 </div>
               ))}
               {!(data.params_at_boundary && data.params_at_boundary.length > 0) && (
                 <div className="text-zinc-500 text-xs">无边界参数</div>
               )}
             </CardContent>
          </Card>
        </div>
      </div>

      <Card>
         <CardHeader><CardTitle>审查备注 (Review Notes)</CardTitle></CardHeader>
          <CardContent>
            <div className="bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-md min-h-[100px] p-4 text-sm text-zinc-700 dark:text-zinc-300 whitespace-pre-wrap">
              {data.summary || '无备注信息'}
            </div>
          </CardContent>
      </Card>

    </div>
  );
}
