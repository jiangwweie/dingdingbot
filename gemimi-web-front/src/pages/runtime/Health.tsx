import React, { useEffect, useState } from 'react';
import { getRuntimeHealth, getRuntimeAttempts } from '@/src/services/api';
import { RuntimeHealth as IRuntimeHealth, Attempt } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Badge } from '@/src/components/ui/Badge';
import { Loader2, AlertTriangle, ShieldAlert, CheckCircle2, RotateCcw, Ban } from 'lucide-react';
import { format } from 'date-fns';

export default function Health() {
  const { refreshCount } = useRefreshContext();
  const [data, setData] = useState<IRuntimeHealth | null>(null);
  const [rejectedAttempts, setRejectedAttempts] = useState<Attempt[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([getRuntimeHealth(), getRuntimeAttempts()]).then(([resHealth, resAttempts]) => {
      if (active) {
        setData(resHealth);
        setRejectedAttempts(resAttempts.filter(a => a.final_result === 'REJECTED'));
        setLoading(false);
      }
    });
    return () => { active = false; };
  }, [refreshCount]);

  if (loading && !data) return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;
  if (!data) return <div className="text-rose-400">加载健康度上下文失败。</div>;

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold tracking-tight">系统健康度 (System Health)</h2>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Strictly separated: Breaker Summary */}
        <Card className="border-rose-900/40">
          <CardHeader className="bg-rose-950/20"><CardTitle className="flex items-center gap-2"><ShieldAlert className="w-4 h-4 text-rose-500"/> 熔断器摘要 (Breaker Summary)</CardTitle></CardHeader>
          <CardContent className="space-y-4 pt-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-white dark:bg-zinc-950 p-4 rounded border border-zinc-200 dark:border-zinc-800">
                <p className="text-sm text-zinc-500 mb-1">总计熔断次数</p>
                <p className="text-3xl font-mono text-rose-500">{data.breaker_summary.total_tripped}</p>
              </div>
              <div className="bg-white dark:bg-zinc-950 p-4 rounded border border-zinc-200 dark:border-zinc-800">
                <p className="text-sm text-zinc-500 mb-1">当前活跃数</p>
                <p className="text-3xl font-mono text-zinc-800 dark:text-zinc-200">{data.breaker_summary.active_breakers.length}</p>
              </div>
            </div>
            {data.breaker_summary.active_breakers.length > 0 && (
              <div className="text-xs font-mono text-rose-400 bg-rose-950/30 p-2 rounded">
                活跃熔断器: {data.breaker_summary.active_breakers.join(', ')}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Strictly separated: Recovery Summary */}
        <Card className="border-blue-900/40">
          <CardHeader className="bg-blue-950/20"><CardTitle className="flex items-center gap-2"><RotateCcw className="w-4 h-4 text-blue-500"/> 恢复状态 (Recovery Summary)</CardTitle></CardHeader>
          <CardContent className="space-y-4 pt-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-white dark:bg-zinc-950 p-4 rounded border border-zinc-200 dark:border-zinc-800">
                <p className="text-sm text-zinc-500 mb-1">待处理任务</p>
                <p className="text-3xl font-mono text-amber-500">{data.recovery_summary.pending_tasks}</p>
              </div>
              <div className="bg-white dark:bg-zinc-950 p-4 rounded border border-zinc-200 dark:border-zinc-800">
                <p className="text-sm text-zinc-500 mb-1">已完成恢复</p>
                <p className="text-3xl font-mono text-emerald-400">{data.recovery_summary.completed_tasks}</p>
              </div>
            </div>
            <p className="text-xs text-zinc-500 font-mono">
              上次恢复时间: {data.recovery_summary.last_recovery_time ? data.recovery_summary.last_recovery_time : 'N/A'}
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader><CardTitle>启动检查点 (Startup Markers)</CardTitle></CardHeader>
          <CardContent className="p-4 space-y-3">
             {Object.entries(data.startup_markers).map(([marker, status]) => (
                <div key={marker} className="flex justify-between items-center text-sm border-b border-zinc-200 dark:border-zinc-800 pb-2 last:border-0 last:pb-0">
                  <span className="text-zinc-700 dark:text-zinc-300">{marker}</span>
                  {status === 'PASSED' ? <CheckCircle2 className="w-4 h-4 text-emerald-500" /> : <Badge>{status === 'PASSED' ? '通过' : status}</Badge>}
                </div>
             ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2 text-amber-500"><AlertTriangle className="w-4 h-4"/> 近期警告与错误</CardTitle></CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-zinc-800">
              {data.recent_errors.map((err, i) => (
                <div key={i} className="p-3 text-sm text-rose-400 font-mono flex items-start gap-2">
                  <span className="text-rose-500 mt-0.5">错误</span>
                  <span>{err}</span>
                </div>
              ))}
              {data.recent_warnings.map((warn, i) => (
                <div key={i} className="p-3 text-sm text-amber-500/90 font-mono flex items-start gap-2">
                  <span className="text-amber-500 mt-0.5">警告</span>
                  <span>{warn}</span>
                </div>
              ))}
              {data.recent_errors.length === 0 && data.recent_warnings.length === 0 && (
                <div className="p-4 text-sm text-zinc-500 text-center">暂无近期报警。</div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2 text-rose-400"><Ban className="w-4 h-4"/> 近期拦截记录 (Recent Blocked Attempts)</CardTitle></CardHeader>
        <CardContent className="p-0">
          <div className="divide-y divide-zinc-800">
            {rejectedAttempts.map((attempt) => (
              <div key={attempt.id} className="p-3 text-sm flex items-center justify-between">
                <div>
                  <div className="font-mono text-zinc-700 dark:text-zinc-300">{attempt.strategy_name} <span className="text-zinc-500 mx-2">|</span> {attempt.symbol} <span className="text-zinc-500 mx-2">|</span> <Badge variant="outline">{attempt.direction}</Badge></div>
                  <div className="text-rose-400 text-xs mt-1">原因: {attempt.reject_reason || '未知'} ({attempt.filter_results_summary})</div>
                </div>
                <div className="text-xs text-zinc-500 font-mono">
                  {format(new Date(attempt.timestamp), 'HH:mm:ss')}
                </div>
              </div>
            ))}
            {rejectedAttempts.length === 0 && (
              <div className="p-4 text-sm text-zinc-500 text-center">系统运行良好，暂无拦截干预。</div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
