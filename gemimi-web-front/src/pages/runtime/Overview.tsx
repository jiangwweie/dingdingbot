import React, { useEffect, useState } from 'react';
import { getRuntimeOverview } from '@/src/services/api';
import { RuntimeOverview as IRuntimeOverview } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Badge } from '@/src/components/ui/Badge';
import { Loader2, AlertCircle } from 'lucide-react';
import { fmtDash, fmtDateTimeFull, fmtTime, runtimeHealthVariant, runtimeHealthLabel, freshnessVariant, freshnessLabel } from '@/src/lib/console-utils';

export default function Overview() {
  const { refreshCount } = useRefreshContext();
  const [data, setData] = useState<IRuntimeOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);
    getRuntimeOverview().then(res => {
      if (active) {
        setData(res);
        setLoading(false);
      }
    }).catch(() => {
      if (active) {
        setError(true);
        setLoading(false);
      }
    });
    return () => { active = false; };
  }, [refreshCount]);

  if (loading && !data) return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;
  if (error && !data) return <div className="flex h-32 items-center justify-center text-rose-400 gap-2"><AlertCircle className="w-5 h-5" /><span>概览数据加载失败</span></div>;

  if (!data) return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold tracking-tight">系统概览</h2>
      <Card><CardContent className="py-10 text-center text-zinc-500">暂无概览数据</CardContent></Card>
    </div>
  );

  return (
    <div className="space-y-6">
      {error && data && (
        <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 text-amber-700 dark:text-amber-400 px-4 py-2 rounded text-sm">
          部分数据刷新失败，显示缓存内容
        </div>
      )}

      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold tracking-tight">系统概览</h2>
        <div className="flex items-center gap-3 bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 px-4 py-2 rounded-lg">
          <span className="text-sm text-zinc-600 dark:text-zinc-400">心跳:</span>
          <Badge variant={freshnessVariant(data.freshness_status)}>
            {freshnessLabel(data.freshness_status)}
          </Badge>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader><CardTitle>Runtime Profile</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between"><span className="text-zinc-500">Profile:</span> <span className="font-mono text-zinc-800 dark:text-zinc-200">{fmtDash(data.profile)}</span></div>
            <div className="flex justify-between"><span className="text-zinc-500">版本:</span> <span className="font-mono text-zinc-800 dark:text-zinc-200">{fmtDash(data.version)}</span></div>
            <div className="flex justify-between"><span className="text-zinc-500">哈希:</span> <span className="font-mono text-zinc-600 dark:text-zinc-400">{fmtDash(data.hash)}</span></div>
            <div className="flex justify-between"><span className="text-zinc-500">冻结:</span> <Badge variant={data.frozen ? 'info' : 'success'}>{data.frozen ? '是' : '否'}</Badge></div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>市场上下文</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between"><span className="text-zinc-500">交易对:</span> <span className="font-mono font-medium text-blue-400">{fmtDash(data.symbol)}</span></div>
            <div className="flex justify-between"><span className="text-zinc-500">周期:</span> <span className="font-mono">{fmtDash(data.timeframe)}</span></div>
            <div className="flex justify-between"><span className="text-zinc-500">模式:</span> <Badge variant="default">{fmtDash(data.mode)}</Badge></div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>子系统状态</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between"><span className="text-zinc-500">交易所 API:</span> <Badge variant={runtimeHealthVariant(data.exchange_health)}>{runtimeHealthLabel(data.exchange_health)}</Badge></div>
            <div className="flex justify-between"><span className="text-zinc-500">数据库 (PG):</span> <Badge variant={runtimeHealthVariant(data.pg_health)}>{runtimeHealthLabel(data.pg_health)}</Badge></div>
            <div className="flex justify-between"><span className="text-zinc-500">Webhooks:</span> <Badge variant={runtimeHealthVariant(data.webhook_health)}>{runtimeHealthLabel(data.webhook_health)}</Badge></div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>时间同步</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between"><span className="text-zinc-500">服务器时间:</span> <span className="font-mono text-zinc-700 dark:text-zinc-300">{fmtDateTimeFull(data.server_time)}</span></div>
            <div className="flex justify-between"><span className="text-zinc-500">最后更新:</span> <span className="font-mono text-zinc-600 dark:text-zinc-400">{fmtTime(data.last_runtime_update_at)}</span></div>
            <div className="flex justify-between"><span className="text-zinc-500">上次心跳:</span> <span className="font-mono text-emerald-400">{fmtTime(data.last_heartbeat_at)}</span></div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="bg-zinc-50 dark:bg-zinc-900/50">
          <CardHeader><CardTitle>后端及执行情况</CardTitle></CardHeader>
          <CardContent className="text-sm">
            <div className="mb-4">
              <p className="text-zinc-600 dark:text-zinc-400 mb-1">运行状态摘要</p>
              <p className="font-mono text-blue-700 dark:text-blue-300">{fmtDash(data.backend_summary)}</p>
            </div>
            <div className="flex gap-4">
              <div className="bg-white dark:bg-zinc-950 p-3 rounded border border-zinc-200 dark:border-zinc-800 flex-1">
                <p className="text-zinc-500 text-xs mb-1">熔断次数</p>
                <p className="text-2xl font-bold font-mono text-amber-600 dark:text-amber-500">{data.breaker_count ?? '--'}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-zinc-50 dark:bg-zinc-900/50">
          <CardHeader><CardTitle>对账系统</CardTitle></CardHeader>
          <CardContent className="text-sm h-full flex flex-col justify-center">
             <div className="bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900/50 p-4 rounded text-emerald-700 dark:text-emerald-400 font-mono text-sm break-all">
                {fmtDash(data.reconciliation_summary)}
             </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}