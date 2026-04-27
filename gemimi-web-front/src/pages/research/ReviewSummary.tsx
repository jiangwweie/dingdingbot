import React, { useEffect, useState } from 'react';
import { getReviewSummary } from '@/src/services/api';
import { ReviewSummary as ReviewSummaryData } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Badge } from '@/src/components/ui/Badge';
import { CheckCircle2, AlertTriangle, Loader2, AlertCircle } from 'lucide-react';
import { useParams } from 'react-router-dom';
import { fmtDash, reviewStatusVariant, reviewStatusLabel } from '@/src/lib/console-utils';

export default function ReviewSummary() {
  const { candidate_name } = useParams<{ candidate_name: string }>();
  const { refreshCount } = useRefreshContext();
  const [data, setData] = useState<ReviewSummaryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!candidate_name) return;
    let active = true;
    setLoading(true);
    setError(false);
    getReviewSummary(candidate_name).then(res => {
      if (active) { setData(res); setLoading(false); }
    }).catch(() => {
      if (active) { setError(true); setLoading(false); }
    });
    return () => { active = false; };
  }, [candidate_name, refreshCount]);

  if (loading && !data) return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;
  if (error && !data) return <div className="flex h-32 items-center justify-center text-rose-400 gap-2"><AlertCircle className="w-5 h-5" /><span>审查报告加载失败</span></div>;
  if (!data) return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold tracking-tight">审查报告</h2>
      <Card><CardContent className="py-10 text-center text-zinc-500">暂无数据</CardContent></Card>
    </div>
  );

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex justify-between items-end border-b border-zinc-200 dark:border-zinc-800 mb-6 pb-4">
        <div>
          <h2 className="text-xl font-bold tracking-tight">审查报告</h2>
          <p className="text-xs text-zinc-500 mt-1 font-mono">{fmtDash(data.candidate_name)}</p>
        </div>
        <Badge variant={reviewStatusVariant(data.review_status)}>
          {reviewStatusLabel(data.review_status)}
        </Badge>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader><CardTitle>Strict v1 Checklist</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            {(data.strict_v1_checklist || []).map((item, idx: number) => (
              <div key={idx} className="flex justify-between items-center border-b border-zinc-100 dark:border-zinc-800 pb-2 last:border-0">
                <span className="text-zinc-700 dark:text-zinc-300">{item.gate} <span className="text-zinc-500 text-xs">({item.threshold})</span></span>
                <Badge variant={item.passed ? 'success' : 'danger'} className="text-[10px]">
                  {item.passed ? <CheckCircle2 className="w-3 h-3 mr-1" /> : <AlertTriangle className="w-3 h-3 mr-1" />}
                  {item.passed ? 'PASS' : 'FAIL'}
                </Badge>
              </div>
            ))}
            {(!data.strict_v1_checklist || data.strict_v1_checklist.length === 0) && (
              <div className="text-zinc-500 text-xs text-center py-2">暂无检查项</div>
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle>Warnings</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              {(data.warnings && data.warnings.length > 0) ? (
                data.warnings.map((warn: string, i: number) => (
                  <div key={i} className="text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/20 px-3 py-2 rounded text-xs">
                    {warn}
                  </div>
                ))
              ) : (
                <div className="text-zinc-500 text-xs">无警告</div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>边界参数</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              {(data.params_at_boundary || []).map((p: string, i: number) => (
                <div key={i} className="flex justify-between items-center text-xs bg-amber-50 dark:bg-amber-950/20 px-3 py-2 rounded">
                  <span className="font-mono text-amber-600 dark:text-amber-400">{p}</span>
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
        <CardHeader><CardTitle>审查备注</CardTitle></CardHeader>
        <CardContent>
          <div className="bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-md min-h-[100px] p-4 text-sm text-zinc-700 dark:text-zinc-300 whitespace-pre-wrap">
            {data.summary || '--'}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}