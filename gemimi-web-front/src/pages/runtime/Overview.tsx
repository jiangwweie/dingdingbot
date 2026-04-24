import React, { useEffect, useState } from 'react';
import { getRuntimeOverview } from '@/src/services/mockApi';
import { RuntimeOverview as IRuntimeOverview } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Badge } from '@/src/components/ui/Badge';
import { Loader2 } from 'lucide-react';
import { format } from 'date-fns';

export default function Overview() {
  const { refreshCount } = useRefreshContext();
  const [data, setData] = useState<IRuntimeOverview | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    getRuntimeOverview().then(res => {
      if (active) {
        setData(res);
        setLoading(false);
      }
    });
    return () => { active = false; };
  }, [refreshCount]);

  if (loading && !data) return <div className="flex h-32 items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-500" /></div>;
  if (!data) return <div className="text-rose-400">加载概览信息失败。</div>;

  const freshnessMap: Record<string, string> = {
    'Fresh': '正常 (Fresh)',
    'Stale': '延迟 (Stale)',
    'Possibly Dead': '疑似宕机'
  };

  const freshnessVariant = {
    'Fresh': 'success',
    'Stale': 'warning',
    'Possibly Dead': 'danger'
  } as const;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold tracking-tight">系统概览</h2>
        <div className="flex items-center gap-3 bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 px-4 py-2 rounded-lg">
          <span className="text-sm text-zinc-600 dark:text-zinc-400">心跳状态 (Heartbeat):</span>
          <Badge variant={freshnessVariant[data.freshness_status as keyof typeof freshnessVariant] || 'default'}>
            {freshnessMap[data.freshness_status] || data.freshness_status}
          </Badge>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader><CardTitle>配置信息 (Profile)</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between"><span className="text-zinc-500">配置:</span> <span className="font-mono text-zinc-800 dark:text-zinc-200">{data.profile}</span></div>
            <div className="flex justify-between"><span className="text-zinc-500">版本:</span> <span className="font-mono text-zinc-800 dark:text-zinc-200">{data.version}</span></div>
            <div className="flex justify-between"><span className="text-zinc-500">哈希:</span> <span className="font-mono text-zinc-600 dark:text-zinc-400">{data.hash}</span></div>
            <div className="flex justify-between"><span className="text-zinc-500">已冻结 (Frozen):</span> <Badge variant={data.frozen ? 'info' : 'warning'}>{data.frozen ? '是' : '否'}</Badge></div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>市场上下文 (Market Context)</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between"><span className="text-zinc-500">交易对 (Symbol):</span> <span className="font-mono font-medium text-blue-400">{data.symbol}</span></div>
            <div className="flex justify-between"><span className="text-zinc-500">时间周期 (Timeframe):</span> <span className="font-mono">{data.timeframe}</span></div>
            <div className="flex justify-between"><span className="text-zinc-500">模式:</span> <Badge variant="default">{data.mode}</Badge></div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>子系统状态 (Subsystems)</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between"><span className="text-zinc-500">交易所 API:</span> <Badge variant={data.exchange_health === 'OK' ? 'success' : 'danger'}>{data.exchange_health === 'OK' ? '正常' : data.exchange_health}</Badge></div>
            <div className="flex justify-between"><span className="text-zinc-500">数据库 (PG):</span> <Badge variant={data.pg_health === 'OK' ? 'success' : 'danger'}>{data.pg_health === 'OK' ? '正常' : data.pg_health}</Badge></div>
            <div className="flex justify-between"><span className="text-zinc-500">Webhooks:</span> <Badge variant={data.webhook_health === 'OK' ? 'success' : 'danger'}>{data.webhook_health === 'OK' ? '正常' : data.webhook_health}</Badge></div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>时间同步 (Time Sync)</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between flex-col mb-2">
              <span className="text-zinc-500">服务器时间:</span> 
              <span className="font-mono text-zinc-700 dark:text-zinc-300">{format(new Date(data.server_time), 'yyyy-MM-dd HH:mm:ss')}</span>
            </div>
            <div className="flex justify-between flex-col mb-2">
              <span className="text-zinc-500">系统最后更新:</span> 
              <span className="font-mono text-zinc-600 dark:text-zinc-400">{format(new Date(data.last_runtime_update_at), 'HH:mm:ss.SSS')}</span>
            </div>
            <div className="flex justify-between flex-col">
              <span className="text-zinc-500">上次心跳时间:</span> 
              <span className="font-mono text-emerald-400">{format(new Date(data.last_heartbeat_at), 'HH:mm:ss.SSS')}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="bg-zinc-50 dark:bg-zinc-900/50">
          <CardHeader><CardTitle>后端及执行情况 (Backend & Execution)</CardTitle></CardHeader>
          <CardContent className="text-sm">
            <div className="mb-4">
              <p className="text-zinc-600 dark:text-zinc-400 mb-1">运行状态摘要</p>
              <p className="font-mono text-blue-300">{data.backend_summary}</p>
            </div>
            <div className="flex gap-4">
              <div className="bg-white dark:bg-zinc-950 p-3 rounded border border-zinc-200 dark:border-zinc-800 flex-1">
                <p className="text-zinc-500 text-xs mb-1">熔断次数 (Breaker Trips)</p>
                <p className="text-2xl font-bold font-mono text-amber-500">{data.breaker_count}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        
        <Card className="bg-zinc-50 dark:bg-zinc-900/50">
          <CardHeader><CardTitle>对账系统 (Reconciliation)</CardTitle></CardHeader>
          <CardContent className="text-sm h-full flex flex-col justify-center">
             <div className="bg-emerald-950/30 border border-emerald-900/50 p-4 rounded text-emerald-400 font-mono text-sm break-all">
                {data.reconciliation_summary}
             </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
